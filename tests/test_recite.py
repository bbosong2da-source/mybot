import datetime as dt
import random
from types import SimpleNamespace as NS

import pytest

from bot import dates, handlers, jobs, quiz_handlers, recite_handlers
from bot.recite import (MAX_REVIEWS, apply_grade, assign_slot, blanks, build_queue, chapter_board,
                        chapter_icon, choseong, exam_card_update, exam_summary, expected_finish,
                        grade_typing, parse_recite_text, toggle_mark, update_mark)
from test_flow import FakeMessage, Harness
from test_quiz import ADMIN

NOV7 = dt.date(2026, 11, 7)
NOV8 = dt.date(2026, 11, 8)
COURSE_TXT = """# 요한계시록
계 1:1 / 예수 그리스도의 계시라 이는 하나님이 그에게 주사 반드시 속히 일어날 일들을
계 1:2 / 요한은 하나님의 말씀과 예수 그리스도의 증거 곧 자기가 본 것을 다 증언하였느니라
1:3 읽는 자와 듣는 자들과 그 가운데에 기록한 것을 지키는 자는 복이 있나니 때가 가까움이라
계 2:1 / 에베소 교회의 사자에게 편지하라
계 1:4 / 요한은 아시아에 있는 일곱 교회에 편지하노니
"""


# --- 순수 로직 ----------------------------------------------------------------
def test_parse_course_orders_by_chapter_and_verse():
    p = parse_recite_text(COURSE_TXT + "잘못된 줄\n계 3:1 /  \n")
    assert [r["ref"] for r in p.rows] == ["계 1:1", "계 1:2", "계 1:3", "계 1:4", "계 2:1"]
    assert [r["seq"] for r in p.rows] == [1, 2, 3, 4, 5]
    assert p.rows[2]["body"].startswith("읽는 자와")   # '/' 없이, 책 이름 없이도 됨
    assert len(p.errors) == 2


def test_choseong_and_blanks():
    assert choseong("하나님이 세상을, 이처럼!") == "ㅎㄴㄴㅇ ㅅㅅㅇ, ㅇㅊㄹ!"
    text = "예수 그리스도의 계시라 이는 하나님이 그에게 주사"
    b = blanks(text, seed=1)
    assert b == blanks(text, seed=1)                  # 같은 구절은 늘 같은 자리
    assert b.count("＿") > 0 and len(b.split()) == len(text.split())
    assert sum("＿" in w for w in b.split()) == 3     # 7단어 중 세 개 중 하나꼴


def _verses(n=30):
    return [{"id": 100 + i, "seq": i, "chapter": 1 + (i - 1) // 10, "ref": f"계 x:{i}", "body": "b"}
            for i in range(1, n + 1)]


def test_build_queue_new_then_due_reviews():
    vs, day = _verses(), NOV7
    cards = [{"verse_id": 100 + i, "box": i % 3, "due_date": day - dt.timedelta(days=i % 4)}
             for i in range(1, 21)]
    cards.append({"verse_id": 125, "box": 0, "due_date": day + dt.timedelta(days=1)})   # 아직 아님
    q = build_queue(day, 2, vs, cards, random.Random(0))
    # 새 구절: 안 외운 절 중 가장 앞 (25절은 이미 외워서 건너뜀)
    assert [(x["seq"], x["k"]) for x in q[:2]] == [(21, "new"), (22, "new")]
    q3 = build_queue(day, 5, vs, cards, random.Random(0))
    assert [x["seq"] for x in q3 if x["k"] == "new"] == [21, 22, 23, 24, 26]
    reviews = q[2:]
    assert len(reviews) == MAX_REVIEWS                # 밀린 복습은 하루 최대 15개
    assert 25 not in [x["seq"] for x in reviews]
    assert {x["k"] for x in reviews} <= {"recall", "chain"}
    assert all(x["g"] is None and x["s"] is None for x in q)
    # 북마크한 구절은 복습 상한 안에 먼저 들어감
    late = {20, 19, 18}
    qb = build_queue(day, 0, vs, cards, random.Random(0), bookmarked={100 + i for i in late})
    assert {x["seq"] for x in qb[:3]} == late
    # 1절은 앞 구절이 없으니 이어 말하기가 될 수 없음
    q = build_queue(day, 1, vs, [{"verse_id": 101, "box": 0, "due_date": day}], random.Random(3))
    assert q[0]["seq"] == 2 and q[1]["k"] == "recall"
    # 끝까지 다 배우면 새 구절 없음
    every = [{"verse_id": v["id"], "box": 0, "due_date": day + dt.timedelta(days=9)} for v in vs]
    assert build_queue(day, 3, vs, every, random.Random(0)) == []


def test_apply_grade_intervals():
    d = NOV7
    new = apply_grade(None, 2, d)
    assert (new["box"], new["due_date"]) == (0, d + dt.timedelta(days=1))
    up = apply_grade({"box": 2}, 2, d)
    assert (up["box"], up["due_date"]) == (3, d + dt.timedelta(days=15))
    top = apply_grade({"box": 5}, 2, d)
    assert top["due_date"] == d + dt.timedelta(days=60)
    keep = apply_grade({"box": 2}, 1, d)
    assert (keep["box"], keep["due_date"]) == (2, d + dt.timedelta(days=7))
    reset = apply_grade({"box": 4}, 0, d)
    assert (reset["box"], reset["due_date"]) == (0, d + dt.timedelta(days=1))


def test_assign_slot_spreads_cards():
    q = [{"g": None, "s": None} for _ in range(7)]
    sizes = []
    for hour in range(18, 23):
        batch = assign_slot(q, hour, 22)
        sizes.append(len(batch))
        for i in batch:
            q[i]["g"] = 2
    assert sizes == [2, 2, 1, 1, 1] and sum(sizes) == 7
    q = [{"g": None, "s": None} for _ in range(7)]
    assert len(assign_slot(q, 21, 22)) == 4           # 늦게 시작하면 남은 시간대에 몰아서


def test_grade_typing():
    ans = "예수 그리스도의 계시라 이는 하나님이 그에게 주사"
    r = grade_typing("예수그리스도의 계시라, 이는 하나님이 그에게 주사.", ans)
    assert r.score == 100 and r.grade == 2 and "<u>" not in r.diff_html
    r = grade_typing("예수 그리스도의 계시라 이는 하나님이 주사", ans)
    assert r.grade == 1 and "<b><u>그에게</u></b>" in r.diff_html
    long_ans = ans + " 반드시 속히 일어날 일들을 그의 천사를 그 종 요한에게 보내어 알게 하신 것이라"
    r = grade_typing(long_ans.replace(" 속히", ""), long_ans)
    assert r.score > 95 and r.grade == 1                # 한 단어라도 빠지면 '완벽' 아님
    r = grade_typing(ans + " 그리고 덧붙인 말이 아주 많이 있습니다", ans)
    assert r.grade != 2
    r = grade_typing("하나님", ans)
    assert r.grade == 0
    r = grade_typing("예수 그리스도의 계시라 이는 하나님이 그에게 주시", ans)   # 한 글자 틀림
    assert "<b><u>주사</u></b>" in r.diff_html and r.diff_html.count("<u>") == 1
    assert grade_typing("<script>", "a<b>").diff_html == "<b><u>a&lt;b&gt;</u></b>"


def test_chapter_board_and_finish():
    vs = _verses(20)
    cards = [{"verse_id": 100 + i, "box": 3} for i in range(1, 11)]
    cards += [{"verse_id": 111, "box": 0}]
    board = chapter_board(vs, cards)
    assert board == [(1, 10, 10, 10), (2, 10, 1, 0)]
    assert chapter_icon(*board[0][1:]) == "🏅" and chapter_icon(*board[1][1:]) == "📜"
    assert chapter_icon(5, 5, 2) == "✅" and chapter_icon(5, 0, 0) == "✉️"
    assert expected_finish(0, 404, 2, NOV7) == NOV7 + dt.timedelta(days=201)
    assert expected_finish(404, 404, 2, NOV7) is None
    assert chapter_icon(5, 1, 0, passed=True) == "🏅"


def test_known_and_bookmark_intervals():
    d = NOV7
    assert apply_grade(None, 2, d, known=True)["due_date"] == d + dt.timedelta(days=7)
    assert apply_grade(None, 1, d, known=True)["due_date"] == d + dt.timedelta(days=1)
    assert apply_grade({"box": 4}, 2, d, bookmarked=True)["due_date"] == d + dt.timedelta(days=3)
    assert exam_card_update(None, 0, d) is None              # 안 외운 절 '못 외움' → 등록 안 함
    assert exam_card_update(None, 2, d)["box"] == 2
    assert exam_card_update({"box": 3}, 0, d)["box"] == 0


def test_bookmark_rules():
    m, ev = update_mark(None, 0)
    assert not m["bookmarked"] and ev is None
    m, ev = update_mark(m, 1)
    m, ev = update_mark(m, 0)
    assert m["bookmarked"] and m["auto"] and ev == "on"        # 못 외움 2번 → 자동 북마크
    for _ in range(2):
        m, ev = update_mark(m, 2)
        assert m["bookmarked"]
    m, ev = update_mark(m, 1)                                   # 연속이 끊김
    for _ in range(3):
        m, ev = update_mark(m, 2)
    assert not m["bookmarked"] and ev == "off" and m["fails"] == 0
    m = toggle_mark(None)
    assert m["bookmarked"] and not m["auto"]
    assert not toggle_mark(m)["bookmarked"]


def test_exam_summary():
    items = [{"g": 2}] * 9 + [{"g": 1}]
    s = exam_summary(items)
    assert s.finished and s.passed and (s.perfect, s.partial) == (9, 1)
    assert not exam_summary([{"g": 2}] * 8 + [{"g": 0}] * 2).passed
    assert not exam_summary([{"g": 2}] * 9 + [{"g": None}]).passed


# --- 사용 흐름 ----------------------------------------------------------------
def at(monkeypatch, day, hour, minute=0):
    monkeypatch.setattr(dates, "today", lambda: day)
    monkeypatch.setattr(dates, "now", lambda: dt.datetime.combine(day, dt.time(hour, minute)))


@pytest.fixture
async def h(monkeypatch):
    recite_handlers.rng.seed(5)
    at(monkeypatch, NOV7, 9)
    h = Harness()
    msg = await h.say("/rva\n" + COURSE_TXT, user=ADMIN, handler=recite_handlers.cmd_recite_add)
    assert "전체 5절" in msg.text and "1장~2장" in msg.text
    return h


def buttons(h, msg):
    return dict((t, cb) for t, cb in h.buttons(msg))


async def test_admin_upload_with_caption_goes_to_recite(monkeypatch):
    at(monkeypatch, NOV7, 9)
    h = Harness()
    data = bytearray(COURSE_TXT.encode("utf-8"))
    async def get_file():
        async def download():
            return data
        return NS(download_as_bytearray=download)
    msg = FakeMessage(h.bot, h.chat, None, user=ADMIN)
    msg.document = NS(file_name="계시록.txt", file_size=len(data), get_file=get_file)
    msg.caption = "암송 본문"
    await quiz_handlers.on_document(h.update(msg, user=ADMIN), h.ctx())
    assert "암송 본문 저장 완료" in h.bot.last.text
    assert len(h.repo.rverses) == 5 and not h.repo.verses     # 성구 퀴즈에는 안 들어감

    msg = await h.say("/rva\n계 1:1 / 고친 본문", user=ADMIN, handler=recite_handlers.cmd_recite_add)
    assert "새로 추가 0절 · 수정 1절" in msg.text
    assert next(v for v in h.repo.rverses.values() if v["ref"] == "계 1:1")["body"] == "고친 본문"


async def test_start_and_full_evening(h, monkeypatch):
    msg = await h.say("/rv", handler=recite_handlers.cmd_recite)
    assert "하루에 몇 절씩" in msg.text
    await h.click(msg, buttons(h, msg)["하루 2절"])
    assert "암송을 시작했어요" in msg.text and "진도 <b>0/5절</b>" in msg.text
    space_id = next(iter(h.repo.members))

    at(monkeypatch, NOV7, 17)
    before = len(h.bot.sent)
    await jobs.minute_job(h.ctx())
    assert len(h.bot.sent) == before                          # 18시 전

    at(monkeypatch, NOV7, 18)
    await jobs.minute_job(h.ctx())
    card = h.bot.last
    assert "🆕 새 구절" in card.text and "계 1:1" in card.text and "1/4" in card.text
    at(monkeypatch, NOV7, 18, 1)
    await jobs.minute_job(h.ctx())
    assert h.bot.last is card                                 # 같은 시간 중복 발송 없음

    b = buttons(h, card)
    await h.click(card, b["다음 단계 ▶"])
    assert "2/4" in card.text and "＿" in card.text
    await h.click(card, buttons(h, card)["다음 단계 ▶"])
    assert "3/4" in card.text and "ㅇㅅ ㄱㄹㅅㄷㅇ" in card.text
    await h.click(card, buttons(h, card)["다음 단계 ▶"])
    assert "암송해 보세요" in card.text
    await h.click(card, buttons(h, card)["👀 정답 보기"])
    assert "얼마나 정확했나요" in card.text
    q = await h.click(card, buttons(h, card)["✅ 완벽"])
    assert q.answers == ["✅ 완벽!"]
    v1 = next(v["id"] for v in h.repo.rverses.values() if v["seq"] == 1)
    assert h.repo.cards[(space_id, v1)]["due_date"] == NOV8
    assert h.repo.members[space_id]["next_seq"] == 2
    assert "이번 시간 카드를 마쳤어요" in card.text          # 18시엔 1장 (2장을 5시간에 나눔)

    lst = await h.say("/l", handler=handlers.cmd_list)
    assert any("📖 계시록 암송 1/2" in t for t, _ in h.buttons(lst))

    await h.click(card, buttons(h, card)["▶ 지금 더 하기"])
    assert "계 1:2" in card.text
    for label in ("다음 단계 ▶", "다음 단계 ▶", "다음 단계 ▶", "👀 정답 보기", "❌ 못 외움"):
        await h.click(card, buttons(h, card)[label])
    assert "오늘 암송 완료" in card.text
    assert h.repo.members[space_id]["next_seq"] == 3

    at(monkeypatch, NOV7, 19)
    before = len(h.bot.sent)
    await jobs.minute_job(h.ctx())
    assert len(h.bot.sent) == before                          # 다 했으면 더 안 보냄

    lst = await h.say("/l", handler=handlers.cmd_list)
    assert any("🍋 📖 계시록 암송 2/2" in t for t, _ in h.buttons(lst))

    # 다음 날: 새 구절 2개 + 어제 배운 2개 복습
    at(monkeypatch, NOV8, 18)
    await jobs.minute_job(h.ctx())
    rec = h.repo.rdays[(space_id, NOV8)]
    assert [(x["seq"], x["k"]) for x in rec["queue"][:2]] == [(3, "new"), (4, "new")]
    assert sorted(x["seq"] for x in rec["queue"][2:]) == [1, 2]
    assert next(x for x in rec["queue"] if x["seq"] == 1)["k"] == "recall"


async def test_typing_check(h, monkeypatch):
    msg = await h.say("/rv 1", handler=recite_handlers.cmd_recite, args=["1"])
    assert "암송을 시작했어요" in msg.text
    at(monkeypatch, NOV7, 22)
    await jobs.minute_job(h.ctx())
    card = next(m for m in h.bot.sent if "계시록 암송</b> ·" in m.text)   # 22시엔 밤 점검도 같이 옴
    await h.click(card, buttons(h, card)["다음 단계 ▶"])
    await h.click(card, buttons(h, card)["다음 단계 ▶"])
    await h.click(card, buttons(h, card)["다음 단계 ▶"])
    await h.click(card, buttons(h, card)["⌨️ 타이핑으로 확인"])
    prompt = h.bot.last
    assert "#V20261107-0-" in prompt.text

    reply = await h.say("예수 그리스도의 계시라 이는 하나님이 그에게 주사 반드시 일어날 일들을", reply_to=prompt)
    assert "정확도" in reply.text and "조금 틀림" in reply.text and "<u>속히</u>" in reply.text
    assert not h.repo.tasks                                   # 답장은 할 일로 등록되지 않음
    assert "오늘 암송 완료" in card.text                      # 원래 카드 메시지가 다음 상태로
    reply = await h.say("다시 입력", reply_to=prompt)
    assert "이미 채점한 카드" in reply.text


async def test_grace_after_midnight_and_expiry(h, monkeypatch):
    await h.say("/rv 1", handler=recite_handlers.cmd_recite, args=["1"])
    at(monkeypatch, NOV7, 22)
    await jobs.minute_job(h.ctx())
    card = next(m for m in h.bot.sent if "계시록 암송</b> ·" in m.text)
    space_id = next(iter(h.repo.members))

    at(monkeypatch, NOV8, 1)                                  # 자정 넘어 새벽 1시
    await h.click(card, buttons(h, card)["다음 단계 ▶"])
    for label in ("다음 단계 ▶", "다음 단계 ▶", "👀 정답 보기", "✅ 완벽"):
        await h.click(card, buttons(h, card)[label])
    v1 = next(v["id"] for v in h.repo.rverses.values() if v["seq"] == 1)
    assert h.repo.cards[(space_id, v1)]["learned_on"] == NOV7  # 전날 기록
    assert "오늘 암송 완료" in card.text

    at(monkeypatch, NOV7, 22)
    await h.say("/rv", handler=recite_handlers.cmd_recite)
    rec = h.repo.rdays[(space_id, NOV7)]
    rec["queue"].append({"v": v1, "seq": 1, "k": "recall", "g": None, "s": 22})
    at(monkeypatch, NOV8, 4)
    q = await h.click(card, "rc:20261107:1:a")
    assert "지난 카드" in q.answers[0] and card.reply_markup is None


async def test_pause_hours_and_admin_status(h, monkeypatch):
    msg = await h.say("/rv 2", handler=recite_handlers.cmd_recite, args=["2"])
    msg = await h.say("/rv 19-21", handler=recite_handlers.cmd_recite, args=["19-21"])
    assert "19~21시" in msg.text
    msg = await h.say("/rv 25-3", handler=recite_handlers.cmd_recite, args=["25-3"])
    assert "0~23" in msg.text

    board = await h.say("/rv", handler=recite_handlers.cmd_recite)
    await h.click(board, buttons(h, board)["하루 3절"])
    assert "하루 새 구절 <b>3절</b>" in board.text
    await h.click(board, buttons(h, board)["⏸ 쉬기"])
    assert "쉬는 중" in board.text

    at(monkeypatch, NOV7, 19)
    before = len(h.bot.sent)
    await jobs.minute_job(h.ctx())
    assert len(h.bot.sent) == before                          # 쉬는 중엔 카드 없음
    lst = await h.say("/l", handler=handlers.cmd_list)
    assert not any("계시록 암송" in t for t, _ in h.buttons(lst))

    await h.click(board, buttons(h, board)["▶ 다시 시작"])
    at(monkeypatch, NOV7, 20)
    await jobs.minute_job(h.ctx())
    assert "계시록 암송" in h.bot.last.text

    status = await h.say("/rvs", user=ADMIN, handler=recite_handlers.cmd_recite_status)
    assert "계시록 암송 현황" in status.text and "0/5절" in status.text and "하루 3절" in status.text
    denied = await h.say("/rvs", handler=recite_handlers.cmd_recite_status)
    assert "관리자만" in denied.text


async def test_off_space_gets_no_cards(h, monkeypatch):
    await h.say("/rv 1", handler=recite_handlers.cmd_recite, args=["1"])
    await h.say("/off", handler=handlers.cmd_off)
    at(monkeypatch, NOV7, 18)
    before = len(h.bot.sent)
    await jobs.minute_job(h.ctx())
    assert len(h.bot.sent) == before
