# ================================
# sql/bootstrap.sql (run once in Supabase SQL editor)
# ================================
-- Users table (custom auth — NO Supabase Auth)
create table if not exists public.users (
id uuid primary key default gen_random_uuid(),
username text unique not null,
password_hash text not null,
role text not null default 'user' check (role in ('user','admin')),
is_active boolean not null default true,
created_at timestamptz not null default now()
);


-- Services catalog
create table if not exists public.services (
id uuid primary key default gen_random_uuid(),
name text unique not null,
price_cents integer not null check (price_cents >= 0),
is_active boolean not null default true,
created_at timestamptz not null default now()
);


-- Logs of completed services + tips
create table if not exists public.service_logs (
id uuid primary key default gen_random_uuid(),
user_id uuid not null references public.users(id) on delete cascade,
service_id uuid not null references public.services(id),
served_at timestamptz not null,
qty integer not null default 1 check (qty > 0),
tip_cents numeric(10,2) not null default 0 check (tip_cents >= 0),
amount_cents numeric(10,2) not null default 0 check (amount_cents >= 0),
created_at timestamptz not null default now()
);


-- Helpful indexes
create index if not exists idx_service_logs_user_date on public.service_logs(user_id, served_at);
create index if not exists idx_service_logs_service on public.service_logs(service_id);


-- NOTE: If Row Level Security is enabled by default, you can disable it for simple server-side usage:
alter table public.users disable row level security;
alter table public.services disable row level security;
alter table public.service_logs disable row level security;


ALTER TABLE services
ADD COLUMN description TEXT,
ADD COLUMN image_url TEXT;

ALTER TABLE public.users
ADD COLUMN service_percentage numeric DEFAULT 100 CHECK (service_percentage >= 0 AND service_percentage <= 100);

ALTER TABLE public.service_logs
ADD COLUMN payment_type text NOT NULL DEFAULT 'Cash'
CHECK (payment_type IN ('Cash','Credit'));


-- Drop services table
drop table if exists public.services cascade;

-- Adjust service_logs
alter table public.service_logs
drop column if exists service_id;

-- Add amount_cents column (manual entry by user)
alter table public.service_logs
add column if not exists amount_cents numeric(10,2)  not null default 0 check (amount_cents >= 0);

-- Rebuild indexes to reflect new structure
drop index if exists idx_service_logs_service;
create index if not exists idx_service_logs_user_date on public.service_logs(user_id, served_at);
