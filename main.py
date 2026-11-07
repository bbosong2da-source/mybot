"""구름 언덕과 까마귀 정원 봇 - 실행 파일."""
import datetime as dt
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import BotCommand, BotCommandScopeChat, BotCommandScopeDefault
from telegram.constants import ParseMode
from telegram.ext import (ApplicationBuilder, CallbackQueryHandler, CommandHandler, Defaults,
                          MessageHandler, filters)

from bot import admin, callbacks, handlers, jobs, quiz_handlers, recite_handlers
from bot.config import (ADMIN_ID, BOT_TOKEN, MORNING_HOUR, PORT, SUPABASE_KEY, SUPABASE_URL, TZ)
from bot.storage import MemoryRepo, SupabaseRepo

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("garden_bot")

USER_COMMANDS = [
    BotCommand("l", "오늘 목록"),
    BotCommand("r", "루틴 관리 (/r 월수금 운동)"),
    BotCommand("w", "주간 리포트"),
    BotCommand("t", "밤 점검 시각 (/t 22:00, /t off)"),
    BotCommand("q", "성구 퀴즈 시간 (/q 13-22, /q off)"),
    BotCommand("rv", "계시록 암송 (시작·진도판)"),
    BotCommand("start", "사용 안내"),
    BotCommand("off", "이 방에서 봇 끄기"),
    BotCommand("on", "이 방에서 봇 켜기"),
]
ADMIN_COMMANDS = USER_COMMANDS + [
    BotCommand("bc", "[관리자] 공지 과제 보내기"),
    BotCommand("bcr", "[관리자] 공지 결과"),
    BotCommand("re", "[관리자] 답변 보내기"),
    BotCommand("qa", "[관리자] 성구 등록"),
    BotCommand("qv", "[관리자] 성구 목록"),
    BotCommand("qd", "[관리자] 성구 삭제"),
    BotCommand("rva", "[관리자] 암송 본문 등록"),
    BotCommand("rvs", "[관리자] 암송 현황"),
]


async def post_init(app):
    await app.bot.set_my_commands(USER_COMMANDS, scope=BotCommandScopeDefault())
    try:
        await app.bot.set_my_commands(ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=ADMIN_ID))
    except Exception as e:
        log.warning("관리자 메뉴 등록 실패 (관리자가 봇과 대화를 시작했는지 확인): %s", e)


async def on_error(update, context):
    log.exception("처리 중 오류", exc_info=context.error)


class HealthCheck(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass


def make_repo():
    if SUPABASE_URL and SUPABASE_KEY:
        log.info("Supabase 저장소 사용")
        return SupabaseRepo(SUPABASE_URL, SUPABASE_KEY)
    log.warning("SUPABASE_URL/SUPABASE_KEY가 없어 메모리 저장소로 실행합니다 (재시작하면 데이터가 사라져요)")
    return MemoryRepo()


def build_app():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN 환경변수가 필요합니다.")
    app = (ApplicationBuilder().token(BOT_TOKEN)
           .defaults(Defaults(parse_mode=ParseMode.HTML, tzinfo=TZ))
           .read_timeout(30).write_timeout(30).connect_timeout(30).pool_timeout(30)
           .post_init(post_init).build())
    app.bot_data["repo"] = make_repo()

    cmd = lambda names, fn: app.add_handler(CommandHandler(names, fn))
    cmd(["start", "s", "help"], handlers.cmd_start)
    cmd(["l", "list"], handlers.cmd_list)
    cmd(["r", "routine"], handlers.cmd_routine)
    cmd(["w", "week", "weekly"], handlers.cmd_week)
    cmd(["t", "time"], handlers.cmd_time)
    cmd(["off"], handlers.cmd_off)
    cmd(["on"], handlers.cmd_on)
    cmd(["bc", "broadcast"], admin.cmd_broadcast)
    cmd(["bcr", "broadcast_report"], admin.cmd_broadcast_report)
    cmd(["re", "reply"], admin.cmd_reply)
    cmd(["q", "quiz"], quiz_handlers.cmd_quiz)
    cmd(["qa"], quiz_handlers.cmd_quiz_add)
    cmd(["qv"], quiz_handlers.cmd_quiz_list)
    cmd(["qd"], quiz_handlers.cmd_quiz_delete)
    cmd(["rv", "recite"], recite_handlers.cmd_recite)
    cmd(["rva"], recite_handlers.cmd_recite_add)
    cmd(["rvs"], recite_handlers.cmd_recite_status)

    app.add_handler(CallbackQueryHandler(callbacks.on_button))
    app.add_handler(MessageHandler(filters.StatusUpdate.FORUM_TOPIC_EDITED, handlers.handle_topic_edited))
    app.add_handler(MessageHandler(filters.Document.ALL, quiz_handlers.on_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_message))
    app.add_error_handler(on_error)

    jq = app.job_queue
    jq.run_daily(jobs.morning_job, time=dt.time(hour=MORNING_HOUR, minute=0, tzinfo=TZ))
    # 매분 0초 근처에 실행되도록 다음 분 시작에 맞춰 시작
    jq.run_repeating(jobs.minute_job, interval=60, first=60 - dt.datetime.now().second)
    return app


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), HealthCheck)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log.info("헬스체크 서버 포트 %s", PORT)
    build_app().run_polling(allowed_updates=["message", "callback_query"])
