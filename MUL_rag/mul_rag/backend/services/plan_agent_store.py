from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Sequence


DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "plan_agent_structured.db"


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS template_fields (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_key TEXT NOT NULL UNIQUE,
    template_id TEXT NOT NULL,
    section_id TEXT NOT NULL,
    field_id TEXT NOT NULL,
    field_name TEXT NOT NULL DEFAULT '',
    kb_id TEXT NOT NULL DEFAULT '',
    module TEXT NOT NULL DEFAULT '',
    content_type TEXT NOT NULL DEFAULT 'text',
    fill_mode TEXT NOT NULL DEFAULT '',
    aliases_json TEXT NOT NULL DEFAULT '[]',
    target_json TEXT NOT NULL DEFAULT '{}',
    query_text TEXT NOT NULL DEFAULT '',
    required INTEGER NOT NULL DEFAULT 0,
    retrieval_method TEXT NOT NULL DEFAULT 'structured_filter',
    source_sheet TEXT NOT NULL DEFAULT '',
    source_location TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_template_fields_lookup
ON template_fields(template_id, section_id, field_id);

CREATE TABLE IF NOT EXISTS field_values (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_key TEXT NOT NULL UNIQUE,
    kb_id TEXT NOT NULL DEFAULT '',
    template_id TEXT NOT NULL,
    well_name TEXT NOT NULL DEFAULT '',
    module TEXT NOT NULL DEFAULT '',
    section_id TEXT NOT NULL,
    field_id TEXT NOT NULL,
    field_name TEXT NOT NULL DEFAULT '',
    aliases_json TEXT NOT NULL DEFAULT '[]',
    value_json TEXT NOT NULL DEFAULT 'null',
    text_value TEXT NOT NULL DEFAULT '',
    unit TEXT NOT NULL DEFAULT '',
    content_type TEXT NOT NULL DEFAULT 'scalar',
    source_doc TEXT NOT NULL DEFAULT '',
    source_location TEXT NOT NULL DEFAULT '',
    source_type TEXT NOT NULL DEFAULT '',
    retrieval_method TEXT NOT NULL DEFAULT 'structured_filter',
    task_run_id TEXT NOT NULL DEFAULT '',
    task_id TEXT NOT NULL DEFAULT '',
    priority INTEGER NOT NULL DEFAULT 50,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_field_values_lookup
ON field_values(template_id, well_name, section_id, field_id, priority, updated_at);
CREATE INDEX IF NOT EXISTS idx_field_values_module
ON field_values(kb_id, module, well_name);

CREATE TABLE IF NOT EXISTS section_payloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_key TEXT NOT NULL UNIQUE,
    kb_id TEXT NOT NULL DEFAULT '',
    template_id TEXT NOT NULL,
    well_name TEXT NOT NULL DEFAULT '',
    module TEXT NOT NULL DEFAULT '',
    section_id TEXT NOT NULL,
    heading TEXT NOT NULL DEFAULT '',
    content_type TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT 'null',
    text_value TEXT NOT NULL DEFAULT '',
    source_doc TEXT NOT NULL DEFAULT '',
    source_location TEXT NOT NULL DEFAULT '',
    source_type TEXT NOT NULL DEFAULT '',
    retrieval_method TEXT NOT NULL DEFAULT 'structured_filter',
    task_run_id TEXT NOT NULL DEFAULT '',
    task_id TEXT NOT NULL DEFAULT '',
    priority INTEGER NOT NULL DEFAULT 50,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_section_payloads_lookup
ON section_payloads(template_id, well_name, section_id, content_type, priority, updated_at);

CREATE TABLE IF NOT EXISTS task_outputs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_key TEXT NOT NULL UNIQUE,
    task_run_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    output_key TEXT NOT NULL DEFAULT 'content',
    template_id TEXT NOT NULL DEFAULT '',
    well_name TEXT NOT NULL DEFAULT '',
    kb_id TEXT NOT NULL DEFAULT '',
    module TEXT NOT NULL DEFAULT '',
    section_id TEXT NOT NULL DEFAULT '',
    content_type TEXT NOT NULL DEFAULT 'text',
    payload_json TEXT NOT NULL DEFAULT 'null',
    text_value TEXT NOT NULL DEFAULT '',
    source_doc TEXT NOT NULL DEFAULT '',
    source_location TEXT NOT NULL DEFAULT '',
    source_type TEXT NOT NULL DEFAULT 'task_output',
    status TEXT NOT NULL DEFAULT 'completed',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_task_outputs_lookup
ON task_outputs(template_id, well_name, task_id, updated_at);

CREATE TABLE IF NOT EXISTS assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_key TEXT NOT NULL UNIQUE,
    kb_id TEXT NOT NULL DEFAULT '',
    template_id TEXT NOT NULL DEFAULT '',
    well_name TEXT NOT NULL DEFAULT '',
    module TEXT NOT NULL DEFAULT '',
    section_id TEXT NOT NULL DEFAULT '',
    file_id TEXT NOT NULL DEFAULT '',
    asset_type TEXT NOT NULL DEFAULT 'image',
    asset_name TEXT NOT NULL DEFAULT '',
    asset_path TEXT NOT NULL,
    caption TEXT NOT NULL DEFAULT '',
    page_num INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    source_doc TEXT NOT NULL DEFAULT '',
    source_location TEXT NOT NULL DEFAULT '',
    retrieval_method TEXT NOT NULL DEFAULT 'structured_filter',
    priority INTEGER NOT NULL DEFAULT 50,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_assets_lookup
ON assets(kb_id, well_name, section_id, asset_type, priority, updated_at);

CREATE TABLE IF NOT EXISTS retrieval_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL DEFAULT '',
    template_id TEXT NOT NULL DEFAULT '',
    well_name TEXT NOT NULL DEFAULT '',
    section_id TEXT NOT NULL DEFAULT '',
    query_text TEXT NOT NULL DEFAULT '',
    retrieval_method TEXT NOT NULL DEFAULT '',
    result_keys_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
"""


TABLE_COLUMNS: Dict[str, Sequence[str]] = {
    "template_fields": (
        "record_key", "template_id", "section_id", "field_id", "field_name", "kb_id", "module",
        "content_type", "fill_mode", "aliases_json", "target_json", "query_text", "required",
        "retrieval_method", "source_sheet", "source_location", "created_at", "updated_at",
    ),
    "field_values": (
        "record_key", "kb_id", "template_id", "well_name", "module", "section_id", "field_id",
        "field_name", "aliases_json", "value_json", "text_value", "unit", "content_type", "source_doc",
        "source_location", "source_type", "retrieval_method", "task_run_id", "task_id", "priority",
        "created_at", "updated_at",
    ),
    "section_payloads": (
        "record_key", "kb_id", "template_id", "well_name", "module", "section_id", "heading",
        "content_type", "payload_json", "text_value", "source_doc", "source_location", "source_type",
        "retrieval_method", "task_run_id", "task_id", "priority", "created_at", "updated_at",
    ),
    "task_outputs": (
        "record_key", "task_run_id", "task_id", "output_key", "template_id", "well_name", "kb_id",
        "module", "section_id", "content_type", "payload_json", "text_value", "source_doc",
        "source_location", "source_type", "status", "created_at", "updated_at",
    ),
    "assets": (
        "record_key", "kb_id", "template_id", "well_name", "module", "section_id", "file_id",
        "asset_type", "asset_name", "asset_path", "caption", "page_num", "metadata_json", "source_doc",
        "source_location", "retrieval_method", "priority", "created_at", "updated_at",
    ),
}

JSON_COLUMNS = {
    "aliases_json", "target_json", "value_json", "payload_json", "metadata_json",
    "result_keys_json",
}

NULLABLE_COLUMNS = {"page_num"}
INTEGER_DEFAULTS = {"required": 0, "priority": 50}
JSON_DEFAULTS = {
    "aliases_json": [],
    "target_json": {},
    "value_json": None,
    "payload_json": None,
    "metadata_json": {},
}

QUERY_FILTERS = {
    "template_fields": {"template_id", "section_id", "field_id", "kb_id", "module", "content_type"},
    "field_values": {"template_id", "well_name", "section_id", "field_id", "kb_id", "module", "content_type", "task_run_id"},
    "section_payloads": {"template_id", "well_name", "section_id", "kb_id", "module", "content_type", "task_run_id"},
    "task_outputs": {"template_id", "well_name", "task_id", "kb_id", "module", "section_id", "task_run_id"},
    "assets": {"template_id", "well_name", "section_id", "kb_id", "module", "file_id", "asset_type"},
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def configured_db_path() -> Path:
    configured = str(os.getenv("PLAN_AGENT_STORE_DB_PATH") or "").strip()
    return Path(configured).expanduser() if configured else DEFAULT_DB_PATH


def make_record_key(prefix: str, *parts: Any) -> str:
    raw = "\x1f".join(str(part or "") for part in parts)
    return f"{prefix}:{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:32]}"


def _json_dump(value: Any) -> str:
    if isinstance(value, str):
        try:
            json.loads(value)
            return value
        except Exception:
            pass
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _json_load(value: Any) -> Any:
    if value in (None, ""):
        return None
    try:
        return json.loads(str(value))
    except Exception:
        return value


class PlanAgentStore:
    """Persistent structured output store layered beside the existing Mul_RAG indexes.

    This database is additive: it does not alter per-KB metadata.db files or FAISS
    indexes. Hard fields/tables are resolved here; narrative evidence continues to
    use the existing BM25/BGE-M3/vector retrieval path.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else configured_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        with self.connection() as conn:
            # DELETE mode avoids cross-user WAL sidecar ownership conflicts when
            # the same server DB is accessed by the MUL_RAG process and Sage's
            # Docker container. busy_timeout still serializes short writes.
            journal_mode = os.getenv("PLAN_AGENT_STORE_JOURNAL_MODE", "DELETE").upper()
            if journal_mode not in {"DELETE", "WAL"}:
                journal_mode = "DELETE"
            conn.execute(f"PRAGMA journal_mode={journal_mode}")
            conn.executescript(SCHEMA_SQL)

    def upsert_template_fields(self, records: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
        return self._upsert("template_fields", records, key_parts=("template_id", "section_id", "field_id"))

    def upsert_field_values(self, records: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
        return self._upsert(
            "field_values", records,
            key_parts=("template_id", "well_name", "section_id", "field_id", "task_run_id", "source_doc"),
        )

    def upsert_section_payloads(self, records: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
        return self._upsert(
            "section_payloads", records,
            key_parts=("template_id", "well_name", "section_id", "content_type", "task_run_id", "source_doc"),
        )

    def upsert_task_outputs(self, records: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
        return self._upsert("task_outputs", records, key_parts=("task_run_id", "task_id", "output_key"))

    def upsert_assets(self, records: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
        return self._upsert("assets", records, key_parts=("kb_id", "file_id", "section_id", "asset_path"))

    def _upsert(
        self,
        table: str,
        records: Iterable[Mapping[str, Any]],
        key_parts: Sequence[str],
    ) -> Dict[str, Any]:
        if table not in TABLE_COLUMNS:
            raise ValueError(f"Unsupported plan-agent table: {table}")
        now = utc_now()
        prepared: List[Dict[str, Any]] = []
        columns = TABLE_COLUMNS[table]
        for raw in records:
            item = dict(raw)
            item.setdefault("record_key", make_record_key(table, *(item.get(key) for key in key_parts)))
            item.setdefault("created_at", now)
            item["updated_at"] = now
            for key in JSON_COLUMNS:
                if key in item:
                    item[key] = _json_dump(item[key])
            normalized: Dict[str, Any] = {}
            for key in columns:
                value = item.get(key)
                if value is None and key not in NULLABLE_COLUMNS:
                    if key in INTEGER_DEFAULTS:
                        value = INTEGER_DEFAULTS[key]
                    elif key in JSON_DEFAULTS:
                        value = _json_dump(JSON_DEFAULTS[key])
                    else:
                        value = ""
                normalized[key] = value
            prepared.append(normalized)

        if not prepared:
            return {"ok": True, "table": table, "upserted": 0, "dbPath": str(self.db_path)}

        placeholders = ", ".join(f":{column}" for column in columns)
        updates = ", ".join(
            f"{column}=excluded.{column}" for column in columns if column not in {"record_key", "created_at"}
        )
        sql = (
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) "
            f"ON CONFLICT(record_key) DO UPDATE SET {updates}"
        )
        with self.connection() as conn:
            conn.executemany(sql, prepared)
        return {"ok": True, "table": table, "upserted": len(prepared), "dbPath": str(self.db_path)}

    def query(self, table: str, filters: Mapping[str, Any] | None = None, limit: int = 100) -> List[Dict[str, Any]]:
        if table not in TABLE_COLUMNS:
            raise ValueError(f"Unsupported plan-agent table: {table}")
        allowed = QUERY_FILTERS[table]
        filters = {key: value for key, value in dict(filters or {}).items() if key in allowed and value not in (None, "")}
        clauses = [f"{key} = ?" for key in filters]
        sql = f"SELECT * FROM {table}"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        if table in {"field_values", "section_payloads", "assets"}:
            sql += " ORDER BY priority DESC, updated_at DESC, id DESC"
        else:
            sql += " ORDER BY updated_at DESC, id DESC"
        sql += " LIMIT ?"
        params = [*filters.values(), max(1, min(int(limit or 100), 5000))]
        with self.connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._decode_row(row) for row in rows]

    def record_retrieval(self, event: Mapping[str, Any]) -> int:
        item = dict(event)
        item.setdefault("created_at", utc_now())
        for key in ("result_keys_json", "metadata_json"):
            item[key] = _json_dump(item.get(key, [] if key == "result_keys_json" else {}))
        columns = (
            "run_id", "template_id", "well_name", "section_id", "query_text", "retrieval_method",
            "result_keys_json", "metadata_json", "created_at",
        )
        with self.connection() as conn:
            cursor = conn.execute(
                f"INSERT INTO retrieval_events ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
                [item.get(key, "") for key in columns],
            )
            return int(cursor.lastrowid)

    def stats(self) -> Dict[str, Any]:
        with self.connection() as conn:
            counts = {
                table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in (*TABLE_COLUMNS.keys(), "retrieval_events")
            }
            templates = [row[0] for row in conn.execute("SELECT DISTINCT template_id FROM template_fields ORDER BY template_id")]
            wells = [row[0] for row in conn.execute("SELECT DISTINCT well_name FROM section_payloads WHERE well_name <> '' ORDER BY well_name")]
        return {"ok": True, "dbPath": str(self.db_path), "counts": counts, "templates": templates, "wells": wells}

    @staticmethod
    def _decode_row(row: sqlite3.Row) -> Dict[str, Any]:
        item = dict(row)
        for key in JSON_COLUMNS:
            if key in item:
                item[key.removesuffix("_json")] = _json_load(item.pop(key))
        return item


_STORE: PlanAgentStore | None = None


def get_plan_agent_store() -> PlanAgentStore:
    global _STORE
    if _STORE is None:
        _STORE = PlanAgentStore()
    return _STORE
