-- 계시록 암송 코스 (기존 프로젝트에 한 번만 실행)
-- Supabase 대시보드 > SQL Editor 에 전체를 붙여넣고 Run 하세요.

-- 관리자가 올린 암송 본문 (순서대로)
create table if not exists recite_verses (
  id      bigint generated always as identity primary key,
  course  text not null default '계시록',
  seq     int not null,                 -- 1, 2, 3 ... 순서
  ref     text not null,                -- '계 1:1'
  chapter int not null,
  verse   int not null,
  body    text not null,
  unique (course, ref)
);

-- 암송에 참여한 방(사람)의 설정과 진도
create table if not exists recite_members (
  space_id   bigint primary key references spaces(id) on delete cascade,
  course     text not null default '계시록',
  daily_new  smallint not null default 2,     -- 하루 새 구절 1~3
  hours      text not null default '18-22',   -- 카드 보내는 시간대
  active     boolean not null default true,   -- false면 쉬는 중
  next_seq   int not null default 1,          -- 다음에 배울 구절 순서
  started_on date
);

-- 방마다 구절별 기억 상태 (간격 복습)
create table if not exists recite_cards (
  space_id   bigint not null references spaces(id) on delete cascade,
  verse_id   bigint not null references recite_verses(id) on delete cascade,
  box        smallint not null default 0,     -- 복습 간격 단계 (1·3·7·15·30·60일)
  due_date   date not null,                   -- 다음 복습일
  learned_on date not null,
  last_grade smallint,
  primary key (space_id, verse_id)
);

-- 방마다 하루 카드 목록과 진행 상황
create table if not exists recite_days (
  space_id    bigint not null references spaces(id) on delete cascade,
  recite_date date not null,
  queue       jsonb not null default '[]',
  sent_hours  smallint[] not null default '{}',
  primary key (space_id, recite_date)
);

alter table recite_verses  enable row level security;
alter table recite_members enable row level security;
alter table recite_cards   enable row level security;
alter table recite_days    enable row level security;
