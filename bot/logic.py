"""DB·텔레그램과 무관한 순수 계산 로직 (연속 기록, 오늘 목록 구성, 주간 통계)."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from .config import DEFAULT_CATEGORY
from .dates import sun_index, week_range

DAY = dt.timedelta(days=1)


def routine_due(days: list[int], d: dt.date) -> bool:
    return sun_index(d) in days


def current_streak(days: list[int], done: set[dt.date], today: dt.date, start: dt.date) -> int:
    """오늘(아직 안 했으면 어제)부터 거꾸로, 예정된 날을 연속으로 해낸 횟수."""
    if not days:
        return 0
    d = today
    if routine_due(days, d) and d not in done:
        d -= DAY  # 오늘 아직 안 한 것은 연속 기록을 끊지 않는다
    count = 0
    while d >= start:
        if routine_due(days, d):
            if d not in done:
                break
            count += 1
        d -= DAY
    return count


def best_streak(days: list[int], done: set[dt.date], today: dt.date, start: dt.date) -> int:
    if not days:
        return 0
    best = run = 0
    d = start
    while d <= today:
        if routine_due(days, d):
            if d in done:
                run += 1
                best = max(best, run)
            elif d != today:
                run = 0
        d += DAY
    return best


@dataclass
class RoutineItem:
    routine: dict
    done_today: bool
    streak: int


@dataclass
class TaskItem:
    task: dict
    overdue: int  # 예정일보다 며칠 지났는지 (완료 항목은 0)

    @property
    def done(self) -> bool:
        return self.task["done_at"] is not None


@dataclass
class TodayView:
    today: dt.date
    routines: list[RoutineItem] = field(default_factory=list)
    categories: list[tuple[str, list[TaskItem]]] = field(default_factory=list)
    upcoming: list[dict] = field(default_factory=list)
    quiz: object | None = None   # quiz.QuizStatus — 오늘의 루틴처럼 보여 주는 성구 퀴즈
    recite: object | None = None  # recite.ReciteStatus — 오늘의 루틴처럼 보여 주는 계시록 암송

    @property
    def task_items(self) -> list[TaskItem]:
        return [t for _, items in self.categories for t in items]

    @property
    def open_tasks(self) -> list[TaskItem]:
        return [t for t in self.task_items if not t.done]

    @property
    def has_today(self) -> bool:
        return bool(self.routines or self.categories or self.quiz or self.recite)

    @property
    def is_empty(self) -> bool:
        return not self.has_today and not self.upcoming

    @property
    def all_clear(self) -> bool:
        return (self.has_today and all(r.done_today for r in self.routines)
                and not self.open_tasks and (self.quiz is None or self.quiz.done)
                and (self.recite is None or self.recite.is_done))


def category_sort_key(name: str):
    return (name == DEFAULT_CATEGORY, name)


def build_today(tasks: list[dict], routines: list[dict], logs: dict[int, set[dt.date]],
                today: dt.date) -> TodayView:
    view = TodayView(today=today)

    for r in routines:
        if routine_due(r["days"], today):
            done = logs.get(r["id"], set())
            view.routines.append(RoutineItem(
                routine=r,
                done_today=today in done,
                streak=current_streak(r["days"], done, today, r["created_on"]),
            ))

    grouped: dict[str, list[TaskItem]] = {}
    for t in tasks:
        if t["done_at"] is None and t["due_date"] > today:
            view.upcoming.append(t)
            continue
        if t["done_at"] is None:
            item = TaskItem(t, overdue=(today - t["due_date"]).days)
        elif t["done_at"] == today:
            item = TaskItem(t, overdue=0)
        else:
            continue  # 지난날 완료한 항목은 오늘 목록에 보이지 않음
        grouped.setdefault(t["category"], []).append(item)

    for cat in sorted(grouped, key=category_sort_key):
        items = sorted(grouped[cat], key=lambda i: (i.done, -i.overdue, i.task["id"]))
        view.categories.append((cat, items))

    view.upcoming.sort(key=lambda t: (t["due_date"], t["id"]))
    return view


@dataclass
class RoutineWeek:
    routine: dict
    done: int
    scheduled: int
    streak: int
    best: int


@dataclass
class WeekReport:
    start: dt.date
    end: dt.date
    tasks_done: int
    tasks_open: list[TaskItem]
    routines: list[RoutineWeek]

    @property
    def task_rate(self) -> float | None:
        total = self.tasks_done + len(self.tasks_open)
        return self.tasks_done / total * 100 if total else None


def build_week(tasks: list[dict], routines: list[dict], logs: dict[int, set[dt.date]],
               today: dt.date) -> WeekReport:
    start, end = week_range(today)
    done = sum(1 for t in tasks if t["done_at"] is not None and start <= t["done_at"] <= today)
    open_items = [
        TaskItem(t, overdue=(today - t["due_date"]).days)
        for t in tasks if t["done_at"] is None and t["due_date"] <= today
    ]
    open_items.sort(key=lambda i: (-i.overdue, i.task["id"]))

    rws = []
    for r in routines:
        log = logs.get(r["id"], set())
        first = max(start, r["created_on"])
        scheduled = done_cnt = 0
        d = first
        while d <= min(end, today):
            if routine_due(r["days"], d):
                scheduled += 1
                done_cnt += d in log
            d += DAY
        rws.append(RoutineWeek(
            routine=r, done=done_cnt, scheduled=scheduled,
            streak=current_streak(r["days"], log, today, r["created_on"]),
            best=best_streak(r["days"], log, today, r["created_on"]),
        ))
    return WeekReport(start, end, done, open_items, rws)
