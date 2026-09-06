-- Schema v13: multi-instance and shared connectors.

ALTER TABLE connectors DROP CONSTRAINT connectors_user_id_kind_key;
ALTER TABLE connectors ADD COLUMN shared INTEGER NOT NULL DEFAULT 0;

WITH ranked AS (
  SELECT id, display_name, instance_id,
         ROW_NUMBER() OVER (
           PARTITION BY user_id, display_name ORDER BY id
         ) AS duplicate_number
  FROM connectors
  WHERE kind <> 'custom-mcp'
)
UPDATE connectors AS c
SET display_name = ranked.display_name || ' (' || right(ranked.instance_id, 6) || ')'
FROM ranked
WHERE c.id = ranked.id AND ranked.duplicate_number > 1;

CREATE INDEX idx_connectors_shared ON connectors(shared) WHERE shared = 1;
CREATE UNIQUE INDEX idx_connectors_user_display_name
  ON connectors(user_id, display_name) WHERE kind <> 'custom-mcp';

UPDATE _schema_version SET version = 13;
