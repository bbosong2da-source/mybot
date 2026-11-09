"""계시록 암송 코스: /rv 진도판·설정, 관리자 본문 등록(/rva, 설명에 '암송'인 .txt), /rvs 현황,
카드 버튼, 타이핑 채점, 시간대별 카드 발송.

callback_data
  rv:s:{n}  시작(하루 n절)   rv:n:{n}  하루 개수 변경   rv:p  쉬기/다시   rc:i  루틴 안내
  rc:{YYYYMMDD}:{idx}:{act}   카드 동작 — act: 1·2·3·4 단계, c 이어 말하기, a 정답 보기,
                              g0·g1·g2 채점, t 타이핑 / rc:{YYYYMMDD}:{hour}:m 다음 카드 더 하기
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import random
import time
from html import escape

from telegram import ForceReply
from telegram import InlineKeyboardButton as Btn
from telegram import InlineKeyboardMarkup, Update

from . import dates
from .common import chunk_text, command_body, ensure_space, repo, safe_edit, send_to_space
from .config import ADMIN_ID
from .quiz import parse_hours, quiz_streak
from .recite import (COURSE, DAILY_CHOICES, DEFAULT_HOURS, GRADE_LABELS, ReciteStatus,
                     apply_grade, assign_slot, blanks, build_queue, chapter_board,
                     chapter_icon, expected_finish, grade_typing, parse_recite_text,
                     pending, queue_counts, toggle_mark, update_mark)

log = logging.getLogger(__name__)
rng = random.Random()
CATCH_UP_MINUTES = 10

FORMAT_HELP = (
    "한 줄에 한 절씩 적어 주세요.\n"
    "<pre>계 1:1 / 예수 그리스도의 계시라 이는 하나님이 …\n"
    "계 1:2 / 요한은 하나님의 말씀과 …</pre>\n"
    "• <code>/</code>는 없어도 되고, 책 이름을 빼고 <code>1:1 본문</code>만 써도 돼요.\n"
    "• 같은 절을 다시 올리면 새 본문으로 바뀌어요 (진도는 그대로).\n"
    "• 파일로 보낼 때는 파일 <b>설명 칸에 '암송'</b>이라고 적어 주세요."
)


_VERSE_CACHE: dict[tuple[int, str], tuple[float, list[dict]]] = {}
CACHE_SECONDS = 600


async def course_verses(r, course: str = COURSE) -> list[dict]:
    """암송 본문(최대 수백 절)은 자주 바뀌지 않으니 10분간 기억해 두고 쓴다."""
    key = (id(r), course)
    hit = _VERSE_CACHE.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    verses = await r.recite_verses(course)
    _VERSE_CACHE[key] = (time.monotonic(), verses)
    return verses


async def load_marks(r, space_id: int) -> dict[int, dict]:
    try:
        return await r.recite_marks(space_id)
    except Exception as e:   # schema_recite_exam.sql 실행 전
        log.info("북마크 불러오기 실패: %s", e)
        return {}


async def save_mark(r, space_id: int, verse_id: int, mark: dict) -> None:
    try:
        await r.save_mark({"space_id": space_id, "verse_id": verse_id,
                           **{k: mark[k] for k in ("bookmarked", "auto", "fails", "streak")}})
    except Exception as e:
        log.info("북마크 저장 실패: %s", e)


MARK_TOAST = {"on": "⭐ 자주 틀려서 북마크했어요", "off": "⭐ 세 번 연속 완벽! 북마크를 해제했어요"}


def _daykey(day: dt.date) -> str:
    return day.strftime("%Y%m%d")


def _parse_daykey(key: str) -> dt.date:
    return dt.datetime.strptime(key, "%Y%m%d").date()


def _hours(member: dict) -> tuple[int, int]:
    return parse_hours(member.get("hours") or DEFAULT_HOURS) or parse_hours(DEFAULT_HOURS)


def _is_admin(update: Update) -> bool:
    return bool(update.effective_user and update.effective_user.id == ADMIN_ID)


# ---------------------------------------------------------------------------
# 하루 카드 목록
# ---------------------------------------------------------------------------
async def ensure_day(r, space_id: int, member: dict, day: dt.date, verses=None) -> dict:
    rec = await r.get_recite_day(space_id, day)
    if rec:
        return rec
    verses = verses if verses is not None else await course_verses(r, member.get("course", COURSE))
    cards = await r.recite_cards(space_id)
    marks = await load_marks(r, space_id)
    bookmarked = {vid for vid, m in marks.items() if m.get("bookmarked")}
    queue = build_queue(day, member["daily_new"], verses, cards, rng, bookmarked)
    rec = {"space_id": space_id, "recite_date": day, "queue": queue, "sent_hours": []}
    await r.save_recite_day(rec)
    return rec


async def load_recite_status(r, space: dict, today: dt.date) -> ReciteStatus | None:
    """오늘의 루틴으로 보여 줄 암송 상태. 참여하지 않았거나 할 카드가 없으면 None."""
    try:
        member = await r.get_member(space["id"])
        if not member or not member.get("active"):
            return None
        if not await course_verses(r, member.get("course", COURSE)):
            return None
        rec = await ensure_day(r, space["id"], member, today)
        total, done = queue_counts(rec["queue"])
        if not total:
            return None
        since = today - dt.timedelta(days=90)
        history = {}
        for d in await r.recite_days_since(space["id"], since):
            t, n = queue_counts(d["queue"])
            if t:
                history[d["recite_date"]] = (t, n)
        is_done = done == total
        return ReciteStatus(done, total, is_done, quiz_streak(history, today, is_done, since))
    except Exception as e:
        log.warning("암송 상태 불러오기 실패 space=%s: %s", space.get("id"), e)
        return None


# ---------------------------------------------------------------------------
# 카드 화면
# ---------------------------------------------------------------------------
KIND_LABEL = {"new": "🆕 새 구절", "recall": "🔁 복습", "chain": "🔗 이어 말하기"}


def _first_stage(item: dict) -> str:
    return {"new": "1", "recall": "4", "chain": "c"}[item["k"]]


def _cb(day: dt.date, idx: int, act: str) -> str:
    return f"rc:{_daykey(day)}:{idx}:{act}"


def render_card(day: dt.date, queue: list[dict], idx: int, stage: str,
                verse: dict, prev: dict | None, bookmarked: bool = False):
    item = queue[idx]
    total, done = queue_counts(queue)
    star = " ⭐" if bookmarked else ""
    head = f"📖 <b>계시록 암송</b> · {KIND_LABEL[item['k']]}{star} · 오늘 {done}/{total}"
    ref, body = escape(verse["ref"]), escape(verse["body"])
    rows = []
    if stage == "1":
        text = (f"{head}\n\n<b>{ref}</b>\n{body}\n\n<i>1/4 · 소리 내어 세 번 읽어 보세요.</i>"
                f"\n<i>이미 외운 구절이면 ⏭ 바로 시험보기 — 완벽하면 7일 뒤 복습해요.</i>")
        rows = [[Btn("다음 단계 ▶", callback_data=_cb(day, idx, "2")),
                 Btn("⏭ 바로 시험보기", callback_data=_cb(day, idx, "q"))]]
    elif stage == "2":
        text = (f"{head}\n\n<b>{ref}</b>\n{escape(blanks(verse['body'], verse['id']))}"
                f"\n\n<i>2/4 · 빈칸을 채우며 읽어 보세요.</i>")
        rows = [[Btn("다음 단계 ▶", callback_data=_cb(day, idx, "3"))]]
    elif stage == "3":
        text = (f"{head}\n\n<b>{ref}</b>\n{escape(blanks(verse['body'], verse['id'], hide=2))}"
                f"\n\n<i>3/4 · 더 넓어진 빈칸을 채우며 읽어 보세요.</i>")
        rows = [[Btn("다음 단계 ▶", callback_data=_cb(day, idx, "4"))]]
    elif stage in ("4", "c"):
        if stage == "c" and prev:
            text = (f"{head}\n\n<b>{escape(prev['ref'])}</b> {escape(prev['body'])}"
                    f"\n\n👉 이어지는 <b>{ref}</b>을 암송해 보세요.")
        else:
            step = "<i>4/4 · </i>" if item["k"] == "new" else ""
            text = f"{head}\n\n<b>{ref}</b>을 암송해 보세요.\n\n{step}<i>다 떠올렸으면 정답을 확인하세요.</i>"
        rows = [[Btn("👀 정답 보기", callback_data=_cb(day, idx, "a")),
                 Btn("⌨️ 타이핑으로 확인", callback_data=_cb(day, idx, "t"))]]
    else:  # 'a' 정답 보기
        text = f"{head}\n\n<b>{ref}</b>\n{body}\n\n얼마나 정확했나요?"
        rows = [[Btn("✅ 완벽", callback_data=_cb(day, idx, "g2")),
                 Btn("🔸 조금 틀림", callback_data=_cb(day, idx, "g1")),
                 Btn("❌ 못 외움", callback_data=_cb(day, idx, "g0"))],
                [Btn("⭐ 북마크 해제" if bookmarked else "☆ 북마크", callback_data=_cb(day, idx, "b"))]]
    return text, InlineKeyboardMarkup(rows)


def render_slot_done(day: dt.date, queue: list[dict], hour: int, intro: str | None = None):
    total, done = queue_counts(queue)
    lines = [intro, ""] if intro else []
    if done == total:
        lines.append(f"🍋 <b>오늘 암송 완료!</b> ({done}/{total}) 수고 많으셨어요 🐦‍⬛")
        return "\n".join(lines), None
    lines.append(f"🌿 이번 시간 카드를 마쳤어요! 오늘 {done}/{total}")
    lines.append("<i>남은 카드는 다음 시간에 보내 드려요.</i>")
    markup = InlineKeyboardMarkup([[Btn("▶ 지금 더 하기", callback_data=_cb(day, hour, "m"))]])
    return "\n".join(lines), markup


async def _verse_pair(r, member_course: str, verse_id: int):
    verses = await course_verses(r, member_course)
    by_id = {v["id"]: v for v in verses}
    v = by_id.get(verse_id)
    prev = next((x for x in verses if v and x["seq"] == v["seq"] - 1), None)
    return v, prev


async def render_item(r, member: dict, day: dt.date, queue: list[dict], idx: int, stage: str):
    v, prev = await _verse_pair(r, member.get("course", COURSE), queue[idx]["v"])
    if v is None:   # 본문이 지워진 경우
        return "📖 이 카드의 본문을 찾을 수 없어요.", None
    marks = await load_marks(r, member["space_id"])
    return render_card(day, queue, idx, stage, v, prev,
                       bookmarked=bool(marks.get(v["id"], {}).get("bookmarked")))


def _next_in_slot(queue: list[dict], hour) -> int | None:
    return next((i for i in pending(queue) if queue[i]["s"] == hour), None)


async def render_after(r, member, day, queue, hour, intro=None):
    """채점 뒤: 같은 시간대의 다음 카드, 없으면 '이번 시간 완료'."""
    nxt = _next_in_slot(queue, hour)
    if nxt is not None:
        text, markup = await render_item(r, member, day, queue, nxt, _first_stage(queue[nxt]))
        return (f"{intro}\n\n{text}" if intro else text), markup
    return render_slot_done(day, queue, hour, intro)


# ---------------------------------------------------------------------------
# 채점 (버튼·타이핑 공통)
# ---------------------------------------------------------------------------
async def grade_item(r, space_id: int, member: dict, rec: dict, idx: int, grade: int,
                     day: dt.date) -> str | None:
    """채점 반영. 북마크가 자동으로 붙거나 풀리면 'on'/'off'를 돌려준다."""
    item = rec["queue"][idx]
    cards = {c["verse_id"]: c for c in await r.recite_cards(space_id)}
    card = cards.get(item["v"])
    mark = (await load_marks(r, space_id)).get(item["v"])
    new_mark, event = update_mark(mark, grade)
    known = item["k"] == "new" and bool(item.get("q"))   # 4단계 없이 바로 시험
    new_fields = apply_grade(card, grade, day, known=known, bookmarked=new_mark["bookmarked"])
    await r.save_card({"space_id": space_id, "verse_id": item["v"],
                       "learned_on": card["learned_on"] if card else day, **new_fields})
    if item["k"] == "new" and member["next_seq"] <= item["seq"]:
        member["next_seq"] = item["seq"] + 1
        member.setdefault("started_on", day)
        await r.save_member({"space_id": space_id, "next_seq": member["next_seq"],
                             "started_on": member.get("started_on") or day})
    item["g"] = grade
    await r.save_recite_day(rec)
    await save_mark(r, space_id, item["v"], new_mark)
    return event


# ---------------------------------------------------------------------------
# 버튼
# ---------------------------------------------------------------------------
async def on_recite_button(update: Update, context, space: dict, args: list[str]):
    """rc:* 버튼"""
    query = update.callback_query
    if args == ["i"]:
        await query.answer("📖 시간대마다 오는 암송 카드를 오늘 모두 마치면 자동으로 체크돼요!", show_alert=True)
        return
    r = repo(context)
    day = _parse_daykey(args[0])
    act = args[2]
    if not dates.within_grace(day, dates.now()):
        await query.answer("⏰ 지난 카드예요. 오늘 카드를 기다려 주세요!", show_alert=True)
        await safe_edit(query, (getattr(query.message, "text_html", None) or "📖")
                        + "\n\n⏰ <i>지난 카드예요.</i>", None)
        return
    member = await r.get_member(space["id"])
    rec = await r.get_recite_day(space["id"], day)
    if not member or not rec:
        await query.answer("암송 카드를 찾을 수 없어요. /rv 로 확인해 주세요.")
        return
    queue = rec["queue"]

    if act == "m":   # 다음 카드 더 하기
        hour = int(args[1])
        left = pending(queue)
        if not left:
            await query.answer("오늘 카드를 모두 마쳤어요!")
            text, markup = render_slot_done(day, queue, hour)
            await safe_edit(query, text, markup)
            return
        queue[left[0]]["s"] = hour
        await r.save_recite_day(rec)
        await query.answer()
        text, markup = await render_item(r, member, day, queue, left[0], _first_stage(queue[left[0]]))
        await safe_edit(query, text, markup)
        return

    idx = int(args[1])
    if not 0 <= idx < len(queue):
        await query.answer("카드를 찾을 수 없어요.")
        return
    item = queue[idx]
    if item["g"] is not None:
        await query.answer("이미 마친 카드예요.")
        text, markup = await render_after(r, member, day, queue, item["s"])
        await safe_edit(query, text, markup)
        return

    if act.startswith("g"):
        grade = int(act[1])
        event = await grade_item(r, space["id"], member, rec, idx, grade, day)
        await query.answer(MARK_TOAST.get(event)
                           or {2: "✅ 완벽!", 1: "🔸 조금만 더!", 0: "❌ 내일 다시 만나요"}[grade])
        text, markup = await render_after(r, member, day, queue, item["s"])
        await safe_edit(query, text, markup)
        return

    if act == "q":   # 바로 시험보기: 4단계를 건너뛰고 주소만 보고 암송
        item["q"] = True
        await r.save_recite_day(rec)
        await query.answer()
        text, markup = await render_item(r, member, day, queue, idx, "4")
        await safe_edit(query, text, markup)
        return

    if act == "b":   # 북마크 켜고 끄기
        marks = await load_marks(r, space["id"])
        new_mark = toggle_mark(marks.get(item["v"]))
        await save_mark(r, space["id"], item["v"], new_mark)
        await query.answer("⭐ 북마크했어요" if new_mark["bookmarked"] else "북마크를 해제했어요")
        text, markup = await render_item(r, member, day, queue, idx, "a")
        await safe_edit(query, text, markup)
        return

    if act == "t":
        await query.answer()
        user = query.from_user
        mention = f'<a href="tg://user?id={user.id}">{escape(user.first_name)}</a>님, ' if user else ""
        v, _ = await _verse_pair(r, member.get("course", COURSE), item["v"])
        await send_to_space(
            context.bot, space,
            f"⌨️ {mention}<b>{escape(v['ref'] if v else '')}</b>을 이 메시지에 <b>답장</b>으로 입력해 주세요.\n"
            f"<i>띄어쓰기와 문장부호는 채점하지 않아요.</i>\n"
            f"<code>#V{_daykey(day)}-{idx}-{query.message.message_id}</code>",
            ForceReply(selective=True, input_field_placeholder="외운 구절을 입력하세요"),
        )
        return

    await query.answer()
    text, markup = await render_item(r, member, day, queue, idx, act)
    await safe_edit(query, text, markup)


async def reply_typing_result(context, space: dict, msg, verse: dict, result, event: str | None):
    """타이핑 채점 결과를 답장으로 보내고, '답장으로 입력해 주세요' 안내 메시지는 지운다
    (안내 메시지가 남아 있으면 답장 상태가 계속 잡히기 때문)."""
    icon = {2: "✅", 1: "🔸", 0: "❌"}[result.grade]
    extra = f"\n{MARK_TOAST[event]}" if event else ""
    await msg.reply_text(
        f"⌨️ <b>타이핑 채점</b> — 정확도 <b>{result.score:.0f}%</b> → {icon} {GRADE_LABELS[result.grade]}\n\n"
        f"<b>{escape(verse['ref'])}</b>\n{result.diff_html}\n\n"
        f"<i>밑줄 친 부분이 틀리거나 빠진 곳이에요.</i>{extra}")
    prompt = getattr(msg, "reply_to_message", None)
    if prompt is not None:
        try:
            await context.bot.delete_message(chat_id=space["chat_id"], message_id=prompt.message_id)
        except Exception as e:
            log.info("타이핑 안내 메시지 삭제 실패: %s", e)


async def handle_typing(update: Update, context, space: dict, daykey: str, idx: int,
                        card_msg_id: int, typed: str):
    """타이핑 답장 채점. 채점 결과를 답장으로 보내고, 원래 카드 메시지는 다음 카드로 바꾼다."""
    r = repo(context)
    msg = update.effective_message
    day = _parse_daykey(daykey)
    if not dates.within_grace(day, dates.now()):
        await msg.reply_text("⏰ 지난 카드라 채점하지 않았어요.")
        return
    member = await r.get_member(space["id"])
    rec = await r.get_recite_day(space["id"], day)
    if not member or not rec or not 0 <= idx < len(rec["queue"]):
        await msg.reply_text("🌧️ 카드를 찾을 수 없어요.")
        return
    item = rec["queue"][idx]
    if item["g"] is not None:
        await msg.reply_text("이미 채점한 카드예요.")
        return
    v, _ = await _verse_pair(r, member.get("course", COURSE), item["v"])
    if not v:
        await msg.reply_text("🌧️ 본문을 찾을 수 없어요.")
        return

    result = grade_typing(typed, v["body"])
    event = await grade_item(r, space["id"], member, rec, idx, result.grade, day)
    await reply_typing_result(context, space, msg, v, result, event)

    text, markup = await render_after(r, member, day, rec["queue"], item["s"])
    try:
        await context.bot.edit_message_text(chat_id=space["chat_id"], message_id=card_msg_id,
                                            text=text, reply_markup=markup)
    except Exception as e:
        log.info("카드 메시지 갱신 실패: %s", e)
        await send_to_space(context.bot, space, text, markup)


# ---------------------------------------------------------------------------
# /rv 진도판과 설정
# ---------------------------------------------------------------------------
def _start_markup():
    return InlineKeyboardMarkup([[Btn(f"하루 {n}절", callback_data=f"rv:s:{n}") for n in DAILY_CHOICES]])


async def render_board(r, space: dict, member: dict, intro: str | None = None):
    verses = await course_verses(r, member.get("course", COURSE))
    cards = await r.recite_cards(space["id"])
    today = dates.today()
    start, end = _hours(member)
    learned = len({c["verse_id"] for c in cards} & {v["id"] for v in verses})
    passed = set(member.get("passed_chapters") or [])
    marks = await load_marks(r, space["id"])
    n_marks = sum(1 for m in marks.values() if m.get("bookmarked"))
    total = len(verses)
    lines = [intro, ""] if intro else []
    lines.append("📖 <b>계시록 암송</b>" + ("  ⏸ <i>쉬는 중</i>" if not member.get("active") else ""))
    lines.append(f"하루 새 구절 <b>{member['daily_new']}절</b> · 카드 시간 <b>{start}~{end}시</b>")
    if total:
        lines.append(f"진도 <b>{learned}/{total}절</b> ({learned / total * 100:.0f}%)")
        finish = expected_finish(learned, total, member["daily_new"], today)
        if finish:
            lines.append(f"예상 완료 {finish.year}년 {finish.month}월 {finish.day}일쯤")
        else:
            lines.append("🎉 <b>새 구절을 모두 익혔어요!</b> 이제 복습으로 단단히 다져요.")
    else:
        lines.append("<i>관리자가 본문을 올리면 시작돼요.</i>")

    markup_rows = []
    if member.get("active") and total:
        status = await load_recite_status(r, space, today)
        if status:
            lines.append(f"오늘 {status.done}/{status.total}" + (" 🍋" if status.is_done else "")
                         + (f" · 🔥{status.streak}" if status.streak >= 2 else ""))
            if not status.is_done:
                markup_rows.append([Btn("▶ 지금 카드 하기",
                                        callback_data=_cb(today, dates.now().hour, "m"))])

    board = chapter_board(verses, cards)
    if board:
        lines += ["", "<b>장별 진도</b>  ✉️ 시작 전 · 📜 진행 중 · ✅ 다 익힘 · 🏅 시험 통과·단단히"]
        cells = []
        for ch, n, got, mastered in board:
            icon = chapter_icon(n, got, mastered, ch in passed)
            cells.append(f"{ch}장 {icon}" + (f"{got}/{n}" if icon == "📜" else ""))
        for i in range(0, len(cells), 4):
            lines.append("  ".join(cells[i:i + 4]))

    lines += ["", "• 시간 바꾸기 <code>/rv 19-22</code>",
              "• 이미 외운 장은 <b>📝 장별 시험</b>으로 통과하면 진도에 바로 반영돼요.",
              "<i>하루 개수를 바꾸면 내일 카드부터 적용돼요.</i>"]
    if total:
        markup_rows.append([Btn("📝 장별 시험", callback_data="rs"),
                            Btn(f"⭐ 북마크 ({n_marks})", callback_data="rk")])
    markup_rows.append([Btn(("✔ " if member["daily_new"] == n else "") + f"하루 {n}절",
                            callback_data=f"rv:n:{n}") for n in DAILY_CHOICES])
    markup_rows.append([Btn("⏸ 쉬기" if member.get("active") else "▶ 다시 시작", callback_data="rv:p")])
    return "\n".join(lines), InlineKeyboardMarkup(markup_rows)


INTRO = (
    "📖 <b>계시록 전문 암송</b>\n\n"
    "매일 저녁 시간대에 나눠서 <b>새 구절</b>과 <b>복습 카드</b>를 보내 드려요.\n"
    "• 새 구절: 전문 → 빈칸 → 더 넓은 빈칸 → 주소만 보고 떠올리기\n"
    "• 복습: 잊을 때쯤 다시 (1·3·7·15·30·60일 간격)\n"
    "• 채점: 정답 보고 스스로, 또는 ⌨️ 타이핑으로\n"
    "• 이미 외운 장은 <code>/rv 시험</code>으로 시험 보고 통과하면 건너뛰어요\n\n"
    "하루에 몇 절씩 외울까요?\n"
    "<i>1절 약 13개월 · 2절 약 7개월 · 3절 약 4.5개월</i>"
)


async def cmd_recite(update: Update, context):
    space = await ensure_space(update, context)
    r = repo(context)
    msg = update.effective_message
    arg = " ".join(context.args or []).strip().lower()
    member = await r.get_member(space["id"])

    if arg.startswith("시험") or arg.startswith("북마크"):
        from . import recite_exam
        if not member:
            await msg.reply_text("📖 먼저 <code>/rv</code>로 암송을 시작해 주세요.")
            return
        if arg.startswith("북마크"):
            text, markup = await recite_exam.render_bookmarks(r, space)
        else:
            text, markup = await recite_exam.exam_entry(r, space, member, arg[2:].strip())
        await msg.reply_text(text, reply_markup=markup)
        return

    if not member:
        if arg in {str(n) for n in DAILY_CHOICES}:
            member = await _start(r, space, int(arg))
            text, markup = await render_board(r, space, member, intro="🌱 <b>암송을 시작했어요!</b>")
            await msg.reply_text(text, reply_markup=markup)
            return
        await msg.reply_text(INTRO, reply_markup=_start_markup())
        return

    intro = None
    if arg in ("off", "쉬기"):
        member["active"] = False
        intro = "⏸ 암송을 잠시 쉬어요. 진도는 그대로 남아 있어요."
    elif arg in ("on", "다시"):
        member["active"] = True
        intro = "▶ 암송을 다시 시작해요!"
    elif arg in {str(n) for n in DAILY_CHOICES}:
        member["daily_new"] = int(arg)
        intro = f"하루 새 구절을 <b>{arg}절</b>로 바꿨어요. (내일 카드부터)"
    elif arg:
        hours = parse_hours(arg)
        if not hours:
            await msg.reply_text("🌧️ <code>/rv 18-22</code>처럼 시작-끝 시각(0~23)을 적어 주세요.")
            return
        member["hours"] = f"{hours[0]}-{hours[1]}"
        intro = f"⏰ 카드 시간을 <b>{hours[0]}~{hours[1]}시</b>로 바꿨어요."
    if intro:
        await r.save_member({"space_id": space["id"], "active": member["active"],
                             "daily_new": member["daily_new"], "hours": member.get("hours") or DEFAULT_HOURS})
    text, markup = await render_board(r, space, member, intro=intro)
    await msg.reply_text(text, reply_markup=markup)


async def _start(r, space: dict, n: int) -> dict:
    member = {"space_id": space["id"], "course": COURSE, "daily_new": n, "hours": DEFAULT_HOURS,
              "active": True, "next_seq": 1, "started_on": dates.today()}
    await r.save_member(member)
    return member


async def on_rv_button(update: Update, context, space: dict, args: list[str]):
    """rv:* 버튼"""
    query = update.callback_query
    r = repo(context)
    member = await r.get_member(space["id"])
    intro = None
    if args[0] == "s":
        if member:
            member["daily_new"] = int(args[1])
            member["active"] = True
            await r.save_member({"space_id": space["id"], "daily_new": member["daily_new"], "active": True})
        else:
            member = await _start(r, space, int(args[1]))
        intro = "🌱 <b>암송을 시작했어요!</b> 카드 시간이 되면 보내 드릴게요."
    elif not member:
        await query.answer("먼저 /rv 로 암송을 시작해 주세요.")
        return
    elif args[0] == "n":
        member["daily_new"] = int(args[1])
        await r.save_member({"space_id": space["id"], "daily_new": member["daily_new"]})
        intro = f"하루 새 구절을 <b>{args[1]}절</b>로 바꿨어요. (내일 카드부터)"
    elif args[0] == "p":
        member["active"] = not member.get("active")
        await r.save_member({"space_id": space["id"], "active": member["active"]})
        intro = "▶ 암송을 다시 시작해요!" if member["active"] else "⏸ 암송을 잠시 쉬어요. 진도는 그대로 남아 있어요."
    await query.answer()
    text, markup = await render_board(r, space, member, intro=intro)
    await safe_edit(query, text, markup)


# ---------------------------------------------------------------------------
# 관리자
# ---------------------------------------------------------------------------
async def import_course(update: Update, context, text: str):
    r = repo(context)
    parsed = parse_recite_text(text)
    existing = {v["ref"] for v in await r.recite_verses(COURSE)}
    await r.upsert_recite_verses(parsed.rows)
    _VERSE_CACHE.clear()
    added = sum(row["ref"] not in existing for row in parsed.rows)
    verses = await r.recite_verses(COURSE)
    chapters = sorted({v["chapter"] for v in verses})
    lines = ["📖 <b>암송 본문 저장 완료</b>",
             f"• 새로 추가 {added}절 · 수정 {len(parsed.rows) - added}절",
             f"• 전체 {len(verses)}절" + (f" ({chapters[0]}장~{chapters[-1]}장)" if chapters else "")]
    if parsed.errors:
        lines += ["", f"⚠️ 건너뛴 줄 {len(parsed.errors)}개"] + [f"  {escape(e)}" for e in parsed.errors[:10]]
    await update.effective_message.reply_text("\n".join(lines))


async def cmd_recite_add(update: Update, context):
    if not _is_admin(update):
        await update.effective_message.reply_text("🌧️ 관리자만 사용할 수 있는 명령어예요.")
        return
    body = command_body(update.effective_message.text or "")
    if not body:
        await update.effective_message.reply_text("📖 <b>암송 본문 등록</b>\n" + FORMAT_HELP)
        return
    await import_course(update, context, body)


async def cmd_recite_status(update: Update, context):
    if not _is_admin(update):
        await update.effective_message.reply_text("🌧️ 관리자만 사용할 수 있는 명령어예요.")
        return
    r = repo(context)
    members = await r.all_members()
    total = len(await r.recite_verses(COURSE))
    if not members:
        await update.effective_message.reply_text("📖 아직 암송에 참여한 방이 없어요.")
        return
    today = dates.today()
    lines = [f"📖 <b>계시록 암송 현황</b> — {len(members)}명 · 전체 {total}절", ""]
    for m in members:
        space = await r.space_by_id(m["space_id"])
        if not space:
            continue
        learned = len(await r.recite_cards(space["id"]))
        rec = await r.get_recite_day(space["id"], today)
        t, d = queue_counts(rec["queue"]) if rec else (0, 0)
        name = escape(space.get("name") or "")
        if space.get("user_name") and space.get("user_name") != space.get("name"):
            name += f" ({escape(space['user_name'])})"
        pause = " ⏸" if not m.get("active") else ""
        lines.append(f"• <b>{name}</b>{pause} — {learned}/{total}절 · 하루 {m['daily_new']}절 · 오늘 {d}/{t}")
    for chunk in chunk_text("\n".join(lines)):
        await update.effective_message.reply_text(chunk)


# ---------------------------------------------------------------------------
# 시간대별 카드 발송 (jobs.minute_job에서 호출)
# ---------------------------------------------------------------------------
async def issue_recite_slots(context, spaces: list[dict], now: dt.datetime, gap: float = 0.05):
    if now.minute > CATCH_UP_MINUTES:
        return
    r = repo(context)
    today = now.date()
    marks: set = context.bot_data.setdefault("recite_marks", set())
    for mark in [m for m in marks if m[1] != today]:
        marks.discard(mark)

    try:
        members = {m["space_id"]: m for m in await r.all_members() if m.get("active")}
    except Exception as e:
        log.warning("암송 참여자 불러오기 실패: %s", e)
        return
    if not members:
        return
    verses = await course_verses(r, COURSE)
    if not verses:
        return

    for space in spaces:
        member = members.get(space["id"])
        if not member or space.get("disabled"):
            continue
        start, end = _hours(member)
        if not start <= now.hour <= end:
            continue
        mark = (space["id"], today, now.hour)
        if mark in marks:
            continue
        marks.add(mark)
        try:
            rec = await ensure_day(r, space["id"], member, today, verses)
            if now.hour in (rec.get("sent_hours") or []):
                continue
            batch = assign_slot(rec["queue"], now.hour, end)
            rec["sent_hours"] = list(rec.get("sent_hours") or []) + [now.hour]
            await r.save_recite_day(rec)
            if not batch:
                continue
            text, markup = await render_item(r, member, today, rec["queue"], batch[0],
                                             _first_stage(rec["queue"][batch[0]]))
            await send_to_space(context.bot, space, text, markup)
        except Exception:
            log.exception("암송 카드 발송 실패 space=%s", space.get("id"))
        await asyncio.sleep(gap)
