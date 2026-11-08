-- 0005: a promise about one segment, or an adjusted figure, is not checked against the
-- whole company's statements.
alter table guidance add column scope text check (scope in ('company', 'segment', 'adjusted'));
alter table guidance add column scope_note text;
