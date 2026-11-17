-- Run once in Supabase SQL Editor.
-- Intended for a trusted, server-side Supabase client (service-role key in Streamlit secrets).
-- Do not expose the service-role key to browser clients.
create table if not exists public.executive_section_notes (
  id bigint generated always as identity primary key,
  section_key text not null,
  report_year integer not null check (report_year between 2000 and 2100),
  report_month integer not null check (report_month between 1 and 12),
  author text not null check (char_length(author) between 1 and 80),
  note text not null check (char_length(note) between 1 and 3000),
  created_at timestamptz not null default now()
);
create index if not exists executive_section_notes_lookup_idx
on public.executive_section_notes(section_key,report_year,report_month,created_at desc);
alter table public.executive_section_notes enable row level security;
-- No anon/authenticated policies: service-role server client can access it.
-- If your app uses an anon key instead, configure proper authenticated RLS policies first.
