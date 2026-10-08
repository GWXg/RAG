from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional
import importlib.util
import re
import time
import uuid

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine, URL


SUPPORTED_DB_TYPES = ["sqlite", "mysql", "postgresql"]
_CONNECTIONS: Dict[str, "StructuredDbConnection"] = {}
_FORBIDDEN_SQL_RE = re.compile(
    r"\b("
    r"insert|update|delete|drop|alter|truncate|create|merge|"
    r"call|execute|exec|grant|revoke|vacuum|attach|detach|pragma|copy|load|"
    r"lock|unlock"
    r")\b|replace\s+into|into\s+(outfile|dumpfile)",
    re.IGNORECASE,
)


@dataclass
class StructuredDbConnection:
    connection_id: str
    name: str
    db_type: str
    engine: Engine
    created_at: int
    safe_config: Dict[str, Any]


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bytes):
        return f"<bytes {len(value)}>"
    return str(value)


def _strip_sql_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", str(sql or ""), flags=re.DOTALL)
    sql = re.sub(r"--[^\n\r]*", " ", sql)
    return sql.strip()


def normalize_readonly_sql(sql: str) -> str:
    """Return a single read-only SQL statement or raise ValueError."""
    cleaned = _strip_sql_comments(sql)
    if not cleaned:
        raise ValueError("SQL 不能为空")

    trailing_stripped = cleaned.rstrip().rstrip(";").strip()
    if not trailing_stripped:
        raise ValueError("SQL 不能为空")
    if ";" in trailing_stripped:
        raise ValueError("只允许执行单条 SQL 语句")

    first = re.match(r"^\s*([a-zA-Z]+)", trailing_stripped)
    first_token = (first.group(1) if first else "").lower()
    if first_token not in {"select", "with"}:
        raise ValueError("只允许执行 SELECT 查询")
    if first_token == "with" and not re.search(r"\bselect\b", trailing_stripped, re.IGNORECASE):
        raise ValueError("WITH 查询必须包含 SELECT")
    if _FORBIDDEN_SQL_RE.search(trailing_stripped):
        raise ValueError("SQL 中包含非只读操作，已拒绝执行")

    return trailing_stripped


def _require(value: Any, label: str) -> str:
    text_value = str(value or "").strip()
    if not text_value:
        raise ValueError(f"{label}不能为空")
    return text_value


def _postgresql_driver() -> str:
    if importlib.util.find_spec("psycopg2"):
        return "postgresql+psycopg2"
    if importlib.util.find_spec("psycopg"):
        return "postgresql+psycopg"
    raise RuntimeError("当前环境未安装 PostgreSQL 驱动，请安装 psycopg2 或 psycopg 后再连接")


def _build_url(config: Dict[str, Any]) -> tuple[str, URL, Dict[str, Any]]:
    db_type = str(config.get("type") or config.get("dbType") or "").strip().lower()
    if db_type not in SUPPORTED_DB_TYPES:
        raise ValueError(f"暂不支持的数据库类型：{db_type or 'unknown'}")

    if db_type == "sqlite":
        sqlite_path = _require(config.get("sqlitePath") or config.get("database"), "SQLite 文件路径")
        if sqlite_path != ":memory:" and not Path(sqlite_path).expanduser().exists():
            raise FileNotFoundError(f"SQLite 文件不存在：{sqlite_path}")
        database = sqlite_path if sqlite_path == ":memory:" else str(Path(sqlite_path).expanduser())
        url = URL.create("sqlite", database=database)
        return db_type, url, {"connect_args": {"check_same_thread": False}}

    host = _require(config.get("host"), "主机地址")
    database = _require(config.get("database"), "数据库名")
    username = _require(config.get("username"), "用户名")
    password = str(config.get("password") or "")
    port = config.get("port")
    try:
        port_value = int(port) if port not in (None, "") else (3306 if db_type == "mysql" else 5432)
    except Exception:
        port_value = 3306 if db_type == "mysql" else 5432

    driver = "mysql+pymysql" if db_type == "mysql" else _postgresql_driver()
    url = URL.create(
        driver,
        username=username,
        password=password,
        host=host,
        port=port_value,
        database=database,
    )
    if db_type == "mysql":
        return db_type, url, {"connect_args": {"connect_timeout": 5, "read_timeout": 30, "write_timeout": 30}}
    return db_type, url, {}


def _connection_error_hint(exc: Exception, db_type: str, config: Dict[str, Any]) -> str:
    message = str(exc)
    host = str(config.get("host") or "").strip() or "<unknown>"
    port = config.get("port") or (3306 if db_type == "mysql" else 5432)
    if db_type == "mysql":
        if "1049" in message or "Unknown database" in message:
            database = str(config.get("database") or "").strip()
            return f"MySQL 已连接，但数据库不存在：{database or '<未填写>'}。请填写已有数据库名，或先在本地 MySQL 中创建该数据库。原始错误：{message}"
        return (
            f"MySQL 连接失败：{host}:{port} 不可达或连接被拒绝。"
            " 请检查数据库是否在目标主机上运行、端口是否开放、MySQL 是否允许远程连接、"
            "防火墙/安全组/白名单是否放行，以及填写的主机名、端口、用户名和密码是否正确。"
            f" 原始错误：{message}"
        )
    return f"数据库连接失败：{message}"


def _safe_config(config: Dict[str, Any], db_type: str) -> Dict[str, Any]:
    safe = {
        "type": db_type,
        "host": config.get("host") or "",
        "port": config.get("port") or "",
        "database": config.get("database") or config.get("sqlitePath") or "",
        "username": config.get("username") or "",
    }
    if db_type == "sqlite":
        safe["host"] = "local file"
        safe["username"] = ""
    return safe


def connect_structured_db(config: Dict[str, Any]) -> Dict[str, Any]:
    db_type, url, engine_kwargs = _build_url(config)
    name = str(config.get("name") or "").strip() or str(config.get("database") or config.get("sqlitePath") or db_type)
    engine = create_engine(url, pool_pre_ping=True, future=True, **engine_kwargs)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        engine.dispose()
        raise ConnectionError(_connection_error_hint(exc, db_type, config)) from exc

    connection_id = uuid.uuid4().hex[:12]
    record = StructuredDbConnection(
        connection_id=connection_id,
        name=name,
        db_type=db_type,
        engine=engine,
        created_at=int(time.time()),
        safe_config=_safe_config(config, db_type),
    )
    _CONNECTIONS[connection_id] = record
    return connection_info(record)


def connection_info(record: StructuredDbConnection) -> Dict[str, Any]:
    return {
        "connectionId": record.connection_id,
        "name": record.name,
        "type": record.db_type,
        "createdAt": record.created_at,
        "config": record.safe_config,
    }


def list_structured_db_connections() -> List[Dict[str, Any]]:
    return [connection_info(record) for record in _CONNECTIONS.values()]


def get_structured_db_connection(connection_id: str) -> StructuredDbConnection:
    record = _CONNECTIONS.get(str(connection_id or "").strip())
    if not record:
        raise KeyError("连接不存在或后端已重启，请重新连接数据库")
    return record


def disconnect_structured_db(connection_id: str) -> Dict[str, Any]:
    record = _CONNECTIONS.pop(str(connection_id or "").strip(), None)
    if not record:
        return {"ok": True, "removed": False}
    record.engine.dispose()
    return {"ok": True, "removed": True}


def get_structured_db_schema(connection_id: str) -> Dict[str, Any]:
    record = get_structured_db_connection(connection_id)
    inspector = inspect(record.engine)
    schema_names: List[Optional[str]]
    try:
        schema_names = inspector.get_schema_names()
    except Exception:
        schema_names = [None]

    if record.db_type in {"mysql", "sqlite"}:
        current_database = record.safe_config.get("database") or None
        schema_names = [current_database if record.db_type == "mysql" else None]

    schemas = []
    for schema_name in schema_names:
        try:
            table_names = inspector.get_table_names(schema=schema_name)
            view_names = inspector.get_view_names(schema=schema_name)
        except Exception:
            continue

        tables = []
        for name, kind in [(item, "table") for item in table_names] + [(item, "view") for item in view_names]:
            try:
                columns = [
                    {
                        "name": col.get("name"),
                        "type": str(col.get("type") or ""),
                        "nullable": bool(col.get("nullable", True)),
                        "default": _json_value(col.get("default")),
                    }
                    for col in inspector.get_columns(name, schema=schema_name)
                ]
            except Exception:
                columns = []
            tables.append({"name": name, "type": kind, "schema": schema_name, "columns": columns})

        schemas.append({"name": schema_name or "", "tables": tables})

    return {"ok": True, "connection": connection_info(record), "schemas": schemas}


def _table_exists(inspector: Any, table_name: str, schema: Optional[str]) -> bool:
    try:
        return table_name in inspector.get_table_names(schema=schema) or table_name in inspector.get_view_names(schema=schema)
    except Exception:
        return False


def preview_structured_db_table(
    connection_id: str,
    table_name: str,
    schema: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> Dict[str, Any]:
    record = get_structured_db_connection(connection_id)
    table_name = _require(table_name, "表名")
    schema = str(schema or "").strip() or None
    limit = max(1, min(int(limit or 100), 500))
    offset = max(0, int(offset or 0))

    inspector = inspect(record.engine)
    if not _table_exists(inspector, table_name, schema):
        raise KeyError(f"未找到表或视图：{table_name}")

    preparer = record.engine.dialect.identifier_preparer
    quoted_table = preparer.quote(table_name)
    qualified_name = f"{preparer.quote_schema(schema)}.{quoted_table}" if schema else quoted_table

    with record.engine.connect() as conn:
        total = conn.execute(text(f"SELECT COUNT(*) AS total FROM {qualified_name}")).scalar_one()
        result = conn.execute(
            text(f"SELECT * FROM {qualified_name} LIMIT :limit OFFSET :offset"),
            {"limit": limit, "offset": offset},
        )
        columns = list(result.keys())
        rows = [
            {key: _json_value(value) for key, value in row.items()}
            for row in result.mappings().all()
        ]

    return {
        "ok": True,
        "connectionId": record.connection_id,
        "schema": schema or "",
        "table": table_name,
        "columns": columns,
        "rows": rows,
        "total": int(total or 0),
        "limit": limit,
        "offset": offset,
    }


def execute_readonly_sql(connection_id: str, sql: str, limit: int = 100) -> Dict[str, Any]:
    record = get_structured_db_connection(connection_id)
    safe_sql = normalize_readonly_sql(sql)
    limit = max(1, min(int(limit or 100), 500))
    fetch_limit = limit + 1
    wrapped_sql = f"SELECT * FROM ({safe_sql}) AS nl2sql_result LIMIT :_nl2sql_limit"

    with record.engine.connect() as conn:
        result = conn.execute(text(wrapped_sql), {"_nl2sql_limit": fetch_limit})
        columns = list(result.keys())
        raw_rows = result.mappings().all()

    truncated = len(raw_rows) > limit
    rows = [
        {key: _json_value(value) for key, value in row.items()}
        for row in raw_rows[:limit]
    ]
    return {
        "ok": True,
        "connectionId": record.connection_id,
        "connection": connection_info(record),
        "sql": safe_sql,
        "columns": columns,
        "rows": rows,
        "rowCount": len(rows),
        "limit": limit,
        "truncated": truncated,
    }
