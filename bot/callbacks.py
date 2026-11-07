"""인라인 버튼 처리. callback_data 규칙은 views.py 맨 위 설명 참고."""
from __future__ import annotations

import datetime as dt
import random
from html import escape

from telegram import ForceReply, Update

from . import dates
from .quiz_handlers import on_quiz_button
from .recite_handlers import on_recite_button, on_rv_button
from .common import load_today, repo, safe_edit, send_to_space, space_of_query
from .views import (render_broadcast, render_routine_delete_confirm, render_routine_detail,
                    render_routines, render_today)

POP_CHEERS = [
    "🎓 학식과 지혜가 한층 깊어졌어요!",
    "🐦‍⬛ 까마귀가 높은 하늘에서 날개를 펼쳤어요!",
    "🍋 싱싱한 열매 하나 수확!",
    "☁️ 정원이 한층 더 풍성해졌네요!",
]


async def on_button(update: Update, context):
    query = update.callback_query
    data = query.data or ""
    if data == "_":
        await query.answer()
        return

    space = await space_of_query(update, context)
    head, *args = data.split(":")
    handler = _HANDLERS.get(head)
    if handler is None:
        await query.answer("오래된 버튼이에요. /l 로 새 목록을 열어 주세요.")
        return
    await handler(update, context, space, args)


async def _rerender_today(query, context, space, mode: str, intro: str | None = None,
                          day: dt.date | None = None):
    view = await load_today(repo(context), space, day or dates.today())
    text, markup = render_today(view, mode, intro=intro)
    await safe_edit(query, text, markup)


def _push_one_day(task: dict, today: dt.date) -> dt.date:
    return max(task["due_date"], today) + dt.timedelta(days=1)


def _action_day(query, mode: str) -> dt.date | None:
    """버튼이 기록할 날짜.
    목록·편집 화면: 누른 날(오늘).
    밤 점검 화면: 그 밤 점검이 가리키는 날. 자정을 넘겨 눌러도 다음 날 새벽 4시 전까지는
    그날로 기록하고, 그 뒤에는 None(지난 점검)."""
    if mode != "n":
        return dates.today()
    sent = getattr(query.message, "date", None) or dates.now()
    day = dates.night_day_of(sent)
    return day if dates.within_grace(day, dates.now()) else None


async def _expired_night(query):
    await query.answer("⏰ 지난 밤 점검이에요. /l 에서 오늘 목록을 확인해 주세요.", show_alert=True)
    msg = query.message
    try:
        text = getattr(msg, "text_html", None) or getattr(msg, "text", None)
    except Exception:   # 아주 오래된 메시지는 내용을 읽을 수 없음
        text = None
    if text:
        await safe_edit(query, text + "\n\n⏰ <i>지난 밤 점검이에요. /l 에서 오늘 목록을 확인해 주세요.</i>", None)


# --- 오늘 목록 / 밤 점검 ----------------------------------------------------
async def _list(update, context, space, args):
    query = update.callback_query
    mode = "n" if args == ["n"] else "l"
    day = _action_day(query, mode)
    if day is None:
        await _expired_night(query)
        return
    await query.answer()
    await _rerender_today(query, context, space, mode, day=day)


async def _toggle_task(update, context, space, args):
    query = update.callback_query
    mode, task_id = args[0], int(args[1])
    day = _action_day(query, mode)
    if day is None:
        await _expired_night(query)
        return
    r = repo(context)
    task = await r.get_task(space["id"], task_id)
    if not task:
        await query.answer("이미 삭제된 할 일이에요.")
    elif mode == "n" and task["done_at"] is not None:
        await query.answer("이미 완료한 할 일이에요.")   # 밤 점검의 ✅는 '완료'만
    else:
        done = task["done_at"] is None
        await r.update_task(space["id"], task_id, {"done_at": day if done else None})
        await query.answer(random.choice(POP_CHEERS) if done and random.random() < 0.15 else None)
    await _rerender_today(query, context, space, mode, day=day)


async def _toggle_routine(update, context, space, args):
    query = update.callback_query
    mode, routine_id = args[0], int(args[1])
    day = _action_day(query, mode)
    if day is None:
        await _expired_night(query)
        return
    r = repo(context)
    routine = await r.get_routine(space["id"], routine_id)
    if not routine:
        await query.answer("이미 삭제된 루틴이에요.")
    else:
        logs = await r.routine_logs([routine_id])
        done = day not in logs.get(routine_id, set())
        await r.set_routine_log(routine_id, day, done)
        await query.answer(random.choice(POP_CHEERS) if done and random.random() < 0.15 else None)
    await _rerender_today(query, context, space, mode, day=day)


async def _night_action(update, context, space, args):
    await _task_action(update, context, space, args, mode="n")


async def _edit(update, context, space, args):
    query = update.callback_query
    if not args:
        await query.answer()
        await _rerender_today(query, context, space, "e")
        return
    if args[0] == "n":
        await _ask_rename(update, context, space, "T", int(args[1]))
        return
    await _task_action(update, context, space, args, mode="e")


async def _task_action(update, context, space, args, mode: str):
    """args: ['t', id] 내일로 / ['x', id] 삭제"""
    query = update.callback_query
    day = _action_day(query, mode)
    if day is None:
        await _expired_night(query)
        return
    action, task_id = args[0], int(args[1])
    r = repo(context)
    task = await r.get_task(space["id"], task_id)
    if not task:
        await query.answer("이미 삭제된 할 일이에요.")
    elif action == "t":
        new_due = _push_one_day(task, day)   # 밤 점검이면 '그 밤의 다음 날'
        await r.update_task(space["id"], task_id, {"due_date": new_due})
        await query.answer(f"➡️ {dates.fmt_short(new_due)}로 미뤘어요")
    elif action == "x":
        await r.delete_task(space["id"], task_id)
        await query.answer("🗑 삭제했어요")
    else:
        await query.answer()
    await _rerender_today(query, context, space, mode, day=day)


async def _undo_date(update, context, space, args):
    query = update.callback_query
    r = repo(context)
    task = await r.get_task(space["id"], int(args[0]))
    if not task:
        await query.answer("이미 삭제된 할 일이에요.")
        intro = None
    else:
        title = task.get("raw_text") or task["title"]
        await r.update_task(space["id"], task["id"],
                            {"due_date": dates.today(), "title": title, "raw_text": None})
        await query.answer("오늘 할 일로 옮겼어요")
        intro = f"↩️ <b>{escape(title)}</b> — 오늘 할 일로 옮겼어요."
    await _rerender_today(query, context, space, "l", intro=intro)


async def _ask_rename(update, context, space, kind: str, ident: int):
    query = update.callback_query
    r = repo(context)
    item = await (r.get_task if kind == "T" else r.get_routine)(space["id"], ident)
    if not item:
        await query.answer("이미 삭제된 항목이에요.")
        return
    await query.answer()
    user = query.from_user
    mention = f'<a href="tg://user?id={user.id}">{escape(user.first_name)}</a>님, ' if user else ""
    await send_to_space(
        context.bot, space,
        f"✏️ {mention}<b>{escape(item['title'])}</b>의 새 이름을 이 메시지에 <b>답장</b>으로 보내 주세요.\n"
        f"<code>#{kind}{ident}</code>",
        ForceReply(selective=True, input_field_placeholder="새 이름"),
    )


# --- 루틴 관리 --------------------------------------------------------------
async def _routine_list(update, context, space, intro=None):
    r = repo(context)
    routines = await r.routines(space["id"])
    logs = await r.routine_logs([x["id"] for x in routines])
    text, markup = render_routines(routines, logs, dates.today(), intro=intro)
    await safe_edit(update.callback_query, text, markup)


async def _routine_detail(update, context, space, routine_id: int):
    r = repo(context)
    routine = await r.get_routine(space["id"], routine_id)
    if not routine:
        await _routine_list(update, context, space, intro="🌧️ 이미 삭제된 루틴이에요.")
        return
    logs = await r.routine_logs([routine_id])
    text, markup = render_routine_detail(routine, logs[routine_id], dates.today())
    await safe_edit(update.callback_query, text, markup)


async def _rm(update, context, space, args):
    await update.callback_query.answer()
    if args:
        await _routine_detail(update, context, space, int(args[0]))
    else:
        await _routine_list(update, context, space)


async def _rd(update, context, space, args):
    query = update.callback_query
    routine_id, day = int(args[0]), int(args[1])
    r = repo(context)
    routine = await r.get_routine(space["id"], routine_id)
    if routine:
        days = set(routine["days"])
        days ^= {day}
        if not days:
            await query.answer("최소 하루는 남겨 주세요.", show_alert=True)
            return
        await r.update_routine(space["id"], routine_id, {"days": sorted(days)})
    await query.answer()
    await _routine_detail(update, context, space, routine_id)


async def _rn(update, context, space, args):
    await _ask_rename(update, context, space, "R", int(args[0]))


async def _rx(update, context, space, args):
    query = update.callback_query
    routine = await repo(context).get_routine(space["id"], int(args[0]))
    await query.answer()
    if not routine:
        await _routine_list(update, context, space, intro="🌧️ 이미 삭제된 루틴이에요.")
        return
    text, markup = render_routine_delete_confirm(routine)
    await safe_edit(query, text, markup)


async def _ry(update, context, space, args):
    query = update.callback_query
    r = repo(context)
    routine = await r.get_routine(space["id"], int(args[0]))
    if routine:
        await r.delete_routine(space["id"], routine["id"])
        await query.answer("🗑 삭제했어요")
        await _routine_list(update, context, space, intro=f"🗑 <b>{escape(routine['title'])}</b> 루틴을 삭제했어요.")
    else:
        await query.answer()
        await _routine_list(update, context, space)


# --- 관리자 공지 ------------------------------------------------------------
async def _bc(update, context, space, args):
    query = update.callback_query
    bid, idx = int(args[0]), int(args[1])
    r = repo(context)
    b = await r.get_broadcast(bid)
    if not b or space["id"] not in await r.broadcast_targets(bid) or not 0 <= idx < len(b["items"]):
        await query.answer("이 방에서 체크할 수 없는 공지예요.")
        return
    checks = {i for s, i in await r.broadcast_checks(bid) if s == space["id"]}
    done = idx not in checks
    await r.set_broadcast_check(bid, space["id"], idx, done)
    checks ^= {idx}
    await query.answer()
    text, markup = render_broadcast(b, checks)
    await safe_edit(query, text, markup)


_HANDLERS = {
    "l": _list, "t": _toggle_task, "r": _toggle_routine, "n": _night_action,
    "e": _edit, "u": _undo_date,
    "rm": _rm, "rd": _rd, "rn": _rn, "rx": _rx, "ry": _ry,
    "bc": _bc,
    "qz": on_quiz_button,
    "rc": on_recite_button,
    "rv": on_rv_button,
}
