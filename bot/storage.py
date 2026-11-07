"""데이터 저장소.

SupabaseRepo: 운영용. supabase-py가 동기 라이브러리라서 asyncio.to_thread로 감싸
              봇의 이벤트 루프를 막지 않게 한다.
MemoryRepo:   테스트와 로컬 실행용 (재시작하면 데이터가 사라짐).

두 저장소는 같은 메서드를 가지며, 날짜 필드는 항상 datetime.date로 주고받는다.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import itertools

DATE_FIELDS = ("due_date", "done_at", "created_on", "log_date", "quiz_date",
               "learned_on", "started_on", "recite_date")


def _to_py(row: dict) -> dict:
    row = dict(row)
    for f in DATE_FIELDS:
        if isinstance(row.get(f), str):
            row[f] = dt.date.fromisoformat(row[f][:10])
    return row


def _to_db(row: dict) -> dict:
    return {k: (v.isoformat() if isinstance(v, dt.date) else v) for k, v in row.items()}


class SupabaseRepo:
    def __init__(self, url: str, key: str):
        from supabase import create_client
        self.db = create_client(url, key)

    async def _run(self, fn):
        res = await asyncio.to_thread(lambda: fn().execute())
        return [_to_py(r) for r in (res.data or [])]

    def _t(self, name):
        return self.db.table(name)

    # --- spaces -----------------------------------------------------------
    async def get_space(self, chat_id: int, thread_id: int) -> dict | None:
        rows = await self._run(lambda: self._t("spaces").select("*")
                               .eq("chat_id", chat_id).eq("thread_id", thread_id))
        return rows[0] if rows else None

    async def create_space(self, row: dict) -> dict:
        rows = await self._run(lambda: self._t("spaces").upsert(
            _to_db(row), on_conflict="chat_id,thread_id"))
        return rows[0]

    async def space_by_id(self, space_id: int) -> dict | None:
        rows = await self._run(lambda: self._t("spaces").select("*").eq("id", space_id))
        return rows[0] if rows else None

    async def update_space(self, space_id: int, fields: dict) -> None:
        await self._run(lambda: self._t("spaces").update(_to_db(fields)).eq("id", space_id))

    async def all_spaces(self) -> list[dict]:
        return await self._run(lambda: self._t("spaces").select("*").order("id"))

    # --- tasks ------------------------------------------------------------
    async def add_tasks(self, rows: list[dict]) -> list[dict]:
        if not rows:
            return []
        return await self._run(lambda: self._t("tasks").insert([_to_db(r) for r in rows]))

    async def get_task(self, space_id: int, task_id: int) -> dict | None:
        rows = await self._run(lambda: self._t("tasks").select("*")
                               .eq("space_id", space_id).eq("id", task_id))
        return rows[0] if rows else None

    async def update_task(self, space_id: int, task_id: int, fields: dict) -> None:
        await self._run(lambda: self._t("tasks").update(_to_db(fields))
                        .eq("space_id", space_id).eq("id", task_id))

    async def delete_task(self, space_id: int, task_id: int) -> None:
        await self._run(lambda: self._t("tasks").delete()
                        .eq("space_id", space_id).eq("id", task_id))

    async def active_tasks(self, space_id: int, done_since: dt.date) -> list[dict]:
        """미완료 전부 + done_since 이후 완료한 항목."""
        return await self._run(lambda: self._t("tasks").select("*").eq("space_id", space_id)
                               .or_(f"done_at.is.null,done_at.gte.{done_since.isoformat()}")
                               .order("id"))

    # --- routines ---------------------------------------------------------
    async def routines(self, space_id: int) -> list[dict]:
        return await self._run(lambda: self._t("routines").select("*")
                               .eq("space_id", space_id).order("id"))

    async def get_routine(self, space_id: int, routine_id: int) -> dict | None:
        rows = await self._run(lambda: self._t("routines").select("*")
                               .eq("space_id", space_id).eq("id", routine_id))
        return rows[0] if rows else None

    async def add_routines(self, rows: list[dict]) -> list[dict]:
        if not rows:
            return []
        return await self._run(lambda: self._t("routines").insert([_to_db(r) for r in rows]))

    async def update_routine(self, space_id: int, routine_id: int, fields: dict) -> None:
        await self._run(lambda: self._t("routines").update(_to_db(fields))
                        .eq("space_id", space_id).eq("id", routine_id))

    async def delete_routine(self, space_id: int, routine_id: int) -> None:
        await self._run(lambda: self._t("routines").delete()
                        .eq("space_id", space_id).eq("id", routine_id))

    async def routine_logs(self, routine_ids: list[int]) -> dict[int, set[dt.date]]:
        out: dict[int, set[dt.date]] = {i: set() for i in routine_ids}
        if not routine_ids:
            return out
        rows = await self._run(lambda: self._t("routine_logs").select("routine_id,log_date")
                               .in_("routine_id", routine_ids))
        for r in rows:
            out.setdefault(r["routine_id"], set()).add(r["log_date"])
        return out

    async def set_routine_log(self, routine_id: int, day: dt.date, done: bool) -> None:
        if done:
            await self._run(lambda: self._t("routine_logs").upsert(
                {"routine_id": routine_id, "log_date": day.isoformat()},
                on_conflict="routine_id,log_date"))
        else:
            await self._run(lambda: self._t("routine_logs").delete()
                            .eq("routine_id", routine_id).eq("log_date", day.isoformat()))

    # --- broadcasts -------------------------------------------------------
    async def create_broadcast(self, title: str, items: list[str]) -> dict:
        rows = await self._run(lambda: self._t("broadcasts").insert({"title": title, "items": items}))
        return rows[0]

    async def get_broadcast(self, broadcast_id: int | None = None) -> dict | None:
        """broadcast_id가 없으면 가장 최근 공지."""
        if broadcast_id is None:
            rows = await self._run(lambda: self._t("broadcasts").select("*")
                                   .order("id", desc=True).limit(1))
        else:
            rows = await self._run(lambda: self._t("broadcasts").select("*").eq("id", broadcast_id))
        return rows[0] if rows else None

    async def add_broadcast_targets(self, broadcast_id: int, space_ids: list[int]) -> None:
        if space_ids:
            await self._run(lambda: self._t("broadcast_targets").insert(
                [{"broadcast_id": broadcast_id, "space_id": s} for s in space_ids]))

    async def broadcast_targets(self, broadcast_id: int) -> list[int]:
        rows = await self._run(lambda: self._t("broadcast_targets").select("space_id")
                               .eq("broadcast_id", broadcast_id).order("space_id"))
        return [r["space_id"] for r in rows]

    async def broadcast_checks(self, broadcast_id: int) -> set[tuple[int, int]]:
        rows = await self._run(lambda: self._t("broadcast_checks").select("space_id,item_idx")
                               .eq("broadcast_id", broadcast_id))
        return {(r["space_id"], r["item_idx"]) for r in rows}

    async def set_broadcast_check(self, broadcast_id: int, space_id: int, idx: int, done: bool) -> None:
        if done:
            await self._run(lambda: self._t("broadcast_checks").upsert(
                {"broadcast_id": broadcast_id, "space_id": space_id, "item_idx": idx},
                on_conflict="broadcast_id,space_id,item_idx"))
        else:
            await self._run(lambda: self._t("broadcast_checks").delete()
                            .eq("broadcast_id", broadcast_id).eq("space_id", space_id)
                            .eq("item_idx", idx))

    # --- 성구 퀴즈 ---------------------------------------------------------
    async def list_verses(self) -> list[dict]:
        return await self._run(lambda: self._t("verses").select("*").order("id"))

    async def count_verses(self) -> int:
        res = await asyncio.to_thread(
            lambda: self._t("verses").select("id", count="exact").limit(1).execute())
        return res.count or 0

    async def upsert_verses(self, rows: list[dict]) -> None:
        if rows:
            await self._run(lambda: self._t("verses").upsert(rows, on_conflict="ref"))

    async def delete_verse(self, ref: str) -> bool:
        rows = await self._run(lambda: self._t("verses").delete().eq("ref", ref))
        return bool(rows)

    async def create_question(self, row: dict) -> dict | None:
        """같은 공간·날짜·시간 문제가 이미 있으면 None."""
        rows = await self._run(lambda: self._t("quiz_questions").upsert(
            _to_db(row), on_conflict="space_id,quiz_date,hour", ignore_duplicates=True))
        return rows[0] if rows else None

    async def get_question(self, space_id: int, qid: int) -> dict | None:
        rows = await self._run(lambda: self._t("quiz_questions").select("*")
                               .eq("space_id", space_id).eq("id", qid))
        return rows[0] if rows else None

    async def questions_since(self, space_id: int, since: dt.date) -> list[dict]:
        return await self._run(lambda: self._t("quiz_questions")
                               .select("id,quiz_date,hour,verse_id,answer_idx")
                               .eq("space_id", space_id).gte("quiz_date", since.isoformat())
                               .order("id"))

    async def answer_question(self, space_id: int, qid: int, idx: int, correct: bool) -> bool:
        """아직 안 푼 문제일 때만 기록. 기록했으면 True (두 번 눌러도 한 번만 반영)."""
        rows = await self._run(lambda: self._t("quiz_questions")
                               .update({"answer_idx": idx, "correct": correct})
                               .eq("space_id", space_id).eq("id", qid).is_("answer_idx", "null"))
        return bool(rows)

    async def verse_misses(self, space_id: int) -> dict[int, int]:
        rows = await self._run(lambda: self._t("verse_misses").select("verse_id,misses")
                               .eq("space_id", space_id))
        return {r["verse_id"]: r["misses"] for r in rows}

    async def set_verse_miss(self, space_id: int, verse_id: int, misses: int) -> None:
        await self._run(lambda: self._t("verse_misses").upsert(
            {"space_id": space_id, "verse_id": verse_id, "misses": misses},
            on_conflict="space_id,verse_id"))

    # --- 계시록 암송 -------------------------------------------------------
    async def recite_verses(self, course: str) -> list[dict]:
        return await self._run(lambda: self._t("recite_verses").select("*")
                               .eq("course", course).order("seq"))

    async def upsert_recite_verses(self, rows: list[dict]) -> None:
        for i in range(0, len(rows), 200):
            part = rows[i:i + 200]
            await self._run(lambda: self._t("recite_verses").upsert(part, on_conflict="course,ref"))

    async def get_member(self, space_id: int) -> dict | None:
        rows = await self._run(lambda: self._t("recite_members").select("*").eq("space_id", space_id))
        return rows[0] if rows else None

    async def save_member(self, row: dict) -> None:
        await self._run(lambda: self._t("recite_members").upsert(_to_db(row), on_conflict="space_id"))

    async def all_members(self) -> list[dict]:
        return await self._run(lambda: self._t("recite_members").select("*").order("space_id"))

    async def recite_cards(self, space_id: int) -> list[dict]:
        return await self._run(lambda: self._t("recite_cards").select("*").eq("space_id", space_id))

    async def save_card(self, row: dict) -> None:
        await self._run(lambda: self._t("recite_cards").upsert(
            _to_db(row), on_conflict="space_id,verse_id"))

    async def get_recite_day(self, space_id: int, day: dt.date) -> dict | None:
        rows = await self._run(lambda: self._t("recite_days").select("*")
                               .eq("space_id", space_id).eq("recite_date", day.isoformat()))
        return rows[0] if rows else None

    async def save_recite_day(self, row: dict) -> None:
        await self._run(lambda: self._t("recite_days").upsert(
            _to_db(row), on_conflict="space_id,recite_date"))

    async def recite_days_since(self, space_id: int, since: dt.date) -> list[dict]:
        return await self._run(lambda: self._t("recite_days").select("recite_date,queue")
                               .eq("space_id", space_id).gte("recite_date", since.isoformat()))


class MemoryRepo:
    def __init__(self):
        self.spaces: dict[int, dict] = {}
        self.tasks: dict[int, dict] = {}
        self.routines_: dict[int, dict] = {}
        self.logs: set[tuple[int, dt.date]] = set()
        self.broadcasts: dict[int, dict] = {}
        self.targets: set[tuple[int, int]] = set()
        self.checks: set[tuple[int, int, int]] = set()
        self.verses: dict[int, dict] = {}
        self.questions: dict[int, dict] = {}
        self.misses: dict[tuple[int, int], int] = {}
        self.rverses: dict[int, dict] = {}
        self.members: dict[int, dict] = {}
        self.cards: dict[tuple[int, int], dict] = {}
        self.rdays: dict[tuple[int, dt.date], dict] = {}
        self._ids = itertools.count(1)

    def _new(self, row: dict, **defaults) -> dict:
        return {**defaults, **row, "id": next(self._ids)}

    async def get_space(self, chat_id, thread_id):
        return next((dict(s) for s in self.spaces.values()
                     if s["chat_id"] == chat_id and s["thread_id"] == thread_id), None)

    async def create_space(self, row):
        existing = await self.get_space(row["chat_id"], row["thread_id"])
        if existing:
            return existing
        s = self._new(row, name=None, user_name=None, notify_time=None, disabled=False,
                      quiz_hours="13-22")
        self.spaces[s["id"]] = s
        return dict(s)

    async def space_by_id(self, space_id):
        s = self.spaces.get(space_id)
        return dict(s) if s else None

    async def update_space(self, space_id, fields):
        if space_id in self.spaces:
            self.spaces[space_id].update(fields)

    async def all_spaces(self):
        return [dict(s) for s in sorted(self.spaces.values(), key=lambda s: s["id"])]

    async def add_tasks(self, rows):
        out = []
        for r in rows:
            t = self._new(r, done_at=None, raw_text=None)
            self.tasks[t["id"]] = t
            out.append(dict(t))
        return out

    async def get_task(self, space_id, task_id):
        t = self.tasks.get(task_id)
        return dict(t) if t and t["space_id"] == space_id else None

    async def update_task(self, space_id, task_id, fields):
        t = self.tasks.get(task_id)
        if t and t["space_id"] == space_id:
            t.update(fields)

    async def delete_task(self, space_id, task_id):
        t = self.tasks.get(task_id)
        if t and t["space_id"] == space_id:
            del self.tasks[task_id]

    async def active_tasks(self, space_id, done_since):
        return [dict(t) for t in sorted(self.tasks.values(), key=lambda t: t["id"])
                if t["space_id"] == space_id
                and (t["done_at"] is None or t["done_at"] >= done_since)]

    async def routines(self, space_id):
        return [dict(r) for r in sorted(self.routines_.values(), key=lambda r: r["id"])
                if r["space_id"] == space_id]

    async def get_routine(self, space_id, routine_id):
        r = self.routines_.get(routine_id)
        return dict(r) if r and r["space_id"] == space_id else None

    async def add_routines(self, rows):
        out = []
        for row in rows:
            r = self._new(row)
            self.routines_[r["id"]] = r
            out.append(dict(r))
        return out

    async def update_routine(self, space_id, routine_id, fields):
        r = self.routines_.get(routine_id)
        if r and r["space_id"] == space_id:
            r.update(fields)

    async def delete_routine(self, space_id, routine_id):
        r = self.routines_.get(routine_id)
        if r and r["space_id"] == space_id:
            del self.routines_[routine_id]
            self.logs = {(rid, d) for rid, d in self.logs if rid != routine_id}

    async def routine_logs(self, routine_ids):
        out = {i: set() for i in routine_ids}
        for rid, d in self.logs:
            if rid in out:
                out[rid].add(d)
        return out

    async def set_routine_log(self, routine_id, day, done):
        (self.logs.add if done else self.logs.discard)((routine_id, day))

    async def create_broadcast(self, title, items):
        b = self._new({"title": title, "items": list(items)})
        self.broadcasts[b["id"]] = b
        return dict(b)

    async def get_broadcast(self, broadcast_id=None):
        if broadcast_id is None:
            if not self.broadcasts:
                return None
            broadcast_id = max(self.broadcasts)
        b = self.broadcasts.get(broadcast_id)
        return dict(b) if b else None

    async def add_broadcast_targets(self, broadcast_id, space_ids):
        self.targets |= {(broadcast_id, s) for s in space_ids}

    async def broadcast_targets(self, broadcast_id):
        return sorted(s for b, s in self.targets if b == broadcast_id)

    async def broadcast_checks(self, broadcast_id):
        return {(s, i) for b, s, i in self.checks if b == broadcast_id}

    async def set_broadcast_check(self, broadcast_id, space_id, idx, done):
        (self.checks.add if done else self.checks.discard)((broadcast_id, space_id, idx))

    # --- 성구 퀴즈 ---------------------------------------------------------
    async def list_verses(self):
        return [dict(v) for v in sorted(self.verses.values(), key=lambda v: v["id"])]

    async def count_verses(self):
        return len(self.verses)

    async def upsert_verses(self, rows):
        by_ref = {v["ref"]: v for v in self.verses.values()}
        for row in rows:
            if row["ref"] in by_ref:
                by_ref[row["ref"]].update(row)
            else:
                v = self._new(row)
                self.verses[v["id"]] = v

    async def delete_verse(self, ref):
        for vid, v in list(self.verses.items()):
            if v["ref"] == ref:
                del self.verses[vid]
                for q in self.questions.values():   # on delete set null
                    if q["verse_id"] == vid:
                        q["verse_id"] = None
                return True
        return False

    async def create_question(self, row):
        for q in self.questions.values():
            if (q["space_id"], q["quiz_date"], q["hour"]) == (row["space_id"], row["quiz_date"], row["hour"]):
                return None
        q = self._new(row, answer_idx=None, correct=None)
        self.questions[q["id"]] = q
        return dict(q)

    async def get_question(self, space_id, qid):
        q = self.questions.get(qid)
        return dict(q) if q and q["space_id"] == space_id else None

    async def questions_since(self, space_id, since):
        return [dict(q) for q in sorted(self.questions.values(), key=lambda q: q["id"])
                if q["space_id"] == space_id and q["quiz_date"] >= since]

    async def answer_question(self, space_id, qid, idx, correct):
        q = self.questions.get(qid)
        if not q or q["space_id"] != space_id or q["answer_idx"] is not None:
            return False
        q.update(answer_idx=idx, correct=correct)
        return True

    async def verse_misses(self, space_id):
        return {vid: m for (sid, vid), m in self.misses.items() if sid == space_id}

    async def set_verse_miss(self, space_id, verse_id, misses):
        self.misses[(space_id, verse_id)] = misses

    # --- 계시록 암송 -------------------------------------------------------
    async def recite_verses(self, course):
        return [dict(v) for v in sorted(self.rverses.values(), key=lambda v: v["seq"])
                if v["course"] == course]

    async def upsert_recite_verses(self, rows):
        by_key = {(v["course"], v["ref"]): v for v in self.rverses.values()}
        for row in rows:
            key = (row["course"], row["ref"])
            if key in by_key:
                by_key[key].update(row)
            else:
                v = self._new(row)
                self.rverses[v["id"]] = v

    async def get_member(self, space_id):
        m = self.members.get(space_id)
        return dict(m) if m else None

    async def save_member(self, row):
        self.members.setdefault(row["space_id"], {}).update(row)

    async def all_members(self):
        return [dict(m) for _, m in sorted(self.members.items())]

    async def recite_cards(self, space_id):
        return [dict(c) for (sid, _), c in self.cards.items() if sid == space_id]

    async def save_card(self, row):
        self.cards.setdefault((row["space_id"], row["verse_id"]), {}).update(row)

    async def get_recite_day(self, space_id, day):
        d = self.rdays.get((space_id, day))
        return {**d, "queue": [dict(q) for q in d["queue"]]} if d else None

    async def save_recite_day(self, row):
        self.rdays[(row["space_id"], row["recite_date"])] = {
            **row, "queue": [dict(q) for q in row["queue"]]}

    async def recite_days_since(self, space_id, since):
        return [dict(d) for (sid, day), d in self.rdays.items() if sid == space_id and day >= since]
