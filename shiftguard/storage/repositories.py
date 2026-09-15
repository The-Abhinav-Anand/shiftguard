from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import Engine, text

from shiftguard.migrations import upgrade_database
from shiftguard.settings import Settings
from shiftguard.storage.db import create_engine_for_settings


@dataclass(frozen=True)
class StoredExperiment:
    experiment_id: str
    content_hashes: dict[str, str]
    deterministic_payload: dict[str, object]


class ExperimentRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @classmethod
    def from_url(cls, database_url: str) -> ExperimentRepository:
        settings = Settings(SHIFTGUARD_DB_URL=database_url)
        upgrade_database(settings)
        return cls(create_engine_for_settings(settings))

    def put(
        self,
        experiment_id: str,
        deterministic_payload: dict[str, object],
        content_hashes: dict[str, str],
        execution_id: str,
        audit_metadata: dict[str, object],
    ) -> None:
        payload_json = json.dumps(deterministic_payload, sort_keys=True, separators=(",", ":"))
        hashes_json = json.dumps(content_hashes, sort_keys=True, separators=(",", ":"))
        audit_json = json.dumps(audit_metadata, sort_keys=True, separators=(",", ":"))
        with self.engine.begin() as connection:
            existing = connection.execute(text("SELECT payload_json, content_hashes_json FROM experiments WHERE id = :id"), {"id": experiment_id}).one_or_none()
            if existing is None:
                connection.execute(text("INSERT INTO experiments (id, payload_json, content_hashes_json) VALUES (:id, :payload, :hashes)"), {"id": experiment_id, "payload": payload_json, "hashes": hashes_json})
            elif existing[0] != payload_json or existing[1] != hashes_json:
                raise ValueError("existing experiment content is immutable and does not match this execution")
            connection.execute(text("INSERT INTO experiment_executions (execution_id, experiment_id, audit_json) VALUES (:execution_id, :experiment_id, :audit)"), {"execution_id": execution_id, "experiment_id": experiment_id, "audit": audit_json})

    def get(self, experiment_id: str) -> StoredExperiment:
        with self.engine.connect() as connection:
            row = connection.execute(text("SELECT content_hashes_json, payload_json FROM experiments WHERE id = :id"), {"id": experiment_id}).one()
        return StoredExperiment(experiment_id=experiment_id, content_hashes=json.loads(row[0]), deterministic_payload=json.loads(row[1]))

    def execution_ids(self, experiment_id: str) -> tuple[str, ...]:
        with self.engine.connect() as connection:
            rows = connection.execute(text("SELECT execution_id FROM experiment_executions WHERE experiment_id = :id ORDER BY execution_id"), {"id": experiment_id}).all()
        return tuple(row[0] for row in rows)

    def dispose(self) -> None:
        self.engine.dispose()
