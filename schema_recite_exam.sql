-- 계시록 암송: 장별 시험·북마크 (schema_recite.sql 다음에 한 번만 실행)
-- Supabase 대시보드 > SQL Editor 에 전체를 붙여넣고 Run 하세요.

-- 장별 시험을 통과한 장 번호 (진도판 🏅)
alter table recite_members add column if not exists passed_chapters int[] not null default '{}';

-- 방마다 구절별 북마크와 틀린 기록
create table if not exists recite_marks (
  space_id   bigint not null references spaces(id) on delete cascade,
  verse_id   bigint not null references recite_verses(id) on delete cascade,
  bookmarked boolean not null default false,
  auto       boolean not null default false,   -- 자동으로 붙은 북마크인지
  fails      smallint not null default 0,      -- 쌓인 '못 외움' 수
  streak     smallint not null default 0,      -- 연속 '완벽' 수
  primary key (space_id, verse_id)
);

-- 장별 시험 / 북마크 시험 (중간에 멈추면 이어서)
create table if not exists recite_exams (
  id         bigint generated always as identity primary key,
  space_id   bigint not null references spaces(id) on delete cascade,
  kind       text not null,                   -- 'chapter' 장별 / 'bookmark' 북마크만
  chapter    int,
  items      jsonb not null,                  -- [{"v": 구절 id, "g": 점수 또는 null}]
  finished   boolean not null default false,
  created_at timestamptz not null default now()
);

alter table recite_marks enable row level security;
alter table recite_exams enable row level security;
