"""메시지 텍스트(HTML)와 인라인 버튼 구성.

callback_data 규칙 (64바이트 제한, 항목은 인덱스가 아닌 DB id로 가리킨다)
  _                  아무 동작 없음 (제목 버튼)
  l / l:n            오늘 목록 / 밤 점검 화면 다시 그리기
  t:{mode}:{id}      할 일 완료 토글            (mode: l=목록, n=밤 점검)
  r:{mode}:{id}      루틴 오늘 완료 토글
  n:t:{id} n:x:{id}  밤 점검 - 내일로 / 삭제
  e                  편집 화면
  e:n|t|x:{id}       편집 - 이름 변경 / 내일로 / 삭제
  u:{id}             날짜 해석 취소 -> 오늘 할 일로
  rm / rm:{id}       루틴 관리 목록 / 루틴 상세
  rd:{id}:{day}      루틴 요일 토글
  rn:{id}            루틴 이름 변경
  rx:{id} / ry:{id}  루틴 삭제 확인 / 삭제 실행
  bc:{bid}:{idx}     공지 과제 토글
  qz:{qid}:{idx}     성구 퀴즈 답 선택 / qz:i 퀴즈 루틴 안내
  rc:* / rv:*        계시록 암송 카드 / 진도판 (recite_handlers.py 맨 위 설명 참고)
  cx:{id}            다 끝내서 접힌 섹션 펼치기 (그 섹션의 할 일 id로 섹션을 찾음)
"""
from __future__ import annotations

import datetime as dt
from html import escape

from telegram import InlineKeyboardButton as Btn
from telegram import InlineKeyboardMarkup

from .dates import WEEKDAYS, days_label, fmt_long, fmt_short
from .logic import TaskItem, TodayView, WeekReport, best_streak, current_streak

MAX_LIST_TASKS = 60
MAX_NIGHT_TASKS = 20
MAX_EDIT_TASKS = 25
MAX_UPCOMING = 10

NOOP = "_"


def _cut(s: str, n: int = 60) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def _markup(rows):
    return InlineKeyboardMarkup(rows) if rows else None


def _task_label(item: TaskItem) -> str:
    icon = "🎓" if item.done else "🥚"
    delay = f"🔥D+{item.overdue} " if item.overdue > 0 and not item.done else ""
    return _cut(f"{icon} {delay}{item.task['title']}")


def _routine_label(r) -> str:
    icon = "🍋" if r.done_today else "🥚"
    fire = f" 🔥{r.streak}" if r.streak >= 2 else ""
    return _cut(f"{icon} {r.routine['title']}{fire}")


def _quiz_label(q) -> str:
    icon = "🍋" if q.done else "🥚"
    fire = f" 🔥{q.streak}" if q.streak >= 2 else ""
    return f"{icon} 📜 성구 퀴즈 {q.answered}/{q.target}{fire}"


def _recite_label(s) -> str:
    icon = "🍋" if s.is_done else "🥚"
    fire = f" 🔥{s.streak}" if s.streak >= 2 else ""
    return f"{icon} 📖 계시록 암송 {s.done}/{s.total}{fire}"


def _routine_rows(view: TodayView, mode: str, pending_only: bool = False):
    items = [r for r in view.routines if not (pending_only and r.done_today)]
    show_quiz = view.quiz is not None and not (pending_only and view.quiz.done)
    show_recite = view.recite is not None and not (pending_only and view.recite.is_done)
    rows = []
    if items or show_quiz or show_recite:
        rows.append([Btn("🐦‍⬛ 남은 루틴" if pending_only else "🐦‍⬛ 오늘의 루틴", callback_data=NOOP)])
    rows += [[Btn(_routine_label(r), callback_data=f"r:{mode}:{r.routine['id']}")] for r in items]
    if show_quiz:
        rows.append([Btn(_quiz_label(view.quiz), callback_data="qz:i")])
    if show_recite:
        rows.append([Btn(_recite_label(view.recite), callback_data="rc:i")])
    return rows


def _stats_line(view: TodayView) -> str:
    parts = []
    total = len(view.routines) + (1 if view.quiz else 0) + (1 if view.recite else 0)
    if total:
        done = (sum(r.done_today for r in view.routines) + (1 if view.quiz and view.quiz.done else 0)
                + (1 if view.recite and view.recite.is_done else 0))
        parts.append(f"🐦‍⬛ 루틴 {done}/{total}")
    items = view.task_items
    if items:
        done = sum(i.done for i in items)
        parts.append(f"🎓 할 일 {done}/{len(items)}")
    return " · ".join(parts)


def _upcoming_text(view: TodayView) -> str:
    if not view.upcoming:
        return ""
    lines = ["", "📅 <b>예정</b>"]
    for t in view.upcoming[:MAX_UPCOMING]:
        cat = f" <i>[{escape(t['category'])}]</i>" if t["category"] != "일반" else ""
        lines.append(f"• {fmt_short(t['due_date'])} {escape(t['title'])}{cat}")
    if len(view.upcoming) > MAX_UPCOMING:
        lines.append(f"  … 외 {len(view.upcoming) - MAX_UPCOMING}개")
    return "\n".join(lines)


def render_today(view: TodayView, mode: str = "l", intro: str | None = None,
                 expanded: str | None = None):
    """mode: l=오늘 목록, n=밤 점검, e=편집
    expanded: 목록에서 펼쳐 볼 '다 끝낸 섹션' 이름 (그 밖의 다 끝낸 섹션은 한 줄로 접힘)"""
    if mode == "n":
        return _render_night(view, intro)
    if mode == "e":
        return _render_edit(view)

    lines = [intro, ""] if intro else []
    lines.append(f"🌿 <b>{fmt_long(view.today)} 오늘의 정원</b>")
    if view.has_today:
        lines.append(_stats_line(view))
        if view.all_clear:
            lines += ["", "🌾 <b>오늘의 농사 완료! ALL CLEAR!</b> 수고 많으셨어요 🐦‍⬛"]
        else:
            lines += ["", "버튼을 누르면 완료 ↔ 미완료가 바뀌어요."]
    else:
        lines += ["", "🍃 아직 오늘 할 일이 없어요.",
                  "채팅창에 할 일을 적거나 <code>/r 루틴</code>으로 루틴을 만들어 보세요."]
    text = "\n".join(lines) + _upcoming_text(view)

    rows = _routine_rows(view, "l")
    shown = hidden = 0
    for cat, items in view.categories:
        if all(i.done for i in items) and cat != expanded:
            # 섹션을 다 끝내면 한 줄로 접는다. 누르면 펼쳐서 실수로 누른 항목을 되돌릴 수 있다.
            rows.append([Btn(f"🌾 {_cut(cat, 30)} 완료 ({len(items)}) ▸",
                             callback_data=f"cx:{items[0].task['id']}")])
            continue
        title = f"🔽 {_cut(cat, 30)} 접기" if cat == expanded else f"☁️ {_cut(cat, 40)}"
        rows.append([Btn(title, callback_data="l" if cat == expanded else NOOP)])
        for item in items:
            if shown >= MAX_LIST_TASKS:
                hidden += 1
                continue
            rows.append([Btn(_task_label(item), callback_data=f"t:l:{item.task['id']}")])
            shown += 1
    if hidden:
        rows.append([Btn(f"… 외 {hidden}개 (편집 화면에서 정리)", callback_data=NOOP)])
    if view.task_items or view.upcoming:
        rows.append([Btn("✏️ 편집", callback_data="e"), Btn("🔄 새로고침", callback_data="l")])
    return text, _markup(rows)


def _render_night(view: TodayView, intro: str | None):
    lines = [intro, ""] if intro else []
    lines.append(f"🌙 <b>밤 점검 · {fmt_long(view.today)}</b>")
    if view.has_today:
        lines.append(_stats_line(view))
    open_tasks = view.open_tasks
    if view.all_clear:
        lines += ["", "🌾 오늘 할 일을 모두 끝냈어요! 푹 쉬세요 ☁️"]
    elif open_tasks:
        lines += ["", "남은 할 일을 정리해 볼까요?",
                  "✅ 완료 · ➡️ 내일로 · 🗑 삭제",
                  "<i>고르지 않은 할 일은 내일 🔥D+1로 넘어가요.</i>"]
    else:
        lines += ["", "남은 루틴을 확인해 보세요!"]
    text = "\n".join(lines) + _upcoming_text(view)

    rows = _routine_rows(view, "n", pending_only=True)
    for item in open_tasks[:MAX_NIGHT_TASKS]:
        tid = item.task["id"]
        rows.append([Btn(_task_label(item), callback_data=NOOP)])
        rows.append([Btn("✅ 완료", callback_data=f"t:n:{tid}"),
                     Btn("➡️ 내일로", callback_data=f"n:t:{tid}"),
                     Btn("🗑 삭제", callback_data=f"n:x:{tid}")])
    if len(open_tasks) > MAX_NIGHT_TASKS:
        rows.append([Btn(f"… 외 {len(open_tasks) - MAX_NIGHT_TASKS}개는 /l 에서", callback_data=NOOP)])
    return text, _markup(rows)


def _render_edit(view: TodayView):
    text = ("✏️ <b>할 일 편집</b>\n"
            "이름을 누르면 이름을 바꿀 수 있어요.\n"
            "➡️ 내일로 미루기 · 🗑 바로 삭제\n"
            "<i>루틴은 /r 에서 관리해요.</i>")
    targets = [(i.task, _task_label(i)) for i in view.open_tasks]
    targets += [(t, _cut(f"📅 {fmt_short(t['due_date'])} {t['title']}")) for t in view.upcoming]
    rows = []
    for task, label in targets[:MAX_EDIT_TASKS]:
        tid = task["id"]
        rows.append([Btn(f"✏️ {label}", callback_data=f"e:n:{tid}"),
                     Btn("➡️", callback_data=f"e:t:{tid}"),
                     Btn("🗑", callback_data=f"e:x:{tid}")])
    if not targets:
        text += "\n\n🍃 편집할 미완료 할 일이 없어요."
    elif len(targets) > MAX_EDIT_TASKS:
        text += f"\n\n<i>앞의 {MAX_EDIT_TASKS}개만 보여요.</i>"
    rows.append([Btn("◀ 목록으로", callback_data="l")])
    return text, _markup(rows)


# ---------------------------------------------------------------------------
def render_week(rep: WeekReport):
    lines = [f"🍃 <b>주간 리포트</b>  {fmt_short(rep.start)} ~ {fmt_short(rep.end)}", ""]

    rate = rep.task_rate
    if rate is None:
        lines.append("🎓 할 일: 이번 주 기록이 없어요.")
    else:
        total = rep.tasks_done + len(rep.tasks_open)
        lines.append(f"🎓 <b>할 일</b> {rep.tasks_done}/{total} 완료 ({rate:.0f}%)")
        for item in rep.tasks_open[:10]:
            delay = f" 🔥D+{item.overdue}" if item.overdue > 0 else ""
            lines.append(f"   🥚 {escape(item.task['title'])}{delay}")
        if len(rep.tasks_open) > 10:
            lines.append(f"   … 외 {len(rep.tasks_open) - 10}개")

    lines.append("")
    if rep.routines:
        lines.append("🐦‍⬛ <b>루틴</b>")
        for rw in rep.routines:
            harvest = " 🍋" if rw.scheduled and rw.done == rw.scheduled else ""
            lines.append(f"• {escape(rw.routine['title'])} — {rw.done}/{rw.scheduled}{harvest}"
                         f"  🔥{rw.streak} (최고 {rw.best})")
    else:
        lines.append("🐦‍⬛ 루틴: 등록된 루틴이 없어요. <code>/r 루틴</code>")
    return "\n".join(lines), _markup([[Btn("📋 오늘 목록", callback_data="l")]])


# ---------------------------------------------------------------------------
def render_routines(routines: list[dict], logs: dict[int, set[dt.date]], today: dt.date, intro: str | None = None):
    lines = [intro, ""] if intro else []
    lines.append("🐦‍⬛ <b>루틴 관리</b>")
    rows = []
    if not routines:
        lines.append("\n아직 루틴이 없어요.")
    for r in routines:
        streak = current_streak(r["days"], logs.get(r["id"], set()), today, r["created_on"])
        lines.append(f"• {escape(r['title'])} — {days_label(r['days'])} · 🔥{streak}")
        rows.append([Btn(_cut(f"⚙️ {r['title']} ({days_label(r['days'])})"), callback_data=f"rm:{r['id']}")])
    lines += ["", "<b>추가하기</b>",
              "<code>/r 영단어 30개</code> → 매일",
              "<code>/r 월수금 운동</code> · <code>/r 평일 출근 전 독서</code> · <code>/r 주말 대청소</code>",
              "<i>여러 줄로 쓰면 한 번에 여러 개를 추가해요.</i>"]
    return "\n".join(lines), _markup(rows)


def render_routine_detail(r: dict, logs: set[dt.date], today: dt.date):
    streak = current_streak(r["days"], logs, today, r["created_on"])
    best = best_streak(r["days"], logs, today, r["created_on"])
    text = (f"⚙️ <b>{escape(r['title'])}</b>\n"
            f"요일: {days_label(r['days'])}\n"
            f"🔥 연속 {streak}일 · 최고 {best}일\n\n"
            f"요일 버튼을 눌러 켜고 끌 수 있어요.")
    day_row = [Btn(("✅" if i in r["days"] else "▫️") + WEEKDAYS[i], callback_data=f"rd:{r['id']}:{i}")
               for i in range(7)]
    rows = [day_row[:4], day_row[4:],
            [Btn("✏️ 이름 변경", callback_data=f"rn:{r['id']}"),
             Btn("🗑 삭제", callback_data=f"rx:{r['id']}")],
            [Btn("◀ 루틴 목록", callback_data="rm")]]
    return text, _markup(rows)


def render_routine_delete_confirm(r: dict):
    text = (f"🗑 <b>{escape(r['title'])}</b> 루틴을 삭제할까요?\n"
            f"지금까지의 기록과 연속 기록도 함께 사라져요.")
    rows = [[Btn("삭제", callback_data=f"ry:{r['id']}"), Btn("취소", callback_data=f"rm:{r['id']}")]]
    return text, _markup(rows)


# ---------------------------------------------------------------------------
def render_broadcast(b: dict, checked: set[int]):
    items = b["items"]
    all_done = items and all(i in checked for i in range(len(items)))
    text = f"🕊️ <b>{escape(b['title'])}</b>\n\n아래 과제를 확인한 뒤 완료한 항목을 눌러 주세요!"
    if all_done:
        text += "\n\n🌿 <b>모든 과제를 완수했어요!</b> 👏🏻✨"
    rows = [[Btn(_cut(f"{'🐦‍⬛' if i in checked else '🥚'} {item}"), callback_data=f"bc:{b['id']}:{i}")]
            for i, item in enumerate(items)]
    return text, _markup(rows)


# ---------------------------------------------------------------------------
def render_quiz(q: dict, verse: dict | None = None, today_progress: str | None = None):
    """q: quiz_questions 행. 아직 안 풀었으면 보기 버튼, 풀었으면 정답과 본문."""
    hour = f" · {q['hour']}시" if q.get("hour") is not None else ""
    if q["kind"] == "ref2core":
        ask = f"<b>{escape(q['ref'])}</b>의 핵심 내용은?"
    else:
        ask = f"“{escape(q['prompt'])}”\n\n이 말씀은 어디에 있을까요?"
    lines = [f"📜 <b>성구 퀴즈</b>{hour}", "", ask]

    answered = q.get("answer_idx")
    if answered is None:
        rows = [[Btn(_cut(f"{'①②③④'[i]} {opt}", 64), callback_data=f"qz:{q['id']}:{i}")]
                for i, opt in enumerate(q["options"])]
        return "\n".join(lines), _markup(rows)

    correct = q["correct_idx"]
    if answered == correct:
        lines += ["", "⭕ <b>정답이에요!</b>"]
    else:
        lines += ["", f"❌ 아쉬워요! 정답은 <b>{escape(q['options'][correct])}</b>"]
    if verse:
        lines += ["", f"📖 <b>{escape(verse['ref'])}</b> {escape(verse.get('body') or verse['core'])}"]
    if today_progress:
        lines += ["", today_progress]
    rows = []
    for i, opt in enumerate(q["options"]):
        mark = "✅" if i == correct else ("❌" if i == answered else "▫️")
        rows.append([Btn(_cut(f"{mark} {opt}", 64), callback_data=NOOP)])
    return "\n".join(lines), _markup(rows)
