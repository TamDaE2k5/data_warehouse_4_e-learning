CREATE TABLE IF NOT EXISTS staging.pipeline_runs (
 run_id TEXT PRIMARY KEY,
 phase TEXT NOT NULL,
 manifest JSONB NOT NULL,
 publication JSONB,
 started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 finished_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS staging.published_state (
 singleton BOOLEAN PRIMARY KEY DEFAULT true CHECK(singleton),
 manifest JSONB NOT NULL,
 safe_xid BIGINT,
 published_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS staging.source_versions (
 table_name TEXT NOT NULL,
 source_id BIGINT NOT NULL,
 revision BIGINT NOT NULL,
 PRIMARY KEY(table_name, source_id)
);
CREATE TABLE IF NOT EXISTS staging.pending_changes (
 table_name TEXT NOT NULL,
 source_id BIGINT NOT NULL,
 operation TEXT NOT NULL,
 revision BIGINT NOT NULL,
 PRIMARY KEY(table_name, source_id)
);
ALTER TABLE quarantine.quarantine_records ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ;
CREATE TABLE IF NOT EXISTS staging.stage_state (
 singleton BOOLEAN PRIMARY KEY DEFAULT true CHECK(singleton),
 needs_full BOOLEAN NOT NULL DEFAULT false
);
INSERT INTO staging.stage_state(singleton) VALUES(true) ON CONFLICT DO NOTHING;
