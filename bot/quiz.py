"""성구 퀴즈 순수 로직 (DB·텔레그램과 무관)."""
from __future__ import annotations

import datetime as dt
import random
import re
from dataclasses import dataclass

DEFAULT_QUIZ_HOURS = "13-22"
MIN_VERSES = 4
CATCH_UP_MINUTES = 10   # 정각 출제를 놓쳤을 때 몇 분 안까지 따라잡아 출제할지
KINDS = ("ref2core", "core2ref")


# ---------------------------------------------------------------------------
# 성구 파일 해석:  주소 / 핵심 내용 / 전체 본문(선택)
# ---------------------------------------------------------------------------
def normalize_ref(ref: str) -> str:
    """'요3 : 16' -> '요 3:16',  '고전13:4' -> '고전 13:4'"""
    ref = re.sub(r"\s+", " ", ref.strip())
    ref = re.sub(r"\s*([:\-~])\s*", r"\1", ref)
    ref = re.sub(r"([가-힣A-Za-z])\s*(\d)", r"\1 \2", ref)
    return ref


@dataclass
class ParsedVerses:
    rows: list[dict]
    errors: list[str]


def parse_verse_text(text: str) -> ParsedVerses:
    rows: dict[str, dict] = {}
    errors = []
    for no, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip().lstrip("﻿")
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("/", 2)]
        if len(parts) < 2 or not parts[0] or not parts[1]:
            errors.append(f"{no}번째 줄: '주소 / 핵심 내용' 형식이 아니에요")
            continue
        ref = normalize_ref(parts[0])
        if not re.search(r"\d", ref):
            errors.append(f"{no}번째 줄: 주소에 장·절 숫자가 없어요 ({parts[0]})")
            continue
        body = parts[2] if len(parts) > 2 and parts[2] else None
        rows[ref] = {"ref": ref, "core": parts[1], "body": body}   # 같은 주소는 마지막 줄 기준
    return ParsedVerses(list(rows.values()), errors)


def decode_upload(data: bytes) -> str:
    """메모장 등에서 저장한 파일: UTF-8 우선, 안 되면 옛 한글 윈도우 인코딩(cp949)."""
    for enc in ("utf-8-sig", "cp949"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# 출제 시간대
# ---------------------------------------------------------------------------
def parse_hours(text: str) -> tuple[int, int] | None:
    m = re.fullmatch(r"\s*(\d{1,2})\s*(?:시)?\s*[-~]\s*(\d{1,2})\s*(?:시)?\s*", text or "")
    if not m:
        return None
    start, end = int(m.group(1)), int(m.group(2))
    if not (0 <= start <= end <= 23):
        return None
    return start, end


def hours_of(space: dict) -> tuple[int, int] | None:
    """공간의 출제 시간대. 꺼져 있으면 None."""
    value = space.get("quiz_hours", DEFAULT_QUIZ_HOURS)
    return parse_hours(value) if value else None


# ---------------------------------------------------------------------------
# 출제
# ---------------------------------------------------------------------------
def pick_verse(verses: list[dict], misses: dict[int, int], used_today: set[int],
               rng: random.Random) -> dict:
    """틀린 횟수가 많을수록 자주, 오늘 이미 낸 구절은 가능하면 피한다."""
    pool = [v for v in verses if v["id"] not in used_today] or verses
    weights = [1 + 2 * misses.get(v["id"], 0) for v in pool]
    return rng.choices(pool, weights=weights, k=1)[0]


def label_of(verse: dict, kind: str) -> str:
    return verse["core"] if kind == "ref2core" else verse["ref"]


def make_question(verse: dict, verses: list[dict], rng: random.Random,
                  kind: str | None = None) -> dict:
    kind = kind or rng.choice(KINDS)
    correct = label_of(verse, kind)
    others = list({label_of(v, kind) for v in verses if v["id"] != verse["id"]} - {correct})
    options = rng.sample(others, k=min(3, len(others))) + [correct]
    rng.shuffle(options)
    return {"verse_id": verse["id"], "kind": kind, "ref": verse["ref"],
            "prompt": verse["ref"] if kind == "ref2core" else (verse.get("body") or verse["core"]),
            "options": options, "correct_idx": options.index(correct)}


# ---------------------------------------------------------------------------
# 오늘의 루틴 상태와 연속 기록
# ---------------------------------------------------------------------------
@dataclass
class QuizStatus:
    answered: int
    target: int
    done: bool
    streak: int


def is_done(answered: int, issued: int, target: int, hour: int, end: int | None) -> bool:
    """오늘 나올 문제를 모두 풀었는가. 출제를 놓친 시간이 있으면 마지막 시간이 지난 뒤
    '나온 문제를 다 풀었는지'로 판단한다."""
    if target and answered >= target:
        return True
    return end is not None and hour > end and issued > 0 and answered == issued


def quiz_streak(days: dict[dt.date, tuple[int, int]], today: dt.date, today_done: bool,
                since: dt.date) -> int:
    """days: 날짜 -> (나온 문제 수, 푼 문제 수). 문제가 없던 날은 건너뛴다."""
    count = 1 if today_done else 0
    d = today - dt.timedelta(days=1)
    while d >= since:
        issued, answered = days.get(d, (0, 0))
        if issued:
            if answered < issued:
                break
            count += 1
        d -= dt.timedelta(days=1)
    return count


def build_status(space: dict, verse_count: int, today_qs: list[dict],
                 history: dict[dt.date, tuple[int, int]], now: dt.datetime,
                 since: dt.date) -> QuizStatus | None:
    """퀴즈를 오늘의 루틴으로 보여 줄지와 그 상태. 보여 줄 필요가 없으면 None."""
    hours = hours_of(space)
    active = hours is not None and verse_count >= MIN_VERSES
    if not active and not today_qs:
        return None
    issued = len(today_qs)
    answered = sum(q.get("answer_idx") is not None for q in today_qs)
    target = (hours[1] - hours[0] + 1) if active else issued
    done = is_done(answered, issued, target, now.hour, hours[1] if hours else -1)
    return QuizStatus(answered, target, done,
                      quiz_streak(history, now.date(), done, since))
