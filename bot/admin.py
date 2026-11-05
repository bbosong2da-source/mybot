"""관리자 전용: /bc 공지 과제, /bcr 결과 리포트, /re 답변."""
from __future__ import annotations

import asyncio
import re
from html import escape

from telegram import Update

from .common import chunk_text, command_body, ensure_space, repo, send_to_space
from .config import ADMIN_ID
from .views import render_broadcast

DEFAULT_EXCLUDES = ["광고", "공지", "자료"]

BC_HELP = (
    "🕊️ <b>공지 과제 보내기</b>\n\n"
    "<code>/bc</code> 다음 줄부터 과제를 한 줄에 하나씩 적어 주세요.\n"
    "• <code>[제목]</code> 줄: 공지 제목 (없으면 '전체 공지 과제')\n"
    "• <code>제외: 광고, 공지</code> 줄: 이름에 이 단어가 들어간 방은 제외\n"
    "  (기본 제외: 광고, 공지, 자료 · /off 한 방은 항상 제외)\n\n"
    "<pre>/bc\n[11월 1주차 공지]\n주간 질문 작성하기\n공지사항 숙지하기</pre>"
)


def _is_admin(update: Update) -> bool:
    return bool(update.effective_user and update.effective_user.id == ADMIN_ID)


async def _deny(update: Update):
    await update.effective_message.reply_text("🌧️ 관리자만 사용할 수 있는 명령어예요.")


async def cmd_broadcast(update: Update, context):
    if not _is_admin(update):
        return await _deny(update)
    body = command_body(update.effective_message.text or "")
    if not body:
        await update.effective_message.reply_text(BC_HELP)
        return

    title, items, excludes = "전체 공지 과제", [], list(DEFAULT_EXCLUDES)
    for line in (l.strip() for l in body.splitlines()):
        if not line:
            continue
        if line.startswith("제외:"):
            excludes = [k.strip() for k in line[3:].split(",") if k.strip()]
        elif m := re.fullmatch(r"\[\s*(.+?)\s*\]", line):
            title = m.group(1)
        else:
            items.append(line)
    if not items:
        await update.effective_message.reply_text("🌧️ 보낼 과제 항목을 한 줄 이상 적어 주세요.")
        return

    r = repo(context)
    here = await ensure_space(update, context)
    b = await r.create_broadcast(title, items)
    text, markup = render_broadcast(b, set())

    sent, skipped, failed = [], 0, 0
    for space in await r.all_spaces():
        if space["id"] == here["id"] or space["chat_id"] == ADMIN_ID:
            continue
        names = f"{space.get('name') or ''} {space.get('user_name') or ''}"
        if space.get("disabled") or any(k in names for k in excludes):
            skipped += 1
            continue
        if await send_to_space(context.bot, space, text, markup):
            sent.append(space["id"])
        else:
            failed += 1
        await asyncio.sleep(0.05)  # 텔레그램 전송 속도 제한 대비

    await r.add_broadcast_targets(b["id"], sent)
    await update.effective_message.reply_text(
        f"🌱 공지 #{b['id']} <b>{escape(title)}</b>\n"
        f"• 보냄: <b>{len(sent)}</b>곳\n• 제외: {skipped}곳 (/off · 제외 단어)\n"
        f"• 실패: {failed}곳\n\n결과 보기: <code>/bcr</code> 또는 <code>/bcr {b['id']}</code>")


async def cmd_broadcast_report(update: Update, context):
    if not _is_admin(update):
        return await _deny(update)
    r = repo(context)
    arg = (context.args or [None])[0]
    b = await r.get_broadcast(int(arg) if arg and arg.isdigit() else None)
    if not b:
        await update.effective_message.reply_text("📊 아직 보낸 공지가 없어요.")
        return

    targets = await r.broadcast_targets(b["id"])
    checks = await r.broadcast_checks(b["id"])
    items = b["items"]
    lines = [f"📊 <b>공지 #{b['id']} {escape(b['title'])}</b> — {len(targets)}곳", ""]
    complete = 0
    for sid in targets:
        space = await r.space_by_id(sid)
        if not space:
            continue
        done = {i for s, i in checks if s == sid}
        complete += len(done) == len(items)
        mark = "🌿" if len(done) == len(items) else ("🌱" if done else "🌧️")
        who = escape(space.get("name") or "")
        if space.get("user_name") and space.get("user_name") != space.get("name"):
            who += f" ({escape(space['user_name'])})"
        lines.append(f"{mark} <b>{who}</b> #S{sid} — {len(done)}/{len(items)}")
        for i, item in enumerate(items):
            if i not in done:
                lines.append(f"    🥚 {escape(item)}")
    lines.insert(1, f"전체 완료: {complete}/{len(targets)}곳")
    for chunk in chunk_text("\n".join(lines)):
        await update.effective_message.reply_text(chunk)


async def cmd_reply(update: Update, context):
    if not _is_admin(update):
        return await _deny(update)
    body = command_body(update.effective_message.text or "")
    m = re.match(r"^#?S?(\d+)\s+(.+)$", body, flags=re.S)
    if not m:
        await update.effective_message.reply_text(
            "💬 <b>답변 보내기</b>\n<code>/re 공간번호 내용</code>\n"
            "공간번호는 질문 메시지의 <code>#S12</code> 숫자예요.\n"
            "질문 메시지에 바로 답장해도 전달돼요.")
        return
    await deliver_answer(context, update.effective_message, int(m.group(1)), m.group(2).strip())


async def deliver_answer(context, admin_msg, space_id: int, text: str):
    space = await repo(context).space_by_id(space_id)
    if not space:
        await admin_msg.reply_text(f"🌧️ #S{space_id} 공간을 찾을 수 없어요.")
        return
    ok = await send_to_space(context.bot, space, f"💬 <b>관리자 답변</b>\n\n{escape(text)}")
    if ok:
        await admin_msg.reply_text(f"🌱 #S{space_id} ({escape(space.get('name') or '')})에 답변을 보냈어요.")
    else:
        await admin_msg.reply_text("🌧️ 전송 실패: 봇이 차단되었거나 방에서 나갔을 수 있어요.")
