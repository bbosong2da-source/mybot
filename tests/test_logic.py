import datetime as dt

from bot.logic import best_streak, build_today, build_week, current_streak

TODAY = dt.date(2026, 11, 5)  # 목
DAILY = [0, 1, 2, 3, 4, 5, 6]
MWF = [1, 3, 5]
d = lambda day: dt.date(2026, 11, day)


def test_streak_daily():
    done = {d(2), d(3), d(4)}
    assert current_streak(DAILY, done, TODAY, d(1)) == 3            # 오늘 아직 안 해도 유지
    assert current_streak(DAILY, done | {TODAY}, TODAY, d(1)) == 4
    assert current_streak(DAILY, {d(2), d(4)}, TODAY, d(1)) == 1    # 3일에 끊김


def test_streak_skips_unscheduled_days():
    # 월수금: 11/2(월) 11/4(수) 했고 오늘(목)은 예정일 아님
    assert current_streak(MWF, {d(2), d(4)}, TODAY, d(1)) == 2
    assert current_streak(MWF, {d(4)}, TODAY, d(1)) == 1


def test_best_streak():
    done = {d(1), d(2), d(3), d(5)}
    assert best_streak(DAILY, done, TODAY, d(1)) == 3
    assert best_streak(DAILY, set(), TODAY, d(1)) == 0


def _task(i, due, done=None, cat="일반"):
    return {"id": i, "title": f"t{i}", "category": cat, "due_date": due, "done_at": done}


def test_build_today():
    tasks = [
        _task(1, d(3)),                 # 이틀 지연
        _task(2, TODAY, done=TODAY),    # 오늘 완료
        _task(3, d(4), done=d(4)),      # 어제 완료 -> 안 보임
        _task(4, d(20)),                # 예정
        _task(5, TODAY, cat="논문"),
    ]
    routines = [{"id": 10, "title": "영단어", "days": DAILY, "created_on": d(1)},
                {"id": 11, "title": "운동", "days": MWF, "created_on": d(1)}]
    view = build_today(tasks, routines, {10: {d(4)}}, TODAY)

    assert [r.routine["id"] for r in view.routines] == [10]          # 목요일엔 월수금 루틴 없음
    assert [c for c, _ in view.categories] == ["논문", "일반"]       # '일반'은 맨 뒤
    general = dict(view.categories)["일반"]
    assert [(i.task["id"], i.overdue) for i in general] == [(1, 2), (2, 0)]
    assert [t["id"] for t in view.upcoming] == [4]
    assert not view.all_clear


def test_build_week():
    tasks = [_task(1, d(2), done=d(3)), _task(2, d(4)), _task(3, d(10))]
    routines = [{"id": 10, "title": "영단어", "days": DAILY, "created_on": d(3)}]
    rep = build_week(tasks, routines, {10: {d(3), d(4), d(5)}}, TODAY)
    assert (rep.start, rep.end) == (d(1), d(7))
    assert rep.tasks_done == 1
    assert [i.task["id"] for i in rep.tasks_open] == [2]             # 예정(11/10)은 제외
    rw = rep.routines[0]
    assert (rw.done, rw.scheduled, rw.streak, rw.best) == (3, 3, 3, 3)  # 만든 날(3일)부터 계산
