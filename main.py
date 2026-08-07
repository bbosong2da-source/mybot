import os
import datetime
import random
import re
import pytz
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import BotCommand, BotCommandScopeChat, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from supabase import create_client, Client

# ⚠️ 1. 본인의 텔레그램 숫자 ID를 입력하세요
ADMIN_ID = 75036448

# ⚠️ 2. 클라우드 서버 환경변수에서 안전하게 값들을 가져옵니다.
TOKEN = os.environ.get("BOT_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

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

# 📢 브로드캐스트 통합 관리 및 미완료 경고용 데이터 구조
daily_broadcast_state = {}

# 💾 DB 저장 / 불러오기 함수
def save_data():
    if not supabase:
        return
    try:
        for k, v in topic_plans.items():
            key_str = f"{k[0]}_{k[1]}"
            supabase.table("bot_data").upsert({"key": key_str, "data": v}).execute()
    except Exception as e:
        print(f"❌ 데이터 저장 중 오류 발생: {e}")

def load_data():
    global topic_plans
    if not supabase:
        return
    try:
        response = supabase.table("bot_data").select("*").execute()
        rows = response.data
        if rows:
            topic_plans = {}
            for row in rows:
                key_str = row["key"]
                data = row["data"]
                chat_id, thread_id = map(int, key_str.split("_"))
                topic_plans[(chat_id, thread_id)] = data
            print("💾 Supabase에서 기존 데이터를 안전하게 복원했습니다!")
    except Exception as e:
        print(f"❌ 데이터 불러오기 중 오류 발생: {e}")

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
    "• **알림 시간 설정:** `/t [시:분]`\n"
    "  (끄기: `/t off`)\n"
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
    "☕ 열심히 달려온 자신에게 따뜻한 차 한 잔 선물해 보는 건 어떨까요?",
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
        topic_plans[key] = {"user_name": user_name, "plans": [], "bible_ch_idx": 0, "bible_chunk": 4, "weekly_tasks": {}, "notify_time": None, "disabled": False}
        save_data()

    welcome_text = random.choice(WELCOME_MESSAGES)
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def bot_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    user_name = update.effective_user.first_name or "사용자"

    if key not in topic_plans:
        topic_plans[key] = {"user_name": user_name, "plans": [], "bible_ch_idx": 0, "bible_chunk": 4, "weekly_tasks": {}, "notify_time": None, "disabled": True}
    else:
        topic_plans[key]["disabled"] = True
    save_data()

    await update.message.reply_text(
        "🔕 **이 토픽에서 봇 기능이 비활성화되었습니다.**\n\n"
        "자유롭게 메시지나 광고글을 나누실 수 있으며, 전체 공지 과제(/bc) 수신 대상에서도 제외됩니다.\n"
        "다시 켜시려면 `/on`을 입력해 주세요!",
        parse_mode="Markdown"
    )

async def bot_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    user_name = update.effective_user.first_name or "사용자"

    if key not in topic_plans:
        topic_plans[key] = {"user_name": user_name, "plans": [], "bible_ch_idx": 0, "bible_chunk": 4, "weekly_tasks": {}, "notify_time": None, "disabled": False}
    else:
        topic_plans[key]["disabled"] = False
    save_data()

    await update.message.reply_text(
        "🔔 **이 토픽에서 봇 기능이 다시 활성화되었습니다!**\n\n"
        "이제 작성하시는 일반 메시지가 오늘 할 일로 등록되며, 전체 공지 과제를 수신합니다.",
        parse_mode="Markdown"
    )

async def admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ 관리자만 사용할 수 있는 명령어입니다.")
        return

    text_content = update.message.text.strip()
    raw_args = re.sub(r"^/(reply|rp)\s*", "", text_content, flags=re.IGNORECASE).strip()

    if not raw_args or " " not in raw_args:
        await update.message.reply_text(
            "💬 **[관리자 답장 전송 방법]**\n\n"
            "**/rp [토픽ID 또는 사용자ID] [답변 내용]**\n\n"
            "**작성 예시:**\n"
            "• 토픽 방 답장: `/rp 12345 안녕하세요.`\n"
            "• 1:1 개인방 답장: `/rp 987654321 안녕하세요.`",
            parse_mode="Markdown"
        )
        return

    target_id_str, reply_text = raw_args.split(" ", 1)
    
    if not target_id_str.lstrip("-").isdigit():
        await update.message.reply_text("❌ ID는 숫자로 입력해 주세요.")
        return

    target_id = int(target_id_str)
    reply_text = reply_text.strip()

    target_chat_id = None
    target_thread_id = None

    for (chat_id, th_id) in topic_plans.keys():
        if th_id == target_id and target_id != 0:
            target_chat_id = chat_id
            target_thread_id = th_id
            break

    if not target_chat_id:
        target_chat_id = target_id
        target_thread_id = None

    msg_to_user = f"💬 **[관리자 답변]**\n\n{reply_text}"

    try:
        await context.bot.send_message(
            chat_id=target_chat_id,
            message_thread_id=target_thread_id,
            text=msg_to_user,
            parse_mode="Markdown"
        )
        await update.message.reply_text(f"✅ **[대상 ID: {target_id}]**로 성공적으로 답변을 발송했습니다!")
    except Exception as e:
        await update.message.reply_text(f"❌ 답변 발송 실패: {e}\n(상대방이 봇을 차단했거나 ID가 올바르지 않은지 확인해 주세요.)")

async def broadcast_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ 관리자만 사용할 수 있는 명령어입니다.")
        return

    admin_key = get_topic_key(update)
    text_content = update.message.text.strip()
    raw_input = re.sub(r"^/(broadcast|bc)\s*", "", text_content, flags=re.IGNORECASE).strip()

    if not raw_input:
        await update.message.reply_text(
            "📢 **[통합 공지 과제 추가 발송 방법]**\n\n"
            "**/bc [과제 내용]**을 입력하시면 오늘 발송된 기존 공지 체크박스 아래에 추가로 합쳐집니다!\n\n"
            "**작성 예시:**\n"
            "```\n"
            "/bc\n"
            "주간 질문 작성하기\n"
            "공지사항 숙지 및 체크하기\n"
            "
