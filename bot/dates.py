"""날짜 계산과 '날짜 + 할 일' 입력 해석.

요일 번호는 0=일, 1=월, ... 6=토 (한 주는 일요일~토요일).
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

from .config import TZ

WEEKDAYS = "일월화수목금토"


def today() -> dt.date:
    return dt.datetime.now(TZ).date()


def now() -> dt.datetime:
    return dt.datetime.now(TZ)


def sun_index(d: dt.date) -> int:
    """일요일=0 ... 토요일=6."""
    return (d.weekday() + 1) % 7


def week_range(d: dt.date) -> tuple[dt.date, dt.date]:
    start = d - dt.timedelta(days=sun_index(d))
    return start, start + dt.timedelta(days=6)


def fmt_short(d: dt.date) -> str:
    return f"{d.month}/{d.day}({WEEKDAYS[sun_index(d)]})"


def fmt_long(d: dt.date) -> str:
    return f"{d.month}월 {d.day}일 ({WEEKDAYS[sun_index(d)]})"


@dataclass
class DateParse:
    due: dt.date | None   # None이면 날짜 지정 없음(오늘 할 일)
    text: str             # 날짜 부분을 뺀 할 일 내용
    error: str | None = None


# 요일: 월~토는 한 글자 허용, 일요일은 '일요일'로만 인식 ('일 정리하기' 오인 방지)
_WD = r"(?:(?P<wd>[월화수목금토])(?:요일)?|(?P<sun>일요일))"
_REST = r"(?:\s+(?P<rest>.*))?$"

_PATTERNS = [
    ("rel", re.compile(r"^(?P<rel>오늘|내일|모레)" + _REST)),
    ("after", re.compile(r"^(?P<n>\d{1,3})\s*일\s*(?:후|뒤)" + _REST)),
    ("week", re.compile(r"^(?P<wk>이번\s*주|다음\s*주)\s*" + _WD + _REST)),
    ("wd", re.compile(r"^" + _WD + _REST)),
    ("md", re.compile(r"^(?P<m>\d{1,2})[/.](?P<d>\d{1,2})" + _REST)),
    ("md", re.compile(r"^(?P<m>\d{1,2})\s*월\s*(?P<d>\d{1,2})\s*일" + _REST)),
]


def _weekday_of(m: re.Match) -> int:
    return 0 if m.group("sun") else WEEKDAYS.index(m.group("wd"))


def parse_dated_line(line: str, base: dt.date) -> DateParse:
    """줄 맨 앞의 날짜 표현을 해석한다. 맨 앞에 '!'를 붙이면 날짜로 해석하지 않는다."""
    line = line.strip()
    if line.startswith("!"):
        return DateParse(None, line[1:].strip())

    for kind, pat in _PATTERNS:
        m = pat.match(line)
        if not m:
            continue
        rest = (m.group("rest") or "").strip()
        if not rest:
            return DateParse(None, line, "날짜 뒤에 할 일을 적어 주세요.")

        if kind == "rel":
            due = base + dt.timedelta(days={"오늘": 0, "내일": 1, "모레": 2}[m.group("rel")])
        elif kind == "after":
            n = int(m.group("n"))
            if n > 365:
                return DateParse(None, line, "1년 이내의 날짜만 지정할 수 있어요.")
            due = base + dt.timedelta(days=n)
        elif kind == "week":
            target = _weekday_of(m)
            start, _ = week_range(base)
            if m.group("wk").startswith("다음"):
                start += dt.timedelta(days=7)
            due = start + dt.timedelta(days=target)
            if due < base:
                return DateParse(None, line, "이미 지난 요일이에요.")
        elif kind == "wd":
            delta = (_weekday_of(m) - sun_index(base)) % 7
            due = base + dt.timedelta(days=delta or 7)  # 오늘과 같은 요일이면 다음 주
        else:  # md
            month, day = int(m.group("m")), int(m.group("d"))
            try:
                due = dt.date(base.year, month, day)
            except ValueError:
                return DateParse(None, line, "없는 날짜예요.")
            if due < base:
                if (base - due).days <= 30:
                    return DateParse(None, line, "이미 지난 날짜예요.")
                try:
                    due = dt.date(base.year + 1, month, day)
                except ValueError:
                    return DateParse(None, line, "없는 날짜예요.")
        return DateParse(due, rest)

    return DateParse(None, line)


# ---------------------------------------------------------------------------
# 루틴 요일 해석:  매일 / 평일 / 주말 / 월수금 / 화요일 / 토
# ---------------------------------------------------------------------------
ALL_DAYS = [0, 1, 2, 3, 4, 5, 6]
WEEKDAYS_ONLY = [1, 2, 3, 4, 5]
WEEKEND = [0, 6]


def parse_routine_days(token: str) -> list[int] | None:
    if token == "매일":
        return list(ALL_DAYS)
    if token == "평일":
        return list(WEEKDAYS_ONLY)
    if token == "주말":
        return list(WEEKEND)
    m = re.fullmatch(r"([일월화수목금토])요일", token)
    if m:
        return [WEEKDAYS.index(m.group(1))]
    if re.fullmatch(r"[월화수목금토]", token):  # '일' 한 글자는 인식하지 않음
        return [WEEKDAYS.index(token)]
    if re.fullmatch(r"[일월화수목금토]{2,7}", token) and len(set(token)) == len(token):
        return sorted(WEEKDAYS.index(c) for c in token)
    return None


def split_routine_line(line: str) -> tuple[list[int], str]:
    """'월수금 운동' -> ([1,3,5], '운동'),  '영단어 30개' -> (매일, '영단어 30개')"""
    line = line.strip()
    parts = line.split(maxsplit=1)
    if len(parts) == 2:
        days = parse_routine_days(parts[0])
        if days is not None:
            return days, parts[1].strip()
    return list(ALL_DAYS), line


def days_label(days: list[int]) -> str:
    s = sorted(set(days))
    if s == ALL_DAYS:
        return "매일"
    if s == WEEKDAYS_ONLY:
        return "평일"
    if s == WEEKEND:
        return "주말"
    return "".join(WEEKDAYS[i] for i in s)
