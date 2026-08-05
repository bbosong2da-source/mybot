import os
import datetime
import random
import re
import pytz
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ⚠️ 1. 본인의 텔레그램 숫자 ID를 입력하세요
ADMIN_ID = 123456789

# ⚠️ 2. 클라우드 서버 환경변수에서 안전하게 토큰을 가져옵니다.
TOKEN = os.environ.get("BOT_TOKEN")

# 인사말 및 사용법 메시지 목록 (admin 제외)
WELCOME_MESSAGES = [
    (
        "👋 **반갑습니다! 공부 계획 봇 사용 방법 안내** 📝\n\n"
        "• **할 일 등록:** 채팅창에 계획을 바로 적어주세요. (`[카테고리명]` 입력 시 구분 가능)\n"
        "• **매일 루틴 등록:** `/routine [내용]` ➔ 매일 반복할 루틴 등록 (`[매일]` 카테고리)\n"
        "• **매일 루틴 수정:** `/edit [기존루틴] -> [새루틴]` ➔ 루틴 이름 변경\n"
        "• **비공개 질문:** `질문: [내용]` ➔ 관리자 1:1 전달\n"
        "• **공개 질문:** `전체질문: [내용]` ➔ 토픽방 공유\n"
        "• `/list` : 오늘의 남은 공부 목록 확인\n"
        "• `/weekly` : 이번 주 주간 정산 및 미완료 체크박스 리포트\n"
        "• `/reset` : 할 일 / 루틴 선택 초기화\n\n"
        "✨ 지금 바로 오늘 달성할 계획을 입력해 보세요!"
    ),
    (
        "🔥 **오늘도 힘차게 계획을 세워볼까요?**\n\n"
        "💡 **간단 사용법:**\n"
        "1. 채팅창에 할 일을 입력하면 체크박스가 생성됩니다.\n"
        "2. `/routine [할일]`로 매일 반복될 루틴을 등록하세요.\n"
        "3. `/edit [기존루틴] -> [새루틴]`으로 루틴명을 수정하세요.\n"
        "4. 버튼을 누르면 완료(🐦‍⬛️) 처리됩니다.\n"
        "5. `/list`로 일일 점검, `/weekly`로 주간 점검이 가능합니다.\n"
        "6. 1:1 문의는 `질문: [내용]`, 공유 문의는 `전체질문: [내용]`을 활용하세요!"
    ),
]

CHEERING_MESSAGES = [
    "🔥 멋진 목표네요! 오늘도 차근차근 달성해 봐요!",
    "✨ 등록 완료! 분명 잘 해내실 거예요. 응원합니다!",
    "📝 작은 실행이 모여 큰 성장을 만듭니다. 화이팅!",
    "👏 계획을 세운 것부터 이미 절반은 성공이에요!",
    "🌱 오늘의 노력이 결실을 맺을 거예요. 끝까지 달려봐요!",
]

# 요일 한글 변환 매핑
WEEKDAY_KOR = ["월", "화", "수", "목", "금", "토", "일"]

# 토픽/개인별 데이터 구조
topic_plans = {}


def get_topic_key(update: Update):
    chat_id = update.effective_chat.id
    thread_id = (
        update.effective_message.message_thread_id
        if update.effective_message and update.effective_message.message_thread_id
        else 0
    )
    return (chat_id, thread_id)


# 현재 한국 시간 기준 날짜 텍스트 반환
def get_korean_date_str():
    now = datetime.datetime.now(pytz.timezone("Asia/Seoul"))
    weekday_str = WEEKDAY_KOR[now.weekday()]
    return now.strftime(f"%m월 %d일 ({weekday_str})")


# 이번 주 (일요일 ~ 토요일) 날짜 범위 텍스트 반환
def get_korean_week_range_str():
    tz = pytz.timezone("Asia/Seoul")
    now = datetime.datetime.now(tz)
    idx = (now.weekday() + 1) % 7
    sun = now - datetime.timedelta(days=idx)
    sat = sun + datetime.timedelta(days=6)
    
    sun_str = f"{sun.strftime('%m월 %d일')} (일)"
    sat_str = f"{sat.strftime('%m월 %d일')} (토)"
    return f"{sun_str} ~ {sat_str}"


# 1. /start 명령어
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    user_name = update.effective_user.first_name or "사용자"

    if key not in topic_plans:
        topic_plans[key] = {"user_name": user_name, "plans": []}

    welcome_text = random.choice(WELCOME_MESSAGES)
    await update.message.reply_text(welcome_text, parse_mode="Markdown")


# 2. 체크박스 뷰 생성
def build_plan_view(key, show_all_buttons=False, target_indices=None):
    data = topic_plans.get(key, {})
    plans = data.get("plans", [])

    if not plans:
        return (
            "📋 등록된 할 일이 없습니다.\n채팅창에 오늘 할 일을 입력해 보세요!",
            None,
        )

    normal_plans = [p for p in plans if p.get("category") != "[매일]"]
    routine_plans = [p for p in plans if p.get("category") == "[매일]"]

    stat_lines = []

    if normal_plans:
        n_completed = sum(1 for p in normal_plans if p["done"])
        n_total = len(normal_plans)
        n_rate = (n_completed / n_total) * 100
        stat_lines.append(f"• **일반 공부 달성률:** `{n_rate:.1f}%` ({n_completed}/{n_total} 완료)")

    if routine_plans:
        r_completed = sum(1 for p in routine_plans if p["done"])
        r_total = len(routine_plans)
        if r_completed == r_total and r_total > 0:
            stat_lines.append(f"• **매일 루틴 달성:** `{r_completed}/{r_total} - (달성!)`")
        else:
            stat_lines.append(f"• **매일 루틴 달성:** `{r_completed}/{r_total}`")

    stat_str = "\n".join(stat_lines)

    completed_count = sum(1 for p in plans if p["done"])
    total_count = len(plans)

    if completed_count == total_count and total_count > 0:
        text = (
            f"🥳 **ALL CLEAR!** 🎉\n\n"
            f"📊 **오늘의 달성 현황:**\n{stat_str}\n\n"
            f"오늘의 모든 계획을 완수하셨습니다! 수고하셨어요! ✨"
        )
        return text, None

    text = (
        f"📝 **오늘의 공부 점검**\n\n"
        f"📊 **달성 현황:**\n{stat_str}\n\n"
        f"버튼을 누르면 완료(🐦‍⬛️) 상태로 전환됩니다.\n"
    )

    if target_indices is not None:
        indices_to_show = set(target_indices)
    elif show_all_buttons:
        indices_to_show = set(range(len(plans)))
    else:
        indices_to_show = {i for i, p in enumerate(plans) if not p["done"]}

    keyboard = []
    last_category = None

    for idx, item in enumerate(plans):
        if idx in indices_to_show:
            category = item.get("category", "")

            if category and category != last_category:
                keyboard.append(
                    [InlineKeyboardButton(f"📂 {category}", callback_data="noop")]
                )
                last_category = category

            status_icon = "🐦‍⬛️" if item["done"] else "🥚"
            btn_text = f"{status_icon} {item['task']}"
            keyboard.append(
                [InlineKeyboardButton(btn_text, callback_data=f"toggle_{idx}")]
            )

    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    return text, reply_markup


# 3. 주간(/weekly) 리포트
def build_weekly_view(key):
    data = topic_plans.get(key, {})
    plans = data.get("plans", [])

    if not plans:
        return "📅 이번 주에 등록된 공부 계획이 없습니다.", None

    uncompleted = [p for p in plans if not p["done"]]

    week_range_str = get_korean_week_range_str()
    msg = f"📅 **[이번 주 공부 종합 점검] ({week_range_str})**\n\n"

    normal_plans = [p for p in plans if p.get("category") != "[매일]"]
    routine_plans = [p for p in plans if p.get("category") == "[매일]"]

    if normal_plans:
        n_completed = sum(1 for p in normal_plans if p["done"])
        n_total = len(normal_plans)
        n_rate = (n_completed / n_total) * 100 if n_total > 0 else 0
        msg += f"📊 **주간 일반 공부 달성률:** `{n_rate:.1f}%` ({n_completed}/{n_total} 완료)\n\n"

    if routine_plans:
        msg += "🔄 **[매일 루틴 항목별 달성 현황]**\n"
        routine_counts = {}
        for p in routine_plans:
            task_name = p["task"]
            if task_name not in routine_counts:
                routine_counts[task_name] = sum(1 for r in routine_plans if r["task"] == task_name and r["done"])
        
        for task_name, count in routine_counts.items():
            if count >= 7:
                msg += f"• **{task_name}:** `7/7 - 달성(!)`\n"
            else:
                msg += f"• **{task_name}:** `{count}/7`\n"
        msg += "\n"

    keyboard = []

    if uncompleted:
        msg += f"⚠️ **[미완료된 할 일 - 추가 점검 필요]** ({len(uncompleted)}개)\n"
        current_cat = None

        for p in uncompleted:
            cat = p.get("category", "")
            if cat and cat != current_cat:
                msg += f"\n📂 **{cat}**\n"
                keyboard.append([InlineKeyboardButton(f"📂 {cat}", callback_data="noop")])
                current_cat = cat

            date_str = f" ({p['date']})" if "date" in p else ""

            msg += f"  🥚 {p['task']}{date_str}\n"
            btn_label = f"🥚 {p['task']}{date_str}"

            real_idx = plans.index(p)
            keyboard.append([InlineKeyboardButton(btn_label, callback_data=f"toggle_{real_idx}")])
    else:
        msg += "🎉 모든 계획을 완수하셨습니다! 완벽한 한 주예요!\n"

    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    return msg, reply_markup


# 4. 일반 텍스트 입력 처리
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    user_name = update.effective_user.first_name or "사용자"
    chat_id, thread_id = key
    text = update.message.text.strip()
    today_str = datetime.datetime.now(pytz.timezone("Asia/Seoul")).strftime(
        "%m/%d"
    )

    if text.startswith("전체질문:") or text.startswith("공개질문:"):
        question_text = re.sub(r"^(전체질문|공개질문)[:\s]*", "", text).strip()

        if not question_text:
            await update.message.reply_text(
                "💡 질문 내용을 작성해 주세요!\n예시: `전체질문: 다음 주 스터디 일정 공유 건`",
                parse_mode="Markdown",
            )
            return

        location_label = f"토픽 #{thread_id}" if thread_id != 0 else "개인방"
        admin_msg = (
            f"📢 **[토픽 공개 질문 도착]**\n\n"
            f"👤 **질문자:** {user_name} ({location_label})\n"
            f"💬 **질문 내용:** {question_text}"
        )
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID, text=admin_msg, parse_mode="Markdown"
            )
        except Exception as e:
            print(f"관리자 알림 실패: {e}")

        public_msg = (
            f"📢 **[전체 질문 게시]**\n\n"
            f"👤 **질문자:** {user_name}\n"
            f"💬 **질문:** {question_text}\n\n"
            f"💡 관리자가 확인 후 답변할 예정입니다."
        )
        await update.message.reply_text(public_msg, parse_mode="Markdown")
        return

    elif (
        text.startswith("질문:")
        or text.startswith("질문 ")
        or text.startswith("비공개질문:")
    ):
        question_text = re.sub(r"^(비공개질문|질문)[:\s]*", "", text).strip()

        if not question_text:
            await update.message.reply_text(
                "💡 질문할 내용을 입력해 주세요!\n예시: `질문: 개인 목표 수정 문의드립니다.`",
                parse_mode="Markdown",
            )
            return

        location_label = f"토픽 #{thread_id}" if thread_id != 0 else "개인방"
        admin_msg = (
            f"🔒 **[비공개 1:1 질문 도착]**\n\n"
            f"👤 **질문자:** {user_name} ({location_label})\n"
            f"💬 **질문 내용:** {question_text}"
        )

        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID, text=admin_msg, parse_mode="Markdown"
            )
            await update.message.reply_text(
                "🔒 질문이 관리자에게 비공개로 성공적으로 전달되었습니다!"
            )
        except Exception as e:
            print(f"질문 전달 실패: {e}")
            await update.message.reply_text(
                "❌ 질문 전달 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
            )
        return

    if key not in topic_plans:
        topic_plans[key] = {"user_name": user_name, "plans": []}
    else:
        topic_plans[key]["user_name"] = user_name

    lines = text.split("\n")
    added_count = 0
    current_category = None

    for line in lines:
        raw_line = line.strip()
        if not raw_line:
            continue

        cat_match = re.search(r"^\[\s*(.*?)\s*\]$", raw_line)
        if cat_match:
            cat_name = cat_match.group(1).strip()
            if cat_name:
                current_category = f"[{cat_name}]"
                continue

        cleaned = raw_line
        if cleaned:
            assigned_cat = current_category if current_category else "[일반]"
            topic_plans[key]["plans"].append({
                "task": cleaned,
                "category": assigned_cat,
                "done": False,
                "date": today_str,
            })
            added_count += 1

    if added_count > 0:
        cheer = random.choice(CHEERING_MESSAGES)
        plan_text, reply_markup = build_plan_view(key, show_all_buttons=True)

        response_msg = (
            f"✅ **{added_count}개의 계획이 추가되었습니다!**\n"
            f"{cheer}\n\n"
            f"-------------------------\n"
            f"{plan_text}"
        )

        await update.message.reply_text(
            response_msg, reply_markup=reply_markup, parse_mode="Markdown"
        )


# 🔄 매일 루틴 등록 명령어 (/routine)
async def add_routine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    user_name = update.effective_user.first_name or "사용자"
    today_str = datetime.datetime.now(pytz.timezone("Asia/Seoul")).strftime("%m/%d")

    if update.message.text:
        lines = update.message.text.split("\n")
        first_line = lines[0]
        first_line_clean = re.sub(r"^/routine\s*", "", first_line).strip()
        routine_lines = [first_line_clean] + lines[1:] if len(lines) > 1 else [first_line_clean]
    else:
        raw_args = " ".join(context.args).strip() if context.args else ""
        routine_lines = [raw_args]

    if key not in topic_plans:
        topic_plans[key] = {"user_name": user_name, "plans": []}
    else:
        topic_plans[key]["user_name"] = user_name

    added_count = 0
    for line in routine_lines:
        cleaned = line.strip()
        if cleaned:
            topic_plans[key]["plans"].append({
                "task": cleaned,
                "category": "[매일]",
                "done": False,
                "date": today_str,
            })
            added_count += 1

    if added_count == 0:
        await update.message.reply_text(
            "💡 매일 반복할 루틴을 입력해 주세요!\n예시: `/routine 영단어 30개 암기`",
            parse_mode="Markdown",
        )
        return

    cheer = random.choice(CHEERING_MESSAGES)
    plan_text, reply_markup = build_plan_view(key, show_all_buttons=True)

    response_msg = (
        f"🔄 **{added_count}개의 [매일] 루틴이 추가되었습니다!**\n"
        f"매일 자정에 새로운 루틴이 추가되어 이월/누적 관리됩니다. ✨\n\n"
        f"-------------------------\n"
        f"{plan_text}"
    )

    await update.message.reply_text(
        response_msg, reply_markup=reply_markup, parse_mode="Markdown"
    )


# ✏️ 매일 루틴 수정 명령어 (/edit)
async def edit_routine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    data = topic_plans.get(key, {})
    plans = data.get("plans", [])

    text_content = update.message.text.strip()
    raw_input = re.sub(r"^/(edit_routine|edit)\s*", "", text_content).strip()

    if "->" not in raw_input:
        await update.message.reply_text(
            "💡 루틴 수정 형식이 올바르지 않습니다.\n\n"
            "**사용법:** `/edit 기존루틴명 -> 새루틴명`\n"
            "예시: `/edit 영단어 30개 암기 -> 영단어 50개 암기`",
            parse_mode="Markdown",
        )
        return

    old_name, new_name = [x.strip() for x in raw_input.split("->", 1)]

    if not old_name or not new_name:
        await update.message.reply_text("💡 기존 루틴 이름과 새 루틴 이름을 정확히 입력해 주세요.")
        return

    modified_count = 0
    for p in plans:
        if p.get("category") == "[매일]" and p["task"] == old_name:
            p["task"] = new_name
            modified_count += 1

    if modified_count > 0:
        plan_text, reply_markup = build_plan_view(key, show_all_buttons=True)
        await update.message.reply_text(
            f"✏️ **루틴이 수정되었습니다!**\n"
            f"`{old_name}` ➔ `{new_name}` (총 {modified_count}개 변경됨)\n\n"
            f"-------------------------\n"
            f"{plan_text}",
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(
            f"❌ `[매일]` 루틴 목록에서 `{old_name}` 항목을 찾을 수 없습니다.\n"
            f"`/list`로 현재 등록된 루틴명을 확인해 주세요.",
            parse_mode="Markdown",
        )


# 5. /list 명령어
async def list_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    text, reply_markup = build_plan_view(key, show_all_buttons=False)
    await update.message.reply_text(
        text, reply_markup=reply_markup, parse_mode="Markdown"
    )


# 6. /weekly 명령어
async def weekly_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    weekly_text, reply_markup = build_weekly_view(key)
    await update.message.reply_text(weekly_text, reply_markup=reply_markup, parse_mode="Markdown")


# 7. 버튼 클릭 처리
async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "noop":
        return

    chat_id = query.message.chat.id
    thread_id = (
        query.message.message_thread_id if query.message.message_thread_id else 0
    )
    key = (chat_id, thread_id)

    data = query.data

    if data.startswith("reset_"):
        if data == "reset_tasks":
            if key in topic_plans:
                plans = topic_plans[key].get("plans", [])
                topic_plans[key]["plans"] = [p for p in plans if p.get("category") == "[매일]"]
            await query.edit_message_text("🧹 **일반 할 일만 초기화되었습니다.** (`[매일]` 루틴 유지)", parse_mode="Markdown")
        elif data == "reset_routines":
            if key in topic_plans:
                plans = topic_plans[key].get("plans", [])
                topic_plans[key]["plans"] = [p for p in plans if p.get("category") != "[매일]"]
            await query.edit_message_text("🧹 **`[매일]` 루틴만 초기화되었습니다.** (일반 할 일 유지)", parse_mode="Markdown")
        elif data == "reset_all":
            if key in topic_plans:
                topic_plans[key]["plans"] = []
            await query.edit_message_text("🧹 **모든 공부 계획과 루틴이 초기화되었습니다.**", parse_mode="Markdown")
        elif data == "reset_cancel":
            await query.edit_message_text("❌ 초기화가 취소되었습니다.")
        return

    if data.startswith("toggle_"):
        idx = int(data.split("_")[1])
        topic_data = topic_plans.get(key, {})
        plans = topic_data.get("plans", [])

        if 0 <= idx < len(plans):
            plans[idx]["done"] = not plans[idx]["done"]

            original_text = query.message.text or ""
            
            if "주 종합 점검" in original_text or "이번 주 공부 종합" in original_text:
                text, reply_markup = build_weekly_view(key)
            else:
                target_indices = []
                if (
                    query.message.reply_markup
                    and query.message.reply_markup.inline_keyboard
                ):
                    for row in query.message.reply_markup.inline_keyboard:
                        for btn in row:
                            if btn.callback_data and btn.callback_data.startswith("toggle_"):
                                try:
                                    b_idx = int(btn.callback_data.split("_")[1])
                                    target_indices.append(b_idx)
                                except ValueError:
                                    pass

                if not target_indices:
                    target_indices = None

                text, reply_markup = build_plan_view(key, target_indices=target_indices)

                if "-------------------------" in original_text:
                    header = original_text.split("-------------------------")[0]
                    text = f"{header}-------------------------\n{text}"

            try:
                await query.edit_message_text(
                    text, reply_markup=reply_markup, parse_mode="Markdown"
                )
            except Exception as e:
                if "Message is not modified" not in str(e):
                    print(f"메시지 수정 예외: {e}")


# 8. /reset 명령어
async def reset_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    data = topic_plans.get(key, {})
    plans = data.get("plans", [])

    if not plans:
        await update.message.reply_text("📋 초기화할 공부 계획이 없습니다.")
        return

    keyboard = [
        [InlineKeyboardButton("📋 일반 할 일만 초기화", callback_data="reset_tasks")],
        [InlineKeyboardButton("🔄 [매일] 루틴만 초기화", callback_data="reset_routines")],
        [InlineKeyboardButton("💥 전체 초기화", callback_data="reset_all")],
        [InlineKeyboardButton("❌ 취소", callback_data="reset_cancel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🧹 **초기화 옵션을 선택해 주세요:**",
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )


# 📊 관리자용 전체 요약
def generate_summary_text():
    if not topic_plans or all(
        len(d.get("plans", [])) == 0 for d in topic_plans.values()
    ):
        return None

    date_str = get_korean_date_str()
    summary_text = f"👑 **[일일 공부 현황 전체 요약 - {date_str}]**\n\n"

    for idx, (key, data) in enumerate(topic_plans.items(), 1):
        plans = data.get("plans", [])
        if not plans:
            continue

        user_name = data.get("user_name", "사용자")
        chat_id, thread_id = key

        normal_plans = [p for p in plans if p.get("category") != "[매일]"]
        routine_plans = [p for p in plans if p.get("category") == "[매일]"]

        location_label = f"토픽 #{thread_id}" if thread_id != 0 else "개인방"
        summary_text += f"**{idx}. [{user_name}] ({location_label})**\n"

        if normal_plans:
            n_completed = sum(1 for p in normal_plans if p["done"])
            n_total = len(normal_plans)
            n_rate = (n_completed / n_total) * 100 if n_total > 0 else 0
            summary_text += f"• 일반 달성률: `{n_rate:.1f}%` ({n_completed}/{n_total})\n"

        if routine_plans:
            r_completed = sum(1 for p in routine_plans if p["done"])
            r_total = len(routine_plans)
            if r_completed == r_total and r_total > 0:
                summary_text += f"• 루틴 달성: `{r_completed}/{r_total} - (달성!)`\n"
            else:
                summary_text += f"• 루틴 달성: `{r_completed}/{r_total}`\n"

        current_cat = None
        for p in plans:
            cat = p.get("category", "")
            if cat and cat != current_cat:
                summary_text += f"  📂 {cat}\n"
                current_cat = cat
            icon = "🐦‍⬛️" if p["done"] else "🥚"
            summary_text += f"    {icon} {p['task']}\n"
        summary_text += "\n"

    return summary_text


# 9. /admin 명령어
async def admin_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("🚫 관리자만 사용할 수 있는 기능입니다.")
        return

    summary_text = generate_summary_text()
    if not summary_text:
        await update.message.reply_text(
            "📊 현재 등록된 전체 계획 데이터가 없습니다."
        )
        return

    await update.message.reply_text(summary_text, parse_mode="Markdown")


# 🌅 아침 알림
async def morning_plan_reminder(context: ContextTypes.DEFAULT_TYPE):
    date_str = get_korean_date_str()
    for key, data in topic_plans.items():
        chat_id, thread_id = key
        random_greeting = random.choice(WELCOME_MESSAGES)
        
        text, reply_markup = build_plan_view(key, show_all_buttons=False)
        
        msg = (
            f"🌅 **[{date_str} 아침 알림]**\n"
            f"새로운 하루가 시작되었습니다! ☀️\n\n"
            f"{random_greeting}\n\n"
            f"-------------------------\n"
            f"{text}"
        )
        await context.bot.send_message(
            chat_id=chat_id,
            message_thread_id=thread_id if thread_id != 0 else None,
            text=msg,
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )


# 🌙 밤 점검 알림
async def daily_check_reminder(context: ContextTypes.DEFAULT_TYPE):
    date_str = get_korean_date_str()
    for key, data in topic_plans.items():
        chat_id, thread_id = key
        text, reply_markup = build_plan_view(key, show_all_buttons=False)
        msg = f"⏰ **[{date_str} 밤 22시 공부 점검 알림]**\n\n" + text
        await context.bot.send_message(
            chat_id=chat_id,
            message_thread_id=thread_id if thread_id != 0 else None,
            text=msg,
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )

    summary_text = generate_summary_text()
    if summary_text:
        try:
            admin_msg = f"⏰ **[{date_str} 밤 10시 자동 종합 보고서]**\n\n" + summary_text
            await context.bot.send_message(
                chat_id=ADMIN_ID, text=admin_msg, parse_mode="Markdown"
            )
        except Exception as e:
            print(f"관리자 알림 실패: {e}")


# 🗓️ 토요일 저녁 주간 알림
async def saturday_weekly_reminder(context: ContextTypes.DEFAULT_TYPE):
    for key, data in topic_plans.items():
        chat_id, thread_id = key
        weekly_text, reply_markup = build_weekly_view(key)
        msg = (
            "🔔 **[토요일 주간 정산 및 점검 리포트]**\n\n"
            + weekly_text
            + "\n\n💡 *미완료된 항목은 일요일 자정에 자동으로 다음 주로 이월됩니다!*"
        )
        await context.bot.send_message(
            chat_id=chat_id,
            message_thread_id=thread_id if thread_id != 0 else None,
            text=msg,
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )


# 🔄 매일 자정: [매일] 카테고리 루틴 항목 새롭게 추가
async def daily_routine_reset_job(context: ContextTypes.DEFAULT_TYPE):
    today_str = datetime.datetime.now(pytz.timezone("Asia/Seoul")).strftime("%m/%d")
    for key, data in topic_plans.items():
        plans = data.get("plans", [])
        
        routine_tasks = list(dict.fromkeys([p["task"] for p in plans if p.get("category") == "[매일]"]))
        
        for task_name in routine_tasks:
            plans.append({
                "task": task_name,
                "category": "[매일]",
                "done": False,
                "date": today_str,
            })


# 🔄 일요일 자정 자동 이월 스케줄러
async def sunday_rollover_job(context: ContextTypes.DEFAULT_TYPE):
    for key, data in topic_plans.items():
        plans = data.get("plans", [])
        if not plans:
            continue

        uncompleted_plans = [p for p in plans if not p["done"]]
        topic_plans[key]["plans"] = uncompleted_plans

        chat_id, thread_id = key
        if uncompleted_plans:
            msg = (
                f"🔄 **[새 주 시작 & 할 일 이월 완료]**\n\n"
                f"지난주 미완료된 **{len(uncompleted_plans)}개**의 할 일이 이번 것으로 자동 이월되었습니다!\n"
                f"이번 주도 파이팅입니다! 🔥\n\n"
                f"확인 명령어: `/list` 또는 `/weekly`"
            )
            await context.bot.send_message(
                chat_id=chat_id,
                message_thread_id=thread_id if thread_id != 0 else None,
                text=msg,
                parse_mode="Markdown",
            )


# 📌 명령어 자동완성 팝업 설정
async def post_init(application):
    commands = [
        BotCommand("start", "봇 시작 및 사용법 보기"),
        BotCommand("routine", "매일 반복할 루틴 등록 ([매일] 카테고리)"),
        BotCommand("edit", "등록된 매일 루틴 수정 (/edit 기존 -> 새이름)"),
        BotCommand("list", "오늘의 남은 공부 체크박스 목록 확인"),
        BotCommand("weekly", "주간 종합 점검 및 미완료 목록"),
        BotCommand("reset", "할 일 / 루틴 선택 초기화"),
    ]
    await application.bot.set_my_commands(commands)


# 🌐 Render Web Service 포트 응답용 가짜 헬스체크 서버
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_health_check_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()


if __name__ == "__main__":
    # Render 포트 통과용 웹서버를 백그라운드 쓰레드로 시작
    threading.Thread(target=run_health_check_server, daemon=True).start()

    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("routine", add_routine))
    app.add_handler(CommandHandler(["edit", "edit_routine"], edit_routine))
    app.add_handler(CommandHandler(["list", "ls"], list_plans))
    app.add_handler(CommandHandler("weekly", weekly_plans))
    app.add_handler(CommandHandler("reset", reset_plans))
    app.add_handler(CommandHandler("admin", admin_summary))
    app.add_handler(CallbackQueryHandler(button_click))
    app.add_handler(
        MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message)
    )

    job_queue = app.job_queue
    tz = pytz.timezone("Asia/Seoul")

    morning_time = datetime.time(hour=8, minute=30, second=0, tzinfo=tz)
    job_queue.run_daily(morning_plan_reminder, time=morning_time)

    night_time = datetime.time(hour=22, minute=0, second=0, tzinfo=tz)
    job_queue.run_daily(daily_check_reminder, time=night_time)

    sat_time = datetime.time(hour=21, minute=0, second=0, tzinfo=tz)
    job_queue.run_daily(saturday_weekly_reminder, time=sat_time, days=(6,))

    midnight_time = datetime.time(hour=0, minute=0, second=0, tzinfo=tz)
    job_queue.run_daily(daily_routine_reset_job, time=midnight_time)

    job_queue.run_daily(sunday_rollover_job, time=midnight_time, days=(0,))

    print("🤖 봇 및 스케줄러가 정상 실행 중입니다...")
    app.run_polling()