import os
import datetime
import random
import re
import pytz
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from supabase import create_client, Client
from telegram import (
    BotCommand,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
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

# ⚠️ 2. 클라우드 서버 환경변수에서 안전하게 토큰 및 Supabase 정보를 가져옵니다.
TOKEN = os.environ.get("BOT_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# Supabase 클라이언트 초기화
supabase_client: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("🌱 Supabase 클라이언트 연결 성공")
    except Exception as e:
        print(f"🌧️ Supabase 연결 실패: {e}")

# 성경 전체 권, 장수 및 장별 총 절수 데이터 (구약 39권 + 신약 27권 = 총 1,189장 / 31,102절)
BIBLE_STRUCTURE = [
    ("창", "창세기", 50, [31, 25, 24, 26, 32, 22, 24, 22, 29, 32, 32, 20, 18, 24, 21, 16, 27, 33, 38, 18, 34, 24, 20, 67, 34, 35, 46, 22, 35, 43, 55, 32, 20, 31, 29, 43, 36, 30, 23, 23, 57, 38, 34, 34, 28, 34, 31, 22, 33, 26]),
    ("출", "출애굽기", 40, [22, 25, 22, 31, 23, 30, 29, 32, 35, 29, 10, 51, 22, 31, 27, 36, 16, 27, 25, 26, 36, 31, 33, 18, 40, 37, 21, 43, 46, 38, 18, 35, 23, 35, 35, 38, 29, 31, 43, 38]),
    ("레", "레위기", 27, [17, 16, 17, 35, 19, 30, 38, 36, 24, 20, 47, 8, 59, 57, 33, 34, 16, 30, 37, 27, 24, 33, 44, 23, 55, 46, 34]),
    ("민", "민수기", 36, [54, 34, 51, 49, 31, 27, 89, 26, 23, 36, 35, 16, 33, 45, 41, 50, 13, 32, 22, 29, 35, 41, 30, 25, 18, 65, 23, 31, 40, 16, 54, 42, 56, 29, 34, 13]),
    ("신", "신명기", 34, [46, 37, 29, 49, 33, 25, 26, 20, 29, 22, 32, 32, 18, 29, 23, 22, 20, 22, 21, 20, 23, 30, 25, 22, 19, 19, 26, 68, 29, 20, 30, 52, 29, 12]),
    ("수", "여호수아", 24, [18, 24, 17, 24, 15, 27, 26, 35, 27, 43, 23, 24, 33, 15, 63, 10, 18, 28, 51, 9, 45, 34, 16, 33]),
    ("삿", "사사기", 21, [36, 23, 31, 24, 31, 40, 25, 35, 57, 18, 40, 15, 25, 20, 20, 31, 13, 31, 30, 48, 25]),
    ("룻", "룻기", 4, [22, 23, 18, 22]),
    ("삼상", "사무엘상", 31, [28, 36, 21, 22, 12, 21, 17, 22, 27, 27, 15, 25, 23, 52, 35, 23, 58, 30, 24, 42, 15, 23, 29, 22, 44, 25, 12, 25, 11, 31, 13]),
    ("삼하", "사무엘하", 24, [27, 32, 39, 12, 25, 23, 29, 18, 13, 19, 27, 31, 39, 33, 37, 23, 29, 33, 43, 26, 22, 51, 39, 25]),
    ("왕상", "열왕기상", 22, [53, 46, 28, 34, 18, 38, 51, 66, 28, 29, 43, 33, 34, 31, 34, 34, 24, 46, 21, 43, 29, 53]),
    ("왕하", "열왕기하", 25, [18, 25, 27, 44, 27, 33, 20, 29, 37, 36, 21, 21, 25, 29, 38, 20, 41, 37, 37, 21, 26, 20, 37, 20, 30]),
    ("대상", "역대상", 29, [54, 55, 24, 43, 26, 81, 40, 40, 44, 14, 47, 40, 14, 17, 29, 43, 27, 17, 19, 8, 30, 19, 32, 31, 31, 32, 34, 21, 30]),
    ("대하", "역대하", 36, [17, 18, 17, 22, 14, 42, 22, 18, 31, 19, 23, 16, 22, 15, 19, 14, 19, 34, 11, 37, 20, 12, 21, 27, 28, 23, 9, 27, 36, 27, 21, 33, 25, 33, 27, 23]),
    ("라", "에스라", 10, [11, 70, 13, 24, 17, 22, 28, 36, 15, 44]),
    ("느", "느헤미야", 13, [11, 20, 32, 23, 19, 19, 73, 18, 38, 39, 36, 47, 31]),
    ("에", "에스더", 10, [22, 23, 15, 14, 14, 14, 10, 17, 32, 3]),
    ("욥", "욥기", 42, [22, 13, 26, 21, 27, 30, 21, 22, 35, 22, 20, 25, 28, 22, 35, 22, 16, 21, 29, 29, 34, 30, 17, 25, 6, 14, 23, 28, 25, 31, 40, 22, 33, 37, 16, 33, 24, 41, 30, 24, 34, 17]),
    ("시", "시편", 150, [6, 12, 8, 8, 12, 10, 17, 9, 20, 18, 7, 8, 6, 7, 5, 11, 15, 50, 14, 9, 13, 31, 6, 10, 22, 12, 14, 9, 11, 12, 24, 11, 22, 22, 28, 12, 40, 22, 13, 17, 13, 11, 5, 26, 17, 11, 9, 14, 20, 23, 19, 9, 6, 7, 23, 13, 11, 11, 17, 12, 8, 12, 11, 10, 13, 20, 7, 35, 36, 5, 24, 20, 28, 23, 10, 12, 20, 72, 13, 19, 16, 8, 18, 12, 13, 17, 7, 18, 52, 17, 16, 15, 5, 23, 11, 13, 12, 9, 9, 5, 8, 28, 22, 35, 45, 48, 43, 13, 31, 7, 10, 10, 9, 8, 18, 19, 2, 29, 176, 7, 8, 9, 4, 8, 5, 6, 5, 6, 8, 8, 3, 18, 3, 3, 21, 26, 9, 8, 24, 13, 10, 7, 12, 15, 21, 10, 20, 14, 9, 6]),
    ("잠", "잠언", 31, [33, 22, 35, 27, 23, 35, 27, 36, 18, 32, 31, 28, 25, 35, 33, 33, 28, 24, 29, 30, 31, 29, 35, 34, 28, 28, 27, 28, 27, 33, 31]),
    ("전", "전도서", 12, [18, 26, 22, 16, 20, 12, 29, 17, 18, 20, 10, 14]),
    ("아", "아가", 8, [17, 17, 11, 16, 16, 13, 13, 14]),
    ("사", "이사야", 66, [31, 22, 26, 6, 30, 13, 25, 22, 21, 34, 16, 6, 22, 32, 9, 14, 14, 7, 25, 6, 17, 25, 18, 23, 12, 21, 13, 29, 24, 33, 20, 20, 24, 17, 10, 22, 38, 22, 8, 31, 29, 25, 28, 28, 25, 13, 15, 22, 26, 11, 23, 15, 12, 17, 13, 12, 21, 14, 21, 22, 11, 12, 19, 12, 25, 24]),
    ("렘", "예레미야", 52, [19, 37, 25, 31, 31, 30, 34, 22, 26, 25, 23, 17, 27, 22, 21, 21, 27, 23, 15, 18, 14, 30, 40, 10, 38, 24, 22, 17, 32, 24, 40, 44, 26, 22, 19, 32, 21, 28, 18, 16, 18, 22, 13, 30, 5, 28, 7, 47, 39, 46, 64, 34]),
    ("애", "예레미야애가", 5, [22, 22, 66, 22, 22]),
    ("겔", "에스겔", 48, [28, 10, 27, 17, 17, 14, 27, 18, 11, 22, 25, 28, 23, 23, 8, 63, 24, 32, 14, 49, 32, 31, 49, 27, 17, 21, 36, 26, 21, 26, 18, 32, 33, 31, 15, 38, 28, 23, 29, 49, 26, 20, 27, 31, 25, 24, 31, 35]),
    ("단", "다니엘", 12, [21, 49, 30, 37, 31, 28, 28, 27, 27, 21, 45, 13]),
    ("호", "호세아", 14, [11, 23, 5, 19, 15, 11, 16, 14, 17, 15, 12, 14, 16, 9]),
    ("요엘", "요엘", 3, [20, 32, 21]),
    ("암", "아모스", 9, [15, 16, 15, 13, 27, 14, 17, 14, 15]),
    ("오", "오바디야", 1, [21]),
    ("요나", "요나", 4, [17, 10, 10, 11]),
    ("미", "미가", 7, [16, 13, 12, 13, 15, 16, 20]),
    ("나", "나훔", 3, [15, 13, 19]),
    ("하", "하박국", 3, [17, 20, 19]),
    ("습", "스바냐", 3, [18, 15, 20]),
    ("학", "학개", 2, [15, 23]),
    ("슥", "스카리야", 14, [21, 13, 10, 14, 11, 15, 14, 23, 17, 12, 17, 14, 9, 21]),
    ("말", "말라기", 4, [14, 17, 18, 6]),
    ("마", "마태복음", 28, [25, 23, 17, 25, 48, 34, 29, 34, 38, 42, 30, 50, 58, 36, 39, 28, 27, 35, 30, 34, 46, 46, 39, 51, 46, 75, 66, 20]),
    ("막", "마가복음", 16, [45, 28, 35, 41, 43, 56, 37, 38, 50, 52, 33, 44, 37, 72, 47, 20]),
    ("눅", "누가복음", 24, [80, 52, 38, 44, 39, 49, 50, 56, 62, 42, 54, 59, 35, 35, 32, 31, 37, 43, 48, 47, 38, 71, 56, 53]),
    ("요", "요한복음", 21, [51, 25, 36, 54, 47, 71, 53, 59, 41, 42, 57, 50, 38, 31, 27, 33, 26, 40, 42, 31, 25]),
    ("행", "사도행전", 28, [26, 47, 26, 37, 42, 15, 60, 40, 43, 48, 30, 25, 52, 28, 41, 40, 34, 28, 41, 38, 40, 30, 35, 27, 27, 32, 44, 31]),
    ("롬", "로마서", 16, [32, 29, 31, 25, 21, 23, 25, 39, 33, 21, 36, 21, 14, 23, 33, 27]),
    ("고전", "고린도전서", 16, [31, 16, 23, 21, 13, 20, 40, 13, 27, 33, 34, 31, 13, 40, 58, 24]),
    ("고후", "고린도후서", 13, [24, 17, 18, 18, 21, 18, 16, 24, 15, 18, 33, 21, 13]),
    ("갈", "갈라디아서", 6, [24, 21, 29, 31, 26, 18]),
    ("엡", "에베소서", 6, [23, 22, 21, 32, 33, 24]),
    ("빌", "빌립보서", 4, [30, 30, 21, 23]),
    ("골", "골로새서", 4, [29, 23, 25, 18]),
    ("살전", "데살로니가전서", 5, [10, 20, 13, 18, 28]),
    ("살후", "데살로니가후서", 3, [12, 17, 18]),
    ("딤전", "디모데전서", 6, [20, 15, 16, 16, 25, 21]),
    ("딤후", "디모데후서", 4, [18, 26, 17, 22]),
    ("딛", "디도서", 3, [16, 15, 15]),
    ("몬", "빌레몬서", 1, [25]),
    ("히", "히브리서", 13, [14, 18, 19, 16, 14, 20, 28, 13, 28, 39, 40, 29, 25]),
    ("야", "야고보서", 5, [27, 26, 18, 17, 20]),
    ("벧전", "베드로전서", 5, [25, 25, 22, 19, 14]),
    ("벧후", "베드로후서", 3, [21, 22, 18]),
    ("요일", "요한1서", 5, [10, 29, 24, 21, 21]),
    ("요이", "요한2서", 1, [13]),
    ("요삼", "요한3서", 1, [15]),
    ("유", "유다서", 1, [25]),
    ("계", "요한계시록", 22, [20, 29, 22, 11, 14, 17, 17, 13, 21, 11, 19, 17, 18, 20, 8, 21, 18, 24, 21, 15, 27, 21])
]

ALL_BIBLE_CHAPTERS = []
ALL_BIBLE_VERSES = []

for short_name, full_name, total_ch, verse_counts in BIBLE_STRUCTURE:
    for ch_idx, total_v in enumerate(verse_counts):
        ch_num = ch_idx + 1
        ALL_BIBLE_CHAPTERS.append((short_name, ch_num))
        for v_num in range(1, total_v + 1):
            ALL_BIBLE_VERSES.append((short_name, ch_num, v_num))

# ---------------------------------------------------------
# 💾 Supabase 연동 HELPER 함수 (DB 읽기 및 쓰기)
# ---------------------------------------------------------
topic_plans = {}

def save_data_to_supabase(key, data):
    """특정 (chat_id, thread_id) 키의 데이터를 Supabase DB에 저장/업데이트"""
    if not supabase_client:
        return
    key_str = f"{key[0]}_{key[1]}"
    try:
        supabase_client.table("bot_data").upsert({
            "key": key_str,
            "data": data
        }).execute()
    except Exception as e:
        print(f"🌧️ Supabase 저장 실패 ({key_str}): {e}")

def load_data_from_supabase():
    """봇 시작 시 Supabase DB에서 전체 데이터를 안전하게 로드"""
    global topic_plans
    if not supabase_client:
        return
    try:
        response = supabase_client.table("bot_data").select("*").execute()
        loaded_count = 0
        for row in response.data:
            key_str = row.get("key", "")
            if not key_str or "_" not in key_str:
                continue
                
            key_parts = key_str.rsplit("_", 1)
            
            if len(key_parts) == 2 and key_parts[0].lstrip("-").isdigit() and key_parts[1].isdigit():
                chat_id = int(key_parts[0])
                thread_id = int(key_parts[1])
                topic_plans[(chat_id, thread_id)] = row["data"]
                loaded_count += 1
            else:
                print(f"🍃 비표준 키 건너뜀 또는 별도 처리: {key_str}")

        print(f"🌱 Supabase에서 {loaded_count}개의 사용자 데이터를 성공적으로 로드했습니다.")
    except Exception as e:
        print(f"🌧️ Supabase 로드 실패: {e}")

def get_full_book_name(short_name):
    for item in BIBLE_STRUCTURE:
        if item[0] == short_name:
            return item[1]
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

def get_transcription_label(start_verse_idx, chunk_size):
    end_verse_idx = min(start_verse_idx + chunk_size - 1, len(ALL_BIBLE_VERSES) - 1)
    start_book, start_ch, start_v = ALL_BIBLE_VERSES[start_verse_idx]
    end_book, end_ch, end_v = ALL_BIBLE_VERSES[end_verse_idx]
    
    if start_book == end_book:
        if start_ch == end_ch:
            if start_v == end_v:
                return f"{start_book} {start_ch}:{start_v}"
            return f"{start_book} {start_ch}:{start_v}-{end_v}"
        return f"{start_book} {start_ch}:{start_v} - {end_ch}:{end_v}"
    return f"{start_book} {start_ch}:{start_v} - {end_book} {end_ch}:{end_v}"

def generate_bible_status_text(current_ch_idx):
    current_global_idx = 0
    msg = "📖 **[성경 66권 완독 현황판]**\n"
    msg += "완료: 🐦‍⬛ | 읽는중: 🪺 | 미완료: 🥚\n\n"
    msg += "📜 **[구약 39권]**\n"

    for idx, (short_name, full_name, total_ch, _) in enumerate(BIBLE_STRUCTURE):
        book_start_idx = current_global_idx
        book_end_idx = current_global_idx + total_ch - 1
        current_global_idx += total_ch

        if idx == 39:
            msg += "\n\n✝️ **[신약 27권]**\n"

        if current_ch_idx > book_end_idx:
            status_icon = "🐦‍⬛"
        elif book_start_idx <= current_ch_idx <= book_end_idx:
            status_icon = "🪺"
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

def generate_transcription_status_text(current_v_idx):
    current_global_v_idx = 0
    msg = "✍️ **[성경 66권 필사 현황판]**\n"
    msg += "하기 전: 🧊 | 하는중: ☕️ | 한 후: 🍪\n\n"
    msg += "📜 **[구약 39권]**\n"

    for idx, (short_name, full_name, _, verse_counts) in enumerate(BIBLE_STRUCTURE):
        book_total_v = sum(verse_counts)
        book_start_v_idx = current_global_v_idx
        book_end_v_idx = current_global_v_idx + book_total_v - 1
        current_global_v_idx += book_total_v

        if idx == 39:
            msg += "\n\n✝️ **[신약 27권]**\n"

        if current_v_idx > book_end_v_idx:
            status_icon = "🍪"
        elif book_start_v_idx <= current_v_idx <= book_end_v_idx:
            status_icon = "☕️"
        else:
            status_icon = "🧊"

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
    "👋🏻 **반갑습니다! 주 7일의 말씀 봇 안내** 🌿\n\n"
    "• **할 일 등록:** 채팅창에 계획 입력 (`[카테고리명]` 지원)\n"
    "• **오늘의 할 일:** `/l` (또는 `/list`)\n"
    "• **매일 루틴:** `/r [내용]`\n"
    "• **요일별 과제:** `/wt`\n"
    "• **알림 시간 설정:** `/t [시:분]` (또는 `/time`, 끄기: `/t off`)\n"
    "• **루틴 수정:** `/e [기존루틴] > [새루틴]` (또는 `/edit`)\n"
    "• **성경 하루 분량:** `/bp [장수]` (예: `/bp 5`)\n"
    "• **성경 시작점:** `/bs [분량]` (예: `/bs 창 1장`)\n"
    "• **성경 완독 현황판:** `/st`\n"
    "• **필사 하루 절수:** `/tp [절수]` (예: `/tp 10`)\n"
    "• **필사 시작점:** `/ts [구절]` (예: `/ts 창 1:1`)\n"
    "• **성경 필사 현황판:** `/tst`\n"
    "• **할 일 삭제:** `/d [번호 또는 이름]`\n"
    "• **질문 보내기:** `질문: [내용]`\n"
    "• **주간 리포트:** `/w`\n"
    "• **계획 초기화:** `/rs`\n\n"
    "🌱 오늘 달성할 계획을 입력하거나 성경 읽기 및 필사를 시작해 보세요!"
]

CHEERING_MESSAGES = [
    "🌿 멋진 목표네요! 오늘도 차근차근 달성해 봐요!",
    "✨ 등록 완료! 분명 잘 해내실 거예요. 응원합니다!",
    "🍃 작은 실행이 모여 큰 성장을 만듭니다. 화이팅!",
    "👏🏻 계획을 세운 것부터 이미 절반은 성공이에요!",
    "🌱 오늘의 노력이 결실을 맺을 거예요. 끝까지 달려봐요!",
]

WEEKDAY_KOR = ["월", "화", "수", "목", "금", "토", "일"]
broadcast_data = {}
current_broadcast_id = 0

WEEKLY_TASK_PROMPT_MSG = (
    "📝 **[새로운 한 주, 주간 과제 설정]**\n\n"
    "이번 주 특정 요일에 정기적으로 진행할 공부나 과제가 있다면 아래 명령어로 등록해 보세요!\n\n"
    "**💡 작성 예시:**\n"
    "`/wt` 입력 후 아래 줄에 적어주시면 해당 요일 새벽 5시에 자동으로 오늘 할 일로 추가됩니다.\n"
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

def default_topic_data(user_name):
    return {
        "user_name": user_name,
        "plans": [],
        "bible_ch_idx": 0,
        "bible_chunk": 4,
        "transcription_v_idx": 0,
        "transcription_chunk": 10,
        "weekly_tasks": {},
        "notify_time": None,
        "disabled": False
    }

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    user_name = update.effective_user.first_name or "사용자"

    if key not in topic_plans:
        topic_plans[key] = default_topic_data(user_name)
        save_data_to_supabase(key, topic_plans[key])

    welcome_text = random.choice(WELCOME_MESSAGES)
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def bot_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    user_name = update.effective_user.first_name or "사용자"

    if key not in topic_plans:
        topic_plans[key] = default_topic_data(user_name)
    topic_plans[key]["disabled"] = True
    save_data_to_supabase(key, topic_plans[key])

    await update.message.reply_text(
        "🌧️ **이 토픽에서 봇 기능이 비활성화되었습니다.**\n\n"
        "자유롭게 메시지나 광고글을 나누실 수 있으며, 전체 공지 과제(/broadcast) 수신 대상에서도 제외됩니다.\n"
        "다시 켜시려면 `/on`을 입력해 주세요!",
        parse_mode="Markdown"
    )

async def bot_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    user_name = update.effective_user.first_name or "사용자"

    if key not in topic_plans:
        topic_plans[key] = default_topic_data(user_name)
    topic_plans[key]["disabled"] = False
    save_data_to_supabase(key, topic_plans[key])

    await update.message.reply_text(
        "☀️ **이 토픽에서 봇 기능이 다시 활성화되었습니다!**\n\n"
        "이제 작성하시는 일반 메시지가 오늘 할 일로 등록되며, 전체 공지 과제를 수신합니다.",
        parse_mode="Markdown"
    )

async def admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("🌧️ 관리자만 사용할 수 있는 명령어입니다.")
        return

    text_content = update.message.text.strip()
    raw_args = re.sub(r"^/(reply|re)\s*", "", text_content, flags=re.IGNORECASE).strip()

    if not raw_args or " " not in raw_args:
        await update.message.reply_text(
            "💬 **[관리자 답장 전송 방법]**\n\n"
            "**/re [토픽ID 또는 사용자ID] [답변 내용]** (또는 `/reply`)\n\n"
            "**작성 예시:**\n"
            "• 토픽 방 답장: `/re 12345 안녕하세요.`\n"
            "• 1:1 개인방 답장: `/re 987654321 안녕하세요.`",
            parse_mode="Markdown"
        )
        return

    target_id_str, reply_text = raw_args.split(" ", 1)
    
    if not target_id_str.lstrip("-").isdigit():
        await update.message.reply_text("🌧️ ID는 숫자로 입력해 주세요.")
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
        await update.message.reply_text(f"🌱 **[대상 ID: {target_id}]**로 성공적으로 답변을 발송했습니다!")
    except Exception as e:
        await update.message.reply_text(f"🌧️ 답변 발송 실패: {e}\n(상대방이 봇을 차단했거나 ID가 올바르지 않은지 확인해 주세요.)")

async def broadcast_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_broadcast_id
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("🌧️ 관리자만 사용할 수 있는 명령어입니다.")
        return

    admin_key = get_topic_key(update)
    user_name = update.effective_user.first_name or "사용자"
    if admin_key not in topic_plans:
        topic_plans[admin_key] = default_topic_data(user_name)
        save_data_to_supabase(admin_key, topic_plans[admin_key])

    text_content = update.message.text.strip()
    raw_input = re.sub(r"^/(broadcast|bc)\s*", "", text_content, flags=re.IGNORECASE).strip()

    if not raw_input:
        await update.message.reply_text(
            "🕊️ **[독립 공지 과제 발송 방법]**\n\n"
            "**/bc [제목]** 입력 후 다음 줄에 과제 항목을 입력해 주세요. (또는 `/broadcast`)\n"
            "(선택: 상단에 `제외: 광고, 공지` 입력 시 특정 키워드 토픽 제외 가능 / `/off` 설정 토픽은 자동 제외)\n\n"
            "**작성 예시:**\n"
            "```\n"
            "/bc 제외: 광고, 공지\n"
            "[전체 필수 공지 과제]\n"
            "주간 질문 작성하기\n"
            "공지사항 숙지 및 체크하기\n"
            "```",
            parse_mode="Markdown"
        )
        return

    lines = raw_input.split("\n")
    title = "[전체 공지 과제]"
    tasks = []
    exclude_keywords = ["광고", "공지", "자료", "자료방", "광고방", "공지방"]

    for line in lines:
        raw_line = line.strip()
        if not raw_line:
            continue
        
        if raw_line.startswith("제외:"):
            ex_str = raw_line.replace("제외:", "").strip()
            custom_excludes = [k.strip() for k in ex_str.split(",") if k.strip()]
            if custom_excludes:
                exclude_keywords = custom_excludes
            continue

        cat_match = re.search(r"^\[\s*(.*?)\s*\]$", raw_line)
        if cat_match:
            title = f"[{cat_match.group(1).strip()}]"
        else:
            tasks.append(raw_line)

    if not tasks:
        await update.message.reply_text("🌧️ 추가할 과제 항목을 입력해 주세요.")
        return

    current_broadcast_id += 1
    bc_id = current_broadcast_id

    broadcast_data[bc_id] = {
        "title": title,
        "tasks": tasks,
        "records": {}
    }

    keyboard = []
    for t_idx, task in enumerate(tasks):
        keyboard.append([InlineKeyboardButton(f"🥚 {task}", callback_data=f"bctoggle_{bc_id}_{t_idx}")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    success_count = 0
    skipped_count = 0
    msg = f"🕊️ **{title}**\n\n아래 안내 과제를 확인하신 후 완료된 항목을 클릭해 주세요!\n"

    for t_key in list(topic_plans.keys()):
        if t_key == admin_key:
            continue

        chat_id, thread_id = t_key
        user_info = topic_plans.get(t_key, {})
        u_name = user_info.get("user_name", "")

        if user_info.get("disabled", False):
            skipped_count += 1
            continue

        if any(keyword in u_name for keyword in exclude_keywords):
            skipped_count += 1
            continue

        broadcast_data[bc_id]["records"][t_key] = {i: False for i in range(len(tasks))}

        try:
            await context.bot.send_message(
                chat_id=chat_id,
                message_thread_id=thread_id if thread_id != 0 else None,
                text=msg,
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
            success_count += 1
        except Exception as e:
            print(f"독립 공지 발송 실패 ({t_key}): {e}")

    await update.message.reply_text(
        f"🌱 총 **{success_count}개**의 대상 채팅방/토픽에 공지를 발송했습니다!\n"
        f"🌧️ 제외된 채팅방/토픽 (/off 설정 및 제외 키워드): **{skipped_count}개**\n"
        f"📊 리포트 확인: `/bcr` (또는 `/broadcast_report`)"
    )

async def broadcast_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("🌧️ 관리자만 사용할 수 있는 명령어입니다.")
        return

    if not broadcast_data:
        await update.message.reply_text("📊 아직 발송된 전체 공지 과제가 없습니다.")
        return

    bc_id = max(broadcast_data.keys())
    data = broadcast_data[bc_id]
    
    title = data["title"]
    tasks = data["tasks"]
    records = data["records"]

    report_msg = f"📊 **[{title} - 수행 결과 리포트]**\n\n"

    for key, task_records in records.items():
        chat_id, thread_id = key
        user_info = topic_plans.get(key, {})
        user_name = user_info.get("user_name", f"사용자 ({chat_id})")
        
        location_str = f"{user_name}"
        if thread_id != 0:
            location_str += f" (토픽 #{thread_id})"

        report_msg += f"👤🏻 **{location_str}**\n"

        for t_idx, task in enumerate(tasks):
            is_done = task_records.get(t_idx, False)
            status_icon = "🌿 완료" if is_done else "🌧️ 미완료"
            report_msg += f"  • {task}: `{status_icon}`\n"
        report_msg += "\n"

    await update.message.reply_text(report_msg, parse_mode="Markdown")

async def set_notify_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    user_name = update.effective_user.first_name or "사용자"
    raw_args = " ".join(context.args).strip() if context.args else ""

    if key not in topic_plans:
        topic_plans[key] = default_topic_data(user_name)

    if not raw_args:
        curr_time = topic_plans[key].get("notify_time")
        status = f"현재 설정된 알림 시간: **{curr_time}**" if curr_time else "현재 알림이 설정되어 있지 않습니다."
        await update.message.reply_text(
            f"🌙 **일일 계획 점검 알림 시간 설정**\n\n"
            f"{status}\n\n"
            f"**사용 예시:**\n"
            f"• `/t 22:00` (매일 밤 10시 알림)\n"
            f"• `/t 08:30` (매일 아침 8시 30분 알림)\n"
            f"• `/t off` (알림 해제)",
            parse_mode="Markdown"
        )
        return

    if raw_args.lower() in ["off", "끄기", "해제"]:
        topic_plans[key]["notify_time"] = None
        save_data_to_supabase(key, topic_plans[key])
        await update.message.reply_text("🌧️ **일일 계획 점검 알림이 해제되었습니다.**", parse_mode="Markdown")
        return

    time_match = re.match(r"^([0-1]?[0-9]|2[0-3]):([0-5][0-9])$", raw_args)
    if not time_match:
        await update.message.reply_text("🌧️ 올바른 시간 형식이 아닙니다. `24시간 형식(HH:MM)`으로 입력해 주세요. (예: `/t 22:00`)", parse_mode="Markdown")
        return

    formatted_time = f"{int(time_match.group(1)):02d}:{int(time_match.group(2)):02d}"
    topic_plans[key]["notify_time"] = formatted_time
    save_data_to_supabase(key, topic_plans[key])

    await update.message.reply_text(
        f"🌙 **매일 `{formatted_time}`에 오늘의 공부 및 성경 점검 알림이 발송됩니다!**",
        parse_mode="Markdown"
    )

async def add_weekly_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    user_name = update.effective_user.first_name or "사용자"
    now = datetime.datetime.now(pytz.timezone("Asia/Seoul"))
    today_str = now.strftime("%m/%d")
    today_weekday_kor = WEEKDAY_KOR[now.weekday()]

    text_content = update.message.text.strip()
    raw_input = re.sub(r"^/(weekly_task|wt)\s*", "", text_content, flags=re.IGNORECASE).strip()

    if key not in topic_plans:
        topic_plans[key] = default_topic_data(user_name)

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
            if d not in topic_plans[key]["weekly_tasks"]:
                topic_plans[key]["weekly_tasks"][d] = []
            topic_plans[key]["weekly_tasks"][d].extend(tasks)
            topic_plans[key]["weekly_tasks"][d] = list(dict.fromkeys(topic_plans[key]["weekly_tasks"][d]))
            added_summary.append(f"• **{d}요일:** {', '.join(tasks)}")

            if d == today_weekday_kor:
                existing_tasks = [p["task"] for p in topic_plans[key]["plans"] if p.get("category") == f"[{d}요일 과제]"]
                for t in tasks:
                    if t not in existing_tasks:
                        topic_plans[key]["plans"].append({
                            "task": t,
                            "category": f"[{d}요일 과제]",
                            "done": False,
                            "date": today_str,
                        })

    if added_summary:
        save_data_to_supabase(key, topic_plans[key])
        plan_text, reply_markup = build_plan_view(key)
        await update.message.reply_text(
            f"🍃 **주간 과제가 세팅되었습니다!**\n"
            f"오늘 요일과 일치하는 과제는 목록에 즉시 반영되었습니다.\n\n"
            + "\n".join(added_summary) + "\n\n"
            f"-------------------------\n"
            f"{plan_text}",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("🌧️ 요일과 할 일 형식을 맞춰서 입력해 주세요. (예: `월: 과제 제출`)")

async def bible_pages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    user_name = update.effective_user.first_name or "사용자"
    raw_args = " ".join(context.args).strip() if context.args else ""

    if not raw_args.isdigit() or int(raw_args) <= 0:
        await update.message.reply_text("💡 **하루에 읽을 장수(숫자)를 입력해 주세요.** (예: `/bp 5`)", parse_mode="Markdown")
        return

    chunk_size = int(raw_args)
    if key not in topic_plans:
        topic_plans[key] = default_topic_data(user_name)
    topic_plans[key]["bible_chunk"] = chunk_size
    save_data_to_supabase(key, topic_plans[key])

    await update.message.reply_text(f"🍃 **성경 읽기 분량이 하루 `{chunk_size}장`으로 설정되었습니다!**", parse_mode="Markdown")

async def bible_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    user_name = update.effective_user.first_name or "사용자"
    raw_args = " ".join(context.args).strip() if context.args else ""

    if not raw_args:
        await update.message.reply_text("💡 예시: `/bs 창 1장`", parse_mode="Markdown")
        return

    matched_ch_idx = -1
    clean_keyword = re.sub(r"\s+", "", raw_args).lower()

    for idx, (b_short, b_ch) in enumerate(ALL_BIBLE_CHAPTERS):
        full_book_name = get_full_book_name(b_short)
        target_str1 = re.sub(r"\s+", "", f"{b_short}{b_ch}장").lower()
        target_str2 = re.sub(r"\s+", "", f"{full_book_name}{b_ch}장").lower()
        
        if clean_keyword in target_str1 or clean_keyword in target_str2 or clean_keyword == f"{b_short}{b_ch}".lower():
            matched_ch_idx = idx
            break

    if matched_ch_idx == -1:
        await update.message.reply_text(f"🌧️ 입력하신 `{raw_args}` 위치를 성경 데이터에서 찾을 수 없습니다.", parse_mode="Markdown")
        return

    if key not in topic_plans:
        topic_plans[key] = default_topic_data(user_name)
    topic_plans[key]["bible_ch_idx"] = matched_ch_idx

    chunk_size = topic_plans[key].get("bible_chunk", 4)
    target_label = get_bible_label(matched_ch_idx, chunk_size)
    today_str = datetime.datetime.now(pytz.timezone("Asia/Seoul")).strftime("%m/%d")

    plans = topic_plans[key].get("plans", [])
    topic_plans[key]["plans"] = [p for p in plans if p.get("is_bible") != True]
    
    topic_plans[key]["plans"].append({
        "task": f"성경 묵상: {target_label}",
        "category": "[매일]",
        "done": False,
        "date": today_str,
        "is_bible": True,
        "bible_ch_idx": matched_ch_idx
    })
    save_data_to_supabase(key, topic_plans[key])

    plan_text, reply_markup = build_plan_view(key)
    await update.message.reply_text(
        f"🌿 **성경 묵상 시작 지점이 설정되었습니다!**\n"
        f"• 하루 설정 분량: **{chunk_size}장씩**\n"
        f"• 시작 분량: **{target_label}**\n\n"
        f"-------------------------\n"
        f"{plan_text}",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def bible_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    data = topic_plans.get(key, {})
    current_ch_idx = data.get("bible_ch_idx", 0)

    msg = generate_bible_status_text(current_ch_idx)
    await update.message.reply_text(msg, parse_mode="Markdown")

async def transcription_pages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    user_name = update.effective_user.first_name or "사용자"
    raw_args = " ".join(context.args).strip() if context.args else ""

    if not raw_args.isdigit() or int(raw_args) <= 0:
        await update.message.reply_text("💡 **하루에 필사할 절수(숫자)를 입력해 주세요.** (예: `/tp 10`)", parse_mode="Markdown")
        return

    chunk_size = int(raw_args)
    if key not in topic_plans:
        topic_plans[key] = default_topic_data(user_name)
    topic_plans[key]["transcription_chunk"] = chunk_size
    save_data_to_supabase(key, topic_plans[key])

    await update.message.reply_text(f"🍃 **성경 필사 분량이 하루 `{chunk_size}절`로 설정되었습니다!**", parse_mode="Markdown")

async def transcription_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    user_name = update.effective_user.first_name or "사용자"
    raw_args = " ".join(context.args).strip() if context.args else ""

    if not raw_args:
        await update.message.reply_text("💡 예시: `/ts 창 1:1` 또는 `/ts 요한복음 3:16`", parse_mode="Markdown")
        return

    matched_v_idx = -1
    clean_keyword = re.sub(r"\s+", "", raw_args).lower()

    for idx, (b_short, b_ch, b_v) in enumerate(ALL_BIBLE_VERSES):
        full_book_name = get_full_book_name(b_short)
        target1 = re.sub(r"\s+", "", f"{b_short}{b_ch}:{b_v}").lower()
        target2 = re.sub(r"\s+", "", f"{full_book_name}{b_ch}:{b_v}").lower()
        target3 = re.sub(r"\s+", "", f"{b_short}{b_ch}장{b_v}절").lower()
        target4 = re.sub(r"\s+", "", f"{full_book_name}{b_ch}장{b_v}절").lower()

        if clean_keyword in [target1, target2, target3, target4]:
            matched_v_idx = idx
            break

    if matched_v_idx == -1:
        await update.message.reply_text(f"🌧️ 입력하신 `{raw_args}` 구절 위치를 성경 데이터에서 찾을 수 없습니다.", parse_mode="Markdown")
        return

    if key not in topic_plans:
        topic_plans[key] = default_topic_data(user_name)
    topic_plans[key]["transcription_v_idx"] = matched_v_idx

    chunk_size = topic_plans[key].get("transcription_chunk", 10)
    target_label = get_transcription_label(matched_v_idx, chunk_size)
    today_str = datetime.datetime.now(pytz.timezone("Asia/Seoul")).strftime("%m/%d")

    plans = topic_plans[key].get("plans", [])
    topic_plans[key]["plans"] = [p for p in plans if p.get("is_transcription") != True]
    
    topic_plans[key]["plans"].append({
        "task": f"성경 필사: {target_label}",
        "category": "[매일]",
        "done": False,
        "date": today_str,
        "is_transcription": True,
        "transcription_v_idx": matched_v_idx
    })
    save_data_to_supabase(key, topic_plans[key])

    plan_text, reply_markup = build_plan_view(key)
    await update.message.reply_text(
        f"✍️ **성경 필사 시작 지점이 설정되었습니다!**\n"
        f"• 하루 설정 분량: **{chunk_size}절씩**\n"
        f"• 시작 분량: **{target_label}**\n\n"
        f"-------------------------\n"
        f"{plan_text}",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def transcription_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    data = topic_plans.get(key, {})
    current_v_idx = data.get("transcription_v_idx", 0)

    msg = generate_transcription_status_text(current_v_idx)
    await update.message.reply_text(msg, parse_mode="Markdown")

async def delete_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    data = topic_plans.get(key, {})
    plans = data.get("plans", [])

    text_content = update.message.text.strip()
    raw_input = re.sub(r"^/(delete|del|d)\s*", "", text_content, flags=re.IGNORECASE).strip()

    if not raw_input:
        await update.message.reply_text("💡 삭제할 할 일 번호 또는 이름을 입력해 주세요! (예: `/d 1` 또는 `/d 영단어`)\n`/l`에서 번호를 확인할 수 있습니다.", parse_mode="Markdown")
        return

    if not plans:
        await update.message.reply_text("🍃 삭제할 할 일이 없습니다.")
        return

    deleted_item = None
    
    if raw_input.isdigit():
        idx = int(raw_input) - 1
        if 0 <= idx < len(plans):
            deleted_item = plans.pop(idx)
    else:
        for i, p in enumerate(plans):
            if raw_input.lower() in p["task"].lower():
                deleted_item = plans.pop(i)
                break

    if deleted_item:
        save_data_to_supabase(key, topic_plans[key])
        plan_text, reply_markup = build_plan_view(key)
        await update.message.reply_text(
            f"🍂 **`{deleted_item['task']}` 항목이 삭제되었습니다.** (통계 분모에서 제외)\n\n"
            f"-------------------------\n"
            f"{plan_text}",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(f"🌧️ `{raw_input}`에 해당하는 할 일을 찾을 수 없습니다.")

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
    today_str = datetime.datetime.now(pytz.timezone("Asia/Seoul")).strftime("%m/%d")

    if not plans:
        return (
            "🍃 등록된 할 일이 없습니다.\n채팅창에 오늘 할 일이나 `/r`, `/bs`, `/ts`를 입력해 보세요!",
            None,
        )

    # 오늘 날짜에 해당하는 항목 또는 미완료 최신 1개 항목 위주로 체크박스 구성 (과거 중복 방지)
    today_plans_with_index = [
        (idx, p) for idx, p in enumerate(plans)
        if p.get("date") == today_str or not p.get("done")
    ]
    
    seen_tasks = set()
    filtered_plans_with_index = []
    for idx, p in reversed(today_plans_with_index):
        task_key = (p.get("category"), p.get("task"))
        if task_key not in seen_tasks:
            seen_tasks.add(task_key)
            filtered_plans_with_index.append((idx, p))
    
    filtered_plans_with_index.reverse()

    filtered_plans_with_index.sort(
        key=lambda x: (
            get_category_priority(x[1].get("category", "")),
            x[1].get("category", ""),
            x[1].get("is_bible", False),
            x[1].get("is_transcription", False)
        )
    )

    today_only_plans = [p for _, p in filtered_plans_with_index]
    normal_plans = [p for p in today_only_plans if "[매일]" not in p.get("category", "")]
    routine_plans = [p for p in today_only_plans if "[매일]" in p.get("category", "") and not p.get("is_bible") and not p.get("is_transcription")]
    bible_plans = [p for p in today_only_plans if p.get("is_bible") == True]
    transcription_plans = [p for p in today_only_plans if p.get("is_transcription") == True]

    stat_lines = []

    if normal_plans:
        n_completed = sum(1 for p in normal_plans if p["done"])
        n_total = len(normal_plans)
        n_rate = (n_completed / n_total) * 100 if n_total > 0 else 0
        stat_lines.append(f"• **일반 공부 달성률:** `{n_rate:.1f}%` ({n_completed}/{n_total} 완료)")

    if routine_plans:
        r_completed = sum(1 for p in routine_plans if p["done"])
        r_total = len(routine_plans)
        if r_completed == r_total and r_total > 0:
            stat_lines.append(f"• **매일 루틴 달성:** `{r_completed}/{r_total} - (달성!)` 🌿")
        else:
            stat_lines.append(f"• **매일 루틴 달성:** `{r_completed}/{r_total}`")

    if bible_plans:
        b_completed = sum(1 for p in bible_plans if p["done"])
        b_total = len(bible_plans)
        status_str = "완료 📖" if b_completed == b_total else "진행 중 🪺"
        stat_lines.append(f"• **오늘의 성경 묵상:** {bible_plans[0]['task'].replace('성경 묵상: ', '')} (`{status_str}`)")

    if transcription_plans:
        t_completed = sum(1 for p in transcription_plans if p["done"])
        t_total = len(transcription_plans)
        t_status_str = "한 후 🍪" if t_completed == t_total else "하는 중 ☕️"
        stat_lines.append(f"• **오늘의 성경 필사:** {transcription_plans[0]['task'].replace('성경 필사: ', '')} (`{t_status_str}`)")

    stat_str = "\n".join(stat_lines)

    completed_count = sum(1 for p in today_only_plans if p["done"])
    total_count = len(today_only_plans)

    if completed_count == total_count and total_count > 0:
        text = (
            f"🌿 **ALL CLEAR!** ✨\n\n"
            f"📊 **오늘의 달성 현황:**\n{stat_str}\n\n"
            f"오늘의 모든 계획을 완수하셨습니다! 수고하셨어요! 🍃"
        )
    else:
        text = (
            f"📝 **오늘의 공부 점검**\n\n"
            f"📊 **달성 현황:**\n{stat_str}\n\n"
            f"버튼을 누르면 완료 상태로 전환되며, 카테고리의 모든 일을 마치면 섹션이 자동으로 정돈됩니다.\n"
        )

    category_uncompleted_count = {}
    for _, item in filtered_plans_with_index:
        cat = item.get("category", "")
        if cat not in category_uncompleted_count:
            category_uncompleted_count[cat] = 0
        if not item["done"]:
            category_uncompleted_count[cat] += 1

    keyboard = []
    last_category = None

    for real_idx, item in filtered_plans_with_index:
        category = item.get("category", "")
        
        # 🎯 1초 애니메이션 동안 잔상이 유지되도록 visible_indices 체크 보완
        should_show = (visible_indices is not None and real_idx in visible_indices) or \
                      (visible_indices is None and category_uncompleted_count.get(category, 0) > 0)

        if should_show:
            if category and category != last_category:
                keyboard.append(
                    [InlineKeyboardButton(f"📂 {category}", callback_data="noop")]
                )
                last_category = category

            if item.get("is_bible"):
                status_icon = "📖" if item["done"] else "🪺"
            elif item.get("is_transcription"):
                status_icon = "🍪" if item["done"] else "☕️"
            else:
                status_icon = "🐦‍⬛" if item["done"] else "🥚"

            btn_text = f"{status_icon} {item['task']}"
            keyboard.append(
                [InlineKeyboardButton(btn_text, callback_data=f"toggle_{real_idx}")]
            )

    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    return text, reply_markup

def build_weekly_view(key):
    data = topic_plans.get(key, {})
    plans = data.get("plans", [])

    if not plans and "bible_ch_idx" not in data and "transcription_v_idx" not in data:
        return "🍃 이번 주에 등록된 공부/성경 읽기/필사 계획이 없습니다.", None

    uncompleted = [p for p in plans if not p["done"]]

    week_range_str = get_korean_week_range_str()
    msg = f"🍃 **[이번 주 공부 & 성경 정산 리포트] ({week_range_str})**\n\n"

    normal_plans = [p for p in plans if "[매일]" not in p.get("category", "")]
    routine_plans = [p for p in plans if "[매일]" in p.get("category", "") and not p.get("is_bible") and not p.get("is_transcription")]
    bible_plans = [p for p in plans if p.get("is_bible") == True]
    transcription_plans = [p for p in plans if p.get("is_transcription") == True]

    if normal_plans:
        n_completed = sum(1 for p in normal_plans if p["done"])
        n_total = len(normal_plans)
        n_rate = (n_completed / n_total) * 100 if n_total > 0 else 0
        msg += f"📊 **주간 일반 공부 달성률:** `{n_rate:.1f}%` ({n_completed}/{n_total} 완료)\n\n"

    if routine_plans:
        msg += "🔄 **[매일 루틴 항목별 달성 현황]**\n"
        routine_names = list(dict.fromkeys([p["task"] for p in routine_plans]))
        
        for task_name in routine_names:
            completed_count = sum(
                1 for p in routine_plans if p["task"] == task_name and p["done"]
            )
            if completed_count >= 7:
                msg += f"• **{task_name}:** `{completed_count}/7 - (달성!)` 🌿\n"
            else:
                msg += f"• **{task_name}:** `{completed_count}/7` 완료\n"
        msg += "\n"

    msg += "📖 **[성경 묵상 & 필사 주간 누적 통계]**\n"
    bible_weekly_completed = sum(1 for p in bible_plans if p["done"])
    bible_weekly_rate = (bible_weekly_completed / 7.0) * 100 if bible_weekly_completed <= 7 else 100.0
    msg += f"• **이번 주 성경 묵상 달성률:** `{bible_weekly_rate:.1f}%` ({bible_weekly_completed}/7일 완수)\n"

    def get_completed_books_count_reading(current_ch_idx):
        if current_ch_idx >= len(ALL_BIBLE_CHAPTERS):
            return 66
        current_book_short = ALL_BIBLE_CHAPTERS[current_ch_idx][0]
        for idx, (b_short, _, _, _) in enumerate(BIBLE_STRUCTURE):
            if b_short == current_book_short:
                return idx
        return 0

    def get_completed_books_count_transcription(current_v_idx):
        if current_v_idx >= len(ALL_BIBLE_VERSES):
            return 66
        current_book_short = ALL_BIBLE_VERSES[current_v_idx][0]
        for idx, (b_short, _, _, _) in enumerate(BIBLE_STRUCTURE):
            if b_short == current_book_short:
                return idx
        return 0

    current_ch_idx = data.get("bible_ch_idx", 0)
    chunk_size = data.get("bible_chunk", 4)
    completed_books_b = get_completed_books_count_reading(current_ch_idx)
    overall_rate_b = (completed_books_b / 66.0) * 100
    current_label_b = get_bible_label(current_ch_idx, chunk_size) if current_ch_idx < len(ALL_BIBLE_CHAPTERS) else "완독 완료!"
    msg += f"• **성경 읽기 통산 달성률:** `{overall_rate_b:.1f}%` ({completed_books_b}/66 권 완독) - `{current_label_b}`\n\n"

    current_v_idx = data.get("transcription_v_idx", 0)
    t_chunk_size = data.get("transcription_chunk", 10)
    completed_books_t = get_completed_books_count_transcription(current_v_idx)
    overall_rate_t = (completed_books_t / 66.0) * 100
    current_label_t = get_transcription_label(current_v_idx, t_chunk_size) if current_v_idx < len(ALL_BIBLE_VERSES) else "필사 완료!"
    msg += f"• **성경 필사 통산 달성률:** `{overall_rate_t:.1f}%` ({completed_books_t}/66 권 완필) - `{current_label_t}`\n\n"

    keyboard = []

    if uncompleted:
        msg += f"🌧️ **[미완료된 항목 - 추가 점검 필요]** ({len(uncompleted)}개)\n"
        current_cat = None

        for p in uncompleted:
            cat = p.get("category", "")
            if cat and cat != current_cat:
                msg += f"\n📂 **{cat}**\n"
                keyboard.append([InlineKeyboardButton(f"📂 {cat}", callback_data="noop")])
                current_cat = cat

            date_str = f" ({p['date']})" if "date" in p else ""

            if p.get("is_bible"):
                icon = "🪺"
            elif p.get("is_transcription"):
                icon = "☕️"
            else:
                icon = "🥚"

            msg += f"  {icon} {p['task']}{date_str}\n"
            btn_label = f"{icon} {p['task']}{date_str}"

            real_idx = plans.index(p)
            keyboard.append([InlineKeyboardButton(btn_label, callback_data=f"toggle_{real_idx}")])
    else:
        msg += "🌱 이번 주 등록된 모든 공부 및 성경 묵상/필사를 완수하셨습니다!\n"

    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    return msg, reply_markup

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    user_name = update.effective_user.first_name or "사용자"
    sender_id = update.effective_user.id
    chat_id, thread_id = key
    text = update.message.text.strip()
    today_str = datetime.datetime.now(pytz.timezone("Asia/Seoul")).strftime("%m/%d")

    if text.startswith("/"):
        return

    if key in topic_plans and topic_plans[key].get("disabled", False):
        return

    if text.startswith("질문:") or text.startswith("질문 "):
        question_text = re.sub(r"^질문[:\s]*", "", text).strip()
        if not question_text:
            await update.message.reply_text("💡 질문 내용을 작성해 주세요!", parse_mode="Markdown")
            return

        location_label = f"토픽 #{thread_id}" if thread_id != 0 else f"개인방 (ID: `{sender_id}`)"
        admin_msg = f"🔒 **[질문]** {user_name} ({location_label}): {question_text}"
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=admin_msg, parse_mode="Markdown")
            await update.message.reply_text("🔒 질문이 관리자에게 전달되었습니다.")
        except Exception as e:
            print(f"질문 전달 실패: {e}")
        return

    if key not in topic_plans:
        topic_plans[key] = default_topic_data(user_name)
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
        save_data_to_supabase(key, topic_plans[key])
        cheer = random.choice(CHEERING_MESSAGES)
        plan_text, reply_markup = build_plan_view(key)

        response_msg = (
            f"🌿 **{added_count}개의 계획이 추가되었습니다!**\n"
            f"{cheer}\n\n"
            f"-------------------------\n"
            f"{plan_text}"
        )
        await update.message.reply_text(response_msg, reply_markup=reply_markup, parse_mode="Markdown")

async def add_routine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    user_name = update.effective_user.first_name or "사용자"
    today_str = datetime.datetime.now(pytz.timezone("Asia/Seoul")).strftime("%m/%d")

    if update.message.text:
        lines = update.message.text.split("\n")
        first_line_clean = re.sub(r"^/(routine|r)\s*", "", lines[0], flags=re.IGNORECASE).strip()
        routine_lines = [first_line_clean] + lines[1:] if len(lines) > 1 else [first_line_clean]
    else:
        raw_args = " ".join(context.args).strip() if context.args else ""
        routine_lines = [raw_args]

    if key not in topic_plans:
        topic_plans[key] = default_topic_data(user_name)

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
        await update.message.reply_text("💡 매일 반복할 루틴을 입력해 주세요!\n예시: `/r 영단어 30개 암기`", parse_mode="Markdown")
        return

    save_data_to_supabase(key, topic_plans[key])
    plan_text, reply_markup = build_plan_view(key)
    await update.message.reply_text(
        f"🔄 **{added_count}개의 [매일] 루틴이 추가되었습니다!**\n\n"
        f"-------------------------\n"
        f"{plan_text}",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def edit_routine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    data = topic_plans.get(key, {})
    plans = data.get("plans", [])

    text_content = update.message.text.strip()
    raw_input = re.sub(r"^/(edit_routine|edit|e)\s*", "", text_content, flags=re.IGNORECASE).strip()

    if ">" not in raw_input:
        await update.message.reply_text("💡 형식: `/e 기존루틴 > 새루틴`", parse_mode="Markdown")
        return

    old_name, new_name = [x.strip() for x in raw_input.split(">", 1)]

    modified_count = 0
    for p in plans:
        if "[매일]" in p.get("category", "") and p["task"] == old_name:
            p["task"] = new_name
            modified_count += 1

    if modified_count > 0:
        save_data_to_supabase(key, topic_plans[key])
        plan_text, reply_markup = build_plan_view(key)
        await update.message.reply_text(
            f"✏️ **루틴 수정 완료!** `{old_name}` ➔ `{new_name}`\n\n-------------------------\n{plan_text}",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(f"🌧️ `{old_name}` 항목을 찾을 수 없습니다.", parse_mode="Markdown")

async def list_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    text, reply_markup = build_plan_view(key)
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def weekly_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    weekly_text, reply_markup = build_weekly_view(key)
    await update.message.reply_text(weekly_text, reply_markup=reply_markup, parse_mode="Markdown")

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    if query.data == "noop":
        await query.answer()
        return

    chat_id = query.message.chat.id
    thread_id = query.message.message_thread_id if query.message.message_thread_id else 0
    key = (chat_id, thread_id)
    data = query.data

    # 🍂 [삭제] 버튼 클릭 시 (즉시 화면 및 DB에서 제거)
    if data.startswith("delete_item_"):
        idx = int(data.split("_")[2])
        topic_data = topic_plans.get(key, {})
        plans = topic_data.get("plans", [])

        if 0 <= idx < len(plans):
            deleted_item = plans.pop(idx)
            save_data_to_supabase(key, topic_plans[key])
            await query.answer(f"🍂 '{deleted_item['task']}' 항목이 삭제되었습니다.")

            now_str = datetime.datetime.now(pytz.timezone("Asia/Seoul")).strftime("%H:%M")
            plans = topic_data.get("plans", [])
            
            normal_plans = [p for p in plans if "[매일]" not in p.get("category", "")]
            routine_plans = [p for p in plans if "[매일]" in p.get("category", "") and not p.get("is_bible") and not p.get("is_transcription")]
            bible_plans = [p for p in plans if p.get("is_bible") == True]

            n_completed = sum(1 for p in normal_plans if p["done"])
            n_total = len(normal_plans)
            n_rate = (n_completed / n_total) * 100 if n_total > 0 else 0.0

            r_completed = sum(1 for p in routine_plans if p["done"])
            r_total = len(routine_plans)

            b_str = "완료 📖" if (bible_plans and bible_plans[0]["done"]) else "진행 중 🪺"

            uncompleted_with_index = [(i, p) for i, p in enumerate(plans) if not p["done"]]
            
            msg = (
                f"🌙 **[오늘의 공부 점검 알림 - {now_str}]**\n\n"
                f"오늘 계획하신 공부 및 성경 묵상은 차근차근 진행하고 계신가요?\n"
                f"잠시 하던 일을 멈추고 오늘의 달성 현황을 점검해 보세요!\n\n"
                f"📊 **오늘의 달성 현황:**\n"
                f"• **일반 공부 달성률:** `{n_rate:.1f}%` ({n_completed}/{n_total} 완료)\n"
                f"• **매일 루틴 달성:** `{r_completed}/{r_total}`\n"
                f"• **오늘의 성경 묵상:** `{b_str}`\n\n"
                f"📂 **[오늘의 남은 할 일]**\n"
            )

            keyboard = []
            if uncompleted_with_index:
                msg += "📋 버튼을 눌러 완료 처리하거나 🍂 삭제할 수 있습니다."
                last_cat = None
                for real_idx, item in uncompleted_with_index:
                    cat = item.get("category", "")
                    if cat and cat != last_cat:
                        keyboard.append([InlineKeyboardButton(f"📂 {cat}", callback_data="noop")])
                        last_cat = cat

                    if item.get("is_bible"):
                        status_icon = "🪺"
                    elif item.get("is_transcription"):
                        status_icon = "☕️"
                    else:
                        status_icon = "🥚"

                    is_routine = "[매일]" in cat
                    is_special = item.get("is_bible") or item.get("is_transcription") or is_routine

                    if is_special:
                        keyboard.append([
                            InlineKeyboardButton(f"{status_icon} {item['task']}", callback_data=f"toggle_{real_idx}")
                        ])
                    else:
                        keyboard.append([
                            InlineKeyboardButton(f"{status_icon} {item['task']}", callback_data=f"toggle_{real_idx}"),
                            InlineKeyboardButton("🍂 삭제", callback_data=f"delete_item_{real_idx}")
                        ])
            else:
                msg += "🌿 오늘 등록된 모든 공부/성경 묵상을 완료하셨습니다! 수고 많으셨습니다! ✨"

            reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
            try:
                await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode="Markdown")
            except Exception as e:
                if "Message is not modified" not in str(e):
                    print(f"알림 수정 예외: {e}")
        return

    if data.startswith("weekly_opt_"):
        await query.answer()
        if data == "weekly_opt_clear":
            if key in topic_plans:
                plans = topic_plans[key].get("plans", [])
                topic_plans[key]["plans"] = [p for p in plans if p["done"] or p.get("is_bible") or p.get("is_transcription")]
                save_data_to_supabase(key, topic_plans[key])
            await query.edit_message_text("🍂 **이번 주 미완료 항목들이 깔끔하게 정리되었습니다!**", parse_mode="Markdown")
        elif data == "weekly_opt_rollover":
            await query.edit_message_text("➡️ **미완료된 항목들이 다음 주로 차곡차곡 이월됩니다!**", parse_mode="Markdown")
        return

    if data.startswith("bctoggle_"):
        await query.answer()
        parts = data.split("_")
        bc_id = int(parts[1])
        t_idx = int(parts[2])

        if bc_id in broadcast_data and key in broadcast_data[bc_id]["records"]:
            curr_val = broadcast_data[bc_id]["records"][key].get(t_idx, False)
            broadcast_data[bc_id]["records"][key][t_idx] = not curr_val

            bc_info = broadcast_data[bc_id]
            title = bc_info["title"]
            tasks = bc_info["tasks"]
            user_records = bc_info["records"][key]

            keyboard = []
            for i, task in enumerate(tasks):
                is_done = user_records.get(i, False)
                icon = "🐦‍⬛" if is_done else "🥚"
                keyboard.append([InlineKeyboardButton(f"{icon} {task}", callback_data=f"bctoggle_{bc_id}_{i}")])

            reply_markup = InlineKeyboardMarkup(keyboard)
            msg = f"🕊️ **{title}**\n\n아래 안내 과제를 확인하신 후 완료된 항목을 클릭해 주세요!\n"

            try:
                await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode="Markdown")
            except Exception as e:
                if "Message is not modified" not in str(e):
                    print(f"공지 버튼 수정 예외: {e}")

            all_done = all(user_records.get(i, False) for i in range(len(tasks)))
            if all_done and len(tasks) > 0:
                congrat_bc_msg = f"🌿 **축하합니다! {title}의 모든 과제를 완수하셨습니다!** 👏🏻✨"
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        message_thread_id=thread_id if thread_id != 0 else None,
                        text=congrat_bc_msg,
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    print(f"공지 완수 축하 메시지 발송 예외: {e}")
        return

    if data.startswith("reset_"):
        await query.answer()
        if data == "reset_tasks":
            if key in topic_plans:
                plans = topic_plans[key].get("plans", [])
                topic_plans[key]["plans"] = [p for p in plans if "[매일]" in p.get("category", "")]
                save_data_to_supabase(key, topic_plans[key])
            await query.edit_message_text("🍂 **일반 할 일만 초기화되었습니다.**", parse_mode="Markdown")
        elif data == "reset_routines":
            if key in topic_plans:
                plans = topic_plans[key].get("plans", [])
                topic_plans[key]["plans"] = [p for p in plans if "[매일]" not in p.get("category", "")]
                save_data_to_supabase(key, topic_plans[key])
            await query.edit_message_text("🍂 **`[매일]` 루틴만 초기화되었습니다.**", parse_mode="Markdown")
        elif data == "reset_all":
            if key in topic_plans:
                topic_plans[key]["plans"] = []
                save_data_to_supabase(key, topic_plans[key])
            await query.edit_message_text("🍂 **모든 공부 계획과 루틴이 초기화되었습니다.**", parse_mode="Markdown")
        elif data == "reset_cancel":
            await query.edit_message_text("🌧️ 초기화가 취소되었습니다.")
        return

    # 🎯 1초 애니메이션 / 섹션 마지막 항목 잔상 유지 / 성경 제자리 리뉴얼 토글 핸들러
    if data.startswith("toggle_"):
        idx = int(data.split("_")[1])
        topic_data = topic_plans.get(key, {})
        plans = topic_data.get("plans", [])

        if 0 <= idx < len(plans):
            target_item = plans[idx]
            was_done = target_item["done"]
            target_item["done"] = not was_done
            save_data_to_supabase(key, topic_plans[key])

            # 🎯 팝업 메시지 (10% 확률)
            if target_item["done"] and random.random() < 0.10:
                cheer_pop = random.choice([
                    "🌿 한 걸음 더 성장하셨네요! 수고하셨어요!",
                    "🧊 영생은 습관 만들기에 달려있다.",
                    "☁️ 사람이 아무것도 모른다고 해도, 해내려는 마음으로 노력하면 하늘이 도우신다.",
                    "🍉 천국 성도가 되려면 나태하면 안되고 부지런해야 한다.",
                    "🌿 성경은 우리의 희망이고, 우리의 생명이고, 우리의 스승이다.",
                    "🎓 자신이 말씀을 좀 안다고 해서 안일하고 교만하면 안 된다.",
                    "✨ 완벽해요! 이대로 계속 달려봐요!",
                    "🍃 멋져요! 집중력이 대단하시네요!",
                    "👏🏻 깔끔하게 하나 해결! 최고예요!",
                ])
                await query.answer(cheer_pop, show_alert=False)
            else:
                await query.answer()

            is_bible_task = target_item.get("is_bible", False)
            is_trans_task = target_item.get("is_transcription", False)

            # 완독/완필 축하 메시지
            if is_bible_task and not was_done:
                curr_ch_idx = target_item.get("bible_ch_idx", 0)
                chunk_size = topic_data.get("bible_chunk", 4)
                
                curr_start_book, _ = ALL_BIBLE_CHAPTERS[curr_ch_idx]
                next_ch_idx = (curr_ch_idx + chunk_size) % len(ALL_BIBLE_CHAPTERS)
                next_start_book, _ = ALL_BIBLE_CHAPTERS[next_ch_idx]

                if curr_start_book != next_start_book:
                    full_name = get_full_book_name(curr_start_book)
                    next_full_name = get_full_book_name(next_start_book)
                    
                    status_board_text = generate_bible_status_text(next_ch_idx)
                    congrat_msg = (
                        f"🌱 **축하합니다! [{full_name}] 묵상을 완독하셨습니다!** 👏🏻✨\n\n"
                        f"끝까지 완수해내신 열정을 응원합니다!\n"
                        f"다음 권인 **[{next_full_name}]**도 힘차게 이어나가 보세요! 🪺\n\n"
                        f"-------------------------\n"
                        f"{status_board_text}"
                    )
                    await context.bot.send_message(
                        chat_id=chat_id,
                        message_thread_id=thread_id if thread_id != 0 else None,
                        text=congrat_msg,
                        parse_mode="Markdown"
                    )

            if is_trans_task and not was_done:
                curr_v_idx = target_item.get("transcription_v_idx", 0)
                chunk_size = topic_data.get("transcription_chunk", 10)
                
                curr_start_book, _, _ = ALL_BIBLE_VERSES[curr_v_idx]
                next_v_idx = (curr_v_idx + chunk_size) % len(ALL_BIBLE_VERSES)
                next_start_book, _, _ = ALL_BIBLE_VERSES[next_v_idx]

                if curr_start_book != next_start_book:
                    full_name = get_full_book_name(curr_start_book)
                    next_full_name = get_full_book_name(next_start_book)
                    
                    t_status_board_text = generate_transcription_status_text(next_v_idx)
                    congrat_msg = (
                        f"🌱 **축하합니다! [{full_name}] 필사를 완필하셨습니다!** 👏🏻✨\n\n"
                        f"한 절 한 절 정성껏 남기신 노고에 박수를 보냅니다!\n"
                        f"다음 권인 **[{next_full_name}]**도 힘차게 써나가 보세요! 🍪\n\n"
                        f"-------------------------\n"
                        f"{t_status_board_text}"
                    )
                    await context.bot.send_message(
                        chat_id=chat_id,
                        message_thread_id=thread_id if thread_id != 0 else None,
                        text=congrat_msg,
                        parse_mode="Markdown"
                    )

            original_text = query.message.text or ""
            
            # 저녁 점검 알림 메시지인 경우
            if "오늘의 공부 점검 알림" in original_text:
                plans = topic_data.get("plans", [])
                uncompleted_with_index = [(i, p) for i, p in enumerate(plans) if not p["done"]]
                
                now_str = datetime.datetime.now(pytz.timezone("Asia/Seoul")).strftime("%H:%M")
                normal_plans = [p for p in plans if "[매일]" not in p.get("category", "")]
                routine_plans = [p for p in plans if "[매일]" in p.get("category", "") and not p.get("is_bible") and not p.get("is_transcription")]
                bible_plans = [p for p in plans if p.get("is_bible") == True]

                n_completed = sum(1 for p in normal_plans if p["done"])
                n_total = len(normal_plans)
                n_rate = (n_completed / n_total) * 100 if n_total > 0 else 0.0
                r_completed = sum(1 for p in routine_plans if p["done"])
                r_total = len(routine_plans)
                b_str = "완료 📖" if (bible_plans and bible_plans[0]["done"]) else "진행 중 🪺"

                msg = (
                    f"🌙 **[오늘의 공부 점검 알림 - {now_str}]**\n\n"
                    f"오늘 계획하신 공부 및 성경 묵상은 차근차근 진행하고 계신가요?\n"
                    f"잠시 하던 일을 멈추고 오늘의 달성 현황을 점검해 보세요!\n\n"
                    f"📊 **오늘의 달성 현황:**\n"
                    f"• **일반 공부 달성률:** `{n_rate:.1f}%` ({n_completed}/{n_total} 완료)\n"
                    f"• **매일 루틴 달성:** `{r_completed}/{r_total}`\n"
                    f"• **오늘의 성경 묵상:** `{b_str}`\n\n"
                    f"📂 **[오늘의 남은 할 일]**\n"
                )

                # 🎬 [1단계] 즉시 까마귀 변경 상태 유지
                keyboard_instant = []
                if uncompleted_with_index:
                    msg += "📋 버튼을 눌러 완료 처리하거나 🍂 삭제할 수 있습니다."
                    last_cat = None
                    for real_idx, item in uncompleted_with_index:
                        cat = item.get("category", "")
                        if cat and cat != last_cat:
                            keyboard_instant.append([InlineKeyboardButton(f"📂 {cat}", callback_data="noop")])
                            last_cat = cat

                        if item.get("is_bible"):
                            status_icon = "📖" if item["done"] else "🪺"
                        elif item.get("is_transcription"):
                            status_icon = "🍪" if item["done"] else "☕️"
                        else:
                            status_icon = "🐦‍⬛" if item["done"] else "🥚"

                        is_routine = "[매일]" in cat
                        is_special = item.get("is_bible") or item.get("is_transcription") or is_routine

                        if item["done"] or is_special:
                            keyboard_instant.append([
                                InlineKeyboardButton(f"{status_icon} {item['task']}", callback_data=f"toggle_{real_idx}")
                            ])
                        else:
                            keyboard_instant.append([
                                InlineKeyboardButton(f"{status_icon} {item['task']}", callback_data=f"toggle_{real_idx}"),
                                InlineKeyboardButton("🍂 삭제", callback_data=f"delete_item_{real_idx}")
                            ])
                else:
                    msg += "🌿 오늘 등록된 모든 공부/성경 묵상을 완료하셨습니다! 수고 많으셨습니다! ✨"

                reply_markup_instant = InlineKeyboardMarkup(keyboard_instant) if keyboard_instant else None
                try:
                    await query.edit_message_text(msg, reply_markup=reply_markup_instant, parse_mode="Markdown")
                except Exception as e:
                    if "Message is not modified" not in str(e):
                        print(f"알림 수정 예외: {e}")

                # 🎬 [2단계] 1초 대기
                await asyncio.sleep(1)

                if is_bible_task and target_item["done"]:
                    curr_ch_idx = target_item.get("bible_ch_idx", 0)
                    chunk_size = topic_data.get("bible_chunk", 4)
                    next_ch_idx = (curr_ch_idx + chunk_size) % len(ALL_BIBLE_CHAPTERS)
                    topic_data["bible_ch_idx"] = next_ch_idx
                    next_label = get_bible_label(next_ch_idx, chunk_size)

                    target_item["task"] = f"성경 묵상: {next_label}"
                    target_item["done"] = False
                    target_item["bible_ch_idx"] = next_ch_idx
                    save_data_to_supabase(key, topic_plans[key])

                if is_trans_task and target_item["done"]:
                    curr_v_idx = target_item.get("transcription_v_idx", 0)
                    chunk_size = topic_data.get("transcription_chunk", 10)
                    next_v_idx = (curr_v_idx + chunk_size) % len(ALL_BIBLE_VERSES)
                    topic_data["transcription_v_idx"] = next_v_idx
                    next_label = get_transcription_label(next_v_idx, chunk_size)

                    target_item["task"] = f"성경 필사: {next_label}"
                    target_item["done"] = False
                    target_item["transcription_v_idx"] = next_v_idx
                    save_data_to_supabase(key, topic_plans[key])

                # 🎬 [3단계] 1초 후 완료 항목 정돈 및 성경/필사 리뉴얼
                plans = topic_data.get("plans", [])
                uncompleted_final = [(i, p) for i, p in enumerate(plans) if not p["done"]]
                
                msg_final = (
                    f"🌙 **[오늘의 공부 점검 알림 - {now_str}]**\n\n"
                    f"오늘 계획하신 공부 및 성경 묵상은 차근차근 진행하고 계신가요?\n"
                    f"잠시 하던 일을 멈추고 오늘의 달성 현황을 점검해 보세요!\n\n"
                    f"📊 **오늘의 달성 현황:**\n"
                    f"• **일반 공부 달성률:** `{n_rate:.1f}%` ({n_completed}/{n_total} 완료)\n"
                    f"• **매일 루틴 달성:** `{r_completed}/{r_total}`\n"
                    f"• **오늘의 성경 묵상:** `{b_str}`\n\n"
                    f"📂 **[오늘의 남은 할 일]**\n"
                )

                keyboard_final = []
                if uncompleted_final:
                    msg_final += "📋 버튼을 눌러 완료 처리하거나 🍂 삭제할 수 있습니다."
                    last_cat = None
                    for real_idx, item in uncompleted_final:
                        cat = item.get("category", "")
                        if cat and cat != last_cat:
                            keyboard_final.append([InlineKeyboardButton(f"📂 {cat}", callback_data="noop")])
                            last_cat = cat

                        if item.get("is_bible"):
                            status_icon = "🪺"
                        elif item.get("is_transcription"):
                            status_icon = "☕️"
                        else:
                            status_icon = "🥚"

                        is_routine = "[매일]" in cat
                        is_special = item.get("is_bible") or item.get("is_transcription") or is_routine

                        if is_special:
                            keyboard_final.append([
                                InlineKeyboardButton(f"{status_icon} {item['task']}", callback_data=f"toggle_{real_idx}")
                            ])
                        else:
                            keyboard_final.append([
                                InlineKeyboardButton(f"{status_icon} {item['task']}", callback_data=f"toggle_{real_idx}"),
                                InlineKeyboardButton("🍂 삭제", callback_data=f"delete_item_{real_idx}")
                            ])
                else:
                    msg_final += "🌿 오늘 등록된 모든 공부/성경 묵상을 완료하셨습니다! 수고 많으셨습니다! ✨"

                reply_markup_final = InlineKeyboardMarkup(keyboard_final) if keyboard_final else None
                try:
                    await query.edit_message_text(msg_final, reply_markup=reply_markup_final, parse_mode="Markdown")
                except Exception as e:
                    if "Message is not modified" not in str(e):
                        print(f"알림 최종 수정 예외: {e}")

            elif "정산 리포트" in original_text or "누적 통계" in original_text:
                text, reply_markup = build_weekly_view(key)
                try:
                    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
                except Exception as e:
                    if "Message is not modified" not in str(e):
                        print(f"메시지 수정 예외: {e}")
            else:
                # 일반 `/l` (오늘의 할 일) 화면에서의 잔상 유지 애니메이션
                current_visible_indices = set()
                if query.message.reply_markup and query.message.reply_markup.inline_keyboard:
                    for row in query.message.reply_markup.inline_keyboard:
                        for btn in row:
                            if btn.callback_data and btn.callback_data.startswith("toggle_"):
                                try:
                                    b_idx = int(btn.callback_data.split("_")[1])
                                    current_visible_indices.add(b_idx)
                                except ValueError:
                                    pass

                if not current_visible_indices:
                    current_visible_indices = None

                # 🎬 [1단계] 까마귀로 즉시 변경하여 클릭 항목 잔상 강제 유지
                text_instant, reply_markup_instant = build_plan_view(key, visible_indices=current_visible_indices)
                if "-------------------------" in original_text:
                    header = original_text.split("-------------------------")[0]
                    text_instant = f"{header}-------------------------\n{text_instant}"

                try:
                    await query.edit_message_text(text_instant, reply_markup=reply_markup_instant, parse_mode="Markdown")
                except Exception as e:
                    if "Message is not modified" not in str(e):
                        print(f"메시지 수정 예외: {e}")

                # 🎬 [2단계] 1초간 까마귀 유지
                await asyncio.sleep(1)

                # 🎬 [3단계] 성경/필사의 경우 글자 리뉴얼 및 상태 미완료로 재설정
                if is_bible_task and target_item["done"]:
                    curr_ch_idx = target_item.get("bible_ch_idx", 0)
                    chunk_size = topic_data.get("bible_chunk", 4)
                    next_ch_idx = (curr_ch_idx + chunk_size) % len(ALL_BIBLE_CHAPTERS)
                    topic_data["bible_ch_idx"] = next_ch_idx
                    next_label = get_bible_label(next_ch_idx, chunk_size)

                    target_item["task"] = f"성경 묵상: {next_label}"
                    target_item["done"] = False
                    target_item["bible_ch_idx"] = next_ch_idx
                    save_data_to_supabase(key, topic_plans[key])

                if is_trans_task and target_item["done"]:
                    curr_v_idx = target_item.get("transcription_v_idx", 0)
                    chunk_size = topic_data.get("transcription_chunk", 10)
                    next_v_idx = (curr_v_idx + chunk_size) % len(ALL_BIBLE_VERSES)
                    topic_data["transcription_v_idx"] = next_v_idx
                    next_label = get_transcription_label(next_v_idx, chunk_size)

                    target_item["task"] = f"성경 필사: {next_label}"
                    target_item["done"] = False
                    target_item["transcription_v_idx"] = next_v_idx
                    save_data_to_supabase(key, topic_plans[key])

                # 🎬 [4단계] 1초 후 최종 화면 전환 (완료된 일반 항목 정리 및 성경/필사 새 분량 표시)
                text_final, reply_markup_final = build_plan_view(key)
                if "-------------------------" in original_text:
                    header = original_text.split("-------------------------")[0]
                    text_final = f"{header}-------------------------\n{text_final}"

                try:
                    await query.edit_message_text(text_final, reply_markup=reply_markup_final, parse_mode="Markdown")
                except Exception as e:
                    if "Message is not modified" not in str(e):
                        print(f"메시지 최종 수정 예외: {e}")

async def reset_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_topic_key(update)
    data = topic_plans.get(key, {})
    plans = data.get("plans", [])

    if not plans:
        await update.message.reply_text("🍃 초기화할 공부 계획이 없습니다.")
        return

    keyboard = [
        [InlineKeyboardButton("📋 일반 할 일만 초기화", callback_data="reset_tasks")],
        [InlineKeyboardButton("🔄 [매일] 루틴만 초기화", callback_data="reset_routines")],
        [InlineKeyboardButton("🍂 전체 초기화", callback_data="reset_all")],
        [InlineKeyboardButton("🌧️ 취소", callback_data="reset_cancel")],
    ]
    await update.message.reply_text("🍂 **초기화 옵션을 선택해 주세요:**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def morning_reminder_job(context: ContextTypes.DEFAULT_TYPE):
    for key, data in topic_plans.items():
        if data.get("disabled", False):
            continue
        chat_id, thread_id = key
        plan_text, reply_markup = build_plan_view(key)
        
        msg = (
            "☀️ **[좋은 아침입니다! 오늘 하루도 힘차게 시작해 봐요!]**\n\n"
            "오늘 달성할 공부 계획이나 할 일을 채팅창에 입력해 보세요!\n\n"
            "-------------------------\n"
            f"{plan_text}"
        )
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                message_thread_id=thread_id if thread_id != 0 else None,
                text=msg,
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"아침 알림 발송 실패 ({key}): {e}")

async def custom_time_reminder_job(context: ContextTypes.DEFAULT_TYPE):
    now_str = datetime.datetime.now(pytz.timezone("Asia/Seoul")).strftime("%H:%M")
    
    for key, data in topic_plans.items():
        if data.get("disabled", False):
            continue
        user_notify_time = data.get("notify_time")
        if user_notify_time and user_notify_time == now_str:
            chat_id, thread_id = key
            plans = data.get("plans", [])
            
            normal_plans = [p for p in plans if "[매일]" not in p.get("category", "")]
            routine_plans = [p for p in plans if "[매일]" in p.get("category", "") and not p.get("is_bible") and not p.get("is_transcription")]
            bible_plans = [p for p in plans if p.get("is_bible") == True]

            n_completed = sum(1 for p in normal_plans if p["done"])
            n_total = len(normal_plans)
            n_rate = (n_completed / n_total) * 100 if n_total > 0 else 0.0

            r_completed = sum(1 for p in routine_plans if p["done"])
            r_total = len(routine_plans)

            b_str = "완료 📖" if (bible_plans and bible_plans[0]["done"]) else "진행 중 🪺"

            uncompleted_with_index = [(i, p) for i, p in enumerate(plans) if not p["done"]]
            
            msg = (
                f"🌙 **[오늘의 공부 점검 알림 - {now_str}]**\n\n"
                f"오늘 계획하신 공부 및 성경 묵상은 차근차근 진행하고 계신가요?\n"
                f"잠시 하던 일을 멈추고 오늘의 달성 현황을 점검해 보세요!\n\n"
                f"📊 **오늘의 달성 현황:**\n"
                f"• **일반 공부 달성률:** `{n_rate:.1f}%` ({n_completed}/{n_total} 완료)\n"
                f"• **매일 루틴 달성:** `{r_completed}/{r_total}`\n"
                f"• **오늘의 성경 묵상:** `{b_str}`\n\n"
                f"📂 **[오늘의 남은 할 일]**\n"
            )

            keyboard = []
            if uncompleted_with_index:
                msg += "📋 버튼을 눌러 완료 처리하거나 🍂 삭제할 수 있습니다."
                
                last_cat = None
                for real_idx, item in uncompleted_with_index:
                    cat = item.get("category", "")
                    if cat and cat != last_cat:
                        keyboard.append([InlineKeyboardButton(f"📂 {cat}", callback_data="noop")])
                        last_cat = cat

                    if item.get("is_bible"):
                        status_icon = "🪺"
                    elif item.get("is_transcription"):
                        status_icon = "☕️"
                    else:
                        status_icon = "🥚"

                    # 알림 발송 시 루틴, 성경, 필사는 삭제 버튼 제외
                    is_routine = "[매일]" in cat
                    is_special = item.get("is_bible") or item.get("is_transcription") or is_routine

                    if is_special:
                        keyboard.append([
                            InlineKeyboardButton(f"{status_icon} {item['task']}", callback_data=f"toggle_{real_idx}")
                        ])
                    else:
                        keyboard.append([
                            InlineKeyboardButton(f"{status_icon} {item['task']}", callback_data=f"toggle_{real_idx}"),
                            InlineKeyboardButton("🍂 삭제", callback_data=f"delete_item_{real_idx}")
                        ])
            else:
                msg += "🌿 오늘 등록된 모든 공부/성경 묵상을 완료하셨습니다! 수고 많으셨습니다! ✨"

            reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    message_thread_id=thread_id if thread_id != 0 else None,
                    text=msg,
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            except Exception as e:
                print(f"맞춤 알림 발송 실패 ({key}): {e}")

async def saturday_weekly_reminder(context: ContextTypes.DEFAULT_TYPE):
    for key, data in topic_plans.items():
        if data.get("disabled", False):
            continue
        chat_id, thread_id = key
        weekly_text, _ = build_weekly_view(key)
        plans = data.get("plans", [])
        
        uncompleted_count = sum(1 for p in plans if not p["done"] and not p.get("is_bible") and not p.get("is_transcription"))

        msg = (
            "🍃 **[토요일 주간 정산 및 점검 리포트]**\n\n"
            + weekly_text
        )

        keyboard = []
        if uncompleted_count > 0:
            msg += "\n\n💡 **이번 주 미완료 항목 처리 방법을 선택해 주세요:**"
            keyboard = [
                [InlineKeyboardButton("🍂 이번 주 미완료 항목 삭제 (초기화)", callback_data="weekly_opt_clear")],
                [InlineKeyboardButton("➡️ 미완료 항목 다음 주로 이월", callback_data="weekly_opt_rollover")],
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
    now = datetime.datetime.now(pytz.timezone("Asia/Seoul"))
    today_str = now.strftime("%m/%d")
    today_weekday_kor = WEEKDAY_KOR[now.weekday()]
    
    for key, data in topic_plans.items():
        if data.get("disabled", False):
            continue
        plans = data.get("plans", [])
        
        routine_names = list(dict.fromkeys([
            p["task"] for p in plans 
            if "[매일]" in p.get("category", "") and not p.get("is_bible") and not p.get("is_transcription")
        ]))
        
        for task_name in routine_names:
            already_exists = any(
                p["task"] == task_name and p.get("date") == today_str and "[매일]" in p.get("category", "")
                for p in plans
            )
            if not already_exists:
                plans.append({
                    "task": task_name,
                    "category": "[매일]",
                    "done": False,
                    "date": today_str,
                })

        weekly_tasks_dict = data.get("weekly_tasks", {})
        if today_weekday_kor in weekly_tasks_dict:
            for task_name in weekly_tasks_dict[today_weekday_kor]:
                already_exists = any(
                    p["task"] == task_name and p.get("date") == today_str
                    for p in plans
                )
                if not already_exists:
                    plans.append({
                        "task": task_name,
                        "category": f"[{today_weekday_kor}요일 과제]",
                        "done": False,
                        "date": today_str,
                    })

        bible_plans = [p for p in plans if p.get("is_bible") == True]
        if bible_plans:
            last_bible = bible_plans[-1]
            if last_bible["done"]:
                curr_ch_idx = data.get("bible_ch_idx", 0)
                chunk_size = data.get("bible_chunk", 4)
                
                next_ch_idx = (curr_ch_idx + chunk_size) % len(ALL_BIBLE_CHAPTERS)
                data["bible_ch_idx"] = next_ch_idx
                next_label = get_bible_label(next_ch_idx, chunk_size)

                plans.append({
                    "task": f"성경 묵상: {next_label}",
                    "category": "[매일]",
                    "done": False,
                    "date": today_str,
                    "is_bible": True,
                    "bible_ch_idx": next_ch_idx
                })

        transcription_plans = [p for p in plans if p.get("is_transcription") == True]
        if transcription_plans:
            last_trans = transcription_plans[-1]
            if last_trans["done"]:
                curr_v_idx = data.get("transcription_v_idx", 0)
                chunk_size = data.get("transcription_chunk", 10)
                
                next_v_idx = (curr_v_idx + chunk_size) % len(ALL_BIBLE_VERSES)
                data["transcription_v_idx"] = next_v_idx
                next_label = get_transcription_label(next_v_idx, chunk_size)

                plans.append({
                    "task": f"성경 필사: {next_label}",
                    "category": "[매일]",
                    "done": False,
                    "date": today_str,
                    "is_transcription": True,
                    "transcription_v_idx": next_v_idx
                })
        
        save_data_to_supabase(key, topic_plans[key])

async def sunday_rollover_job(context: ContextTypes.DEFAULT_TYPE):
    for key, data in topic_plans.items():
        if data.get("disabled", False):
            continue
        plans = data.get("plans", [])
        
        uncompleted_plans = [p for p in plans if not p["done"]]
        topic_plans[key]["plans"] = uncompleted_plans
        topic_plans[key]["weekly_tasks"] = {}
        save_data_to_supabase(key, topic_plans[key])

# 🎯 그룹/토픽 방에서는 자동완성이 차단되도록 Scope 분리 적용
async def post_init(application):
    load_data_from_supabase()

    user_commands = [
        BotCommand("s", "봇 시작 및 안내문 보기 (/start)"),
        BotCommand("l", "오늘의 할 일 체크박스 확인 (/list)"),
        BotCommand("r", "매일 반복 루틴 등록 (/routine)"),
        BotCommand("wt", "주간 요일별 과제 등록 (/weekly_task)"),
        BotCommand("bs", "성경 묵상 시작점 지정 (/bible_start)"),
        BotCommand("bp", "하루 읽을 성경 장수 설정 (/bible_pages)"),
        BotCommand("st", "성경 66권 완독 현황판 보기 (/bible_status)"),
        BotCommand("ts", "성경 필사 시작점 지정 (/tr_start)"),
        BotCommand("tp", "하루 필사할 성경 절수 설정 (/tr_pages)"),
        BotCommand("tst", "성경 66권 필사 현황판 보기 (/tr_status)"),
        BotCommand("d", "할 일 삭제 (/del)"),
        BotCommand("t", "일일 점검 알림 시간 설정 (/time)"),
        BotCommand("e", "등록된 매일 루틴 수정 (/edit)"),
        BotCommand("w", "주간 공부/성경 달성률 리포트 (/weekly)"),
        BotCommand("rs", "오늘 계획 초기화 (/reset)"),
        BotCommand("off", "이 토픽에서 봇 비활성화"),
        BotCommand("on", "이 토픽에서 봇 재활성화"),
    ]

    # 1. 🎯 기본/그룹/토픽 방의 명령어 자동완성 삭제
    await application.bot.delete_my_commands()

    # 2. 🎯 1:1 개인 대화방(Private Chats)에만 명령어 목록 등록
    try:
        await application.bot.set_my_commands(
            user_commands,
            scope=BotCommandScopeAllPrivateChats()
        )
    except Exception as e:
        print(f"개인방 명령어 메뉴 등록 실패: {e}")

    # 3. 🎯 관리자(ADMIN_ID) 전용 채팅방 메뉴 등록
    admin_commands = user_commands + [
        BotCommand("re", "[관리자] 답변 전송 (/reply)"),
        BotCommand("bc", "[관리자] 공지 과제 발송 (/broadcast)"),
        BotCommand("bcr", "[관리자] 공지 결과 리포트 (/broadcast_report)"),
    ]
    
    try:
        await application.bot.set_my_commands(
            admin_commands,
            scope=BotCommandScopeChat(chat_id=ADMIN_ID)
        )
    except Exception as e:
        print(f"관리자 전용 메뉴 등록 실패 (ADMIN_ID 확인 필요): {e}")

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        return

def run_health_check_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    print(f"🌐 헬스체크 웹 서버가 포트 {port}에서 대기 중입니다...")
    server.serve_forever()

if __name__ == "__main__":
    health_thread = threading.Thread(target=run_health_check_server, daemon=True)
    health_thread.start()
    
    import time
    time.sleep(1)

    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .read_timeout(30)
        .write_timeout(30)
        .connect_timeout(30)
        .pool_timeout(30)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler(["start", "START", "Start", "s", "S"], start))
    app.add_handler(CommandHandler(["off", "OFF", "Off"], bot_off))
    app.add_handler(CommandHandler(["on", "ON", "On"], bot_on))
    app.add_handler(CommandHandler(["reply", "REPLY", "Reply", "re", "RE"], admin_reply))
    app.add_handler(CommandHandler(["routine", "ROUTINE", "Routine", "r", "R"], add_routine))
    app.add_handler(CommandHandler(["weekly_task", "WEEKLY_TASK", "Weekly_task", "wt", "WT"], add_weekly_task))
    app.add_handler(CommandHandler(["broadcast", "BROADCAST", "Broadcast", "bc", "BC"], broadcast_task))
    app.add_handler(CommandHandler(["broadcast_report", "BROADCAST_REPORT", "bcr", "BCR"], broadcast_report))
    app.add_handler(CommandHandler(["time", "TIME", "Time", "t", "T"], set_notify_time))
    app.add_handler(CommandHandler(["bible_pages", "BIBLE_PAGES", "bp", "BP"], bible_pages))
    app.add_handler(CommandHandler(["bible_start", "BIBLE_START", "bs", "BS"], bible_start))
    app.add_handler(CommandHandler(["bible_status", "BIBLE_STATUS", "st", "ST"], bible_status))
    app.add_handler(CommandHandler(["tr_pages", "TR_PAGES", "tp", "TP"], transcription_pages))
    app.add_handler(CommandHandler(["tr_start", "TR_START", "ts", "TS"], transcription_start))
    app.add_handler(CommandHandler(["tr_status", "TR_STATUS", "tst", "TST"], transcription_status))
    app.add_handler(CommandHandler(["delete", "del", "d", "DELETE", "DEL", "D"], delete_plan))
    app.add_handler(CommandHandler(["edit", "edit_routine", "EDIT", "EDIT_ROUTINE", "e", "E"], edit_routine))
    app.add_handler(CommandHandler(["list", "ls", "LIST", "LS", "List", "l", "L"], list_plans))
    app.add_handler(CommandHandler(["weekly", "WEEKLY", "Weekly", "w", "W"], weekly_plans))
    app.add_handler(CommandHandler(["reset", "RESET", "Reset", "rs", "RS"], reset_plans))
    app.add_handler(CallbackQueryHandler(button_click))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    job_queue = app.job_queue
    tz = pytz.timezone("Asia/Seoul")

    reset_time = datetime.time(hour=5, minute=0, second=0, tzinfo=tz)
    morning_time = datetime.time(hour=8, minute=0, second=0, tzinfo=tz)
    sat_time = datetime.time(hour=21, minute=0, second=0, tzinfo=tz)

    job_queue.run_daily(morning_reminder_job, time=morning_time)
    job_queue.run_daily(saturday_weekly_reminder, time=sat_time, days=(6,))
    job_queue.run_daily(daily_routine_reset_job, time=reset_time)
    job_queue.run_daily(sunday_rollover_job, time=reset_time, days=(0,))
    
    job_queue.run_repeating(custom_time_reminder_job, interval=60, first=10)

    print("🤖 봇 및 스케줄러가 정상 실행 중입니다...")
    app.run_polling()
