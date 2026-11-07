"""자정을 넘겨 밤 점검·퀴즈를 눌러도 다음 날 새벽 4시 전까지는 '그날' 기록으로 처리."""
import datetime as dt

import pytest

from bot import dates, handlers, jobs, quiz_handlers
from bot.config import TZ
from test_flow import Harness
from test_quiz import ADMIN, VERSES_TXT

NOV5 = dt.date(2026, 11, 5)   # 목
NOV6 = dt.date(2026, 11, 6)


def at(monkeypatch, day, hour, minute=0):
    monkeypatch.setattr(dates, "today", lambda: day)
    monkeypatch.setattr(dates, "now", lambda: dt.datetime.combine(day, dt.time(hour, minute)))


@pytest.mark.parametrize("when, day", [
    (dt.datetime(2026, 11, 5, 22, 0), NOV5),
    (dt.datetime(2026, 11, 6, 0, 30), NOV5),
    (dt.datetime(2026, 11, 6, 3, 59), NOV5),
    (dt.datetime(2026, 11, 6, 4, 0), NOV6),
])
def test_night_day_of(when, day):
    assert dates.night_day_of(when) == day
    assert dates.night_day_of(TZ.localize(when)) == day
    # 텔레그램은 UTC 시각을 준다
    assert dates.night_day_of(TZ.localize(when).astimezone(dt.timezone.utc)) == day


def test_within_grace():
    assert dates.within_grace(NOV5, dt.datetime(2026, 11, 5, 23, 59))
    assert dates.within_grace(NOV5, dt.datetime(2026, 11, 6, 3, 59))
    assert not dates.within_grace(NOV5, dt.datetime(2026, 11, 6, 4, 0))
    assert not dates.within_grace(NOV5, dt.datetime(2026, 11, 7, 1, 0))   # 바로 전날만


@pytest.fixture
async def night(monkeypatch):
    """11/5 22:00에 밤 점검 메시지를 받은 상태."""
    h = Harness()
    at(monkeypatch, NOV5, 9)
    await h.say("보고서\n청소\n독서")
    await h.say("/r 영단어", handler=handlers.cmd_routine)
    at(monkeypatch, NOV5, 22)
    await jobs.minute_job(h.ctx())
    msg = h.bot.last
    assert "밤 점검 · 11월 5일" in msg.text
    ids = {t["title"]: t["id"] for t in h.repo.tasks.values()}
    rid = next(iter(h.repo.routines_))
    return h, msg, ids, rid


async def test_after_midnight_counts_for_previous_day(night, monkeypatch):
    h, msg, ids, rid = night
    at(monkeypatch, NOV6, 0, 30)
    await h.click(msg, f"t:n:{ids['보고서']}")
    await h.click(msg, f"r:n:{rid}")
    await h.click(msg, f"n:t:{ids['청소']}")
    assert h.repo.tasks[ids["보고서"]]["done_at"] == NOV5          # 전날 완료
    assert (rid, NOV5) in h.repo.logs and (rid, NOV6) not in h.repo.logs
    assert h.repo.tasks[ids["청소"]]["due_date"] == NOV6           # '내일' = 그 밤의 다음 날
    assert "밤 점검 · 11월 5일" in msg.text                         # 화면도 그날 기준

    # 새 날 목록에는 어제 완료한 할 일이 보이지 않고, 루틴은 새로 미완료
    lst = await h.say("/l", handler=handlers.cmd_list)
    labels = [t for t, _ in h.buttons(lst)]
    assert not any("보고서" in t for t in labels)
    assert any("🥚 청소" in t for t in labels)
    assert any("🥚 영단어" in t for t in labels)


async def test_streak_kept_when_checked_after_midnight(night, monkeypatch):
    h, msg, ids, rid = night
    h.repo.logs |= {(rid, NOV5 - dt.timedelta(days=1))}             # 11/4도 했음
    h.repo.routines_[rid]["created_on"] = NOV5 - dt.timedelta(days=1)
    at(monkeypatch, NOV6, 1)
    await h.click(msg, f"r:n:{rid}")
    lst = await h.say("/l", handler=handlers.cmd_list)
    assert any("영단어 🔥2" in t for t, _ in h.buttons(lst))         # 연속 기록 유지


async def test_after_4am_is_expired(night, monkeypatch):
    h, msg, ids, rid = night
    at(monkeypatch, NOV6, 4, 0)
    q = await h.click(msg, f"t:n:{ids['보고서']}")
    assert "지난 밤 점검" in q.answers[0]
    assert h.repo.tasks[ids["보고서"]]["done_at"] is None
    assert msg.reply_markup is None and "지난 밤 점검" in msg.text
    for data in (f"r:n:{rid}", f"n:t:{ids['청소']}", f"n:x:{ids['독서']}"):
        await h.click(msg, data)
    assert not h.repo.logs and ids["독서"] in h.repo.tasks
    assert h.repo.tasks[ids["청소"]]["due_date"] == NOV5


async def test_list_buttons_still_use_click_day(night, monkeypatch):
    h, msg, ids, rid = night
    lst = await h.say("/l", handler=handlers.cmd_list)               # 11/5에 연 목록
    at(monkeypatch, NOV6, 0, 30)
    await h.click(lst, f"t:l:{ids['보고서']}")
    assert h.repo.tasks[ids["보고서"]]["done_at"] == NOV6            # 목록 화면은 누른 날 기준


async def test_night_done_button_does_not_undo(night, monkeypatch):
    h, msg, ids, rid = night
    await h.click(msg, f"t:n:{ids['보고서']}")
    q = await h.click(msg, f"t:n:{ids['보고서']}")
    assert q.answers == ["이미 완료한 할 일이에요."]
    assert h.repo.tasks[ids["보고서"]]["done_at"] == NOV5


async def test_notify_after_midnight_is_previous_nights_check(monkeypatch):
    h = Harness()
    at(monkeypatch, dt.date(2026, 11, 7), 9)                         # 토요일
    await h.say("보고서")
    await h.say("/t 00:30", handler=handlers.cmd_time, args=["00:30"])
    at(monkeypatch, dt.date(2026, 11, 8), 0, 30)                     # 일요일 00:30
    before = len(h.bot.sent)
    await jobs.minute_job(h.ctx())
    new = h.bot.sent[before:]
    assert "밤 점검 · 11월 7일" in new[0].text                       # 토요일 밤 점검
    assert "주간 리포트" in new[1].text and "11/1(일) ~ 11/7(토)" in new[1].text
    await h.click(new[0], f"t:n:{next(iter(h.repo.tasks))}")
    assert next(iter(h.repo.tasks.values()))["done_at"] == dt.date(2026, 11, 7)


async def test_quiz_answer_after_midnight(monkeypatch):
    h = Harness()
    quiz_handlers.rng.seed(1)
    at(monkeypatch, NOV5, 9)
    await h.say("/q 22-22", handler=quiz_handlers.cmd_quiz, args=["22-22"])
    await h.say("/qa\n" + VERSES_TXT, user=ADMIN, handler=quiz_handlers.cmd_quiz_add)
    at(monkeypatch, NOV5, 22)
    await jobs.minute_job(h.ctx())
    quiz_msg = h.bot.last
    q = next(iter(h.repo.questions.values()))

    at(monkeypatch, NOV6, 1)
    await h.click(quiz_msg, f"qz:{q['id']}:{q['correct_idx']}")
    assert h.repo.questions[q["id"]]["correct"] is True              # 새벽 1시에도 인정
    assert "🍋 오늘 퀴즈 완료!" in quiz_msg.text                      # 11/5 퀴즈 1/1 완료

    q2 = await h.repo.create_question({**{k: q[k] for k in ("space_id", "verse_id", "kind", "ref",
                                                             "prompt", "options", "correct_idx")},
                                       "quiz_date": NOV5, "hour": 21})
    at(monkeypatch, NOV6, 4)
    click = await h.click(quiz_msg, f"qz:{q2['id']}:0")
    assert "지난 문제" in click.answers[0]
    assert h.repo.questions[q2["id"]]["answer_idx"] is None
