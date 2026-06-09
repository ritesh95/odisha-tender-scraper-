create table if not exists scraper_runs (
  id            bigserial primary key,
  run_at        timestamptz not null,
  tenders_found integer     not null default 0,
  new_added     integer     not null default 0,
  updated       integer     not null default 0,
  skipped       integer     not null default 0,
  errors        integer     not null default 0,
  captcha_solved boolean    not null default true,
  runtime_s     integer     not null default 0,
  environment   text        not null default 'local'
);
