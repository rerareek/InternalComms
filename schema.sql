-- Jalankan di Supabase: SQL Editor > New query > Run
create table if not exists public.meetings (
    id           bigint generated always as identity primary key,
    meeting_date date not null,
    location     text not null check (location in ('In JICT', 'Out JICT')),
    with_whom    text not null,
    pics         text not null,
    agenda       text not null,
    discussion   text,
    created_at   timestamptz not null default now()
);

create index if not exists meetings_date_idx on public.meetings (meeting_date desc);

-- RLS aktif tanpa policy = anon key tidak bisa baca/tulis.
-- App akses lewat service_role key (hanya di Streamlit Secrets).
alter table public.meetings enable row level security;
