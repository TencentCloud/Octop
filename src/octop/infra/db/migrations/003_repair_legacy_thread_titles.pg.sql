-- Schema v3: one-shot rewrite of thread titles hard-cut at 40 chars without
-- ellipsis. Actual UPDATE runs in Python (UTF-8 character length) from migrate.py.
UPDATE _schema_version SET version = 3;
