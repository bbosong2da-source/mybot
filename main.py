import asyncio
import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
import os
import random
import re
import threading
from pytz import timezone
from supabase import Client, create_client
from telegram import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ⚠️ 1. 본인의 텔레그램 숫자 ID를 입력하세요
ADMIN_ID = 75036448

# ⚠️ 2. 클라우드 서버 환경변수에서 안전하게 값들을 가져옵니다.
TOKEN = os.environ.get("BOT_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

KST = timezone("Asia/Seoul")

# 💾 Supabase 클라이언트 연결
supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("⚡ Supabase 클라우드 데이터베이스에 연결되었습니다!")
    except Exception as e:
        print(f"❌ Supabase 연결 실패: {e}")
else:
    print("⚠️ SUPABASE_URL 또는 SUPABASE_KEY 환경변수가 설정되지 않았습니다.")

topic_plans = {}
daily_broadcast_state = {}


# 💾 DB 저장 / 불러오기 함수
def save_data():
    if not supabase:
        return
    try:
        for k, v in topic_plans.items():
            key_str = f"{k[0]}_{k[1]}"
            supabase.table("bot_data").upsert(
                {"key": key_str, "data": v}
            ).execute()

        for k, v in daily_broadcast_state.items():
            key_str = f"bc_{k[0]}_{k[1]}"
            supabase.table("bot_data").upsert(
                {"key": key_str, "data": v}
            ).execute()
    except Exception as e:
        print(f"❌ 데이터 저장 중 오류 발생: {e}")


def load_data():
    global topic_plans, daily_broadcast_state
    if not supabase:
        return
    try:
        response = supabase.table("bot_data").select("*").execute()
        rows = response.data
        if rows:
            topic_plans = {}
            daily_broadcast_state = {}
            for row in rows:
                key_str = str(row["key"])
                data = row["data"]
                if key_str.startswith("bc_"):
                    parts = key_str.split("_")
                    if len(parts) >= 3:
                        chat_id, thread_id = int(parts[1]), int(parts[2])
                        daily_broadcast_state[(chat_id, thread_id)] = data
                else:
                    parts = key_str.split("_")
                    if len(parts) >= 2:
                        chat_id, thread_id = int(parts[0]), int(parts[1])
                        topic_plans[(chat_id, thread_id)] = data
            print("💾 Supabase에서 기존 데이터를 안전하게 복원했습니다!")
    except Exception as e:
        print(f"❌ 데이터 불러오기 중 오류 발생: {e}")


# 성경 전체 권 및 장수 데이터 (구약 39권 + 신약 27권 = 총 1,189장)
BIBLE_STRUCTURE = [
    ("창", "창세기", 50),
    ("출", "출애굽기", 40),
    ("레", "레위기", 27),
    ("민", "민수기", 36),
    ("신", "신명기", 34),
    ("수", "여호수아", 24),
    ("삿", "사사기", 21),
    ("룻", "룻기", 4),
    ("삼상", "사무엘상", 31),
    ("삼하", "사무엘하", 24),
    ("왕상", "열왕기상", 22),
    ("왕하", "열왕기하", 25),
    ("대상", "역대상", 29),
    ("대하", "역대하", 36),
    ("라", "에스라", 10),
    ("느", "느헤미야", 13),
    ("에", "에스더", 10),
    ("욥", "욥기", 42),
    ("시", "시편", 150),
    ("잠", "잠언", 31),
    ("전", "전도서", 12),
    ("아", "아가", 8),
    ("사", "이사야", 66),
    ("렘", "예레미야", 52),
    ("애", "예레미야애가", 5),
    ("겔", "에스겔", 48),
    ("단", "다니엘", 12),
    ("호", "호세아", 14),
    ("요엘", "요엘", 3),
    ("암", "아모스", 9),
    ("오", "오바디야", 1),
    ("요나", "요나", 4),
    ("미", "미가", 7),
    ("나", "나훔", 3),
    ("하", "하박국", 3),
    ("습", "스바냐", 3),
    ("학", "학개", 2),
    ("슥", "스가랴", 14),
    ("말", "말라기", 4),
    ("마", "마태복음", 28),
    ("막", "마가복음", 16),
    ("눅", "누가복음", 24),
    ("요", "요한복음", 21),
    ("행", "사도행전", 28),
    ("롬", "로마서", 16),
    ("고전", "고린도전서", 16),
    ("고후", "고린도후서", 13),
    ("갈", "갈라디아서", 6),
    ("엡", "에베소서", 6),
    ("빌", "빌립보서", 4),
    ("골", "골로새서", 4),
    ("살전", "데살로니가전서", 5),
    ("살후", "데살로니가후서", 3),
    ("딤전", "디모데전서", 6),
    ("딤후", "디모데후서", 4),
    ("딛", "디도서", 3),
    ("몬", "빌레몬서", 1),
    ("히", "히브리서", 13),
    ("야", "야고보서", 5),
    ("벧전", "베드로전서", 5),
    ("벧후", "베드로후서", 3),
    ("요일", "요한1서", 5),
    ("요이", "요한2서", 1),
    ("요삼", "요한3서", 1),
    ("유", "유다서", 1),
    ("계", "요한계시록", 22),
]

ALL_BIBLE_CHAPTERS = []
for short_name, full_name, total_ch in BIBLE_STRUCTURE:
    for ch in range(1, total_ch + 1):
        ALL_BIBLE_CHAPTERS.append((short_name, ch))


def get_full_book_name(short_name):
    for s, f, _ in BIBLE_STRUCTURE:
        if s == short_name:
            return f
    return short_name


def get_bible_label(start_chapter_idx, chunk_size):
    end_chapter_idx = min(
        start_chapter_idx + chunk_size - 1, len(ALL_BIBLE_CHAPTERS) - 1
    )
    start_book, start_ch = ALL_BIBLE_CHAPTERS[start_chapter_idx]
    end_book, end_ch = ALL_BIBLE_CHAPTERS[end_chapter_idx]

    if start_book == end_book:
        if start_ch == end_ch:
            return f"{start_book} {start_ch}장"
        else:
            return f"{start_book} {start_ch}장 - {start_book} {end_ch}장"
    else:
        return f"{start_book} {start_ch}장 - {end_book} {end_ch}장"


def generate_bible_status_text(current_ch_idx):
    current_global_idx = 0
    msg = "📖 **[성경 66권 완독 현황판]**\n"
    msg += "완료: 🐥 | 읽는중: 🐣 | 미완료: 🥚\n\n"
    msg += "📜 **[구약 39권]**\n"

    for idx, (short_name, full_name, total_ch) in enumerate(BIBLE_STRUCTURE):
        book_start_idx = current_global_idx
        book_end_idx = current_global_idx + total_ch - 1
        current_global_idx += total_ch

        if idx == 39:
            msg += "\n\n✝️ **[신약 27권]**\n"

        if current_ch_idx > book_end_idx:
            status_icon = "🐥"
        elif book_start_idx <= current_ch_idx <= book_end_idx:
            status_icon = "🐣"
        else:
            status_icon = "🥚"

        msg += f"{status_icon} `{short_name}` "

        if idx < 39:
            if (idx + 1) % 5 == 0 and idx != 38:
                msg += "\n"
        else:
            nt_idx = idx - 39
            if (nt_idx + 1) % 5 == 0 and nt_idx != 26:
                msg += "\n"

    return msg


WELCOME_MESSAGES = [
    "🐦‍⬛️✨ 반갑습니다! 주 7일의 말씀 봇 안내입니다.\n\n"
    "• **할 일 등록:** 채팅창에 계획 보내기\n"
    "  (줄 바꿈 > 다른 할 일)\n"
    "  ([카테고리명] 으로 할일 구분 가능)\n"
    "• **매일 루틴:** `/r [내용]`\n"
    "• **요일별 과제:** `/wt [월화수목금]: 내용`\n"
    "• **알림 시간 설정:** `/t [시:분]` (끄기: `/t off`)\n"
    "• **성경 하루 분량:** `/bp [장수]` (예: `/bp 5`)\n"
    "• **성경 시작점:** `/bs [분량]` (예: `/bs 창 1장`)\n"
    "• **성경 완독 현황판:** `/st`\n"
    "• **질문 보내기:** `질문: [내용]`\n"
    "• **오늘의 할 일:** `/l` (미완료 과제)\n"
    "• **주간 리포트:** `/w`\n"
    "• **매일 루틴 수정:** `/e (기존 > 변경)`\n"
    "• **계획 초기화:** `/rs`\n\n"
    "✨ 오늘 달성할 계획을 입력하거나 성경 읽기를 시작해 보세요!"
]

CHEERING_MESSAGES = [
    "🔥 멋진 목표네요! 오늘도 차근차근 달성해 봐요!",
    "✨ 등록 완료! 분명 잘 해내실 거예요. 응원합니다!",
    "📝 작은 실행이 모여 큰 성장을 만듭니다. 화이팅!",
    "👏 계획을 세운 것부터 이미 절반은 성공이에요!",
    "🌱 오늘의 노력이 결실을 맺을 거예요. 끝까지 달려봐요!",
]

RANDOM_SURPRISE_MESSAGES = [
    "💌 깜짝 응원! 꾸준히 해내는 당신이 정말 멋져요!",
    "🍀 오늘 흘린 땀방울이 곧 결실을 맺을 거예요! 화이팅!",
    "🌟 집중력이 대단하시네요! 잠시 기지개 한번 켜고 가세요~",
    "👏 작은 실행 하나가 모여 큰 성장을 만듭니다. 응원해요!",
    "🧊 영생은 습관 만들기에 달려있다.",
    "🎓 천국 성도가 되려면 나태하면 안되고 부지런해야 한다.",
    "⚡️ 하나님의 말씀을 모른다는 자체는 하나님의 사람이 아니기 때문에 그런 것이다.",
    "🍉 행복. 행하면 복이 옴.",
]

WEEKDAY_KOR = ["월", "화", "수", "목", "금", "토", "일"]

WEEKLY_TASK_PROMPT_MSG = (
    "📝 **[새로운 한 주, 주간 과제 설정]**\n\n"
    "이번 주 특정 요일에 정기적으로 진행할 공부나 과제가 있다면 아래 명령어로 등록해 보세요!\n\n"
    "**💡 작성 예시:**\n"
    "`/wt` 입력 후 아래 줄에 적어주시면 해당 요일 자정에 자동으로 오늘 할 일로 추가됩니다.\n"
    "```\n"
    "/wt\n"
    "월: 과제 제출, 데이터 분석 강의\n"
    "수: 알고리즘 스터디\n"
    "금: 주간 보고서 작성\n"
    "```"
)


def get_topic_key(update: Update):
    chat_id = update.effective_chat.id
    thread_id = (
        update.effective_message.message_thread_id
        if update.effective_message
        and update.effective_message.message_thread_id
        else 0
    )
    return (int(chat_id), int(thread_id))


def get_korean_week_range_str():
    now = datetime.datetime.now(KST)
    idx = (now.weekday() + 1) % 7
    sun = now - datetime.timedelta(days=idx)
    sat = sun + datetime.timedelta(days=6)
    return f"{sun.strftime('%m월 %d일')} (일) ~ {sat.strftime('%m월 %d일')} (토)"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    user_name = update.effective_user.first_name or "사용자"

    if key not in topic_plans:
        topic_plans[key] = {
            "user_name": user_name,
            "plans": [],
            "bible_ch_idx": 0,
            "bible_chunk": 4,
            "weekly_tasks": {},
            "notify_time": None,
            "disabled": False,
        }
        save_data()

    welcome_text = random.choice(WELCOME_MESSAGES)
    await update.message.reply_text(welcome_text, parse_mode="Markdown")


async def bot_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    user_name = update.effective_user.first_name or "사용자"

    if key not in topic_plans:
        topic_plans[key] = {
            "user_name": user_name,
            "plans": [],
            "bible_ch_idx": 0,
            "bible_chunk": 4,
            "weekly_tasks": {},
            "notify_time": None,
            "disabled": True,
        }
    else:
        topic_plans[key]["disabled"] = True
    save_data()

    await update.message.reply_text(
        "🔕 **이 토픽에서 봇 기능이 비활성화되었습니다.**\n\n"
        "자유롭게 메시지나 광고글을 나누실 수 있으며, 전체 공지 과제(/bc) 수신 대상에서도 제외됩니다.\n"
        "다시 켜시려면 `/on`을 입력해 주세요!",
        parse_mode="Markdown",
    )


async def bot_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    user_name = update.effective_user.first_name or "사용자"

    if key not in topic_plans:
        topic_plans[key] = {
            "user_name": user_name,
            "plans": [],
            "bible_ch_idx": 0,
            "bible_chunk": 4,
            "weekly_tasks": {},
            "notify_time": None,
            "disabled": False,
        }
    else:
        topic_plans[key]["disabled"] = False
    save_data()

    await update.message.reply_text(
        "🔔 **이 토픽에서 봇 기능이 다시 활성화되었습니다!**\n\n"
        "이제 작성하시는 일반 메시지가 오늘 할 일로 등록되며, 전체 공지 과제를 수신합니다.",
        parse_mode="Markdown",
    )


async def admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ 관리자만 사용할 수 있는 명령어입니다.")
        return

    text_content = update.message.text.strip()
    raw_args = re.sub(
        r"^/(reply|rp)\s*", "", text_content, flags=re.IGNORECASE
    ).strip()

    if not raw_args or " " not in raw_args:
        await update.message.reply_text(
            "💬 **[관리자 답장 전송 방법]**\n\n"
            "**/rp [토픽ID 또는 사용자ID] [답변 내용]**\n\n"
            "**작성 예시:**\n"
            "• 토픽 방 답장: `/rp 12345 안녕하세요.`\n"
            "• 1:1 개인방 답장: `/rp 987654321 안녕하세요.`",
            parse_mode="Markdown",
        )
        return

    target_id_str, reply_text = raw_args.split(" ", 1)
    if not target_id_str.lstrip("-").isdigit():
        await update.message.reply_text("❌ ID는 숫자로 입력해 주세요.")
        return

    target_id = int(target_id_str)
    reply_text = reply_text.strip()

    target_chat_id, target_thread_id = None, None
    for chat_id, th_id in topic_plans.keys():
        if th_id == target_id and target_id != 0:
            target_chat_id, target_thread_id = chat_id, th_id
            break

    if not target_chat_id:
        target_chat_id, target_thread_id = target_id, None

    msg_to_user = f"💬 **[관리자 답변]**\n\n{reply_text}"
    try:
        await context.bot.send_message(
            chat_id=target_chat_id,
            message_thread_id=target_thread_id,
            text=msg_to_user,
            parse_mode="Markdown",
        )
        await update.message.reply_text(
            f"✅ **[대상 ID: {target_id}]**로 성공적으로 답변을 발송했습니다!"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ 답변 발송 실패: {e}")


async def broadcast_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ 관리자만 사용할 수 있는 명령어입니다.")
        return

    admin_key = get_topic_key(update)
    text_content = update.message.text.strip()
    raw_input = re.sub(
        r"^/(broadcast|bc)\s*", "", text_content, flags=re.IGNORECASE
    ).strip()

    if not raw_input:
        await update.message.reply_text(
            "📢 **[통합 공지 과제 발송 방법]**\n\n"
            "**/bc [과제 내용]**을 입력해 주세요.",
            parse_mode="Markdown",
        )
        return

    lines = raw_input.split("\n")
    new_tasks = [
        line.strip()
        for line in lines
        if line.strip() and not line.strip().startswith("제외:")
    ]
    if not new_tasks:
        await update.message.reply_text("❌ 추가할 과제 항목을 입력해 주세요.")
        return

    success_count = 0
    exclude_keywords = ["광고", "공지", "자료", "자료방", "광고방", "공지방"]
    today_str = datetime.datetime.now(KST).strftime("%Y-%m-%d")

    for t_key in list(topic_plans.keys()):
        if t_key == admin_key:
            continue

        chat_id, thread_id = t_key
        user_info = topic_plans.get(t_key, {})
        u_name = user_info.get("user_name", "")

        if user_info.get("disabled", False) or any(
            k in u_name for k in exclude_keywords
        ):
            continue

        if t_key not in daily_broadcast_state:
            daily_broadcast_state[t_key] = {
                "message_id": None,
                "tasks": [],
                "records": {},
                "created_date": today_str,
            }

        state = daily_broadcast_state[t_key]
        start_idx = len(state["tasks"])
        state["tasks"].extend(new_tasks)
        for i in range(start_idx, len(state["tasks"])):
            state["records"][i] = False

        keyboard = []
        for idx, task in enumerate(state["tasks"]):
            is_done = state["records"].get(idx, False)
            icon = "🐦‍⬛️" if is_done else "🥚"
            keyboard.append(
                [
                    InlineKeyboardButton(
                        f"{icon} {task}",
                        callback_data=f"bctoggle_merged_{idx}",
                    )
                ]
            )
        reply_markup = InlineKeyboardMarkup(keyboard)
        msg_text = "📢 **[전체 공지 과제 목록]**\n\n아래 과제들을 확인하신 후 완료된 항목을 클릭해 주세요!\n"

        try:
            if state.get("message_id"):
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_thread_id=thread_id if thread_id != 0 else None,
                    message_id=state["message_id"],
                    text=msg_text,
                    reply_markup=reply_markup,
                    parse_mode="Markdown",
                )
            else:
                sent_msg = await context.bot.send_message(
                    chat_id=chat_id,
                    message_thread_id=thread_id if thread_id != 0 else None,
                    text=msg_text,
                    reply_markup=reply_markup,
                    parse_mode="Markdown",
                )
                state["message_id"] = sent_msg.message_id
            success_count += 1
        except Exception as e:
            print(f"통합 공지 발송/수정 실패 ({t_key}): {e}")

    save_data()
    await update.message.reply_text(
        f"✅ 총 **{success_count}개** 방의 공지 체크박스에 새 과제가 추가되었습니다!"
    )


async def broadcast_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ 관리자만 사용할 수 있는 명령어입니다.")
        return

    if not daily_broadcast_state:
        await update.message.reply_text(
            "📊 아직 발송된 전체 공지 과제가 없습니다."
        )
        return

    report_msg = "📊 **[전체 공지 과제 수행 결과 리포트]**\n\n"
    for key, state in daily_broadcast_state.items():
        chat_id, thread_id = key
        user_info = topic_plans.get(key, {})
        user_name = user_info.get("user_name", f"사용자 ({chat_id})")

        location_str = (
            f"{user_name} (토픽 #{thread_id})"
            if thread_id != 0
            else f"{user_name}"
        )
        report_msg += f"👤 **{location_str}**\n"

        tasks = state.get("tasks", [])
        records = state.get("records", {})
        for t_idx, task in enumerate(tasks):
            is_done = records.get(t_idx, False)
            status_icon = "✅ 완료" if is_done else "❌ 미완료"
            report_msg += f"  • {task}: `{status_icon}`\n"
        report_msg += "\n"

    await update.message.reply_text(report_msg, parse_mode="Markdown")


async def set_notify_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    user_name = update.effective_user.first_name or "사용자"
    raw_args = " ".join(context.args).strip() if context.args else ""

    if key not in topic_plans:
        topic_plans[key] = {
            "user_name": user_name,
            "plans": [],
            "bible_ch_idx": 0,
            "bible_chunk": 4,
            "weekly_tasks": {},
            "notify_time": None,
            "disabled": False,
        }

    if not raw_args:
        curr_time = topic_plans[key].get("notify_time")
        status = (
            f"현재 설정된 알림 시간: **{curr_time}**"
            if curr_time
            else "현재 알림이 설정되어 있지 않습니다."
        )
        await update.message.reply_text(
            f"⏰ **일일 계획 점검 알림 시간 설정**\n\n{status}\n\n"
            f"**사용 예시:**\n• `/t 22:00` (매일 밤 10시 알림)\n• `/t off` (알림 해제)",
            parse_mode="Markdown",
        )
        return

    if raw_args.lower() in ["off", "끄기", "해제"]:
        topic_plans[key]["notify_time"] = None
        save_data()
        await update.message.reply_text(
            "🔕 **일일 계획 점검 알림이 해제되었습니다.**",
            parse_mode="Markdown",
        )
        return

    time_match = re.match(r"^([0-1]?[0-9]|2[0-3]):([0-5][0-9])$", raw_args)
    if not time_match:
        await update.message.reply_text(
            "❌ 올바른 시간 형식이 아닙니다. `HH:MM` 형식으로 입력해 주세요.",
            parse_mode="Markdown",
        )
        return

    formatted_time = (
        f"{int(time_match.group(1)):02d}:{int(time_match.group(2)):02d}"
    )
    topic_plans[key]["notify_time"] = formatted_time
    save_data()

    await update.message.reply_text(
        f"🔔 **매일 `{formatted_time}`에 오늘의 공부 및 성경 점검 알림이 발송됩니다!**",
        parse_mode="Markdown",
    )


async def add_weekly_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    user_name = update.effective_user.first_name or "사용자"
    now = datetime.datetime.now(KST)
    today_str = now.strftime("%m/%d")
    today_weekday_kor = WEEKDAY_KOR[now.weekday()]

    text_content = update.message.text.strip()
    raw_input = re.sub(
        r"^/(weekly_task|wt)\s*", "", text_content, flags=re.IGNORECASE
    ).strip()

    if key not in topic_plans:
        topic_plans[key] = {
            "user_name": user_name,
            "plans": [],
            "bible_ch_idx": 0,
            "bible_chunk": 4,
            "weekly_tasks": {},
            "notify_time": None,
            "disabled": False,
        }

    if not raw_input:
        await update.message.reply_text(
            WEEKLY_TASK_PROMPT_MSG, parse_mode="Markdown"
        )
        return

    lines = raw_input.split("\n")
    added_summary = []
    if "weekly_tasks" not in topic_plans[key]:
        topic_plans[key]["weekly_tasks"] = {}

    for line in lines:
        line_clean = line.strip()
        if not line_clean or ":" not in line_clean:
            continue

        day_part, tasks_part = line_clean.split(":", 1)
        valid_days = [d for d in WEEKDAY_KOR if d in day_part.strip()]
        tasks = [t.strip() for t in tasks_part.split(",") if t.strip()]

        for d in valid_days:
            if d not in topic_plans[key]["weekly_tasks"]:
                topic_plans[key]["weekly_tasks"][d] = []
            topic_plans[key]["weekly_tasks"][d].extend(tasks)
            topic_plans[key]["weekly_tasks"][d] = list(
                dict.fromkeys(topic_plans[key]["weekly_tasks"][d])
            )
            added_summary.append(f"• **{d}요일:** {', '.join(tasks)}")

            if d == today_weekday_kor:
                existing_tasks = [
                    p["task"]
                    for p in topic_plans[key]["plans"]
                    if p.get("category") == f"[{d}요일 과제]"
                ]
                for t in tasks:
                    if t not in existing_tasks:
                        topic_plans[key]["plans"].append(
                            {
                                "task": t,
                                "category": f"[{d}요일 과제]",
                                "done": False,
                                "date": today_str,
                            }
                        )

    if added_summary:
        save_data()
        plan_text, reply_markup = build_plan_view(key)
        await update.message.reply_text(
            f"📅 **주간 과제가 세팅되었습니다!**\n\n"
            + "\n".join(added_summary)
            + f"\n\n-------------------------\n{plan_text}",
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(
            "❌ 요일과 할 일 형식을 맞춰서 입력해 주세요. (예: `월: 과제 제출`)"
        )


async def bible_pages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    user_name = update.effective_user.first_name or "사용자"
    raw_args = " ".join(context.args).strip() if context.args else ""

    if not raw_args.isdigit() or int(raw_args) <= 0:
        await update.message.reply_text(
            "💡 **하루에 읽을 장수(숫자)를 입력해 주세요.** (예: `/bp 5`)",
            parse_mode="Markdown",
        )
        return

    chunk_size = int(raw_args)
    if key not in topic_plans:
        topic_plans[key] = {
            "user_name": user_name,
            "plans": [],
            "bible_ch_idx": 0,
            "bible_chunk": chunk_size,
            "weekly_tasks": {},
            "notify_time": None,
            "disabled": False,
        }
    else:
        topic_plans[key]["bible_chunk"] = chunk_size
    save_data()

    await update.message.reply_text(
        f"⚙️ **성경 읽기 분량이 하루 `{chunk_size}장`으로 설정되었습니다!**",
        parse_mode="Markdown",
    )


async def bible_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    user_name = update.effective_user.first_name or "사용자"
    raw_args = " ".join(context.args).strip() if context.args else ""

    if not raw_args:
        await update.message.reply_text(
            "💡 예시: `/bs 창 1장`", parse_mode="Markdown"
        )
        return

    matched_ch_idx = -1
    clean_keyword = re.sub(r"\s+", "", raw_args).lower()

    for idx, (b_short, b_ch) in enumerate(ALL_BIBLE_CHAPTERS):
        full_book_name = next(
            (f for s, f, _ in BIBLE_STRUCTURE if s == b_short), ""
        )
        target_str1 = re.sub(r"\s+", "", f"{b_short}{b_ch}장").lower()
        target_str2 = re.sub(r"\s+", "", f"{full_book_name}{b_ch}장").lower()

        if (
            clean_keyword in target_str1
            or clean_keyword in target_str2
            or clean_keyword == f"{b_short}{b_ch}".lower()
        ):
            matched_ch_idx = idx
            break

    if matched_ch_idx == -1:
        await update.message.reply_text(
            f"❌ 입력하신 `{raw_args}` 위치를 성경 데이터에서 찾을 수 없습니다.",
            parse_mode="Markdown",
        )
        return

    if key not in topic_plans:
        topic_plans[key] = {
            "user_name": user_name,
            "plans": [],
            "bible_ch_idx": matched_ch_idx,
            "bible_chunk": 4,
            "weekly_tasks": {},
            "notify_time": None,
            "disabled": False,
        }
    else:
        topic_plans[key]["bible_ch_idx"] = matched_ch_idx

    chunk_size = topic_plans[key].get("bible_chunk", 4)
    target_label = get_bible_label(matched_ch_idx, chunk_size)
    today_str = datetime.datetime.now(KST).strftime("%m/%d")

    plans = topic_plans[key].get("plans", [])
    topic_plans[key]["plans"] = [
        p for p in plans if p.get("is_bible") is not True
    ]

    topic_plans[key]["plans"].append(
        {
            "task": f"성경 묵상: {target_label}",
            "category": "[매일]",
            "done": False,
            "date": today_str,
            "is_bible": True,
            "bible_ch_idx": matched_ch_idx,
        }
    )
    save_data()

    plan_text, reply_markup = build_plan_view(key)
    await update.message.reply_text(
        f"🔥 **성경 묵상 시작 지점이 설정되었습니다!**\n"
        f"• 하루 설정 분량: **{chunk_size}장씩**\n"
        f"• 시작 분량: **{target_label}**\n\n"
        f"-------------------------\n{plan_text}",
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )


async def bible_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    data = topic_plans.get(key, {})
    current_ch_idx = data.get("bible_ch_idx", 0)
    msg = generate_bible_status_text(current_ch_idx)
    await update.message.reply_text(msg, parse_mode="Markdown")


def get_category_priority(category_name):
    if category_name == "[매일]":
        return 1
    elif "요일 과제]" in category_name or "요일 할일]" in category_name:
        return 2
    elif category_name == "[일반]":
        return 99
    else:
        return 3


def build_plan_view(key, visible_indices=None):
    data = topic_plans.get(key, {})
    plans = data.get("plans", [])

    if not plans:
        return (
            "📋 등록된 할 일이 없습니다.\n채팅창에 오늘 할 일이나 `/r`, `/bs`를 입력해 보세요!",
            None,
        )

    plans_with_index = list(enumerate(plans))
    plans_with_index.sort(
        key=lambda x: (
            get_category_priority(x[1].get("category", "")),
            x[1].get("category", ""),
            x[1].get("is_bible", False),
        )
    )

    normal_plans = [
        p for p in plans if "[매일]" not in p.get("category", "")
    ]
    routine_plans = [
        p
        for p in plans
        if "[매일]" in p.get("category", "") and p.get("is_bible") is not True
    ]
    bible_plans = [p for p in plans if p.get("is_bible") is True]

    stat_lines = []
    if normal_plans:
        n_completed = sum(1 for p in normal_plans if p["done"])
        n_total = len(normal_plans)
        n_rate = (n_completed / n_total) * 100 if n_total > 0 else 0
        stat_lines.append(
            f"• **일반 공부 달성률:** `{n_rate:.1f}%` ({n_completed}/{n_total} 완료)"
        )

    if routine_plans:
        r_completed = sum(1 for p in routine_plans if p["done"])
        r_total = len(routine_plans)
        if r_completed == r_total and r_total > 0:
            stat_lines.append(
                f"• **매일 루틴 달성:** `{r_completed}/{r_total} - (달성!)` 🥳"
            )
        else:
            stat_lines.append(
                f"• **매일 루틴 달성:** `{r_completed}/{r_total}`"
            )

    if bible_plans:
        b_completed = sum(1 for p in bible_plans if p["done"])
        b_total = len(bible_plans)
        status_str = "완료 📖" if b_completed == b_total else "진행 중 🔥"
        stat_lines.append(
            f"• **오늘의 성경 묵상:** {bible_plans[0]['task'].replace('성경 묵상: ', '')} (`{status_str}`)"
        )

    stat_str = "\n".join(stat_lines)
    completed_count = sum(1 for p in plans if p["done"])
    total_count = len(plans)

    if completed_count == total_count and total_count > 0:
        text = (
            f"🥳 **ALL CLEAR!** 🎉\n\n"
            f"📊 **오늘의 달성 현황:**\n{stat_str}\n\n"
            f"오늘의 모든 계획을 완수하셨습니다! 수고하셨어요! ✨"
        )
    else:
        text = (
            f"📝 **오늘의 공부 점검**\n\n"
            f"📊 **달성 현황:**\n{stat_str}\n\n"
            f"버튼을 누르면 완료 상태로 전환됩니다.\n"
        )

    category_uncompleted_count = {}
    for _, item in plans_with_index:
        cat = item.get("category", "")
        if cat not in category_uncompleted_count:
            category_uncompleted_count[cat] = 0
        if not item["done"]:
            category_uncompleted_count[cat] += 1

    keyboard = []
    last_category = None

    for real_idx, item in plans_with_index:
        category = item.get("category", "")
        should_show = (
            visible_indices is not None and real_idx in visible_indices
        ) or (
            visible_indices is None
            and category_uncompleted_count.get(category, 0) > 0
        )

        if should_show:
            if category and category != last_category:
                keyboard.append(
                    [
                        InlineKeyboardButton(
                            f"📂 {category}", callback_data="noop"
                        )
                    ]
                )
                last_category = category

            if item.get("is_bible"):
                status_icon = "📖" if item["done"] else "🔥"
            else:
                status_icon = "🐦‍⬛️" if item["done"] else "🥚"

            btn_text = f"{status_icon} {item['task']}"
            keyboard.append(
                [
                    InlineKeyboardButton(
                        btn_text, callback_data=f"toggle_{real_idx}"
                    )
                ]
            )

    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    return text, reply_markup


def build_weekly_view(key):
    data = topic_plans.get(key, {})
    plans = data.get("plans", [])

    if not plans and "bible_ch_idx" not in data:
        return "📅 이번 주에 등록된 공부/성경 읽기 계획이 없습니다.", None

    uncompleted = [p for p in plans if not p["done"]]
    week_range_str = get_korean_week_range_str()
    msg = f"📅 **[이번 주 공부 & 성경 정산 리포트] ({week_range_str})**\n\n"

    normal_plans = [
        p for p in plans if "[매일]" not in p.get("category", "")
    ]
    routine_plans = [
        p
        for p in plans
        if "[매일]" in p.get("category", "") and p.get("is_bible") is not True
    ]
    bible_plans = [p for p in plans if p.get("is_bible") is True]

    if normal_plans:
        n_completed = sum(1 for p in normal_plans if p["done"])
        n_total = len(normal_plans)
        n_rate = (n_completed / n_total) * 100 if n_total > 0 else 0
        msg += f"📊 **주간 일반 공부 달성률:** `{n_rate:.1f}%` ({n_completed}/{n_total} 완료)\n\n"

    if routine_plans:
        msg += "🔄 **[매일 루틴 항목별 달성 현황]**\n"
        routine_names = list(
            dict.fromkeys([p["task"] for p in routine_plans])
        )
        for task_name in routine_names:
            completed_count = sum(
                1
                for p in routine_plans
                if p["task"] == task_name and p["done"]
            )
            if completed_count >= 7:
                msg += f"• **{task_name}:** `{completed_count}/7 - (달성!)` 🥳\n"
            else:
                msg += f"• **{task_name}:** `{completed_count}/7` 완료\n"
        msg += "\n"

    msg += "📖 **[성경 묵상 주간 & 전체 누적 통계]**\n"
    bible_weekly_completed = sum(1 for p in bible_plans if p["done"])
    bible_weekly_rate = (bible_weekly_completed / 7.0) * 100.0
    msg += f"• **이번 주 성경 묵상 달성률:** `{bible_weekly_rate:.1f}%` ({bible_weekly_completed}/7일 완수)\n"

    current_ch_idx = data.get("bible_ch_idx", 0)
    chunk_size = data.get("bible_chunk", 4)

    curr_book_short, _ = ALL_BIBLE_CHAPTERS[min(current_ch_idx, len(ALL_BIBLE_CHAPTERS) - 1)]

    completed_books = 0
    for idx, (b_short, _, _) in enumerate(BIBLE_STRUCTURE):
        if b_short == curr_book_short:
            completed_books = idx
            break
    else:
        if current_ch_idx >= len(ALL_BIBLE_CHAPTERS):
            completed_books = 66

    total_books = len(BIBLE_STRUCTURE)
    overall_rate = (completed_books / total_books) * 100

    current_label = (
        get_bible_label(current_ch_idx, chunk_size)
        if current_ch_idx < len(ALL_BIBLE_CHAPTERS)
        else "완독 완료!"
    )

    msg += f"• **성경 전체 통산 달성률:** `{overall_rate:.1f}%` ({completed_books}/{total_books}권 완독)\n"
    msg += (
        f"• **현재 진행 위치 및 설정:** `{current_label}` (하루 {chunk_size}장씩)\n\n"
    )

    keyboard = []
    if uncompleted:
        msg += f"⚠️ **[미완료된 항목 - 추가 점검 필요]** ({len(uncompleted)}개)\n"
        current_cat = None
        for p in uncompleted:
            cat = p.get("category", "")
            if cat and cat != current_cat:
                msg += f"\n📂 **{cat}**\n"
                keyboard.append(
                    [InlineKeyboardButton(f"📂 {cat}", callback_data="noop")]
                )
                current_cat = cat

            date_str = f" ({p['date']})" if "date" in p else ""
            icon = "🔥" if p.get("is_bible") else "🥚"
            msg += f"  {icon} {p['task']}{date_str}\n"

            real_idx = plans.index(p)
            keyboard.append(
                [
                    InlineKeyboardButton(
                        f"{icon} {p['task']}{date_str}",
                        callback_data=f"toggle_{real_idx}",
                    )
                ]
            )
    else:
        msg += (
            "🎉 이번 주 등록된 모든 공부 및 성경 묵상을 완수하셨습니다!\n"
        )

    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    return msg, reply_markup


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    user_name = update.effective_user.first_name or "사용자"
    sender_id = update.effective_user.id
    chat_id, thread_id = key
    text = update.message.text.strip()
    today_str = datetime.datetime.now(KST).strftime("%m/%d")

    if text.startswith("/"):
        return

    if key in topic_plans and topic_plans[key].get("disabled", False):
        return

    if text.startswith("질문:") or text.startswith("질문 "):
        question_text = re.sub(r"^질문[:\s]*", "", text).strip()
        if not question_text:
            await update.message.reply_text(
                "💡 질문 내용을 작성해 주세요!", parse_mode="Markdown"
            )
            return

        location_label = (
            f"토픽 #{thread_id}"
            if thread_id != 0
            else f"개인방 (ID: `{sender_id}`)"
        )
        admin_msg = (
            f"🔒 **[질문]** {user_name} ({location_label}): {question_text}"
        )
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID, text=admin_msg, parse_mode="Markdown"
            )
            await update.message.reply_text(
                "🔒 질문이 관리자에게 전달되었습니다."
            )
        except Exception as e:
            print(f"질문 전달 실패: {e}")
        return

    if key not in topic_plans:
        topic_plans[key] = {
            "user_name": user_name,
            "plans": [],
            "bible_ch_idx": 0,
            "bible_chunk": 4,
            "weekly_tasks": {},
            "notify_time": None,
            "disabled": False,
        }
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

        assigned_cat = current_category if current_category else "[일반]"
        topic_plans[key]["plans"].append(
            {
                "task": raw_line,
                "category": assigned_cat,
                "done": False,
                "date": today_str,
            }
        )
        added_count += 1

    if added_count > 0:
        save_data()
        cheer = random.choice(CHEERING_MESSAGES)
        plan_text, reply_markup = build_plan_view(key)

        response_msg = (
            f"✅ **{added_count}개의 계획이 추가되었습니다!**\n"
            f"{cheer}\n\n-------------------------\n{plan_text}"
        )
        await update.message.reply_text(
            response_msg, reply_markup=reply_markup, parse_mode="Markdown"
        )


async def add_routine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    user_name = update.effective_user.first_name or "사용자"
    today_str = datetime.datetime.now(KST).strftime("%m/%d")

    if update.message.text:
        lines = update.message.text.split("\n")
        first_line_clean = re.sub(
            r"^/(routine|r)\s*", "", lines[0], flags=re.IGNORECASE
        ).strip()
        routine_lines = (
            [first_line_clean] + lines[1:]
            if len(lines) > 1
            else [first_line_clean]
        )
    else:
        raw_args = " ".join(context.args).strip() if context.args else ""
        routine_lines = [raw_args]

    if key not in topic_plans:
        topic_plans[key] = {
            "user_name": user_name,
            "plans": [],
            "bible_ch_idx": 0,
            "bible_chunk": 4,
            "weekly_tasks": {},
            "notify_time": None,
            "disabled": False,
        }

    added_count = 0
    for line in routine_lines:
        cleaned = line.strip()
        if cleaned:
            topic_plans[key]["plans"].append(
                {
                    "task": cleaned,
                    "category": "[매일]",
                    "done": False,
                    "date": today_str,
                }
            )
            added_count += 1

    if added_count == 0:
        await update.message.reply_text(
            "💡 매일 반복할 루틴을 입력해 주세요!\n예시: `/r 영단어 30개 암기`",
            parse_mode="Markdown",
        )
        return

    save_data()
    plan_text, reply_markup = build_plan_view(key)
    await update.message.reply_text(
        f"🔄 **{added_count}개의 [매일] 루틴이 추가되었습니다!**\n\n-------------------------\n{plan_text}",
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )


async def edit_routine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    data = topic_plans.get(key, {})
    plans = data.get("plans", [])

    text_content = update.message.text.strip()
    raw_input = re.sub(
        r"^/(edit_routine|edit|e)\s*", "", text_content, flags=re.IGNORECASE
    ).strip()

    delimiter = ">" if ">" in raw_input else None
    if not delimiter:
        await update.message.reply_text(
            "💡 형식: `/e 기존루틴 > 새루틴`", parse_mode="Markdown"
        )
        return

    old_name, new_name = [x.strip() for x in raw_input.split(delimiter, 1)]
    modified_count = 0
    for p in plans:
        if "[매일]" in p.get("category", "") and p["task"] == old_name:
            p["task"] = new_name
            modified_count += 1

    if modified_count > 0:
        save_data()
        plan_text, reply_markup = build_plan_view(key)
        await update.message.reply_text(
            f"✏️ **루틴 수정 완료!** `{old_name}` > `{new_name}`\n\n-------------------------\n{plan_text}",
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(
            f"❌ `{old_name}` 항목을 찾을 수 없습니다.",
            parse_mode="Markdown",
        )


async def list_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    text, reply_markup = build_plan_view(key)
    await update.message.reply_text(
        text, reply_markup=reply_markup, parse_mode="Markdown"
    )


async def weekly_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    weekly_text, reply_markup = build_weekly_view(key)
    await update.message.reply_text(
        weekly_text, reply_markup=reply_markup, parse_mode="Markdown"
    )


async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.data == "noop":
        await query.answer()
        return

    chat_id = query.message.chat.id
    thread_id = (
        query.message.message_thread_id
        if query.message.message_thread_id
        else 0
    )
    key = (int(chat_id), int(thread_id))
    data = query.data

    if data.startswith("weekly_opt_"):
        await query.answer()
        if data == "weekly_opt_clear":
            if key in topic_plans:
                plans = topic_plans[key].get("plans", [])
                topic_plans[key]["plans"] = [
                    p for p in plans if p["done"] or p.get("is_bible")
                ]
                save_data()
            await query.edit_message_text(
                "🧹 **이번 주 미완료 항목들이 깔끔하게 정리되었습니다!**",
                parse_mode="Markdown",
            )
        elif data == "weekly_opt_rollover":
            await query.edit_message_text(
                "➡️ **미완료된 항목들이 다음 주로 차곡차곡 이월됩니다!**",
                parse_mode="Markdown",
            )
        return

    if data.startswith("bctoggle_merged_"):
        task_idx = int(data.split("_")[2])
        if key in daily_broadcast_state:
            state = daily_broadcast_state[key]
            curr_val = state["records"].get(task_idx, False)
            state["records"][task_idx] = not curr_val

            if not curr_val and random.random() < 0.1:
                await query.answer(
                    text=random.choice(RANDOM_SURPRISE_MESSAGES), show_alert=True
                )
            else:
                await query.answer()

            keyboard = []
            all_done = True
            for idx, task in enumerate(state["tasks"]):
                is_done = state["records"].get(idx, False)
                if not is_done:
                    all_done = False
                icon = "🐦‍⬛️" if is_done else "🥚"
                keyboard.append(
                    [
                        InlineKeyboardButton(
                            f"{icon} {task}",
                            callback_data=f"bctoggle_merged_{idx}",
                        )
                    ]
                )

            reply_markup = InlineKeyboardMarkup(keyboard)
            msg_text = "📢 **[전체 공지 과제 목록]**\n\n아래 과제들을 확인하신 후 완료된 항목을 클릭해 주세요!\n"

            try:
                await query.edit_message_text(
                    msg_text, reply_markup=reply_markup, parse_mode="Markdown"
                )
            except Exception as e:
                if "Message is not modified" not in str(e):
                    print(f"공지 버튼 수정 실패: {e}")

            save_data()
            if all_done and len(state["tasks"]) > 0 and not curr_val:
                congrat_bc_msg = "🎉 **[전체 공지 과제 ALL CLEAR!]** 🎉\n\n모든 필수 공지 과제를 완수하셨습니다! 수고 많으셨습니다! ✨"
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        message_thread_id=thread_id if thread_id != 0 else None,
                        text=congrat_bc_msg,
                        parse_mode="Markdown",
                    )
                except Exception as e:
                    print(f"공지 축하 메시지 발송 실패: {e}")
        else:
            await query.answer()
        return

    if data.startswith("reset_"):
        await query.answer()
        if data == "reset_tasks":
            if key in topic_plans:
                plans = topic_plans[key].get("plans", [])
                topic_plans[key]["plans"] = [
                    p for p in plans if "[매일]" in p.get("category", "")
                ]
                save_data()
            await query.edit_message_text(
                "🧹 **일반 할 일만 초기화되었습니다.**",
                parse_mode="Markdown",
            )
        elif data == "reset_routines":
            if key in topic_plans:
                plans = topic_plans[key].get("plans", [])
                topic_plans[key]["plans"] = [
                    p for p in plans if "[매일]" not in p.get("category", "")
                ]
                save_data()
            await query.edit_message_text(
                "🧹 **`[매일]` 루틴만 초기화되었습니다.**",
                parse_mode="Markdown",
            )
        elif data == "reset_all":
            if key in topic_plans:
                topic_plans[key]["plans"] = []
                save_data()
            await query.edit_message_text(
                "🧹 **모든 공부 계획과 루틴이 초기화되었습니다.**",
                parse_mode="Markdown",
            )
        elif data == "reset_cancel":
            await query.edit_message_text("❌ 초기화가 취소되었습니다.")
        return

    if data.startswith("toggle_"):
        idx = int(data.split("_")[1])
        topic_data = topic_plans.get(key, {})
        plans = topic_data.get("plans", [])

        if 0 <= idx < len(plans):
            target_item = plans[idx]
            was_done = target_item["done"]
            target_item["done"] = not was_done

            if not was_done and random.random() < 0.1:
                await query.answer(
                    text=random.choice(RANDOM_SURPRISE_MESSAGES), show_alert=True
                )
            else:
                await query.answer()

            is_bible_task = target_item.get("is_bible", False)

            if is_bible_task and target_item["done"]:
                curr_ch_idx = target_item.get("bible_ch_idx", 0)
                chunk_size = topic_data.get("bible_chunk", 4)

                curr_start_book, _ = ALL_BIBLE_CHAPTERS[curr_ch_idx]
                next_ch_idx = (curr_ch_idx + chunk_size) % len(
                    ALL_BIBLE_CHAPTERS
                )
                next_start_book, _ = ALL_BIBLE_CHAPTERS[next_ch_idx]

                topic_data["bible_ch_idx"] = next_ch_idx
                next_label = get_bible_label(next_ch_idx, chunk_size)
                target_item["task"] = f"성경 묵상: {next_label}"
                target_item["done"] = False
                target_item["bible_ch_idx"] = next_ch_idx

                if curr_start_book != next_start_book:
                    full_name = get_full_book_name(curr_start_book)
                    next_full_name = get_full_book_name(next_start_book)
                    status_board_text = generate_bible_status_text(next_ch_idx)
                    congrat_msg = (
                        f"🎉 **축하합니다! [{full_name}] 묵상을 완독하셨습니다!** 👏✨\n\n"
                        f"다음 권인 **[{next_full_name}]**도 힘차게 이어나가 보세요! 🔥\n\n"
                        f"-------------------------\n{status_board_text}"
                    )
                    await context.bot.send_message(
                        chat_id=chat_id,
                        message_thread_id=thread_id if thread_id != 0 else None,
                        text=congrat_msg,
                        parse_mode="Markdown",
                    )

            save_data()
            original_text = query.message.text or ""

            if (
                "정산 리포트" in original_text
                or "누적 통계" in original_text
            ):
                text, reply_markup = build_weekly_view(key)
            else:
                text, reply_markup = build_plan_view(key)
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


async def reset_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    data = topic_plans.get(key, {})
    plans = data.get("plans", [])

    if not plans:
        await update.message.reply_text("📋 초기화할 공부 계획이 없습니다.")
        return

    keyboard = [
        [
            InlineKeyboardButton(
                "📋 일반 할 일만 초기화", callback_data="reset_tasks"
            )
        ],
        [
            InlineKeyboardButton(
                "🔄 [매일] 루틴만 초기화", callback_data="reset_routines"
            )
        ],
        [
            InlineKeyboardButton(
                "💥 전체 초기화", callback_data="reset_all"
            )
        ],
        [InlineKeyboardButton("❌ 취소", callback_data="reset_cancel")],
    ]
    await update.message.reply_text(
        "🧹 **초기화 옵션을 선택해 주세요:**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


async def morning_reminder_job(context: ContextTypes.DEFAULT_TYPE):
    for key, data in topic_plans.items():
        if data.get("disabled", False):
            continue
        chat_id, thread_id = key
        plan_text, reply_markup = build_plan_view(key)

        msg = (
            "🌅 **[좋은 아침입니다! 오늘 하루도 힘차게 시작해 봐요!]**\n\n"
            "오늘 달성할 공부 계획이나 할 일을 채팅창에 입력해 보세요!\n\n"
            f"-------------------------\n{plan_text}"
        )
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                message_thread_id=thread_id if thread_id != 0 else None,
                text=msg,
                reply_markup=reply_markup,
                parse_mode="Markdown",
            )
        except Exception as e:
            print(f"아침 알림 발송 실패 ({key}): {e}")


async def custom_time_reminder_job(context: ContextTypes.DEFAULT_TYPE):
    now_dt = datetime.datetime.now(KST)
    now_str = now_dt.strftime("%H:%M")
    yesterday_date = (now_dt - datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    for key, data in topic_plans.items():
        if data.get("disabled", False):
            continue
        user_notify_time = data.get("notify_time")
        if user_notify_time and user_notify_time == now_str:
            chat_id, thread_id = key
            plans = data.get("plans", [])
            uncompleted = [p for p in plans if not p["done"]]

            if not uncompleted and len(plans) > 0:
                msg = f"🔔 **[오늘의 공부 점검 알림 - {now_str}]**\n\n🥳 오늘 등록된 모든 공부/성경 묵상을 완료하셨습니다! ✨"
                reply_markup = None
            else:
                plan_text, reply_markup = build_plan_view(key)
                msg = (
                    f"🔔 **[오늘의 공부 점검 알림 - {now_str}]**\n\n{plan_text}"
                )

            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    message_thread_id=thread_id if thread_id != 0 else None,
                    text=msg,
                    reply_markup=reply_markup,
                    parse_mode="Markdown",
                )
            except Exception as e:
                print(f"맞춤 알림 발송 실패 ({key}): {e}")

    if now_str == "22:00":
        for key, state in daily_broadcast_state.items():
            chat_id, thread_id = key
            created_date = state.get("created_date")
            if created_date == yesterday_date:
                records = state.get("records", {})
                tasks = state.get("tasks", [])
                has_uncompleted = any(
                    not records.get(i, False) for i in range(len(tasks))
                )

                if has_uncompleted:
                    warning_msg = (
                        "⚠️ **[어제 발송된 공지 과제 미완료 경고]** 🔔\n\n"
                        "아직 체크되지 않은 필수 공지 과제가 남아있습니다!\n"
                        "상단의 **[전체 공지 과제 목록]** 메시지를 확인하시고 완료된 항목을 클릭해 주세요! 💪"
                    )
                    try:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            message_thread_id=thread_id if thread_id != 0 else None,
                            text=warning_msg,
                            parse_mode="Markdown",
                        )
                    except Exception as e:
                        print(f"공지 경고 메시지 발송 실패 ({key}): {e}")


async def saturday_weekly_reminder(context: ContextTypes.DEFAULT_TYPE):
    for key, data in topic_plans.items():
        if data.get("disabled", False):
            continue
        chat_id, thread_id = key
        weekly_text, _ = build_weekly_view(key)
        plans = data.get("plans", [])

        uncompleted_count = sum(
            1 for p in plans if not p["done"] and not p.get("is_bible")
        )
        msg = f"🔔 **[토요일 주간 정산 및 점검 리포트]**\n\n{weekly_text}"

        keyboard = []
        if uncompleted_count > 0:
            msg += "\n\n💡 **이번 주 미완료 항목 처리 방법을 선택해 주세요:**"
            keyboard = [
                [
                    InlineKeyboardButton(
                        "🧹 이번 주 미완료 항목 삭제 (초기화)",
                        callback_data="weekly_opt_clear",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "➡️ 미완료 항목 다음 주로 이월",
                        callback_data="weekly_opt_rollover",
                    )
                ],
            ]

        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        await context.bot.send_message(
            chat_id=chat_id,
            message_thread_id=thread_id if thread_id != 0 else None,
            text=msg,
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )

        await context.bot.send_message(
            chat_id=chat_id,
            message_thread_id=thread_id if thread_id != 0 else None,
            text=WEEKLY_TASK_PROMPT_MSG,
            parse_mode="Markdown",
        )


async def daily_routine_reset_job(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.datetime.now(KST)
    today_str = now.strftime("%m/%d")
    today_weekday_kor = WEEKDAY_KOR[now.weekday()]

    for key, data in topic_plans.items():
        if data.get("disabled", False):
            continue

        plans = data.get("plans", [])

        new_plans = [
            p for p in plans if not (p["done"] and "[일반]" in p.get("category", ""))
        ]

        for p in new_plans:
            if "[매일]" in p.get("category", ""):
                p["done"] = False
                p["date"] = today_str

        weekly_tasks_dict = data.get("weekly_tasks", {})
        if today_weekday_kor in weekly_tasks_dict:
            existing_today_tasks = [
                p["task"]
                for p in new_plans
                if p.get("category") == f"[{today_weekday_kor}요일 과제]"
            ]
            for task_name in weekly_tasks_dict[today_weekday_kor]:
                if task_name not in existing_today_tasks:
                    new_plans.append(
                        {
                            "task": task_name,
                            "category": f"[{today_weekday_kor}요일 과제]",
                            "done": False,
                            "date": today_str,
                        }
                    )

        data["plans"] = new_plans

    save_data()


async def sunday_rollover_job(context: ContextTypes.DEFAULT_TYPE):
    for key, data in topic_plans.items():
        if data.get("disabled", False):
            continue
        plans = data.get("plans", [])
        uncompleted_plans = [p for p in plans if not p["done"]]
        topic_plans[key]["plans"] = uncompleted_plans
        topic_plans[key]["weekly_tasks"] = {}

    save_data()


async def post_init(application):
    try:
        private_commands = [
            BotCommand("s", "봇 시작 및 안내"),
            BotCommand("l", "오늘 할 일 목록"),
            BotCommand("r", "매일 루틴 추가"),
            BotCommand("wt", "요일별 과제 설정"),
            BotCommand("t", "알림 시간 설정"),
            BotCommand("bp", "성경 하루 분량 설정"),
            BotCommand("bs", "성경 시작 지점 설정"),
            BotCommand("st", "성경 완독 현황판"),
            BotCommand("w", "주간 리포트"),
            BotCommand("e", "매일 루틴 수정"),
            BotCommand("rs", "계획 초기화"),
            BotCommand("bc", "[관리자] 통합 공지 과제 발송"),
            BotCommand("rp", "[관리자] 사용자 답장"),
            BotCommand("bcr", "[관리자] 공지 수행 리포트"),
        ]
        await application.bot.set_my_commands(
            commands=private_commands, scope=BotCommandScopeAllPrivateChats()
        )
        await application.bot.delete_my_commands(
            scope=BotCommandScopeAllGroupChats()
        )
    except Exception as e:
        print(f"메뉴 스코프 설정 중 오류 발생: {e}")


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
    threading.Thread(target=run_health_check_server, daemon=True).start()
    load_data()

    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler(["start", "s", "START", "S"], start))
    app.add_handler(CommandHandler(["off", "OFF"], bot_off))
    app.add_handler(CommandHandler(["on", "ON"], bot_on))
    app.add_handler(CommandHandler(["rp", "reply", "RP", "REPLY"], admin_reply))
    app.add_handler(CommandHandler(["r", "routine", "R", "ROUTINE"], add_routine))
    app.add_handler(CommandHandler(["wt", "weekly_task", "WT"], add_weekly_task))
    app.add_handler(CommandHandler(["bc", "broadcast", "BC"], broadcast_task))
    app.add_handler(
        CommandHandler(
            ["bcr", "broadcast_report", "bcrp", "BCR"], broadcast_report
        )
    )
    app.add_handler(CommandHandler(["t", "time", "T"], set_notify_time))
    app.add_handler(CommandHandler(["bp", "bible_pages", "BP"], bible_pages))
    app.add_handler(CommandHandler(["bs", "bible_start", "BS"], bible_start))
    app.add_handler(CommandHandler(["st", "bible_status", "ST"], bible_status))
    app.add_handler(
        CommandHandler(["e", "edit", "edit_routine", "E"], edit_routine)
    )
    app.add_handler(CommandHandler(["l", "list", "ls", "L"], list_plans))
    app.add_handler(CommandHandler(["w", "weekly", "W"], weekly_plans))
    app.add_handler(CommandHandler(["rs", "reset", "RS"], reset_plans))

    app.add_handler(CallbackQueryHandler(button_click))
    app.add_handler(
        MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message)
    )

    job_queue = app.job_queue

    midnight_time = datetime.time(hour=0, minute=0, second=0, tzinfo=KST)
    morning_time = datetime.time(hour=8, minute=0, second=0, tzinfo=KST)
    sat_time = datetime.time(hour=21, minute=0, second=0, tzinfo=KST)

    job_queue.run_daily(morning_reminder_job, time=morning_time)
    job_queue.run_daily(saturday_weekly_reminder, time=sat_time, days=(5,))
    job_queue.run_daily(daily_routine_reset_job, time=midnight_time)
    job_queue.run_daily(sunday_rollover_job, time=midnight_time, days=(6,))

    job_queue.run_repeating(custom_time_reminder_job, interval=60, first=10)

    print("🤖 봇 및 스케줄러가 정상 실행 중입니다...")
    app.run_polling()
