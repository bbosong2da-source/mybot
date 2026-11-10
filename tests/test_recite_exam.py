"""바로 시험보기, 장별 시험(진도 반영), 북마크, 타이핑 안내 삭제."""
import datetime as dt

import pytest

from bot import handlers, jobs, recite_handlers
from test_flow import Harness
from test_quiz import ADMIN
from test_recite import COURSE_TXT, NOV7, NOV8, at, buttons

# 1장 4절 + 2장 1절
CH1 = ["계 1:1", "계 1:2", "계 1:3", "계 1:4"]


@pytest.fixture
async def h(monkeypatch):
    recite_handlers.rng.seed(5)
    at(monkeypatch, NOV7, 9)
    h = Harness()
    await h.say("/rva\n" + COURSE_TXT, user=ADMIN, handler=recite_handlers.cmd_recite_add)
    await h.say("/rv 2", handler=recite_handlers.cmd_recite, args=["2"])
    h.sid = next(iter(h.repo.members))
    h.vid = {v["ref"]: v["id"] for v in h.repo.rverses.values()}
    return h


async def evening_card(h, monkeypatch, day=NOV7, hour=18):
    at(monkeypatch, day, hour)
    await jobs.minute_job(h.ctx())
    return next(m for m in reversed(h.bot.sent) if "계시록 암송</b> ·" in m.text)


async def test_quick_test_known_verse_gets_long_interval(h, monkeypatch):
    card = await evening_card(h, monkeypatch)
    assert "⏭ 바로 시험보기" in buttons(h, card)
    await h.click(card, buttons(h, card)["⏭ 바로 시험보기"])
    assert "암송해 보세요" in card.text and "1/4" not in card.text
    await h.click(card, buttons(h, card)["👀 정답 보기"])
    await h.click(card, buttons(h, card)["✅ 완벽"])
    c = h.repo.cards[(h.sid, h.vid["계 1:1"])]
    assert (c["box"], c["due_date"]) == (2, NOV7 + dt.timedelta(days=7))   # 이미 아는 구절

    # 4단계를 다 거친 새 구절은 기존처럼 다음 날 복습
    await h.click(card, buttons(h, card)["▶ 지금 더 하기"])
    for label in ("다음 단계 ▶", "다음 단계 ▶", "다음 단계 ▶", "👀 정답 보기", "✅ 완벽"):
        await h.click(card, buttons(h, card)[label])
    assert h.repo.cards[(h.sid, h.vid["계 1:2"])]["due_date"] == NOV8


async def test_bookmark_toggle_and_auto(h, monkeypatch):
    card = await evening_card(h, monkeypatch)
    await h.click(card, buttons(h, card)["⏭ 바로 시험보기"])
    await h.click(card, buttons(h, card)["👀 정답 보기"])
    q = await h.click(card, buttons(h, card)["☆ 북마크"])
    assert q.answers == ["⭐ 북마크했어요"] and "⭐ 북마크 해제" in buttons(h, card)
    assert "⭐" in card.text.split("\n")[0]
    await h.click(card, buttons(h, card)["✅ 완벽"])
    c = h.repo.cards[(h.sid, h.vid["계 1:1"])]
    assert c["due_date"] == NOV7 + dt.timedelta(days=3)         # 북마크는 최대 3일 간격

    board = await h.say("/rv 북마크", handler=recite_handlers.cmd_recite, args=["북마크"])
    assert "북마크한 구절</b> (1)" in board.text and "계 1:1" in board.text
    await h.click(board, buttons(h, board)["☆ 계 1:1 해제"])
    assert "아직 없어요" in board.text

    # '못 외움' 2번 → 자동 북마크
    await h.click(card, buttons(h, card)["▶ 지금 더 하기"])
    await h.click(card, buttons(h, card)["⏭ 바로 시험보기"])
    await h.click(card, buttons(h, card)["👀 정답 보기"])
    await h.click(card, buttons(h, card)["❌ 못 외움"])
    assert not h.repo.marks[(h.sid, h.vid["계 1:2"])]["bookmarked"]
    msg = await h.say("/rv 시험 1", handler=recite_handlers.cmd_recite, args=["시험", "1"])
    await h.click(msg, buttons(h, msg)["👀 정답 보기"])        # 1:1
    await h.click(msg, buttons(h, msg)["✅ 완벽"])
    await h.click(msg, buttons(h, msg)["👀 정답 보기"])        # 1:2 두 번째 못 외움
    q = await h.click(msg, buttons(h, msg)["❌ 못 외움"])
    assert q.answers == ["⭐ 자주 틀려서 북마크했어요"]
    assert h.repo.marks[(h.sid, h.vid["계 1:2"])]["auto"] is True


async def test_chapter_exam_reflects_progress(h, monkeypatch):
    msg = await h.say("/rv 시험", handler=recite_handlers.cmd_recite, args=["시험"])
    assert "장별 시험" in msg.text and "1장 ✉️" in buttons(h, msg)
    await h.click(msg, buttons(h, msg)["1장 ✉️"])
    assert "계시록 1장 시험</b> · 1/4" in msg.text and "계 1:1" in msg.text

    await h.click(msg, buttons(h, msg)["👀 정답 보기"])
    await h.click(msg, buttons(h, msg)["✅ 완벽"])
    await h.click(msg, buttons(h, msg)["⏸ 그만하기"])          # 멈췄다가
    assert "멈췄어요 (1/4)" in msg.text
    await h.click(msg, buttons(h, msg)["▶ 이어서 하기"])        # 이어서
    assert "이어서 시작해요 (1/4 완료)" in msg.text and "계 1:2" in msg.text

    for _ in range(3):
        await h.click(msg, buttons(h, msg)["👀 정답 보기"])
        await h.click(msg, buttons(h, msg)["✅ 완벽"])
    assert "1장 시험 결과" in msg.text and "완벽 4" in msg.text and "통과!" in msg.text
    assert h.repo.members[h.sid]["passed_chapters"] == [1]
    for ref in CH1:
        assert h.repo.cards[(h.sid, h.vid[ref])]["due_date"] == NOV7 + dt.timedelta(days=7)

    board = await h.say("/rv", handler=recite_handlers.cmd_recite)
    assert "1장 🏅" in board.text and "진도 <b>4/5절</b>" in board.text

    # 새 구절 카드는 시험으로 외운 1장을 건너뛰고 2:1부터
    at(monkeypatch, NOV8, 18)
    await jobs.minute_job(h.ctx())
    rec = h.repo.rdays[(h.sid, NOV8)]
    assert [x["seq"] for x in rec["queue"] if x["k"] == "new"] == [5]


async def test_exam_fail_on_unlearned_stays_new(h, monkeypatch):
    msg = await h.say("/rv 시험 1장", handler=recite_handlers.cmd_recite, args=["시험", "1장"])
    grades = ["✅ 완벽", "❌ 못 외움", "🔸 조금 틀림", "✅ 완벽"]
    for g in grades:
        await h.click(msg, buttons(h, msg)["👀 정답 보기"])
        await h.click(msg, buttons(h, msg)[g])
    assert "통과(완벽 90%)까지" in msg.text and "다시 볼 구절: 계 1:2, 계 1:3" in msg.text
    assert (h.sid, h.vid["계 1:2"]) not in h.repo.cards           # 못 외운 절은 새 구절로 남음
    assert h.repo.cards[(h.sid, h.vid["계 1:3"])]["due_date"] == NOV8
    assert not h.repo.members[h.sid].get("passed_chapters")
    at(monkeypatch, NOV8, 18)
    await jobs.minute_job(h.ctx())
    rec = h.repo.rdays[(h.sid, NOV8)]
    assert [x["seq"] for x in rec["queue"] if x["k"] == "new"] == [2, 5]

    await h.click(msg, buttons(h, msg)["🔁 처음부터 다시"])       # 끝난 시험은 새로 시작
    assert "1/4" in msg.text


async def test_exam_typing_and_prompt_deleted(h, monkeypatch):
    msg = await h.say("/rv 시험 2", handler=recite_handlers.cmd_recite, args=["시험", "2"])
    await h.click(msg, buttons(h, msg)["⌨️ 타이핑으로 확인"])
    prompt = h.bot.last
    assert "#X" in prompt.text
    reply = await h.say("에베소 교회의 사자에게 편지하라", reply_to=prompt)
    assert "정확도 <b>100%</b>" in reply.text and "완벽" in reply.text and "2장 통과!" in reply.text
    assert prompt.message_id in h.bot.deleted and msg.message_id in h.bot.deleted
    assert h.repo.members[h.sid]["passed_chapters"] == [2]
    assert not h.repo.tasks
    await h.click(reply, buttons(h, reply)["📊 결과 보기"])
    assert "2장 시험 결과" in reply.text and len(h.bot.deleted) == 3


async def test_exam_typing_next_verse_is_ready_to_type(h, monkeypatch):
    bodies = {v["ref"]: v["body"] for v in h.repo.rverses.values()}
    card = await h.say("/rv 시험 1", handler=recite_handlers.cmd_recite, args=["시험", "1"])
    await h.click(card, buttons(h, card)["⌨️ 타이핑으로 확인"])    # 첫 절만 버튼으로 타이핑 시작
    question = h.bot.last
    for n, ref in enumerate(CH1):
        assert "#X" in question.text and ref in question.text
        if n:   # 다음 절부터는 답장 입력창이 열린 문제가 바로 옴 (⌨️ 버튼 없이)
            assert f"{n + 1}/4" in question.text and question.reply_markup.__class__.__name__ == "ForceReply"
        result = await h.say(bodies[ref], reply_to=question)
        assert "정확도 <b>100%</b>" in result.text
        assert question.message_id in h.bot.deleted               # 문제(답장 대상)는 지움
        last = n == len(CH1) - 1
        b = buttons(h, result)
        assert ("⏸ 그만하기" in b) != last
        label = "📊 결과 보기" if last else "다음 절 ⌨️ ▶"
        await h.click(result, b[label])
        assert int(b[label].split(":")[-1]) in h.bot.deleted     # 내가 보낸 답 메시지 삭제
        if last:
            assert "1장 시험 결과" in result.text and "통과!" in result.text
        else:
            assert result.message_id in h.bot.deleted             # 결과 카드도 지우고
            question = h.bot.last                                 # 다음 절 문제가 새로 옴
    alive = [m for m in h.bot.sent if m.message_id not in h.bot.deleted]
    assert [m for m in alive if "1장 시험" in (m.text or "")] == [result]
    assert not h.repo.tasks


async def test_exam_typing_stop_from_result(h, monkeypatch):
    bodies = {v["ref"]: v["body"] for v in h.repo.rverses.values()}
    card = await h.say("/rv 시험 1", handler=recite_handlers.cmd_recite, args=["시험", "1"])
    await h.click(card, buttons(h, card)["⌨️ 타이핑으로 확인"])
    result = await h.say(bodies["계 1:1"], reply_to=h.bot.last)
    stop_cb = buttons(h, result)["⏸ 그만하기"]
    await h.click(result, stop_cb)
    assert "멈췄어요 (1/4)" in result.text and int(stop_cb.split(":")[-1]) in h.bot.deleted
    await h.click(result, buttons(h, result)["▶ 이어서 하기"])    # 이어서 하면 원래 카드로
    assert "계 1:2" in result.text and "👀 정답 보기" in buttons(h, result)


async def test_daily_typing_prompt_deleted(h, monkeypatch):
    card = await evening_card(h, monkeypatch)
    await h.click(card, buttons(h, card)["⏭ 바로 시험보기"])
    await h.click(card, buttons(h, card)["⌨️ 타이핑으로 확인"])
    prompt = h.bot.last
    await h.say("예수 그리스도의 계시라 이는 하나님이 그에게 주사 반드시 속히 일어날 일들을", reply_to=prompt)
    assert prompt.message_id in h.bot.deleted
    c = h.repo.cards[(h.sid, h.vid["계 1:1"])]
    assert c["box"] == 2                                       # 바로 시험 + 타이핑 완벽 → 이미 아는 구절


async def test_bookmark_only_exam(h, monkeypatch):
    msg = await h.say("/rv 시험 북마크", handler=recite_handlers.cmd_recite, args=["시험", "북마크"])
    assert "북마크한 구절이 없어요" in msg.text
    h.repo.marks[(h.sid, h.vid["계 1:3"])] = {"space_id": h.sid, "verse_id": h.vid["계 1:3"],
                                             "bookmarked": True, "auto": False, "fails": 0, "streak": 0}
    msg = await h.say("/rv 시험 북마크", handler=recite_handlers.cmd_recite, args=["시험", "북마크"])
    assert "북마크 시험</b> · 1/1" in msg.text and "계 1:3" in msg.text
    await h.click(msg, buttons(h, msg)["👀 정답 보기"])
    await h.click(msg, buttons(h, msg)["✅ 완벽"])
    assert "북마크 시험 결과" in msg.text and "통과" not in msg.text


async def test_routine_delete_buttons_still_work(h):
    # 시험 버튼 이름이 루틴 삭제(rx/ry)와 겹치지 않는지
    mgr = await h.say("/r 운동", handler=handlers.cmd_routine)
    rid = next(iter(h.repo.routines_))
    await h.click(mgr, f"rx:{rid}")
    assert "삭제할까요" in mgr.text


async def test_bookmark_from_exam_typing_result(h, monkeypatch):
    bodies = {v["ref"]: v["body"] for v in h.repo.rverses.values()}
    card = await h.say("/rv 시험 1", handler=recite_handlers.cmd_recite, args=["시험", "1"])
    await h.click(card, buttons(h, card)["⌨️ 타이핑으로 확인"])
    result = await h.say(bodies["계 1:1"], reply_to=h.bot.last)
    text_before = result.text
    q = await h.click(result, buttons(h, result)["☆ 북마크"])
    assert q.answers == ["⭐ 북마크했어요"]
    assert h.repo.marks[(h.sid, h.vid["계 1:1"])]["bookmarked"]
    assert result.text == text_before                          # 채점 내용은 그대로
    b = buttons(h, result)
    assert "⭐ 북마크 해제" in b and "다음 절 ⌨️ ▶" in b and "⏸ 그만하기" in b
    await h.click(result, b["⭐ 북마크 해제"])
    assert not h.repo.marks[(h.sid, h.vid["계 1:1"])]["bookmarked"]
    await h.click(result, buttons(h, result)["☆ 북마크"])
    await h.click(result, buttons(h, result)["다음 절 ⌨️ ▶"])   # 다음 절도 그대로 동작
    assert "계 1:2" in h.bot.last.text and "#X" in h.bot.last.text
    lst = await h.say("/rv 북마크", handler=recite_handlers.cmd_recite, args=["북마크"])
    assert "계 1:1" in lst.text


async def test_bookmark_from_daily_typing_result(h, monkeypatch):
    card = await evening_card(h, monkeypatch)
    await h.click(card, buttons(h, card)["⏭ 바로 시험보기"])
    await h.click(card, buttons(h, card)["⌨️ 타이핑으로 확인"])
    result = await h.say("예수 그리스도의 계시라", reply_to=h.bot.last)
    b = buttons(h, result)
    assert "☆ 북마크" in b and "확인 ✔" in b
    await h.click(result, b["☆ 북마크"])
    assert h.repo.marks[(h.sid, h.vid["계 1:1"])]["bookmarked"]
    assert "⭐ 북마크 해제" in buttons(h, result)
    await h.click(result, buttons(h, result)["확인 ✔"])
    assert "이번 시간 카드를 마쳤어요" in result.text


async def grade_all(h, msg, grades):
    for g in grades:
        await h.click(msg, buttons(h, msg)["👀 정답 보기"])
        await h.click(msg, buttons(h, msg)[g])


async def test_retry_only_missed_until_all_perfect(h, monkeypatch):
    msg = await h.say("/rv 시험 1", handler=recite_handlers.cmd_recite, args=["시험", "1"])
    await grade_all(h, msg, ["✅ 완벽", "❌ 못 외움", "🔸 조금 틀림", "✅ 완벽"])
    b = buttons(h, msg)
    assert "🔁 틀린 구절만 다시 (2)" in b and "🔁 처음부터 다시" in b

    await h.click(msg, b["🔁 틀린 구절만 다시 (2)"])
    assert "계시록 1장 다시 보기</b> · 1/2" in msg.text and "계 1:2" in msg.text
    await grade_all(h, msg, ["✅ 완벽", "🔸 조금 틀림"])
    assert "1장 다시 보기 결과" in msg.text and "통과" not in msg.text   # 🏅 판정 없음
    assert "다시 볼 구절: 계 1:3" in msg.text
    # 처음 시험에서 못 외웠던 1:2를 다시 보기에서 완벽 → 외운 구절로 등록
    assert h.repo.cards[(h.sid, h.vid["계 1:2"])]["box"] == 2

    await h.click(msg, buttons(h, msg)["🔁 틀린 구절만 다시 (1)"])
    assert "1/1" in msg.text and "계 1:3" in msg.text
    await grade_all(h, msg, ["✅ 완벽"])
    b = buttons(h, msg)
    assert not any("틀린 구절만" in t for t in b)                      # 모두 완벽 → 버튼 없음
    assert not h.repo.members[h.sid].get("passed_chapters")          # 다시 보기로는 🏅 없음
    await h.click(msg, b["🔁 처음부터 다시"])
    assert "계시록 1장 시험</b> · 1/4" in msg.text


async def test_retry_stop_and_resume_same_retry(h, monkeypatch):
    msg = await h.say("/rv 시험 1", handler=recite_handlers.cmd_recite, args=["시험", "1"])
    await grade_all(h, msg, ["❌ 못 외움", "❌ 못 외움", "✅ 완벽", "✅ 완벽"])
    await h.click(msg, buttons(h, msg)["🔁 틀린 구절만 다시 (2)"])
    await grade_all(h, msg, ["✅ 완벽"])
    await h.click(msg, buttons(h, msg)["⏸ 그만하기"])
    assert "다시 보기</b>를 멈췄어요 (1/2)" in msg.text
    await h.click(msg, buttons(h, msg)["▶ 이어서 하기"])
    assert "이어서 시작해요 (1/2 완료)" in msg.text and "2/2" in msg.text and "계 1:2" in msg.text


async def test_retry_from_bookmark_exam(h, monkeypatch):
    for ref in ("계 1:3", "계 1:4"):
        h.repo.marks[(h.sid, h.vid[ref])] = {"space_id": h.sid, "verse_id": h.vid[ref],
                                             "bookmarked": True, "auto": False, "fails": 0, "streak": 0}
    msg = await h.say("/rv 시험 북마크", handler=recite_handlers.cmd_recite, args=["시험", "북마크"])
    await grade_all(h, msg, ["🔸 조금 틀림", "✅ 완벽"])
    await h.click(msg, buttons(h, msg)["🔁 틀린 구절만 다시 (1)"])
    assert "틀린 구절 다시 보기</b> · 1/1" in msg.text and "계 1:3" in msg.text
    await grade_all(h, msg, ["✅ 완벽"])
    assert "틀린 구절 다시 보기 결과" in msg.text and "⭐ 북마크만 시험" in buttons(h, msg)
