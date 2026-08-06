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

# 성경 전체 권 및 장수 데이터 (구약 39권 + 신약 27권 = 총 1,189장)
BIBLE_STRUCTURE = [
    ("창", "창세기", 50), ("출", "출애굽기", 40), ("레", "레위기", 27), ("민", "민수기", 36), ("신", "신명기", 34),
    ("수", "여호수아", 24), ("삿", "사사기", 21), ("룻", "룻기", 4), ("삼상", "사무엘상", 31), ("삼하", "사무엘하", 24),
    ("왕상", "열왕기상", 22), ("왕하", "열왕기하", 25), ("대상", "역대상", 29), ("대하", "역대하", 36), ("라", "에스라", 10),
    ("느", "느헤미야", 13), ("에", "에스더", 10), ("욥", "욥기", 42), ("시", "시편", 150), ("잠", "잠언", 31),
    ("전", "전도서", 12), ("아", "아가", 8), ("사", "이사야", 66), ("렘", "예레미야", 52), ("애", "예레미야애가", 5),
    ("겔", "에스겔", 48), ("단", "다니엘", 12), ("호", "호세아", 14), ("요엘", "요엘", 3), ("암", "아모스", 9),
    ("오", "오바디야", 1), ("요나", "요나", 4), ("미", "미가", 7), ("나", "나훔", 3), ("하", "하박국", 3),
    ("습", "스바냐", 3), ("학", "학개", 2), ("슥", "스카리야", 14), ("말", "말라기", 4),
    ("마", "마태복음", 28), ("막", "마가복음", 16), ("눅", "누가복음", 24), ("요", "요한복음", 21), ("행", "사도행전", 28),
    ("롬", "로마서", 16), ("고전", "고린도전서", 16), ("고후", "고린도후서", 13), ("갈", "갈라디아서", 6), ("엡", "에베소서", 6),
    ("빌", "빌립보서", 4), ("골", "골로새서", 4), ("살전", "데살로니가전서", 5), ("살후", "데살로니가후서", 3), ("딤전", "디모데전서", 6),
    ("딤후", "디모데후서", 4), ("딛", "디도서", 3), ("몬", "빌레몬서", 1), ("히", "히브리서", 13), ("야", "야고보서", 5),
    ("벧전", "베드로전서", 5), ("벧후", "베드로후서", 3), ("요일", "요한1서", 5), ("요이", "요한2서", 1), ("요삼", "요한3서", 1),
    ("유", "유다서", 1), ("계", "요한계시록", 22)
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
    end_chapter_idx = min(start_chapter_idx + chunk_size - 1, len(ALL_BIBLE_CHAPTERS) - 1)
    
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
            msg += "\n✝️ **[신약 27권]**\n"

        if current_ch_idx > book_end_idx:
            status_icon = "🐥"
        elif book_start_idx <= current_ch_idx <= book_end_idx:
            status_icon = "🐣"
        else:
            status_icon = "🥚"

        msg += f"{status_icon} `{short_name}` "
        if (idx + 1) % 5 == 0 and idx != 38 and idx != 65:
            msg += "\n"
    return msg

WELCOME_MESSAGES = [
    "👋 **반갑습니다! 공부 및 성경 읽기 계획 봇 안내** 📝\n\n"
    "• **할 일 등록:** 채팅창에 계획 입력 (`[카테고리명]` 지원)\n"
    "• **매일 루틴 등록:** `/routine [내용]` ➔ 매일 반복 루틴\n"
    "• **주간 요일별 과제 등록:** `/weekly_task` ➔ 특정 요일 반복 과제\n"
    "• **알림 시간 설정:** `/time [시:분]` (예: `/time 22:00` / 끄기: `/time off`)\n"
    "• **하루 읽을 장수 설정:** `/bible_pages [장수]` (예: `/bible_pages 5`)\n"
    "• **성경 읽기 시작점 설정:** `/bible_start [분량]` (예: `/bible_start 창 1장`)\n"
    "• **성경 66권 현황판:** `/bible_status` (완료: 🐥 / 읽는중: 🐣 / 미완료: 🥚)\n"
    "• **질문:** `질문: [내용]` (1:1 비공개) / `전체질문: [내용]` (공개)\n"
    "• `/list` : 오늘의 남은 공부 및 성경 체크박스\n"
    "• `/weekly` : 주간 공부/루틴 달성률 + 성경 리포트\n"
    "• `/reset` : 계획 초기화\n\n"
    "✨ 오늘 달성할 계획을 입력하거나 성경 읽기를 시작해 보세요!"
]

CHEERING_MESSAGES = [
    "🔥 멋진 목표네요! 오늘도 차근차근 달성해 봐요!",
    "✨ 등록 완료! 분명 잘 해내실 거예요. 응원합니다!",
    "📝 작은 실행이 모여 큰 성장을 만듭니다. 화이팅!",
    "👏 계획을 세운 것부터 이미 절반은 성공이에요!",
    "🌱 오늘의 노력이 결실을 맺을 거예요. 끝까지 달려봐요!",
]

WEEKDAY_KOR = ["월", "화", "수", "목", "금", "토", "일"]
topic_plans = {}

WEEKLY_TASK_PROMPT_MSG = (
    "📝 **[새로운 한 주, 주간 반복 과제 설정]**\n\n"
    "이번 주 특정 요일에 정기적으로 진행할 공부나 과제가 있다면 아래 명령어로 등록해 보세요!\n\n"
    "**💡 작성 예시:**\n"
    "`/weekly_task` 입력 후 아래 줄에 적어주시면 해당 요일 자정에 자동으로 오늘 할 일로 추가됩니다.\n"
    "```\n"
    "/weekly_task\n"
    "월: 과제 제출, 데이터 분석 강의\n"
    "수: 알고리즘 스터디\n"
    "금: 주간 보고서 작성\n"
    "```"
)


def get_topic_key(update: Update):
    chat_id = update.effective_chat.id
    thread_id = (
        update.effective_message.message_thread_id
        if update.effective_message and update.effective_message.message_thread_id
        else 0
    )
    return (chat_id, thread_id)


def get_korean_date_str():
    now = datetime.datetime.now(pytz.timezone("Asia/Seoul"))
    weekday_str = WEEKDAY_KOR[now.weekday()]
    return now.strftime(f"%m월 %d일 ({weekday_str})")


def get_korean_week_range_str():
    tz = pytz.timezone("Asia/Seoul")
    now = datetime.datetime.now(tz)
    idx = (now.weekday() + 1) % 7
    sun = now - datetime.timedelta(days=idx)
    sat = sun + datetime.timedelta(days=6)
    
    sun_str = f"{sun.strftime('%m월 %d일')} (일)"
    sat_str = f"{sat.strftime('%m월 %d일')} (토)"
    return f"{sun_str} ~ {sat_str}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    user_name = update.effective_user.first_name or "사용자"

    if key not in topic_plans:
        topic_plans[key] = {"user_name": user_name, "plans": [], "bible_ch_idx": 0, "bible_chunk": 4, "weekly_tasks": {}, "notify_time": None}

    welcome_text = random.choice(WELCOME_MESSAGES)
    await update.message.reply_text(welcome_text, parse_mode="Markdown")


async def set_notify_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    user_name = update.effective_user.first_name or "사용자"
    raw_args = " ".join(context.args).strip() if context.args else ""

    if key not in topic_plans:
        topic_plans[key] = {"user_name": user_name, "plans": [], "bible_ch_idx": 0, "bible_chunk": 4, "weekly_tasks": {}, "notify_time": None}

    if not raw_args:
        curr_time = topic_plans[key].get("notify_time")
        status = f"현재 설정된 알림 시간: **{curr_time}**" if curr_time else "현재 알림이 설정되어 있지 않습니다."
        await update.message.reply_text(
            f"⏰ **일일 계획 점검 알림 시간 설정**\n\n"
            f"{status}\n\n"
            f"**사용 예시:**\n"
            f"• `/time 22:00` (매일 밤 10시 알림)\n"
            f"• `/time 08:30` (매일 아침 8시 30분 알림)\n"
            f"• `/time off` (알림 해제)",
            parse_mode="Markdown"
        )
        return

    if raw_args.lower() in ["off", "끄기", "해제"]:
        topic_plans[key]["notify_time"] = None
        await update.message.reply_text("🔕 **일일 계획 점검 알림이 해제되었습니다.**", parse_mode="Markdown")
        return

    time_match = re.match(r"^([0-1]?[0-9]|2[0-3]):([0-5][0-9])$", raw_args)
    if not time_match:
        await update.message.reply_text("❌ 올바른 시간 형식이 아닙니다. `24시간 형식(HH:MM)`으로 입력해 주세요. (예: `/time 22:00`)", parse_mode="Markdown")
        return

    formatted_time = f"{int(time_match.group(1)):02d}:{int(time_match.group(2)):02d}"
    topic_plans[key]["notify_time"] = formatted_time

    await update.message.reply_text(
        f"🔔 **매일 `{formatted_time}`에 미완료 공부 및 성경 점검 알림이 발송됩니다!**",
        parse_mode="Markdown"
    )


async def add_weekly_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    user_name = update.effective_user.first_name or "사용자"

    text_content = update.message.text.strip()
    raw_input = re.sub(r"^/weekly_task\s*", "", text_content).strip()

    if key not in topic_plans:
        topic_plans[key] = {"user_name": user_name, "plans": [], "bible_ch_idx": 0, "bible_chunk": 4, "weekly_tasks": {}, "notify_time": None}

    if not raw_input:
        await update.message.reply_text(WEEKLY_TASK_PROMPT_MSG, parse_mode="Markdown")
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
        day_str = day_part.strip()
        
        valid_days = [d for d in WEEKDAY_KOR if d in day_str]
        tasks = [t.strip() for t in tasks_part.split(",") if t.strip()]

        for d in valid_days:
            if d not in