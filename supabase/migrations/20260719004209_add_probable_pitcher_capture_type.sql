alter table public.probable_pitchers
add column if not exists capture_type text not null default 'legacy_unknown';

update public.probable_pitchers
set capture_type = 'legacy_unknown'
where capture_type = 'pregame'
  and updated_at < timestamptz '2026-07-14T00:00:00Z';

alter table public.probable_pitchers
alter column capture_type set default 'pregame';

alter table public.probable_pitchers
drop constraint if exists probable_pitchers_capture_type_check;

alter table public.probable_pitchers
add constraint probable_pitchers_capture_type_check
check (capture_type in ('legacy_unknown', 'pregame', 'postgame_recovery'));

comment on column public.probable_pitchers.capture_type is
  'How the assignment was captured: legacy_unknown, pregame, or postgame_recovery.';
