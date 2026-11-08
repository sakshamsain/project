-- 0004: a promise for a period still running can already be behind its range.
alter table guidance drop constraint guidance_status_check;
alter table guidance add constraint guidance_status_check check (status in
  ('delivered', 'missed', 'on_track', 'off_track', 'too_early', 'not_measurable', 'dropped'));
alter table guidance add column basis text;               -- inr, constant_currency, usd, other
alter table guidance add column period_label text;        -- FY27, H2 FY27, Q3 FY27, as normalised
