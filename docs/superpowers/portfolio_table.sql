-- Supabase portfolio 테이블 생성 SQL
-- Supabase Dashboard > SQL Editor에서 실행

create table if not exists portfolio (
  id uuid primary key default gen_random_uuid(),
  ticker text not null,
  name text not null,
  category text not null check (category in ('possession', 'interest')),
  buy_price numeric,
  buy_quantity integer,
  buy_date date,
  market text not null check (market in ('domestic', 'overseas')),
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- 중복 방지 (같은 종목코드 + 카테고리)
create unique index if not exists idx_portfolio_ticker_category
  on portfolio (ticker, category);

-- updated_at 자동 갱신 트리거
create or replace function update_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create or replace trigger portfolio_updated_at
  before update on portfolio
  for each row execute function update_updated_at();
