"""계시록 암송: 장별 시험(배치고사)과 북마크.

장별 시험: 고른 장을 1절부터 순서대로 '주소 보고 암송'. 결과가 진도에 바로 반영된다.
  - 아직 안 외운 절: 완벽 → 외운 구절로 등록(7일 뒤 복습), 조금 틀림 → 다음 날 복습,
    못 외움 → 등록하지 않음 (나중에 새 구절 카드 4단계로 차근차근)
  - 이미 외운 절: 평소 복습처럼 간격 조정
  - 완벽 90% 이상이면 그 장 🏅 통과
  - 중간에 멈추면 다음에 이어서

callback_data
  rs             장 고르기          rs:{장}  그 장 시험 (이어서)      rs:b  북마크만 시험
  ex:{시험id}:{번호}:{act}           act: a 정답 보기 · g0/g1/g2 채점 · t 타이핑 · b 북마크 · s 그만하기
                                     n 다음 절(바로 타이핑할 수 있게 답장 입력창을 연 문제를 보냄)
                                     k 타이핑 결과 카드에서 북마크
  rk             북마크 목록        rb:{구절id}  북마크 해제
"""
from __future__ import annotations

from html import escape

from telegram import ForceReply
from telegram import InlineKeyboardButton as Btn
from telegram import InlineKeyboardMarkup, Update

from . import dates
from .common import repo, safe_edit, send_to_space
from .recite import (COURSE, PASS_RATE, chapter_board, chapter_icon, exam_card_update,
                     exam_summary, grade_typing, toggle_mark, update_mark)
from .recite_handlers import (MARK_TOAST, bookmark_btn, course_verses, delete_quietly, edit_markup,
                              load_marks, reply_typing_result, retire_card, save_mark)

MAX_BOOKMARK_BUTTONS = 15


def _title(exam: dict) -> str:
    return "⭐ 북마크 시험" if exam["kind"] == "bookmark" else f"계시록 {exam['chapter']}장 시험"


def _cb(exam: dict, idx: int, act: str) -> str:
    return f"ex:{exam['id']}:{idx}:{act}"


def _restart_cb(exam: dict) -> str:
    return "rs:b" if exam["kind"] == "bookmark" else f"rs:{exam['chapter']}"


def exam_result_markup(exam: dict, idx: int, typed_id: int, has_next: bool, bookmarked: bool):
    """장별 시험 타이핑 결과의 버튼."""
    first = [Btn("다음 절 ⌨️ ▶" if has_next else "📊 결과 보기", callback_data=_cb(exam, idx, f"n:{typed_id}"))]
    if has_next:
        first.append(Btn("⏸ 그만하기", callback_data=_cb(exam, idx, f"s:{typed_id}")))
    return InlineKeyboardMarkup([first, [bookmark_btn(bookmarked, _cb(exam, idx, f"k:{typed_id}"))]])


def _next_idx(exam: dict) -> int | None:
    return next((i for i, it in enumerate(exam["items"]) if it["g"] is None), None)


# ---------------------------------------------------------------------------
# 화면
# ---------------------------------------------------------------------------
def render_question(exam: dict, idx: int, verse: dict, bookmarked: bool, intro: str | None = None):
    n = len(exam["items"])
    star = " ⭐" if bookmarked else ""
    lines = [intro, ""] if intro else []
    lines += [f"📝 <b>{_title(exam)}</b> · {idx + 1}/{n}{star}", "",
              f"<b>{escape(verse['ref'])}</b>을 암송해 보세요.",
              "<i>다 떠올렸으면 정답을 확인하세요.</i>"]
    rows = [[Btn("👀 정답 보기", callback_data=_cb(exam, idx, "a")),
             Btn("⌨️ 타이핑으로 확인", callback_data=_cb(exam, idx, "t"))],
            [Btn("⏸ 그만하기", callback_data=_cb(exam, idx, "s"))]]
    return "\n".join(lines), InlineKeyboardMarkup(rows)


def render_answer(exam: dict, idx: int, verse: dict, bookmarked: bool):
    n = len(exam["items"])
    star = " ⭐" if bookmarked else ""
    text = (f"📝 <b>{_title(exam)}</b> · {idx + 1}/{n}{star}\n\n"
            f"<b>{escape(verse['ref'])}</b>\n{escape(verse['body'])}\n\n얼마나 정확했나요?")
    rows = [[Btn("✅ 완벽", callback_data=_cb(exam, idx, "g2")),
             Btn("🔸 조금 틀림", callback_data=_cb(exam, idx, "g1")),
             Btn("❌ 못 외움", callback_data=_cb(exam, idx, "g0"))],
            [Btn("⭐ 북마크 해제" if bookmarked else "☆ 북마크", callback_data=_cb(exam, idx, "b")),
             Btn("⏸ 그만하기", callback_data=_cb(exam, idx, "s"))]]
    return text, InlineKeyboardMarkup(rows)


def render_result(exam: dict, by_id: dict[int, dict], newly_passed: bool, intro: str | None = None):
    s = exam_summary(exam["items"])
    rate = s.perfect / s.total * 100 if s.total else 0
    lines = [intro, ""] if intro else []
    lines += [f"📊 <b>{_title(exam)} 결과</b>",
              f"✅ 완벽 {s.perfect} · 🔸 조금 틀림 {s.partial} · ❌ 못 외움 {s.fail}  (완벽 {rate:.0f}%)"]
    if exam["kind"] == "chapter":
        if s.passed:
            lines.append("🏅 <b>통과!</b> 진도판에 🏅가 붙었어요." if newly_passed else "🏅 <b>통과!</b>")
        else:
            need = max(0, int(-(-PASS_RATE * s.total // 1)) - s.perfect)
            lines.append(f"🏅 통과(완벽 {PASS_RATE:.0%})까지 {need}절 남았어요.")
    retry = [by_id[i["v"]]["ref"] for i in exam["items"] if i["g"] != 2 and i["v"] in by_id]
    if retry:
        shown = ", ".join(escape(x) for x in retry[:20]) + (f" 외 {len(retry) - 20}절" if len(retry) > 20 else "")
        lines += ["", f"🔁 다시 볼 구절: {shown}"]
    lines += ["", "<i>완벽·조금 틀림인 절은 복습 일정에 들어가고, 아직 못 외운 절은 "
                  "새 구절 카드로 차근차근 다시 나와요.</i>"]
    rows = [[Btn("🔁 다시 시험보기", callback_data=_restart_cb(exam)),
             Btn("⭐ 북마크만 시험", callback_data="rs:b")],
            [Btn("📖 진도판", callback_data="rv:v")]]
    return "\n".join(lines), InlineKeyboardMarkup(rows)


async def render_picker(r, space: dict, member: dict):
    verses = await course_verses(r, member.get("course", COURSE))
    cards = await r.recite_cards(space["id"])
    marks = await load_marks(r, space["id"])
    passed = set(member.get("passed_chapters") or [])
    n_marks = sum(1 for m in marks.values() if m.get("bookmarked"))
    text = ("📝 <b>장별 시험</b>\n\n"
            "장을 고르면 1절부터 순서대로 <b>주소를 보고 암송</b>하는 시험을 봐요.\n"
            "• 완벽한 절은 <b>외운 구절로 등록</b>돼서 새 구절 카드에서 건너뛰어요.\n"
            f"• 완벽 {PASS_RATE:.0%} 이상이면 🏅 통과!\n"
            "• 중간에 멈춰도 다음에 이어서 볼 수 있어요.")
    cells = [Btn(f"{ch}장 {chapter_icon(n, got, mastered, ch in passed)}", callback_data=f"rs:{ch}")
             for ch, n, got, mastered in chapter_board(verses, cards)]
    rows = [cells[i:i + 4] for i in range(0, len(cells), 4)]
    rows.append([Btn(f"⭐ 북마크만 시험 ({n_marks})", callback_data="rs:b")])
    return text, InlineKeyboardMarkup(rows)


async def render_bookmarks(r, space: dict):
    verses = await course_verses(r)
    by_id = {v["id"]: v for v in verses}
    marks = await load_marks(r, space["id"])
    items = sorted(((by_id[vid], m) for vid, m in marks.items() if m.get("bookmarked") and vid in by_id),
                   key=lambda x: x[0]["seq"])
    if not items:
        return ("⭐ <b>북마크한 구절</b>\n\n아직 없어요.\n"
                "카드나 시험의 정답 화면에서 ☆를 누르면 추가돼요.\n"
                "<i>'못 외움'이 2번 쌓이면 자동으로 ⭐가 붙어요.</i>"), None
    lines = [f"⭐ <b>북마크한 구절</b> ({len(items)})", ""]
    for v, m in items[:40]:
        short = v["body"][:22] + ("…" if len(v["body"]) > 22 else "")
        lines.append(f"• <b>{escape(v['ref'])}</b> {escape(short)}" + (" <i>(자동)</i>" if m.get("auto") else ""))
    if len(items) > 40:
        lines.append(f"… 외 {len(items) - 40}절")
    lines += ["", "<i>북마크한 구절은 복습에 더 자주(최대 3일 간격) 나와요. "
                  "3번 연속 완벽이면 자동으로 해제돼요.</i>"]
    rows = [[Btn("📝 북마크만 시험보기", callback_data="rs:b")]]
    rows += [[Btn(f"☆ {v['ref']} 해제", callback_data=f"rb:{v['id']}")]
             for v, _ in items[:MAX_BOOKMARK_BUTTONS]]
    return "\n".join(lines), InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------------------
# 시험 시작·진행
# ---------------------------------------------------------------------------
async def start_exam(r, space: dict, member: dict, kind: str, chapter: int | None):
    """같은 시험이 진행 중이면 이어서, 아니면 새로 만든다. 문제가 없으면 None."""
    exam = await r.open_exam(space["id"], kind, chapter)
    if exam:
        return exam, True
    verses = await course_verses(r, member.get("course", COURSE))
    if kind == "bookmark":
        marks = await load_marks(r, space["id"])
        chosen = [v for v in verses if marks.get(v["id"], {}).get("bookmarked")]
    else:
        chosen = [v for v in verses if v["chapter"] == chapter]
    if not chosen:
        return None, False
    exam = await r.create_exam({"space_id": space["id"], "kind": kind, "chapter": chapter,
                                "items": [{"v": v["id"], "g": None} for v in chosen]})
    return exam, False


async def _next_verse(r, exam: dict):
    """다음에 풀 (번호, 구절). 본문이 지워진 절은 완벽 처리하고 건너뛴다. 다 풀었으면 (None, None)."""
    by_id = {v["id"]: v for v in await course_verses(r)}
    while (idx := _next_idx(exam)) is not None:
        verse = by_id.get(exam["items"][idx]["v"])
        if verse:
            return idx, verse
        exam["items"][idx]["g"] = 2
        await r.save_exam(exam)
    return None, None


async def send_typing_question(context, space: dict, exam: dict, idx: int, verse: dict, user=None):
    """답장 입력창이 열린 상태로 문제를 보낸다 (버튼을 누르지 않고 바로 입력해서 전송).
    이 메시지 자체가 답장 대상이므로 표시의 카드 번호는 0."""
    marks = await load_marks(repo(context), space["id"])
    star = " ⭐" if marks.get(verse["id"], {}).get("bookmarked") else ""
    mention = f'<a href="tg://user?id={user.id}">{escape(user.first_name)}</a>님, ' if user else ""
    await send_to_space(
        context.bot, space,
        f"📝 <b>{_title(exam)}</b> · {idx + 1}/{len(exam['items'])}{star}\n\n"
        f"⌨️ {mention}<b>{escape(verse['ref'])}</b>을 암송해서 이 메시지에 <b>답장</b>으로 보내 주세요.\n"
        f"<i>띄어쓰기와 문장부호는 채점하지 않아요.</i>\n"
        f"<code>#X{exam['id']}-{idx}-0</code>",
        ForceReply(selective=True, input_field_placeholder=f"{verse['ref']} 입력"),
    )


async def _show_current(r, space: dict, exam: dict, intro: str | None = None, newly_passed=False):
    by_id = {v["id"]: v for v in await course_verses(r)}
    idx = _next_idx(exam)
    if idx is None:
        return render_result(exam, by_id, newly_passed, intro)
    verse = by_id.get(exam["items"][idx]["v"])
    if verse is None:   # 본문이 지워진 절은 건너뜀
        exam["items"][idx]["g"] = 2
        await r.save_exam(exam)
        return await _show_current(r, space, exam, intro, newly_passed)
    marks = await load_marks(r, space["id"])
    return render_question(exam, idx, verse, bool(marks.get(verse["id"], {}).get("bookmarked")), intro)


async def exam_entry(r, space: dict, member: dict, arg: str):
    """/rv 시험 [장 | 북마크]"""
    arg = arg.replace("장", "").strip()
    if arg.isdigit():
        return await _begin(r, space, member, "chapter", int(arg))
    if arg.startswith("북마크"):
        return await _begin(r, space, member, "bookmark", None)
    return await render_picker(r, space, member)


async def _begin(r, space, member, kind, chapter):
    exam, resumed = await start_exam(r, space, member, kind, chapter)
    if exam is None:
        msg = ("⭐ 북마크한 구절이 없어요." if kind == "bookmark"
               else f"🌧️ {chapter}장을 찾을 수 없어요.")
        return msg, None
    done = sum(i["g"] is not None for i in exam["items"])
    intro = f"▶ 이어서 시작해요 ({done}/{len(exam['items'])} 완료)" if resumed else None
    return await _show_current(r, space, exam, intro)


async def grade_exam(r, space: dict, member: dict, exam: dict, idx: int, grade: int):
    """시험 채점과 진도 반영. (북마크 이벤트, 이번에 처음 통과했는지)"""
    item = exam["items"][idx]
    day = dates.today()
    cards = {c["verse_id"]: c for c in await r.recite_cards(space["id"])}
    card = cards.get(item["v"])
    mark = (await load_marks(r, space["id"])).get(item["v"])
    new_mark, event = update_mark(mark, grade)
    fields = exam_card_update(card, grade, day, new_mark["bookmarked"])
    if fields:
        await r.save_card({"space_id": space["id"], "verse_id": item["v"],
                           "learned_on": card["learned_on"] if card else day, **fields})
    item["g"] = grade
    newly_passed = False
    summary = exam_summary(exam["items"])
    if summary.finished:
        exam["finished"] = True
        passed = set(member.get("passed_chapters") or [])
        if exam["kind"] == "chapter" and summary.passed and exam["chapter"] not in passed:
            member["passed_chapters"] = sorted(passed | {exam["chapter"]})
            await r.save_member({"space_id": space["id"], "passed_chapters": member["passed_chapters"]})
            newly_passed = True
    await r.save_exam(exam)
    await save_mark(r, space["id"], item["v"], new_mark)
    return event, newly_passed


# ---------------------------------------------------------------------------
# 버튼
# ---------------------------------------------------------------------------
async def _member_or_warn(r, space, query):
    member = await r.get_member(space["id"])
    if not member:
        await query.answer("먼저 /rv 로 암송을 시작해 주세요.", show_alert=True)
    return member


async def on_rs(update: Update, context, space: dict, args: list[str]):
    """rs / rs:{장} / rs:b"""
    query = update.callback_query
    r = repo(context)
    member = await _member_or_warn(r, space, query)
    if not member:
        return
    await query.answer()
    if not args:
        text, markup = await render_picker(r, space, member)
    elif args[0] == "b":
        text, markup = await _begin(r, space, member, "bookmark", None)
    else:
        text, markup = await _begin(r, space, member, "chapter", int(args[0]))
    await safe_edit(query, text, markup)


async def on_ex(update: Update, context, space: dict, args: list[str]):
    """ex:{시험id}:{번호}:{act}"""
    query = update.callback_query
    r = repo(context)
    exam = await r.get_exam(space["id"], int(args[0]))
    member = await r.get_member(space["id"])
    idx, act = int(args[1]), args[2]
    if not exam or not member or not 0 <= idx < len(exam["items"]):
        await query.answer("시험을 찾을 수 없어요. /rv 시험 으로 다시 시작해 주세요.")
        return
    item = exam["items"][idx]
    by_id = {v["id"]: v for v in await course_verses(r)}
    verse = by_id.get(item["v"])

    if act == "s":
        if len(args) > 3 and args[3].isdigit():
            await delete_quietly(context, space["chat_id"], int(args[3]))
        await query.answer()
        done = sum(i["g"] is not None for i in exam["items"])
        await safe_edit(query, f"⏸ <b>{_title(exam)}</b>을 멈췄어요 ({done}/{len(exam['items'])}).\n"
                               f"다음에 이어서 볼 수 있어요.",
                        InlineKeyboardMarkup([[Btn("▶ 이어서 하기", callback_data=_restart_cb(exam))]]))
        return
    if act == "k":   # 타이핑 결과 카드에서 북마크 켜고 끄기 (내용은 그대로, 버튼만 바꿈)
        marks = await load_marks(r, space["id"])
        new_mark = toggle_mark(marks.get(item["v"]))
        await save_mark(r, space["id"], item["v"], new_mark)
        await query.answer("⭐ 북마크했어요" if new_mark["bookmarked"] else "북마크를 해제했어요")
        typed_id = int(args[3]) if len(args) > 3 and args[3].isdigit() else 0
        await edit_markup(query, exam_result_markup(exam, idx, typed_id, _next_idx(exam) is not None,
                                                    new_mark["bookmarked"]))
        return
    if act == "n":   # 타이핑 채점 결과 → [다음 절 ▶]
        if len(args) > 3 and args[3].isdigit():
            await delete_quietly(context, space["chat_id"], int(args[3]))   # 내가 보낸 답
        await query.answer()
        nidx, nverse = await _next_verse(r, exam)
        if nidx is None:   # 마지막 절이었으면 이 카드를 결과로
            text, markup = await _show_current(r, space, exam)
            await safe_edit(query, text, markup)
            return
        # 답장 입력창이 열린 메시지는 버튼을 달 수 없어서 수정 대신 새로 보낸다
        await delete_quietly(context, space["chat_id"], query.message.message_id)
        await send_typing_question(context, space, exam, nidx, nverse, query.from_user)
        return
    if item["g"] is not None or verse is None:
        await query.answer("이미 채점한 문제예요.")
        text, markup = await _show_current(r, space, exam)
        await safe_edit(query, text, markup)
        return

    marks = await load_marks(r, space["id"])
    bookmarked = bool(marks.get(item["v"], {}).get("bookmarked"))
    if act == "a":
        await query.answer()
        text, markup = render_answer(exam, idx, verse, bookmarked)
    elif act == "b":
        new_mark = toggle_mark(marks.get(item["v"]))
        await save_mark(r, space["id"], item["v"], new_mark)
        await query.answer("⭐ 북마크했어요" if new_mark["bookmarked"] else "북마크를 해제했어요")
        text, markup = render_answer(exam, idx, verse, new_mark["bookmarked"])
    elif act.startswith("g"):
        grade = int(act[1])
        event, newly_passed = await grade_exam(r, space, member, exam, idx, grade)
        await query.answer(MARK_TOAST.get(event) or {2: "✅ 완벽!", 1: "🔸 조금 틀림", 0: "❌ 못 외움"}[grade])
        text, markup = await _show_current(r, space, exam, newly_passed=newly_passed)
    elif act == "t":
        await query.answer()
        user = query.from_user
        mention = f'<a href="tg://user?id={user.id}">{escape(user.first_name)}</a>님, ' if user else ""
        await send_to_space(
            context.bot, space,
            f"⌨️ {mention}<b>{escape(verse['ref'])}</b>을 이 메시지에 <b>답장</b>으로 입력해 주세요.\n"
            f"<i>띄어쓰기와 문장부호는 채점하지 않아요.</i>\n"
            f"<code>#X{exam['id']}-{idx}-{query.message.message_id}</code>",
            ForceReply(selective=True, input_field_placeholder="외운 구절을 입력하세요"),
        )
        return
    else:
        await query.answer()
        return
    await safe_edit(query, text, markup)


async def handle_exam_typing(update: Update, context, space: dict, exam_id: int, idx: int,
                             card_msg_id: int, typed: str):
    r = repo(context)
    msg = update.effective_message
    exam = await r.get_exam(space["id"], exam_id)
    member = await r.get_member(space["id"])
    if not exam or not member or not 0 <= idx < len(exam["items"]):
        await msg.reply_text("🌧️ 시험을 찾을 수 없어요.")
        return
    item = exam["items"][idx]
    if item["g"] is not None:
        await msg.reply_text("이미 채점한 문제예요.")
        return
    verse = next((v for v in await course_verses(r) if v["id"] == item["v"]), None)
    if not verse:
        await msg.reply_text("🌧️ 본문을 찾을 수 없어요.")
        return
    result = grade_typing(typed, verse["body"])
    event, newly_passed = await grade_exam(r, space, member, exam, idx, result.grade)
    if card_msg_id:   # 0이면 문제 메시지 자체에 답한 것 (아래에서 답장 대상으로 지움)
        await retire_card(context, space, card_msg_id)
    has_next = _next_idx(exam) is not None
    note = f"\n\n🏅 <b>{exam['chapter']}장 통과!</b>" if newly_passed else ""
    bookmarked = bool((await load_marks(r, space["id"])).get(item["v"], {}).get("bookmarked"))
    await reply_typing_result(context, space, msg, verse, result, event,
                              exam_result_markup(exam, idx, msg.message_id, has_next, bookmarked), note)


async def on_rk(update: Update, context, space: dict, args: list[str]):
    """rk: 북마크 목록"""
    query = update.callback_query
    await query.answer()
    text, markup = await render_bookmarks(repo(context), space)
    await safe_edit(query, text, markup)


async def on_rb(update: Update, context, space: dict, args: list[str]):
    """rb:{구절id}: 북마크 해제"""
    query = update.callback_query
    r = repo(context)
    vid = int(args[0])
    mark = (await load_marks(r, space["id"])).get(vid)
    if mark and mark.get("bookmarked"):
        await save_mark(r, space["id"], vid, toggle_mark(mark))
        await query.answer("북마크를 해제했어요")
    else:
        await query.answer()
    text, markup = await render_bookmarks(r, space)
    await safe_edit(query, text, markup)
