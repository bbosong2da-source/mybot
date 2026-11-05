-- 성구 퀴즈 기능 추가 (schema.sql을 이미 실행한 프로젝트에서 한 번만 실행)
-- Supabase 대시보드 > SQL Editor 에 전체를 붙여넣고 Run 하세요.

-- 방마다 퀴즈 시간대 '시작-끝' (예: '13-22'), null이면 꺼짐
alter table spaces add column if not exists quiz_hours text default '13-22';

-- 관리자가 올린 성구 (모든 방이 같이 사용)
create table if not exists verses (
  id         bigint generated always as identity primary key,
  ref        text not null unique,       -- '요 3:16'
  core       text not null,              -- 핵심 내용
  body       text,                       -- 전체 본문 (선택)
  created_at timestamptz not null default now()
);

-- 방마다 출제된 문제 (보기는 글자로 저장해서 구절을 고치거나 지워도 문제가 깨지지 않음)
create table if not exists quiz_questions (
  id          bigint generated always as identity primary key,
  space_id    bigint not null references spaces(id) on delete cascade,
  quiz_date   date not null,
  hour        smallint not null,
  verse_id    bigint references verses(id) on delete set null,
  kind        text not null,               -- 'ref2core' 주소→핵심 / 'core2ref' 내용→주소
  ref         text not null,
  prompt      text not null,
  options     text[] not null,
  correct_idx smallint not null,
  answer_idx  smallint,                    -- 고른 보기, 아직 안 풀었으면 null
  correct     boolean,
  created_at  timestamptz not null default now(),
  unique (space_id, quiz_date, hour)
);

-- 방마다 구절별 '틀린 정도' (틀리면 +1, 맞히면 -1). 화면에는 표시하지 않음
create table if not exists verse_misses (
  space_id bigint not null references spaces(id) on delete cascade,
  verse_id bigint not null references verses(id) on delete cascade,
  misses   int not null default 0,
  primary key (space_id, verse_id)
);

alter table verses         enable row level security;
alter table quiz_questions enable row level security;
alter table verse_misses   enable row level security;
