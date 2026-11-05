"""가짜 텔레그램 객체 + MemoryRepo로 실제 사용 흐름을 끝까지 돌려 본다."""
import datetime as dt
from types import SimpleNamespace as NS

import pytest

from bot import admin as admin_mod
from bot import callbacks, dates, handlers, jobs
from bot.config import ADMIN_ID
from bot.storage import MemoryRepo

TODAY = dt.date(2026, 11, 5)  # 목


class FakeMessage:
    _ids = iter(range(1000, 100000))

    def __init__(self, bot, chat, text, thread=None, user=None, reply_to=None, markup=None):
        self.bot, self.chat, self.text = bot, chat, text
        self.message_thread_id = thread
        self.is_topic_message = bool(thread)
        self.from_user, self.reply_to_message = user, reply_to
        self.reply_markup = markup
        self.message_id = next(self._ids)

    async def reply_text(self, text, reply_markup=None, **kw):
        return await self.bot.send_message(self.chat.id, text, message_thread_id=self.message_thread_id,
                                           reply_markup=reply_markup)


class FakeBot:
    id = 999

    def __init__(self):
        self.sent = []
        self.user = NS(id=self.id, first_name="bot")

    async def send_message(self, chat_id, text, message_thread_id=None, reply_markup=None, **kw):
        m = FakeMessage(self, NS(id=chat_id, type="private"), text, message_thread_id,
                        user=self.user, markup=reply_markup)
        self.sent.append(m)
        return m

    @property
    def last(self):
        return self.sent[-1]


class FakeQuery:
    def __init__(self, data, message, user):
        self.data, self.message, self.from_user = data, message, user
        self.answers = []

    async def answer(self, text=None, show_alert=False):
        self.answers.append(text)

    async def edit_message_text(self, text, reply_markup=None):
        self.message.text, self.message.reply_markup = text, reply_markup


class Harness:
    def __init__(self, chat_id=1, user_id=1, thread=None, chat_type="private"):
        self.bot = FakeBot()
        self.repo = MemoryRepo()
        self.bot_data = {"repo": self.repo}
        self.chat = NS(id=chat_id, type=chat_type, title="스터디 그룹")
        self.user = NS(id=user_id, first_name="다은", full_name="김다은")
        self.thread = thread

    def ctx(self, args=None):
        return NS(application=NS(bot_data=self.bot_data), bot_data=self.bot_data, bot=self.bot, args=args or [])

    def update(self, msg=None, query=None, user=None):
        return NS(effective_chat=self.chat, effective_message=msg or (query.message if query else None),
                  effective_user=user or self.user, callback_query=query)

    async def say(self, text, reply_to=None, user=None, handler=None, args=None):
        msg = FakeMessage(self.bot, self.chat, text, self.thread, user or self.user, reply_to)
        await (handler or handlers.handle_message)(self.update(msg, user=user), self.ctx(args))
        return self.bot.last

    async def click(self, message, data):
        q = FakeQuery(data, message, self.user)
        await callbacks.on_button(self.update(query=q), self.ctx())
        return q

    @staticmethod
    def buttons(message):
        if not message.reply_markup:
            return []
        return [(b.text, b.callback_data) for row in message.reply_markup.inline_keyboard for b in row]

    def button(self, message, contains):
        return next(cb for text, cb in self.buttons(message) if contains in text)


@pytest.fixture
def h(monkeypatch):
    monkeypatch.setattr(dates, "today", lambda: TODAY)
    return Harness()


async def test_add_tasks_with_dates_and_categories(h):
    msg = await h.say("보고서 작성\n[논문]\n내일 초안 작성\n11/01 회의\n[운동] 스쿼트")
    tasks = sorted(h.repo.tasks.values(), key=lambda t: t["id"])
    assert [(t["title"], t["category"], t["due_date"]) for t in tasks] == [
        ("보고서 작성", "일반", TODAY),
        ("초안 작성", "논문", TODAY + dt.timedelta(days=1)),
        ("스쿼트", "운동", TODAY),
    ]
    assert "3개의 계획" in msg.text and "이미 지난 날짜" in msg.text
    assert "📅 11/6(금) 초안 작성" in msg.text
    assert any("오늘 할 일로" in t for t, _ in h.buttons(msg))

    # [오늘 할 일로] -> 원래 입력 그대로 오늘 할 일
    await h.click(msg, h.button(msg, "오늘 할 일로"))
    t = h.repo.tasks[tasks[1]["id"]]
    assert (t["title"], t["due_date"]) == ("내일 초안 작성", TODAY)


async def test_html_special_chars_are_escaped(h):
    msg = await h.say("내일 a_b *c* <script> & `x`")   # 예정 항목은 본문에 제목이 나온다
    assert "a_b *c* &lt;script&gt; &amp; `x`" in msg.text


async def test_toggle_and_stale_button(h):
    msg = await h.say("보고서")
    cb = h.button(msg, "보고서")
    await h.click(msg, cb)
    task = next(iter(h.repo.tasks.values()))
    assert task["done_at"] == TODAY
    assert "ALL CLEAR" in msg.text

    await h.click(msg, cb)
    assert h.repo.tasks[task["id"]]["done_at"] is None

    # 다른 항목을 지워도 버튼은 id로 가리키므로 엉뚱한 항목이 바뀌지 않는다
    await h.repo.delete_task(task["space_id"], task["id"])
    q = await h.click(msg, cb)
    assert q.answers == ["이미 삭제된 할 일이에요."]


async def test_overdue_and_night_actions(h, monkeypatch):
    await h.say("보고서\n청소\n독서")
    monkeypatch.setattr(dates, "today", lambda: TODAY + dt.timedelta(days=1))  # 다음 날
    space = (await h.repo.all_spaces())[0]
    night = await h.bot.send_message(1, "x")
    await h.click(night, "l:n")
    assert "밤 점검" in night.text
    assert any("🔥D+1 보고서" in t for t, _ in h.buttons(night))

    ids = {t["title"]: t["id"] for t in h.repo.tasks.values()}
    await h.click(night, f"t:n:{ids['보고서']}")
    await h.click(night, f"n:t:{ids['청소']}")
    await h.click(night, f"n:x:{ids['독서']}")
    assert h.repo.tasks[ids["보고서"]]["done_at"] == TODAY + dt.timedelta(days=1)
    assert h.repo.tasks[ids["청소"]]["due_date"] == TODAY + dt.timedelta(days=2)
    assert ids["독서"] not in h.repo.tasks
    assert "모두 끝냈어요" in night.text and space


async def test_edit_rename_via_reply(h):
    list_msg = await h.say("보고서 초안")
    await h.click(list_msg, "e")
    assert "할 일 편집" in list_msg.text
    await h.click(list_msg, h.button(list_msg, "보고서 초안"))  # ✏️ 이름 변경
    prompt = h.bot.last
    assert "답장" in prompt.text and "#T" in prompt.text

    await h.say("보고서 최종본", reply_to=prompt)
    assert [t["title"] for t in h.repo.tasks.values()] == ["보고서 최종본"]
    assert len(h.repo.tasks) == 1   # 답장이 새 할 일로 추가되지 않음


async def test_routines(h):
    msg = await h.say("/r 영단어 30개\n월수금 운동", handler=handlers.cmd_routine)
    assert "루틴 2개" in msg.text
    rs = sorted(h.repo.routines_.values(), key=lambda r: r["id"])
    assert [(r["title"], r["days"]) for r in rs] == [("영단어 30개", [0, 1, 2, 3, 4, 5, 6]), ("운동", [1, 3, 5])]

    lst = await h.say("/l", handler=handlers.cmd_list)
    labels = [t for t, _ in h.buttons(lst)]
    assert any("영단어" in t for t in labels) and not any("운동" in t for t in labels)  # 목요일

    await h.click(lst, h.button(lst, "영단어"))
    assert (rs[0]["id"], TODAY) in h.repo.logs

    # 요일 토글: 운동에 목요일 추가 -> 오늘 목록에 나타남
    mgr = await h.say("/r", handler=handlers.cmd_routine)
    await h.click(mgr, f"rm:{rs[1]['id']}")
    await h.click(mgr, f"rd:{rs[1]['id']}:4")
    assert h.repo.routines_[rs[1]["id"]]["days"] == [1, 3, 4, 5]

    # 마지막 요일은 끌 수 없음
    await h.click(mgr, f"rm:{rs[0]['id']}")
    for day in range(6):
        await h.click(mgr, f"rd:{rs[0]['id']}:{day}")
    q = await h.click(mgr, f"rd:{rs[0]['id']}:6")
    assert q.answers == ["최소 하루는 남겨 주세요."]

    # 삭제는 확인 후
    await h.click(mgr, f"rx:{rs[1]['id']}")
    assert "삭제할까요" in mgr.text
    await h.click(mgr, f"ry:{rs[1]['id']}")
    assert rs[1]["id"] not in h.repo.routines_


async def test_off_blocks_task_creation(h):
    await h.say("/off", handler=handlers.cmd_off)
    await h.say("이건 광고 메시지")
    assert not h.repo.tasks
    await h.say("/on", handler=handlers.cmd_on)
    await h.say("보고서")
    assert len(h.repo.tasks) == 1


async def test_question_and_admin_answer(h):
    await h.say("질문: 주간 리포트는 언제 오나요?")
    to_admin = next(m for m in h.bot.sent if m.chat.id == ADMIN_ID)
    assert "#S" in to_admin.text and not h.repo.tasks

    # 관리자가 질문 메시지에 답장
    admin = NS(id=ADMIN_ID, first_name="관리자", full_name="관리자")
    admin_chat = NS(id=ADMIN_ID, type="private", title=None)
    msg = FakeMessage(h.bot, admin_chat, "토요일 밤에 와요!", user=admin, reply_to=to_admin)
    upd = NS(effective_chat=admin_chat, effective_message=msg, effective_user=admin, callback_query=None)
    await handlers.handle_message(upd, h.ctx())
    answer = next(m for m in h.bot.sent if "관리자 답변" in m.text)
    assert answer.chat.id == h.chat.id and "토요일 밤에 와요!" in answer.text
    assert not any(t["space_id"] for t in h.repo.tasks.values())   # 관리자 답장이 할 일이 되지 않음


async def test_broadcast(h):
    await h.say("보고서")                                    # 사용자 공간 생성
    ad_space = await h.repo.create_space({"chat_id": 50, "thread_id": 7, "name": "광고방"})
    off_space = await h.repo.create_space({"chat_id": 51, "thread_id": 0, "name": "철수"})
    await h.repo.update_space(off_space["id"], {"disabled": True})

    admin = NS(id=ADMIN_ID, first_name="관리자", full_name="관리자")
    admin_chat = NS(id=ADMIN_ID, type="private", title=None)
    msg = FakeMessage(h.bot, admin_chat, "/bc\n[1주차]\n질문 작성\n공지 숙지", user=admin)
    upd = NS(effective_chat=admin_chat, effective_message=msg, effective_user=admin, callback_query=None)
    await admin_mod.cmd_broadcast(upd, h.ctx())

    notice = next(m for m in h.bot.sent if "1주차" in m.text and m.chat.id == h.chat.id)
    assert "보냄: <b>1</b>곳" in h.bot.last.text
    assert not any(m.chat.id in (50, 51) for m in h.bot.sent)

    await h.click(notice, notice.reply_markup.inline_keyboard[0][0].callback_data)
    await h.click(notice, notice.reply_markup.inline_keyboard[1][0].callback_data)
    assert "모든 과제를 완수" in notice.text

    msg2 = FakeMessage(h.bot, admin_chat, "/bcr", user=admin)
    upd2 = NS(effective_chat=admin_chat, effective_message=msg2, effective_user=admin, callback_query=None)
    await admin_mod.cmd_broadcast_report(upd2, h.ctx([]))
    assert "전체 완료: 1/1곳" in h.bot.last.text
    assert ad_space


async def test_non_admin_cannot_broadcast(h):
    msg = await h.say("/bc\n과제", handler=admin_mod.cmd_broadcast)
    assert "관리자만" in msg.text


async def test_minute_job_night_and_saturday_weekly(h, monkeypatch):
    await h.say("보고서")
    await h.say("/r 영단어", handler=handlers.cmd_routine)
    sat = dt.date(2026, 11, 7)
    monkeypatch.setattr(dates, "today", lambda: sat)
    monkeypatch.setattr(dates, "now", lambda: dt.datetime(2026, 11, 7, 22, 0))
    before = len(h.bot.sent)
    await jobs.minute_job(h.ctx())
    new = h.bot.sent[before:]
    assert len(new) == 2 and "밤 점검" in new[0].text and "주간 리포트" in new[1].text
    assert "11/1(일) ~ 11/7(토)" in new[1].text

    await jobs.minute_job(h.ctx())               # 같은 분에 두 번 돌아도 중복 전송 없음
    assert len(h.bot.sent) == before + 2


async def test_minute_job_weekly_when_notify_off(h, monkeypatch):
    await h.say("보고서")
    await h.say("/t off", handler=handlers.cmd_time, args=["off"])
    monkeypatch.setattr(dates, "today", lambda: dt.date(2026, 11, 6))
    monkeypatch.setattr(dates, "now", lambda: dt.datetime(2026, 11, 6, 22, 0))   # 금요일
    before = len(h.bot.sent)
    await jobs.minute_job(h.ctx())
    assert len(h.bot.sent) == before                                              # 꺼져 있으면 밤 점검 없음
    monkeypatch.setattr(dates, "today", lambda: dt.date(2026, 11, 7))
    monkeypatch.setattr(dates, "now", lambda: dt.datetime(2026, 11, 7, 22, 0))   # 토요일
    await jobs.minute_job(h.ctx())
    assert "주간 리포트" in h.bot.last.text


async def test_topic_spaces_are_separate(monkeypatch):
    monkeypatch.setattr(dates, "today", lambda: TODAY)
    h1 = Harness(chat_id=-100, chat_type="supergroup", thread=11)
    await h1.say("A 할 일")
    h1.thread = 12
    await h1.say("B 할 일")
    spaces = await h1.repo.all_spaces()
    assert [(s["chat_id"], s["thread_id"]) for s in spaces] == [(-100, 11), (-100, 12)]
    assert h1.bot.sent[-1].message_thread_id == 12
