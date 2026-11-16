CREATE SEQUENCE IF NOT EXISTS oltp.dw_revision_seq;
CREATE TABLE IF NOT EXISTS oltp.change_journal (
 revision BIGINT PRIMARY KEY,
 source_xid BIGINT NOT NULL,
 table_name TEXT NOT NULL,
 source_id BIGINT NOT NULL,
 operation TEXT NOT NULL CHECK(operation IN ('INSERT','UPDATE','DELETE')),
 raw_payload JSONB NOT NULL,
 changed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS change_journal_xid_idx ON oltp.change_journal(source_xid,revision);
CREATE OR REPLACE FUNCTION oltp.touch_row() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 NEW.updated_at := clock_timestamp();
 NEW.dw_revision := CASE WHEN current_setting('dw.bulk_seed',true) = 'on'
   THEN 0 ELSE nextval('oltp.dw_revision_seq') END;
 RETURN NEW;
END $$;
CREATE OR REPLACE FUNCTION oltp.record_change() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE payload JSONB; revision BIGINT;
BEGIN
 IF current_setting('dw.bulk_seed',true) = 'on' THEN RETURN NULL; END IF;
 IF TG_OP = 'DELETE' THEN
   payload := to_jsonb(OLD);
   revision := nextval('oltp.dw_revision_seq');
 ELSE
   payload := to_jsonb(NEW);
   revision := NEW.dw_revision;
 END IF;
 INSERT INTO oltp.change_journal(revision, source_xid, table_name, source_id, operation, raw_payload)
 VALUES (revision, pg_current_xact_id()::text::bigint, TG_TABLE_NAME,
         (payload ->> TG_ARGV[0])::bigint, TG_OP, payload);
 RETURN NULL;
END $$;
