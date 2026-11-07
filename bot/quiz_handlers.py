"""성구 퀴즈: /q 시간 설정, 관리자 성구 등록(/qa, .txt 파일), /qv 목록, /qd 삭제,
답 버튼 처리, 매시 정각 출제."""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import random
from html import escape

from telegram import Update

from . import dates
from .common import (chunk_text, command_body, ensure_space, load_quiz_status, repo,
                     safe_edit, send_to_space)
from .config import ADMIN_ID
from .quiz import (CATCH_UP_MINUTES, DEFAULT_QUIZ_HOURS, MIN_VERSES, decode_upload, hours_of,
                   make_question, normalize_ref, parse_hours, parse_verse_text, pick_verse)
from .views import render_quiz

log = logging.getLogger(__name__)
rng = random.Random()
MAX_UPLOAD_BYTES = 1_000_000

FORMAT_HELP = (
    "한 줄에 한 구절씩, <b>/</b> 로 칸을 나눠 주세요.\n"
    "<pre>요 3:16 / 하나님이 세상을 사랑하사 독생자를 주심 / 하나님이 세상을 이처럼 사랑하사…\n"
    "시 23:1 / 여호와는 나의 목자 / 여호와는 나의 목자시니 내게 부족함이 없으리로다\n"
    "빌 4:13 / 능력 주시는 자 안에서 모든 것을 할 수 있음</pre>\n"
    "• 순서: 주소 / 핵심 내용 / 전체 본문(없어도 돼요)\n"
    "• 같은 주소를 다시 올리면 새 내용으로 바뀌어요.\n"
    "• <code>#</code>으로 시작하는 줄은 무시해요."
)


def _is_admin(update: Update) -> bool:
    return bool(update.effective_user and update.effective_user.id == ADMIN_ID)


def _hours_text(space: dict) -> str:
    hours = hours_of(space)
    if not hours:
        return "<b>꺼짐</b>"
    return f"<b>{hours[0]}~{hours[1]}시</b> 매시 정각 (하루 {hours[1] - hours[0] + 1}문제)"


# --- /q : 방별 출제 시간 ------------------------------------------------------
async def cmd_quiz(update: Update, context):
    space = await ensure_space(update, context)
    r = repo(context)
    arg = " ".join(context.args or []).strip().lower()
    msg = update.effective_message

    if arg in ("off", "끄기", "해제"):
        await r.update_space(space["id"], {"quiz_hours": None})
        await msg.reply_text("➖ 이 방의 성구 퀴즈를 껐어요. 다시 켜려면 <code>/q on</code>")
        return
    if arg in ("on", "켜기"):
        await r.update_space(space["id"], {"quiz_hours": DEFAULT_QUIZ_HOURS})
        space["quiz_hours"] = DEFAULT_QUIZ_HOURS
        await msg.reply_text(f"📜 성구 퀴즈를 켰어요! {_hours_text(space)}")
        return
    if arg:
        hours = parse_hours(arg)
        if not hours:
            await msg.reply_text("🌧️ <code>/q 13-22</code>처럼 시작-끝 시각(0~23)을 적어 주세요.")
            return
        value = f"{hours[0]}-{hours[1]}"
        await r.update_space(space["id"], {"quiz_hours": value})
        space["quiz_hours"] = value
        await msg.reply_text(f"📜 성구 퀴즈 시간을 바꿨어요! {_hours_text(space)}")
        return

    count = await r.count_verses()
    status = await load_quiz_status(r, space, dates.today())
    lines = ["📜 <b>성구 퀴즈</b>", f"출제 시간: {_hours_text(space)}"]
    if status:
        lines.append(f"오늘: {status.answered}/{status.target}" + (" 🍋" if status.done else ""))
    if count < MIN_VERSES:
        lines.append(f"\n<i>관리자가 성구를 {MIN_VERSES}개 이상 등록하면 퀴즈가 시작돼요.</i>")
    lines += ["", "• <code>/q 9-18</code> 시간 바꾸기",
              "• <code>/q off</code> 끄기 · <code>/q on</code> 켜기 (13~22시)"]
    await msg.reply_text("\n".join(lines))


# --- 관리자: 성구 등록 / 목록 / 삭제 -------------------------------------------
async def _import_verses(update: Update, context, text: str):
    r = repo(context)
    parsed = parse_verse_text(text)
    existing = {v["ref"] for v in await r.list_verses()}
    await r.upsert_verses(parsed.rows)
    added = sum(row["ref"] not in existing for row in parsed.rows)
    total = len(existing | {row["ref"] for row in parsed.rows})

    lines = ["📜 <b>성구 저장 완료</b>",
             f"• 새로 추가: {added}개", f"• 내용 수정: {len(parsed.rows) - added}개",
             f"• 전체: {total}개"]
    if parsed.errors:
        lines += ["", f"⚠️ 건너뛴 줄 {len(parsed.errors)}개"]
        lines += [f"  {escape(e)}" for e in parsed.errors[:10]]
        if len(parsed.errors) > 10:
            lines.append(f"  … 외 {len(parsed.errors) - 10}개")
    if total < MIN_VERSES:
        lines += ["", f"<i>구절이 {MIN_VERSES}개 이상이어야 퀴즈가 나와요.</i>"]
    await update.effective_message.reply_text("\n".join(lines))


async def cmd_quiz_add(update: Update, context):
    if not _is_admin(update):
        await update.effective_message.reply_text("🌧️ 관리자만 사용할 수 있는 명령어예요.")
        return
    body = command_body(update.effective_message.text or "")
    if not body:
        await update.effective_message.reply_text(
            "📜 <b>성구 등록</b>\n<code>/qa</code> 다음 줄부터 붙여넣거나, 봇에게 <b>.txt 파일</b>을 보내 주세요.\n\n"
            + FORMAT_HELP)
        return
    await _import_verses(update, context, body)


async def on_document(update: Update, context):
    """관리자가 보낸 .txt 파일을 성구로 등록. 다른 사람이 보낸 파일은 무시."""
    doc = update.effective_message.document
    if not _is_admin(update) or not doc:
        return
    if not (doc.file_name or "").lower().endswith(".txt"):
        await update.effective_message.reply_text("📜 성구는 <b>.txt</b> 파일로 보내 주세요.\n\n" + FORMAT_HELP)
        return
    if doc.file_size and doc.file_size > MAX_UPLOAD_BYTES:
        await update.effective_message.reply_text("🌧️ 파일이 너무 커요 (1MB 이하).")
        return
    file = await doc.get_file()
    data = bytes(await file.download_as_bytearray())
    await _import_verses(update, context, decode_upload(data))


async def cmd_quiz_list(update: Update, context):
    if not _is_admin(update):
        await update.effective_message.reply_text("🌧️ 관리자만 사용할 수 있는 명령어예요.")
        return
    verses = await repo(context).list_verses()
    if not verses:
        await update.effective_message.reply_text("📜 아직 등록된 성구가 없어요. <code>/qa</code>로 등록해 주세요.")
        return
    lines = [f"📜 <b>저장된 성구 {len(verses)}개</b>", ""]
    lines += [f"{i}. <b>{escape(v['ref'])}</b> — {escape(v['core'])}" for i, v in enumerate(verses, 1)]
    lines += ["", "삭제: <code>/qd 요 3:16</code>"]
    for chunk in chunk_text("\n".join(lines)):
        await update.effective_message.reply_text(chunk)


async def cmd_quiz_delete(update: Update, context):
    if not _is_admin(update):
        await update.effective_message.reply_text("🌧️ 관리자만 사용할 수 있는 명령어예요.")
        return
    ref = normalize_ref(" ".join(context.args or []))
    if not ref:
        await update.effective_message.reply_text("💡 <code>/qd 요 3:16</code>처럼 지울 구절 주소를 적어 주세요.")
        return
    if await repo(context).delete_verse(ref):
        await update.effective_message.reply_text(f"🗑 <b>{escape(ref)}</b>를 삭제했어요.")
    else:
        await update.effective_message.reply_text(f"🌧️ <b>{escape(ref)}</b> 구절을 찾을 수 없어요. <code>/qv</code>로 확인해 주세요.")


# --- 답 버튼 (callback_data: qz:{qid}:{idx} / qz:i) -----------------------------
async def on_quiz_button(update: Update, context, space: dict, args: list[str]):
    query = update.callback_query
    if args == ["i"]:
        await query.answer("📜 매시 정각에 나오는 퀴즈를 오늘 모두 풀면 자동으로 체크돼요!", show_alert=True)
        return

    r = repo(context)
    qid, idx = int(args[0]), int(args[1])
    q = await r.get_question(space["id"], qid)
    if not q or not 0 <= idx < len(q["options"]):
        await query.answer("문제를 찾을 수 없어요.")
        return
    verse = next((v for v in await r.list_verses() if v["id"] == q.get("verse_id")), None)

    if q["answer_idx"] is not None:
        await query.answer("이미 푼 문제예요.")
        text, markup = render_quiz(q, verse)
        await safe_edit(query, text, markup)
        return

    # 그날 문제는 다음 날 새벽 4시 전까지 풀 수 있다 (밤 점검과 같은 기준)
    if not dates.within_grace(q["quiz_date"], dates.now()):
        await query.answer("⏰ 지난 문제예요. 다음 문제를 기다려 주세요!")
        text, _ = render_quiz(q)
        text += (f"\n\n⏰ 지난 문제라 기록되지 않아요. 정답: <b>{escape(q['options'][q['correct_idx']])}</b>")
        await safe_edit(query, text, None)
        return

    correct = idx == q["correct_idx"]
    if not await r.answer_question(space["id"], qid, idx, correct):
        await query.answer("이미 푼 문제예요.")
        return
    q.update(answer_idx=idx, correct=correct)

    if q.get("verse_id") is not None:
        try:
            misses = (await r.verse_misses(space["id"])).get(q["verse_id"], 0)
            new = misses + 1 if not correct else max(0, misses - 1)
            if new != misses:
                await r.set_verse_miss(space["id"], q["verse_id"], new)
        except Exception as e:
            log.warning("틀린 기록 저장 실패: %s", e)

    await query.answer("⭕ 정답!" if correct else "❌ 아쉬워요!")
    status = await load_quiz_status(r, space, q["quiz_date"])
    progress = None
    if status:
        progress = f"📜 오늘 퀴즈 {status.answered}/{status.target}"
        if status.done:
            progress += " — 🍋 오늘 퀴즈 완료!"
    text, markup = render_quiz(q, verse, progress)
    await safe_edit(query, text, markup)


# --- 매시 정각 출제 (jobs.minute_job에서 호출) -----------------------------------
async def issue_due_quizzes(context, spaces: list[dict], now: dt.datetime, gap: float = 0.05):
    if now.minute > CATCH_UP_MINUTES:
        return
    r = repo(context)
    today = now.date()
    marks: set = context.bot_data.setdefault("quiz_marks", set())
    for mark in [m for m in marks if m[1] != today]:
        marks.discard(mark)

    verses = None
    for space in spaces:
        if space.get("disabled"):
            continue
        hours = hours_of(space)
        if not hours or not hours[0] <= now.hour <= hours[1]:
            continue
        mark = (space["id"], today, now.hour)
        if mark in marks:
            continue
        try:
            if verses is None:
                verses = await r.list_verses()
            if len(verses) < MIN_VERSES:
                return
            today_qs = await r.questions_since(space["id"], today)
            marks.add(mark)
            if any(q["hour"] == now.hour for q in today_qs):
                continue
            misses = await r.verse_misses(space["id"])
            verse = pick_verse(verses, misses, {q["verse_id"] for q in today_qs}, rng)
            q = await r.create_question({"space_id": space["id"], "quiz_date": today,
                                         "hour": now.hour, **make_question(verse, verses, rng)})
            if q is None:
                continue
            text, markup = render_quiz(q)
            await send_to_space(context.bot, space, text, markup)
        except Exception:
            log.exception("퀴즈 출제 실패 space=%s", space.get("id"))
        await asyncio.sleep(gap)
