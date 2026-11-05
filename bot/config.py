"""환경변수와 공통 상수."""
import os

import pytz

TZ = pytz.timezone("Asia/Seoul")

BOT_TOKEN = os.environ.get("BOT_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "75036448"))
PORT = int(os.environ.get("PORT", "8080"))

DEFAULT_NOTIFY_TIME = "22:00"   # 새 공간의 밤 점검 기본 시각
MORNING_HOUR = 8                # 아침 알림 (08:00 고정)
WEEKLY_FALLBACK_TIME = "22:00"  # 밤 점검을 끈 공간의 토요일 주간 리포트 시각

MAX_TITLE_LEN = 200
DEFAULT_CATEGORY = "일반"
