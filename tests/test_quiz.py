import datetime as dt
import random
from types import SimpleNamespace as NS

import pytest

from bot import dates, handlers, jobs, quiz_handlers
from bot.config import ADMIN_ID
from bot.quiz import (decode_upload, is_done, make_question, normalize_ref, parse_hours,
                      parse_verse_text, pick_verse, quiz_streak)
from test_flow import FakeMessage, Harness

TODAY = dt.date(2026, 11, 5)
ADMIN = NS(id=ADMIN_ID, first_name="관리자", full_name="관리자")

VERSES_TXT = """# 11월 암송 구절
요 3:16 / 하나님이 세상을 사랑하사 독생자를 주심 / 하나님이 세상을 이처럼 사랑하사 독생자를 주셨으니
시 23:1 / 여호와는 나의 목자 / 여호와는 나의 목자시니 내게 부족함이 없으리로다
빌 4:13 / 능력 주시는 자 안에서 모든 것을 할 수 있음
살전 5:16 / 항상 기뻐하라
롬 8:28 / 모든 것이 합력하여 선을 이룸 / 하나님을 사랑하는 자 곧 그의 뜻대로 부르심을 입은 자들에게는 모든 것이 합력하여 선을 이루느니라
"""


# --- 순수 로직 ----------------------------------------------------------------
@pytest.mark.parametrize("raw, ref", [
    ("요 3:16", "요 3:16"), ("요3:16", "요 3:16"), ("요 3 : 16", "요 3:16"),
    ("고전13:4-7", "고전 13:4-7"), ("  시   23:1 ", "시 23:1"), ("요일 1:9", "요일 1:9"),
])
def test_normalize_ref(raw, ref):
    assert normalize_ref(raw) == ref


def test_parse_verse_text():
    text = (VERSES_TXT
            + "요3:16 / 독생자를 주신 사랑 / 본문 안에 / 슬래시가 있어도 됨\n"   # 같은 주소 -> 마지막 줄
            + "잘못된 줄\n"
            + "주소만 / \n"
            + "창세기 / 숫자 없는 주소\n")
    p = parse_verse_text(text)
    refs = [r["ref"] for r in p.rows]
    assert refs == ["요 3:16", "시 23:1", "빌 4:13", "살전 5:16", "롬 8:28"]
    john = p.rows[0]
    assert (john["core"], john["body"]) == ("독생자를 주신 사랑", "본문 안에 / 슬래시가 있어도 됨")
    assert p.rows[2]["body"] is None
    assert len(p.errors) == 3 and "8번째 줄" in p.errors[0]


def test_decode_upload_handles_old_windows_encoding():
    assert decode_upload("요 3:16 / 사랑".encode("cp949")) == "요 3:16 / 사랑"
    assert decode_upload("﻿요 3:16 / 사랑".encode("utf-8")) == "요 3:16 / 사랑"


@pytest.mark.parametrize("text, hours", [
    ("13-22", (13, 22)), ("9~18", (9, 18)), ("9시-18시", (9, 18)), ("0-23", (0, 23)),
    ("22-13", None), ("13-24", None), ("abc", None),
])
def test_parse_hours(text, hours):
    assert parse_hours(text) == hours


def _verses():
    return [dict(r, id=i) for i, r in enumerate(parse_verse_text(VERSES_TXT).rows, start=1)]


def test_make_question_both_kinds():
    vs, rng = _verses(), random.Random(1)
    q = make_question(vs[0], vs, rng, kind="ref2core")
    assert q["prompt"] == "요 3:16" and len(set(q["options"])) == 4
    assert q["options"][q["correct_idx"]] == "하나님이 세상을 사랑하사 독생자를 주심"
    q = make_question(vs[2], vs, rng, kind="core2ref")
    assert q["prompt"] == "능력 주시는 자 안에서 모든 것을 할 수 있음"   # 본문이 없으면 핵심 내용
    assert q["options"][q["correct_idx"]] == "빌 4:13"
    assert all(o in {v["ref"] for v in vs} for o in q["options"])


def test_pick_verse_prefers_missed_and_avoids_today():
    vs, rng = _verses(), random.Random(7)
    picks = [pick_verse(vs, {3: 10}, set(), rng)["id"] for _ in range(500)]
    assert picks.count(3) > 250                       # 많이 틀린 구절이 훨씬 자주
    picks = {pick_verse(vs, {}, {1, 2, 3, 4}, rng)["id"] for _ in range(50)}
    assert picks == {5}                               # 오늘 낸 구절은 피함
    assert pick_verse(vs, {}, {1, 2, 3, 4, 5}, rng)   # 다 냈으면 다시 아무거나


def test_is_done_and_streak():
    assert is_done(10, 10, 10, 22, 22)
    assert not is_done(9, 10, 10, 22, 22)
    assert not is_done(3, 3, 10, 16, 22)              # 아직 출제 중
    assert is_done(9, 9, 10, 23, 22)                  # 한 시간 출제를 놓쳤어도 끝난 뒤 다 풀었으면 완료
    d = lambda day: dt.date(2026, 11, day)
    hist = {d(1): (10, 10), d(3): (10, 10), d(4): (10, 10)}   # 2일은 출제 없음 -> 건너뜀
    assert quiz_streak(hist, d(5), False, d(1)) == 3
    assert quiz_streak(hist, d(5), True, d(1)) == 4
    assert quiz_streak({**hist, d(4): (10, 9)}, d(5), False, d(1)) == 0


# --- 사용 흐름 ----------------------------------------------------------------
@pytest.fixture
def h(monkeypatch):
    monkeypatch.setattr(dates, "today", lambda: TODAY)
    monkeypatch.setattr(dates, "now", lambda: dt.datetime(2026, 11, 5, 13, 0))
    quiz_handlers.rng.seed(3)
    return Harness()


def at(monkeypatch, hour, minute=0, day=TODAY):
    monkeypatch.setattr(dates, "today", lambda: day)
    monkeypatch.setattr(dates, "now", lambda: dt.datetime.combine(day, dt.time(hour, minute)))


async def admin_import(h, text=VERSES_TXT):
    return await h.say("/qa\n" + text, user=ADMIN, handler=quiz_handlers.cmd_quiz_add)


async def test_admin_import_and_permissions(h):
    msg = await h.say("/qa\n" + VERSES_TXT, handler=quiz_handlers.cmd_quiz_add)
    assert "관리자만" in msg.text and not h.repo.verses

    msg = await admin_import(h)
    assert "새로 추가: 5개" in msg.text and "전체: 5개" in msg.text
    msg = await admin_import(h, "요 3:16 / 독생자를 주신 사랑\n고전 13:4 / 사랑은 오래 참고")
    assert "새로 추가: 1개" in msg.text and "내용 수정: 1개" in msg.text and "전체: 6개" in msg.text

    msg = await h.say("/qv", user=ADMIN, handler=quiz_handlers.cmd_quiz_list)
    assert "저장된 성구 6개" in msg.text and "독생자를 주신 사랑" in msg.text
    msg = await h.say("/qd 고전13:4", user=ADMIN, handler=quiz_handlers.cmd_quiz_delete, args=["고전13:4"])
    assert "삭제했어요" in msg.text and len(h.repo.verses) == 5


async def test_admin_txt_upload(h):
    data = bytearray(VERSES_TXT.encode("cp949", errors="ignore"))
    async def get_file():
        async def download():
            return data
        return NS(download_as_bytearray=download)
    msg = FakeMessage(h.bot, h.chat, None, user=ADMIN)
    msg.document = NS(file_name="11월.TXT", file_size=len(data), get_file=get_file)
    await quiz_handlers.on_document(h.update(msg, user=ADMIN), h.ctx())
    assert "새로 추가: 5개" in h.bot.last.text

    msg.document = NS(file_name="photo.jpg", file_size=10, get_file=get_file)
    await quiz_handlers.on_document(h.update(msg, user=ADMIN), h.ctx())
    assert ".txt" in h.bot.last.text

    before = len(h.bot.sent)
    await quiz_handlers.on_document(h.update(msg), h.ctx())   # 일반 사용자 파일은 무시
    assert len(h.bot.sent) == before


async def test_hourly_issue_answer_and_routine(h, monkeypatch):
    await h.say("보고서")                       # 사용자 공간 생성 (기본 13~22시)
    await admin_import(h)

    at(monkeypatch, 12, 0)
    before = len(h.bot.sent)
    await jobs.minute_job(h.ctx())
    assert len(h.bot.sent) == before           # 시간대 밖

    at(monkeypatch, 13, 0)
    await jobs.minute_job(h.ctx())
    quiz_msg = h.bot.last
    assert "성구 퀴즈</b> · 13시" in quiz_msg.text and len(quiz_msg.reply_markup.inline_keyboard) == 4
    at(monkeypatch, 13, 1)
    await jobs.minute_job(h.ctx())
    assert h.bot.last is quiz_msg              # 같은 시간에 두 번 출제하지 않음
    assert len(h.repo.questions) == 1

    q = next(iter(h.repo.questions.values()))
    wrong = (q["correct_idx"] + 1) % 4
    click = await h.click(quiz_msg, f"qz:{q['id']}:{wrong}")
    assert click.answers == ["❌ 아쉬워요!"]
    assert "아쉬워요! 정답은" in quiz_msg.text and "📖" in quiz_msg.text
    assert "오늘 퀴즈 1/10" in quiz_msg.text
    assert h.repo.misses[(q["space_id"], q["verse_id"])] == 1

    click = await h.click(quiz_msg, f"qz:{q['id']}:{q['correct_idx']}")
    assert click.answers == ["이미 푼 문제예요."]   # 두 번째 답은 반영 안 됨
    assert h.repo.questions[q["id"]]["correct"] is False

    lst = await h.say("/l", handler=handlers.cmd_list)
    assert any("📜 성구 퀴즈 1/10" in t for t, _ in h.buttons(lst))
    assert "루틴 0/1" in lst.text

    # 정각을 놓쳐도 10분 안이면 따라잡아 출제, 그 뒤엔 출제 안 함
    at(monkeypatch, 14, 7)
    await jobs.minute_job(h.ctx())
    assert len(h.repo.questions) == 2
    at(monkeypatch, 15, 11)
    await jobs.minute_job(h.ctx())
    assert len(h.repo.questions) == 2


async def test_correct_answer_reduces_misses_and_completes_routine(h, monkeypatch):
    await h.say("/q 13-13", handler=quiz_handlers.cmd_quiz, args=["13-13"])   # 하루 1문제
    await admin_import(h)
    space = (await h.repo.all_spaces())[0]
    q0 = await h.repo.create_question({"space_id": space["id"], "quiz_date": TODAY, "hour": 9,
                                       "verse_id": 1, "kind": "ref2core", "ref": "요 3:16",
                                       "prompt": "요 3:16", "options": ["a", "b", "c", "d"],
                                       "correct_idx": 0})
    await h.repo.answer_question(space["id"], q0["id"], 0, True)              # 지난 설정에서 푼 문제
    await h.repo.set_verse_miss(space["id"], 2, 2)
    h.repo.questions.clear()

    at(monkeypatch, 13)
    await jobs.minute_job(h.ctx())
    q = next(iter(h.repo.questions.values()))
    h.repo.misses[(space["id"], q["verse_id"])] = 2
    await h.click(h.bot.last, f"qz:{q['id']}:{q['correct_idx']}")
    assert "⭕ <b>정답이에요!</b>" in h.bot.last.text
    assert "🍋 오늘 퀴즈 완료!" in h.bot.last.text
    assert h.repo.misses[(space["id"], q["verse_id"])] == 1

    lst = await h.say("/l", handler=handlers.cmd_list)
    assert any("🍋 📜 성구 퀴즈 1/1" in t for t, _ in h.buttons(lst))
    assert "ALL CLEAR" in lst.text


async def test_stale_question_and_deleted_verse(h, monkeypatch):
    await h.say("/q", handler=quiz_handlers.cmd_quiz)
    await admin_import(h)
    at(monkeypatch, 13)
    await jobs.minute_job(h.ctx())
    quiz_msg = h.bot.last
    q = next(iter(h.repo.questions.values()))

    await h.say("/qd " + q["ref"], user=ADMIN, handler=quiz_handlers.cmd_quiz_delete, args=q["ref"].split())
    at(monkeypatch, 9, day=TODAY + dt.timedelta(days=1))
    click = await h.click(quiz_msg, f"qz:{q['id']}:0")
    assert "지난 문제" in click.answers[0]
    assert "기록되지 않아요" in quiz_msg.text and quiz_msg.reply_markup is None
    assert h.repo.questions[q["id"]]["answer_idx"] is None


async def test_quiz_settings_and_off(h, monkeypatch):
    await admin_import(h)
    msg = await h.say("/q", handler=quiz_handlers.cmd_quiz)
    assert "13~22시" in msg.text and "하루 10문제" in msg.text
    msg = await h.say("/q 9-18", handler=quiz_handlers.cmd_quiz, args=["9-18"])
    assert "9~18시" in msg.text
    msg = await h.say("/q 25-3", handler=quiz_handlers.cmd_quiz, args=["25-3"])
    assert "0~23" in msg.text

    await h.say("/q off", handler=quiz_handlers.cmd_quiz, args=["off"])
    at(monkeypatch, 13)
    await jobs.minute_job(h.ctx())
    assert not h.repo.questions
    lst = await h.say("/l", handler=handlers.cmd_list)
    assert not any("성구 퀴즈" in t for t, _ in h.buttons(lst))

    await h.say("/q on", handler=quiz_handlers.cmd_quiz, args=["on"])
    await h.say("/off", handler=handlers.cmd_off)                    # /off 한 방도 출제 안 함
    await jobs.minute_job(h.ctx())
    assert not h.repo.questions


async def test_no_quiz_until_four_verses(h, monkeypatch):
    await h.say("보고서")
    await admin_import(h, "요 3:16 / 사랑\n시 23:1 / 목자\n빌 4:13 / 능력")
    at(monkeypatch, 13)
    await jobs.minute_job(h.ctx())
    assert not h.repo.questions
    lst = await h.say("/l", handler=handlers.cmd_list)
    assert not any("성구 퀴즈" in t for t, _ in h.buttons(lst))


async def test_quiz_info_button_and_night_check(h, monkeypatch):
    await h.say("보고서")
    await admin_import(h)
    lst = await h.say("/l", handler=handlers.cmd_list)
    click = await h.click(lst, "qz:i")
    assert "자동으로 체크" in click.answers[0]
    await h.click(lst, "l:n")
    assert any("📜 성구 퀴즈 0/10" in t for t, _ in h.buttons(lst))   # 밤 점검 '남은 루틴'에도 표시
