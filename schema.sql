-- 구름 언덕과 까마귀 정원 봇 - Supabase 테이블
-- Supabase 대시보드 > SQL Editor 에 전체를 붙여넣고 Run 하세요.
-- (기존 bot_data 테이블은 건드리지 않습니다.)

-- 공간: 개인방 하나 또는 그룹 토픽 하나
create table if not exists spaces (
  id          bigint generated always as identity primary key,
  chat_id     bigint not null,
  thread_id   bigint not null default 0,          -- 토픽이 아니면 0
  name        text,                               -- 토픽 이름 / 그룹 이름 / 개인 이름
  user_name   text,                               -- 마지막으로 쓴 사람 이름
  notify_time text default '22:00',               -- 밤 점검 시각 'HH:MM', null이면 꺼짐
  disabled    boolean not null default false,     -- /off
  created_at  timestamptz not null default now(),
  unique (chat_id, thread_id)
);

-- 할 일 (한 번 하고 끝나는 항목)
create table if not exists tasks (
  id         bigint generated always as identity primary key,
  space_id   bigint not null references spaces(id) on delete cascade,
  title      text not null,
  category   text not null default '일반',
  due_date   date not null,                       -- 목록에 나타나는 날 (지나면 🔥D+N)
  done_at    date,                                -- 완료한 날, 미완료면 null
  raw_text   text,                                -- 날짜로 해석되기 전 원래 입력 ([오늘 할 일로] 복구용)
  created_at timestamptz not null default now()
);
create index if not exists tasks_space_open on tasks (space_id, done_at);

-- 루틴 (반복 규칙). days: 0=일 1=월 ... 6=토
create table if not exists routines (
  id         bigint generated always as identity primary key,
  space_id   bigint not null references spaces(id) on delete cascade,
  title      text not null,
  days       smallint[] not null default '{0,1,2,3,4,5,6}',
  created_on date not null,
  created_at timestamptz not null default now()
);
create index if not exists routines_space on routines (space_id);

-- 루틴 수행 기록: 행이 있으면 그날 완료
create table if not exists routine_logs (
  routine_id bigint not null references routines(id) on delete cascade,
  log_date   date not null,
  primary key (routine_id, log_date)
);

-- 관리자 공지
create table if not exists broadcasts (
  id         bigint generated always as identity primary key,
  title      text not null,
  items      text[] not null,
  created_at timestamptz not null default now()
);

create table if not exists broadcast_targets (
  broadcast_id bigint not null references broadcasts(id) on delete cascade,
  space_id     bigint not null references spaces(id) on delete cascade,
  primary key (broadcast_id, space_id)
);

create table if not exists broadcast_checks (
  broadcast_id bigint not null references broadcasts(id) on delete cascade,
  space_id     bigint not null references spaces(id) on delete cascade,
  item_idx     int not null,
  primary key (broadcast_id, space_id, item_idx)
);

-- 보안: RLS를 켜고 정책은 만들지 않습니다.
-- 봇은 service_role 키로 접속하므로 RLS의 영향을 받지 않고,
-- 공개용 anon 키로는 이 테이블들을 읽거나 쓸 수 없게 됩니다.
alter table spaces            enable row level security;
alter table tasks             enable row level security;
alter table routines          enable row level security;
alter table routine_logs      enable row level security;
alter table broadcasts        enable row level security;
alter table broadcast_targets enable row level security;
alter table broadcast_checks  enable row level security;

-- 성구 퀴즈 기능은 schema_quiz.sql 을 이어서 실행하세요.
