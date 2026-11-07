"""정해진 시각 작업.

할 일과 루틴 상태는 '날짜'로 계산되므로 자정에 데이터를 바꾸는 작업이 없다.
(미완료 할 일은 다음 날 자동으로 🔥D+1, 루틴은 요일에 맞춰 자동으로 나타남)
"""
from __future__ import annotations

import asyncio
import logging

from . import dates
from .common import load_state, load_today, repo, send_to_space
from .config import WEEKLY_FALLBACK_TIME
from .logic import build_week
from .quiz_handlers import issue_due_quizzes
from .recite_handlers import issue_recite_slots
from .views import render_today, render_week

log = logging.getLogger(__name__)
SEND_GAP = 0.05  # 텔레그램 전송 속도 제한 대비


async def morning_job(context):
    r = repo(context)
    today = dates.today()
    for space in await r.all_spaces():
        if space.get("disabled"):
            continue
        try:
            view = await load_today(r, space, today)
            if view.is_empty:
                continue
            text, markup = render_today(view, "l", intro="☀️ <b>좋은 아침이에요!</b> 오늘의 씨앗을 뿌려 볼까요?")
            await send_to_space(context.bot, space, text, markup)
        except Exception:
            log.exception("아침 알림 실패 space=%s", space.get("id"))
        await asyncio.sleep(SEND_GAP)


async def minute_job(context):
    """매분 실행: 성구 퀴즈 정각 출제 + 계시록 암송 카드 + 공간별 밤 점검(토요일엔 주간 리포트도) 전송."""
    r = repo(context)
    now = dates.now()
    hhmm = now.strftime("%H:%M")
    # 밤 점검이 가리키는 날: 새벽 4시 전이면 전날 (예: /t 00:30 -> 전날 밤 점검)
    night_day = dates.night_day_of(now)
    is_saturday = dates.sun_index(night_day) == 6

    sent: set = context.bot_data.setdefault("sent_marks", set())
    for mark in [m for m in sent if m[1] != night_day]:
        sent.discard(mark)

    spaces = await r.all_spaces()
    await issue_due_quizzes(context, spaces, now, SEND_GAP)
    await issue_recite_slots(context, spaces, now, SEND_GAP)

    for space in spaces:
        if space.get("disabled"):
            continue
        notify = space.get("notify_time")
        night = notify == hhmm
        weekly = is_saturday and (night or (notify is None and hhmm == WEEKLY_FALLBACK_TIME))
        if not (night or weekly):
            continue
        mark = (space["id"], night_day)
        if mark in sent:
            continue
        sent.add(mark)
        try:
            state = await load_state(r, space["id"], night_day)
            if night:
                view = await load_today(r, space, night_day, state)
                if not view.is_empty:
                    text, markup = render_today(view, "n")
                    await send_to_space(context.bot, space, text, markup)
            if weekly:
                tasks, routines, _ = state
                if tasks or routines:
                    text, markup = render_week(build_week(*state, night_day))
                    await send_to_space(context.bot, space, text, markup)
        except Exception:
            log.exception("밤 점검 실패 space=%s", space.get("id"))
        await asyncio.sleep(SEND_GAP)
