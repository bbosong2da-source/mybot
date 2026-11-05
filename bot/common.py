"""핸들러들이 같이 쓰는 도우미."""
from __future__ import annotations

import asyncio
import datetime as dt
import logging

from telegram import Message, Update
from telegram.error import BadRequest, Forbidden, TelegramError

from .config import DEFAULT_NOTIFY_TIME
from .dates import week_range
from .logic import TodayView, build_today

log = logging.getLogger(__name__)


def repo(context):
    return context.application.bot_data["repo"]


def thread_of(msg: Message | None) -> int:
    # 일반 그룹의 '답장'에도 message_thread_id가 붙으므로, 진짜 토픽 메시지일 때만 사용
    if msg is not None and getattr(msg, "is_topic_message", False) and msg.message_thread_id:
        return msg.message_thread_id
    return 0


def _detect_names(update: Update) -> tuple[str | None, str | None]:
    """(공간 이름, 보낸 사람 이름). 확실히 알 수 없으면 None."""
    chat, msg, user = update.effective_chat, update.effective_message, update.effective_user
    user_name = user.first_name if user else None
    name = None
    if chat.type == "private":
        name = user.full_name if user else None
    elif thread_of(msg):
        reply = getattr(msg, "reply_to_message", None)
        created = getattr(reply, "forum_topic_created", None) if reply else None
        if created:
            name = created.name
    else:
        name = chat.title
    return name, user_name


async def ensure_space(update: Update, context) -> dict:
    """메시지/명령이 온 공간을 찾고, 없으면 만든다. 이름이 바뀌었으면 갱신."""
    r = repo(context)
    chat = update.effective_chat
    thread = thread_of(update.effective_message)
    name, user_name = _detect_names(update)

    space = await r.get_space(chat.id, thread)
    if space is None:
        fallback = chat.title or user_name or "이름 없음"
        if thread and not name:
            fallback = f"{fallback} #{thread}"
        return await r.create_space({
            "chat_id": chat.id, "thread_id": thread,
            "name": name or fallback, "user_name": user_name,
            "notify_time": DEFAULT_NOTIFY_TIME, "disabled": False,
        })

    changes = {}
    if name and name != space.get("name"):
        changes["name"] = name
    if user_name and user_name != space.get("user_name"):
        changes["user_name"] = user_name
    if changes:
        await r.update_space(space["id"], changes)
        space.update(changes)
    return space


async def space_of_query(update: Update, context) -> dict:
    msg = update.callback_query.message
    r = repo(context)
    space = await r.get_space(msg.chat.id, thread_of(msg))
    if space is None:
        space = await r.create_space({
            "chat_id": msg.chat.id, "thread_id": thread_of(msg),
            "name": getattr(msg.chat, "title", None) or "이름 없음",
            "notify_time": DEFAULT_NOTIFY_TIME, "disabled": False,
        })
    return space


async def load_state(r, space_id: int, today: dt.date):
    start, _ = week_range(today)
    tasks, routines = await asyncio.gather(r.active_tasks(space_id, start), r.routines(space_id))
    logs = await r.routine_logs([x["id"] for x in routines])
    return tasks, routines, logs


async def load_today(r, space_id: int, today: dt.date) -> TodayView:
    return build_today(*await load_state(r, space_id, today), today)


async def send_to_space(bot, space: dict, text: str, markup=None, **kwargs):
    try:
        return await bot.send_message(
            chat_id=space["chat_id"],
            message_thread_id=space["thread_id"] or None,
            text=text, reply_markup=markup, **kwargs,
        )
    except Forbidden as e:
        log.warning("전송 차단됨 space=%s: %s", space.get("id"), e)
    except TelegramError as e:
        log.warning("전송 실패 space=%s: %s", space.get("id"), e)
    return None


async def safe_edit(query, text: str, markup=None) -> None:
    try:
        await query.edit_message_text(text, reply_markup=markup)
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            log.warning("메시지 수정 실패: %s", e)


def command_body(text: str) -> str:
    """'/r@bot 운동\\n독서' -> '운동\\n독서'"""
    first, _, rest = text.partition("\n")
    parts = first.split(maxsplit=1)
    head = parts[1] if len(parts) > 1 else ""
    return (head + ("\n" + rest if rest else "")).strip()


def chunk_text(text: str, limit: int = 3900) -> list[str]:
    chunks, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > limit and cur:
            chunks.append(cur)
            cur = ""
        cur += line + "\n"
    if cur.strip():
        chunks.append(cur)
    return chunks
