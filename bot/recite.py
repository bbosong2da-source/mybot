"""계시록(전문) 암송 코스 순수 로직 (DB·텔레그램과 무관).

하루 흐름: 그날 할 카드 목록(queue)을 만들고 → 시간대에 나눠 보내고 → 채점 결과로
다음 복습일을 정한다(간격 복습).

queue 항목: {"v": 구절 id, "seq": 순서, "k": "new"|"recall"|"chain", "g": 점수 또는 None, "s": 보낸 시각(시) 또는 None}
점수(grade): 2 완벽 / 1 조금 틀림 / 0 못 외움
"""
from __future__ import annotations

import datetime as dt
import difflib
import math
import random
import re
from dataclasses import dataclass
from html import escape

COURSE = "계시록"
DEFAULT_BOOK = "계"
DEFAULT_HOURS = "18-22"
DAILY_CHOICES = (1, 2, 3)
INTERVALS = (1, 3, 7, 15, 30, 60)   # 상자(box) 단계별 다음 복습까지 날짜
MAX_REVIEWS = 15                    # 하루 복습 최대 개수 (밀린 복습 폭탄 방지)
CHAIN_RATE = 0.4                    # 복습 중 '이어 말하기' 비율
MASTER_BOX = 3                      # 이 단계(15일 간격) 이상이면 '단단히 외움'
KNOWN_BOX = 2                       # 바로 시험·장별 시험에서 처음부터 완벽 → '이미 아는 구절'(7일 뒤 복습)
BOOKMARK_MAX_DAYS = 3               # 북마크한 구절은 복습 간격을 최대 3일로
AUTO_BOOKMARK_FAILS = 2             # '못 외움'이 이만큼 쌓이면 자동 북마크
AUTO_UNBOOKMARK_STREAK = 3          # 북마크한 구절을 연속 이만큼 '완벽'이면 자동 해제
PASS_RATE = 0.9                     # 장별 시험 통과 기준 (완벽 비율)
GRADE_LABELS = {2: "완벽", 1: "조금 틀림", 0: "못 외움"}


# ---------------------------------------------------------------------------
# 본문 파일 해석:  "계 1:1 / 본문"  ("/"는 없어도 되고, 책 이름을 빼면 '계')
# ---------------------------------------------------------------------------
_LINE_RE = re.compile(r"^(?:([가-힣A-Za-z]+)\s*)?(\d{1,3})\s*:\s*(\d{1,3})\s*/?\s*(.+)$")


@dataclass
class ParsedCourse:
    rows: list[dict]
    errors: list[str]


def parse_recite_text(text: str) -> ParsedCourse:
    rows: dict[tuple[int, int], dict] = {}
    errors = []
    for no, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip().lstrip("﻿")
        if not line or line.startswith("#"):
            continue
        m = _LINE_RE.match(line)
        body = m.group(4).strip().lstrip("/").strip() if m else ""
        if not body:
            errors.append(f"{no}번째 줄: '계 1:1 / 본문' 형식이 아니에요")
            continue
        book = m.group(1) or DEFAULT_BOOK
        ch, vs = int(m.group(2)), int(m.group(3))
        rows[(ch, vs)] = {"course": COURSE, "ref": f"{book} {ch}:{vs}", "chapter": ch,
                          "verse": vs, "body": body}
    ordered = [rows[k] for k in sorted(rows)]
    for seq, row in enumerate(ordered, start=1):
        row["seq"] = seq
    return ParsedCourse(ordered, errors)


# ---------------------------------------------------------------------------
# 점점 가리기: 빈칸, 초성
# ---------------------------------------------------------------------------
_CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"


def choseong(text: str) -> str:
    out = []
    for ch in text:
        code = ord(ch) - 0xAC00
        out.append(_CHO[code // 588] if 0 <= code < 11172 else ch)
    return "".join(out)


def blanks(text: str, seed: int, every: int = 3, hide: int = 1) -> str:
    """단어 every개마다 hide개를 ___ 로 가린다 (구절마다 늘 같은 자리).
    2단계는 hide=1(세 개 중 하나), 3단계는 hide=2(세 개 중 둘). 3단계는 2단계에서 가린 자리를
    그대로 가리고 하나를 더 가리므로 단계가 자연스럽게 어려워진다.
    빈칸 길이는 단어 길이를 따라가서(2~4칸) 글자 수 힌트가 된다."""
    words = text.split()
    offset = random.Random(seed).randrange(every)
    return " ".join("＿" * max(2, min(len(w), 4)) if (i - offset) % every < hide else w
                    for i, w in enumerate(words))


# ---------------------------------------------------------------------------
# 하루 카드 목록과 간격 복습
# ---------------------------------------------------------------------------
def build_queue(day: dt.date, daily_new: int, verses: list[dict], cards: list[dict],
                rng: random.Random, bookmarked: set[int] | frozenset = frozenset()) -> list[dict]:
    """새 구절: 아직 안 외운 절 중 가장 앞 절부터 (장별 시험으로 외운 절은 건너뜀).
    복습: 복습일이 된 절, 북마크한 절을 먼저 (하루 최대 MAX_REVIEWS개)."""
    learned = {c["verse_id"] for c in cards}
    queue = [{"v": v["id"], "seq": v["seq"], "k": "new", "g": None, "s": None}
             for v in sorted(verses, key=lambda v: v["seq"]) if v["id"] not in learned][:daily_new]
    seq_of = {v["id"]: v["seq"] for v in verses}
    due = [c for c in cards if c["due_date"] <= day and c["verse_id"] in seq_of]
    due.sort(key=lambda c: (c["verse_id"] not in bookmarked, c["due_date"], c["box"],
                            seq_of[c["verse_id"]]))
    for c in due[:MAX_REVIEWS]:
        seq = seq_of[c["verse_id"]]
        kind = "chain" if seq > 1 and rng.random() < CHAIN_RATE else "recall"
        queue.append({"v": c["verse_id"], "seq": seq, "k": kind, "g": None, "s": None})
    return queue


def apply_grade(card: dict | None, grade: int, day: dt.date, known: bool = False,
                bookmarked: bool = False) -> dict:
    """채점 결과로 새 상자 단계와 다음 복습일.
    known: 처음 보는 구절을 4단계 없이 바로 시험 봐서 완벽 → 이미 아는 구절로 보고 7일 뒤 복습.
    bookmarked: 북마크한 구절은 복습 간격을 최대 3일로."""
    box = -1 if card is None else card["box"]
    if card is None and known and grade == 2:
        box = KNOWN_BOX
    elif grade == 2:
        box = min(box + 1, len(INTERVALS) - 1)
    elif grade == 1:
        box = max(box, 0)
    else:
        box = 0
    days = min(INTERVALS[box], BOOKMARK_MAX_DAYS) if bookmarked else INTERVALS[box]
    return {"box": box, "due_date": day + dt.timedelta(days=days), "last_grade": grade}


def exam_card_update(card: dict | None, grade: int, day: dt.date, bookmarked: bool = False) -> dict | None:
    """장별 시험 결과를 진도에 반영. None이면 카드를 만들지 않음
    (아직 안 외운 절을 '못 외움' → 나중에 새 구절 4단계로 차근차근 배우도록)."""
    if card is None:
        if grade == 0:
            return None
        return apply_grade(None, grade, day, known=True, bookmarked=bookmarked)
    return apply_grade(card, grade, day, bookmarked=bookmarked)


# ---------------------------------------------------------------------------
# 북마크: 직접 ⭐ + '못 외움' 2번이면 자동 ⭐, 북마크 중 연속 3번 '완벽'이면 자동 해제
# ---------------------------------------------------------------------------
def update_mark(mark: dict | None, grade: int) -> tuple[dict, str | None]:
    m = {"bookmarked": False, "auto": False, "fails": 0, "streak": 0, **(mark or {})}
    event = None
    if grade == 0:
        m["fails"] += 1
        m["streak"] = 0
        if not m["bookmarked"] and m["fails"] >= AUTO_BOOKMARK_FAILS:
            m.update(bookmarked=True, auto=True)
            event = "on"
    elif grade == 2:
        m["streak"] += 1
        if m["bookmarked"] and m["streak"] >= AUTO_UNBOOKMARK_STREAK:
            m.update(bookmarked=False, auto=False, fails=0, streak=0)
            event = "off"
    else:
        m["streak"] = 0
    return m, event


def toggle_mark(mark: dict | None) -> dict:
    m = {"bookmarked": False, "auto": False, "fails": 0, "streak": 0, **(mark or {})}
    if m["bookmarked"]:
        m.update(bookmarked=False, auto=False, fails=0, streak=0)
    else:
        m.update(bookmarked=True, auto=False, streak=0)
    return m


# ---------------------------------------------------------------------------
# 장별 시험 결과
# ---------------------------------------------------------------------------
@dataclass
class ExamSummary:
    total: int
    perfect: int
    partial: int
    fail: int

    @property
    def finished(self) -> bool:
        return self.perfect + self.partial + self.fail == self.total

    @property
    def passed(self) -> bool:
        return self.finished and self.total > 0 and self.perfect / self.total >= PASS_RATE


def exam_summary(items: list[dict]) -> ExamSummary:
    grades = [i["g"] for i in items]
    return ExamSummary(len(items), grades.count(2), grades.count(1), grades.count(0))


def pending(queue: list[dict]) -> list[int]:
    return [i for i, q in enumerate(queue) if q["g"] is None]


def assign_slot(queue: list[dict], hour: int, end_hour: int) -> list[int]:
    """이번 시각에 보낼 카드: 남은 카드를 남은 시간대 수로 나눠 골고루."""
    left = pending(queue)
    if not left:
        return []
    slots_left = max(1, end_hour - hour + 1)
    batch = left[: math.ceil(len(left) / slots_left)]
    for i in batch:
        queue[i]["s"] = hour
    return batch


@dataclass
class ReciteStatus:
    done: int
    total: int
    is_done: bool
    streak: int


def queue_counts(queue: list[dict]) -> tuple[int, int]:
    return len(queue), sum(q["g"] is not None for q in queue)


def expected_finish(learned: int, total: int, daily_new: int, today: dt.date) -> dt.date | None:
    remaining = total - learned
    if remaining <= 0:
        return None
    return today + dt.timedelta(days=math.ceil(remaining / daily_new) - 1)


# ---------------------------------------------------------------------------
# 타이핑 채점
# ---------------------------------------------------------------------------
_PUNCT = re.compile(r"[\s.,;:!?\"'“”‘’()\[\]「」『』·…\-—~]")


def _norm(text: str) -> str:
    return _PUNCT.sub("", text)


@dataclass
class TypingResult:
    score: float     # 0~100
    grade: int
    diff_html: str   # 정답 본문에서 틀린·빠진 단어를 굵게 밑줄


def grade_typing(typed: str, answer: str) -> TypingResult:
    a, t = _norm(answer), _norm(typed)
    sm = difflib.SequenceMatcher(None, t, a, autojunk=False)
    score = sm.ratio() * 100 if a else 0.0

    # 띄어쓰기·문장부호를 뺀 글자끼리 맞춰 보고, 맞지 않은 글자가 있는 정답 단어에 표시
    matched = [False] * len(a)
    wrong_words = 0
    for block in sm.get_matching_blocks():
        for k in range(block.b, block.b + block.size):
            matched[k] = True
    out, pos = [], 0
    for word in answer.split():
        n = len(_norm(word))
        ok = all(matched[pos:pos + n])
        pos += n
        out.append(escape(word) if ok else f"<b><u>{escape(word)}</u></b>")
        wrong_words += not ok
    # 전문 암송이므로 '완벽'은 틀리거나 빠진 단어가 하나도 없을 때만 (덧붙인 말이 많아도 감점)
    if wrong_words == 0 and score >= 95:
        grade = 2
    else:
        grade = 1 if score >= 80 else 0
    return TypingResult(round(score, 1), grade, " ".join(out))


# ---------------------------------------------------------------------------
# 장별 진도판
# ---------------------------------------------------------------------------
def chapter_board(verses: list[dict], cards: list[dict]) -> list[tuple[int, int, int, int]]:
    """[(장, 전체 절 수, 익힌 절 수, 단단히 외운 절 수)]"""
    box_of = {c["verse_id"]: c["box"] for c in cards}
    stats: dict[int, list[int]] = {}
    for v in verses:
        s = stats.setdefault(v["chapter"], [0, 0, 0])
        s[0] += 1
        if v["id"] in box_of:
            s[1] += 1
            s[2] += box_of[v["id"]] >= MASTER_BOX
    return [(ch, *stats[ch]) for ch in sorted(stats)]


def chapter_icon(total: int, learned: int, mastered: int, passed: bool = False) -> str:
    if passed or (total and mastered == total):
        return "🏅"
    if total and learned == total:
        return "✅"
    return "📜" if learned else "✉️"
