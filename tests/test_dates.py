import datetime as dt

import pytest

from bot.dates import days_label, parse_dated_line, split_routine_line, week_range

BASE = dt.date(2026, 11, 5)  # 목요일
D = lambda m, d, y=2026: dt.date(y, m, d)


@pytest.mark.parametrize("line, due, text", [
    ("내일 보고서 작성", D(11, 6), "보고서 작성"),
    ("모레 장보기", D(11, 7), "장보기"),
    ("오늘 운동", D(11, 5), "운동"),
    ("3일 후 서류 제출", D(11, 8), "서류 제출"),
    ("3일뒤 서류 제출", D(11, 8), "서류 제출"),
    ("금 발표 연습", D(11, 6), "발표 연습"),
    ("금요일 발표 연습", D(11, 6), "발표 연습"),
    ("토 대청소", D(11, 7), "대청소"),
    ("일요일 예배 준비", D(11, 8), "예배 준비"),
    ("목 회의", D(11, 12), "회의"),               # 오늘과 같은 요일 -> 다음 주
    ("다음주 일요일 장보기", D(11, 8), "장보기"),
    ("다음주 월 회의", D(11, 9), "회의"),
    ("다음주 수 회의 준비", D(11, 11), "회의 준비"),
    ("다음 주 토 모임", D(11, 14), "모임"),
    ("이번주 토 모임", D(11, 7), "모임"),
    ("11/20 발표 준비", D(11, 20), "발표 준비"),
    ("11.20 발표 준비", D(11, 20), "발표 준비"),
    ("11월 20일 발표 준비", D(11, 20), "발표 준비"),
    ("1/10 신년 계획", D(1, 10, 2027), "신년 계획"),   # 지난 지 오래된 날짜 -> 내년
])
def test_dated(line, due, text):
    p = parse_dated_line(line, BASE)
    assert p.error is None
    assert (p.due, p.text) == (due, text)


@pytest.mark.parametrize("line", [
    "보고서 11/20까지",     # 줄 맨 앞이 아니면 날짜 아님
    "일 정리하기",          # '일' 한 글자는 요일로 보지 않음
    "수학 공부",            # 요일 글자 뒤에 공백이 없음
    "월말 정산",
    "1.5배속 강의 듣기",
    "3단원 풀기",
    "내일보고서",           # 공백 없음
])
def test_not_dated(line):
    p = parse_dated_line(line, BASE)
    assert p.error is None and p.due is None and p.text == line


def test_escape_bang():
    p = parse_dated_line("!10/20 비율 계산", BASE)
    assert (p.due, p.text, p.error) == (None, "10/20 비율 계산", None)


@pytest.mark.parametrize("line, err", [
    ("11/01 회의", "이미 지난 날짜"),
    ("2/30 회의", "없는 날짜"),
    ("이번주 월 회의", "이미 지난 요일"),
    ("내일", "할 일을 적어"),
    ("400일 후 여행", "1년 이내"),
])
def test_errors(line, err):
    assert err in parse_dated_line(line, BASE).error


def test_week_is_sunday_to_saturday():
    assert week_range(BASE) == (D(11, 1), D(11, 7))
    assert week_range(D(11, 1)) == (D(11, 1), D(11, 7))   # 일요일
    assert week_range(D(11, 7)) == (D(11, 1), D(11, 7))   # 토요일
    assert week_range(D(11, 8)) == (D(11, 8), D(11, 14))


@pytest.mark.parametrize("line, days, title", [
    ("영단어 30개", [0, 1, 2, 3, 4, 5, 6], "영단어 30개"),
    ("월수금 운동", [1, 3, 5], "운동"),
    ("평일 독서", [1, 2, 3, 4, 5], "독서"),
    ("주말 대청소", [0, 6], "대청소"),
    ("화요일 PT", [2], "PT"),
    ("토 장보기", [6], "장보기"),
    ("일요일 예배", [0], "예배"),
    ("일 정리", [0, 1, 2, 3, 4, 5, 6], "일 정리"),       # '일' 한 글자 -> 요일 아님
    ("일일 회고", [0, 1, 2, 3, 4, 5, 6], "일일 회고"),   # 중복 글자 -> 요일 아님
    ("일기 쓰기", [0, 1, 2, 3, 4, 5, 6], "일기 쓰기"),
])
def test_routine_days(line, days, title):
    assert split_routine_line(line) == (days, title)


def test_days_label():
    assert days_label([0, 1, 2, 3, 4, 5, 6]) == "매일"
    assert days_label([5, 1, 3]) == "월수금"
    assert days_label([6, 0]) == "주말"
