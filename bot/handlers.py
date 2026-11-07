"""사용자 명령어와 일반 메시지 처리."""
from __future__ import annotations

import random
import re
from html import escape

from telegram import InlineKeyboardButton as Btn
from telegram import InlineKeyboardMarkup, Update

from . import dates
from .common import command_body, ensure_space, load_state, load_today, repo
from .config import ADMIN_ID, DEFAULT_CATEGORY, MAX_TITLE_LEN
from .dates import days_label, fmt_short, split_routine_line
from .logic import build_week
from .views import render_routines, render_today, render_week

WELCOME = (
    "☁️ <b>구름 언덕과 까마귀 정원에 오신 것을 환영합니다!</b> 🐦‍⬛\n\n"
    "<b>할 일 등록</b> — 채팅창에 그냥 적으세요. 한 줄에 하나씩!\n"
    "• <code>[논문]</code> 줄을 먼저 쓰면 아래 줄들이 그 카테고리로 들어가요.\n"
    "• 날짜 지정: <code>내일 보고서</code> · <code>금 발표 연습</code> · <code>다음주 월 회의</code>\n"
    "  <code>11/20 발표</code> · <code>3일 후 서류 제출</code> · <code>일요일 장보기</code>\n"
    "• 날짜로 읽히지 않게 하려면 맨 앞에 <code>!</code> (예: <code>!10/20 비율 계산</code>)\n\n"
    "<b>명령어</b>\n"
    "/l 오늘 목록 (완료 체크 · ✏️ 편집)\n"
    "/r 루틴 관리 — <code>/r 월수금 운동</code>으로 추가\n"
    "/w 주간 리포트 (일~토)\n"
    "/t 밤 점검 시각 — <code>/t 22:30</code>, 끄기 <code>/t off</code>\n"
    "/q 성구 퀴즈 시간 — <code>/q 9-18</code>, 끄기 <code>/q off</code>\n"
    "/rv 계시록 암송 — 시작·진도판·설정\n"
    "/off · /on 이 방에서 봇 끄기·켜기\n\n"
    "💬 관리자에게 질문하려면 <code>질문: 내용</code>\n\n"
    "🌱 배움의 씨앗을 심고 촘촘하게 가꿔 보세요!"
)

CHEERS = [
    "🌿 멋진 목표네요! 오늘도 싱그러운 하루 만들어봐요!",
    "☁️ 구름 위로 훌쩍 날아오를 준비 완료!",
    "🐦‍⬛ 까마귀 정원에 소중한 씨앗이 심어졌어요.",
    "🎓 지식의 나무가 또 한 뼘 자라날 거예요!",
    "🍋 상큼한 결실을 향해 오늘도 기운 내세요!",
]

MARKER_RE = re.compile(r"#([TRS])(\d+)\b")
TYPING_RE = re.compile(r"#V(\d{8})-(\d+)-(\d+)\b")
CATEGORY_RE = re.compile(r"^\[\s*([^\]]{1,30}?)\s*\]\s*(.*)$")


# ---------------------------------------------------------------------------
async def cmd_start(update: Update, context):
    await ensure_space(update, context)
    await update.effective_message.reply_text(WELCOME)


async def cmd_list(update: Update, context):
    space = await ensure_space(update, context)
    view = await load_today(repo(context), space, dates.today())
    text, markup = render_today(view, "l")
    await update.effective_message.reply_text(text, reply_markup=markup)


async def cmd_week(update: Update, context):
    space = await ensure_space(update, context)
    today = dates.today()
    rep = build_week(*await load_state(repo(context), space["id"], today), today)
    text, markup = render_week(rep)
    await update.effective_message.reply_text(text, reply_markup=markup)


async def cmd_routine(update: Update, context):
    space = await ensure_space(update, context)
    r = repo(context)
    today = dates.today()
    body = command_body(update.effective_message.text or "")

    intro = None
    if body:
        rows, added = [], []
        for line in body.splitlines():
            line = line.strip()
            if not line:
                continue
            days, title = split_routine_line(line)
            title = title[:MAX_TITLE_LEN]
            rows.append({"space_id": space["id"], "title": title, "days": days, "created_on": today})
            added.append(f"• {escape(title)} ({days_label(days)})")
        await r.add_routines(rows)
        intro = f"🔄 <b>루틴 {len(rows)}개를 추가했어요!</b>\n" + "\n".join(added)

    routines = await r.routines(space["id"])
    logs = await r.routine_logs([x["id"] for x in routines])
    text, markup = render_routines(routines, logs, today, intro=intro)
    await update.effective_message.reply_text(text, reply_markup=markup)


async def cmd_time(update: Update, context):
    space = await ensure_space(update, context)
    arg = " ".join(context.args or []).strip()

    if not arg:
        cur = space.get("notify_time")
        status = f"지금 설정: <b>{cur}</b>" if cur else "지금은 밤 점검이 <b>꺼져</b> 있어요."
        await update.effective_message.reply_text(
            f"🌙 <b>밤 점검 시각</b>\n{status}\n\n"
            "• <code>/t 22:30</code> 매일 밤 10시 30분\n"
            "• <code>/t off</code> 끄기\n\n"
            "<i>토요일 밤 점검 때는 주간 리포트도 함께 보내 드려요.</i>")
        return

    if arg.lower() in ("off", "끄기", "해제"):
        await repo(context).update_space(space["id"], {"notify_time": None})
        await update.effective_message.reply_text(
            "➖ 밤 점검을 껐어요. (주간 리포트는 토요일 22:00에 보내 드려요)")
        return

    m = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", arg)
    if not m:
        await update.effective_message.reply_text(
            "🌧️ 24시간 형식으로 입력해 주세요. 예: <code>/t 22:00</code>")
        return
    hhmm = f"{int(m.group(1)):02d}:{m.group(2)}"
    await repo(context).update_space(space["id"], {"notify_time": hhmm})
    await update.effective_message.reply_text(f"🌙 매일 <b>{hhmm}</b>에 밤 점검을 보내 드릴게요!")


async def cmd_off(update: Update, context):
    space = await ensure_space(update, context)
    await repo(context).update_space(space["id"], {"disabled": True})
    await update.effective_message.reply_text(
        "🌧️ <b>이 방에서 봇을 껐어요.</b>\n"
        "일반 메시지가 할 일로 등록되지 않고, 알림과 전체 공지도 오지 않아요.\n"
        "다시 켜려면 /on")


async def cmd_on(update: Update, context):
    space = await ensure_space(update, context)
    await repo(context).update_space(space["id"], {"disabled": False})
    await update.effective_message.reply_text(
        "☀️ <b>이 방에서 봇을 다시 켰어요!</b>\n채팅창에 적는 내용이 할 일로 등록돼요.")


# ---------------------------------------------------------------------------
async def handle_message(update: Update, context):
    msg = update.effective_message
    if not msg or not msg.text:
        return
    text = msg.text.strip()
    space = await ensure_space(update, context)

    # 1) 봇의 '이름 변경' 또는 '질문' 메시지에 단 답장
    reply = msg.reply_to_message
    if reply and reply.from_user and reply.from_user.id == context.bot.id and reply.text:
        t = TYPING_RE.search(reply.text)
        if t:   # 계시록 암송 타이핑 채점
            from .recite_handlers import handle_typing
            await handle_typing(update, context, space, t.group(1), int(t.group(2)), int(t.group(3)), text)
            return
        m = MARKER_RE.search(reply.text)
        if m and await _handle_marker_reply(update, context, space, m.group(1), int(m.group(2)), text):
            return

    if space.get("disabled"):
        return

    # 2) 관리자에게 질문
    if re.match(r"^질문[:\s]", text):
        await _forward_question(update, context, space, re.sub(r"^질문[:\s]*", "", text).strip())
        return

    # 3) 할 일 등록
    await _add_tasks(update, context, space, text)


async def _add_tasks(update: Update, context, space: dict, text: str):
    r = repo(context)
    today = dates.today()
    category = DEFAULT_CATEGORY
    rows, errors = [], []

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        line_cat = category
        m = CATEGORY_RE.match(line)
        if m:
            if not m.group(2):          # '[논문]' 한 줄 -> 아래 줄들의 카테고리
                category = m.group(1)
                continue
            line_cat, line = m.group(1), m.group(2)   # '[논문] 초안' -> 이 줄만
        p = dates.parse_dated_line(line, today)
        if p.error:
            errors.append(f"⚠️ {escape(line)} — {p.error}")
            continue
        if not p.text:
            continue
        due = p.due or today
        rows.append({
            "space_id": space["id"], "title": p.text[:MAX_TITLE_LEN], "category": line_cat,
            "due_date": due, "raw_text": line if due != today else None,
        })

    added = await r.add_tasks(rows)
    if not added:
        if errors:
            await update.effective_message.reply_text("\n".join(errors))
        return

    future = [t for t in added if t["due_date"] > today]
    lines = [f"🌿 <b>{len(added)}개의 계획을 추가했어요!</b>", random.choice(CHEERS)]
    for t in future:
        lines.append(f"📅 {fmt_short(t['due_date'])} {escape(t['title'])} → 예정 목록")
    lines += errors

    view = await load_today(r, space, today)
    body, markup = render_today(view, "l", intro="\n".join(lines))

    undo = [[Btn(f"↩️ 오늘 할 일로: {t['title'][:30]}", callback_data=f"u:{t['id']}")] for t in future[:5]]
    if undo:
        markup = InlineKeyboardMarkup(undo + list(markup.inline_keyboard if markup else []))
    await update.effective_message.reply_text(body, reply_markup=markup)


async def _handle_marker_reply(update, context, space, kind: str, ident: int, text: str) -> bool:
    """처리했으면 True."""
    r = repo(context)
    msg = update.effective_message
    new_title = text.strip()[:MAX_TITLE_LEN]

    if kind == "S":  # 관리자가 질문 메시지에 답장 -> 질문한 공간으로 전달
        if update.effective_user.id != ADMIN_ID:
            return False
        from .admin import deliver_answer
        await deliver_answer(context, msg, ident, text)
        return True

    if not new_title:
        return True

    if kind == "T":
        task = await r.get_task(space["id"], ident)
        if not task:
            await msg.reply_text("🌧️ 이미 삭제된 할 일이에요.")
            return True
        await r.update_task(space["id"], ident, {"title": new_title, "raw_text": None})
        intro = f"✏️ 이름을 바꿨어요: <b>{escape(task['title'])}</b> → <b>{escape(new_title)}</b>"
        view = await load_today(r, space, dates.today())
        body, markup = render_today(view, "l", intro=intro)
        await msg.reply_text(body, reply_markup=markup)
        return True

    if kind == "R":
        routine = await r.get_routine(space["id"], ident)
        if not routine:
            await msg.reply_text("🌧️ 이미 삭제된 루틴이에요.")
            return True
        await r.update_routine(space["id"], ident, {"title": new_title})
        routines = await r.routines(space["id"])
        logs = await r.routine_logs([x["id"] for x in routines])
        intro = f"✏️ 루틴 이름을 바꿨어요: <b>{escape(routine['title'])}</b> → <b>{escape(new_title)}</b>"
        body, markup = render_routines(routines, logs, dates.today(), intro=intro)
        await msg.reply_text(body, reply_markup=markup)
        return True
    return False


async def _forward_question(update, context, space, question: str):
    msg = update.effective_message
    if not question:
        await msg.reply_text("💡 질문 내용을 함께 적어 주세요. 예: <code>질문: 주간 리포트는 언제 오나요?</code>")
        return
    who = escape(update.effective_user.full_name if update.effective_user else "알 수 없음")
    admin_text = (
        f"🔒 <b>질문</b> · {who} / {escape(space.get('name') or '')} (#S{space['id']})\n\n"
        f"{escape(question)}\n\n"
        f"<i>이 메시지에 답장하거나</i> <code>/re {space['id']} 답변</code>"
    )
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_text)
        await msg.reply_text("🔒 질문을 관리자에게 전달했어요.")
    except Exception:
        await msg.reply_text("🌧️ 질문 전달에 실패했어요. 잠시 후 다시 시도해 주세요.")


async def handle_topic_edited(update: Update, context):
    """토픽 이름이 바뀌면 공간 이름도 갱신 (이미 등록된 공간만)."""
    msg = update.effective_message
    edited = getattr(msg, "forum_topic_edited", None)
    if not edited or not edited.name:
        return
    r = repo(context)
    space = await r.get_space(msg.chat.id, msg.message_thread_id or 0)
    if space:
        await r.update_space(space["id"], {"name": edited.name})
