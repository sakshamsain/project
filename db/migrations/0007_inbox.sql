-- 0007: the in-app inbox. Items are read from events and anomalies; a profile only
-- records when it last looked, for the unread count.
alter table profiles add column if not exists inbox_seen_at timestamptz;
