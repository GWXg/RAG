from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from langchain_ollama import ChatOllama

from services.rag_service import answer_stream, retrieve
from services.structured_db_service import (
    execute_readonly_sql,
    get_structured_db_schema,
    normalize_readonly_sql,
)

load_dotenv(override=True)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
MODEL_NAME = os.getenv("QUERY_AGENT_MODEL", os.getenv("MODEL_NAME", "qwen2.5:7b"))
TEMPERATURE = 0

QUERY_MODES = {"vector", "sql", "hybrid", "agent"}


def _get_llm() -> ChatOllama:
    return ChatOllama(model=MODEL_NAME, temperature=TEMPERATURE, base_url=OLLAMA_BASE_URL)


def _content(resp: Any) -> str:
    return str(getattr(resp, "content", "") or "")


def _clip(text: Any, limit: int = 6000) -> str:
    value = str(text or "").strip()
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "\n...(已截断)"


def _parse_jsonish(text: str) -> Dict[str, Any]:
    raw = str(text or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        pass

    match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            return data if isinstance(data, dict) else {}
        except Exception:
            pass

    sql_match = re.search(r"```sql\s*(.*?)```", raw, flags=re.IGNORECASE | re.DOTALL)
    if sql_match:
        return {"sql": sql_match.group(1).strip()}
    select_match = re.search(r"\b(with|select)\b[\s\S]+", raw, flags=re.IGNORECASE)
    if select_match:
        return {"sql": select_match.group(0).strip()}
    return {}


def _schema_lines(schema_payload: Dict[str, Any], table_names: Optional[List[str]] = None) -> str:
    allowed = {name for name in (table_names or []) if name}
    lines: List[str] = []
    table_count = 0
    max_tables = 40
    max_cols_per_table = 36

    for schema in schema_payload.get("schemas") or []:
        schema_name = str(schema.get("name") or "")
        for table in schema.get("tables") or []:
            table_name = str(table.get("name") or "")
            if allowed and table_name not in allowed:
                continue
            if table_count >= max_tables:
                lines.append("...更多表已省略")
                return "\n".join(lines)
            columns = []
            for col in (table.get("columns") or [])[:max_cols_per_table]:
                col_name = str(col.get("name") or "")
                col_type = str(col.get("type") or "")
                columns.append(f"{col_name} {col_type}".strip())
            if len(table.get("columns") or []) > max_cols_per_table:
                columns.append("...")
            qualified = f"{schema_name}.{table_name}" if schema_name else table_name
            lines.append(f"- {qualified} ({'; '.join(columns)})")
            table_count += 1

    return "\n".join(lines) or "(未读取到表结构)"


def _rows_to_markdown(rows: List[Dict[str, Any]], columns: List[str], max_rows: int = 20) -> str:
    if not rows or not columns:
        return "(无返回行)"

    def cell(value: Any) -> str:
        return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ").strip()

    shown = rows[:max_rows]
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = ["| " + " | ".join(cell(row.get(col)) for col in columns) + " |" for row in shown]
    if len(rows) > max_rows:
        body.append(f"| ... | {' | '.join([''] * max(0, len(columns) - 1))} |")
    return "\n".join([header, separator, *body])


def _sql_observation(sql_result: Dict[str, Any]) -> str:
    if not sql_result.get("ok"):
        return f"SQL 查询失败：{sql_result.get('error') or 'unknown error'}"
    rows = sql_result.get("rows") or []
    columns = sql_result.get("columns") or []
    return _clip(
        "\n".join(
            [
                f"SQL: {sql_result.get('sql') or ''}",
                f"返回行数: {len(rows)}",
                _rows_to_markdown(rows, columns, max_rows=12),
            ]
        ),
        5000,
    )


async def _generate_sql(
    question: str,
    connection_id: str,
    table_names: Optional[List[str]] = None,
    repair_context: str = "",
) -> Dict[str, Any]:
    schema_payload = get_structured_db_schema(connection_id)
    connection = schema_payload.get("connection") or {}
    schema_text = _schema_lines(schema_payload, table_names=table_names)
    dialect = connection.get("type") or "sql"
    repair_block = f"\n上一次 SQL 报错，请修正：\n{repair_context}\n" if repair_context else ""
    prompt = f"""
你是严谨的 Text-to-SQL 助手。请把用户问题转换成只读 SQL。

数据库类型：{dialect}
可用表结构：
{schema_text}

用户问题：
{question}
{repair_block}
规则：
1. 只能使用上面列出的表和字段。
2. 只能生成 SELECT 或 WITH ... SELECT，不要生成任何写入、删除、DDL、存储过程或权限语句。
3. 不要编造字段；字段名含空格、中文或特殊字符时，按数据库方言加引号。
4. 只输出 JSON，不要输出 Markdown。

JSON 格式：
{{"sql":"SELECT ...","explanation":"一句话说明查询逻辑","confidence":0.0到1.0}}
""".strip()
    resp = await _get_llm().ainvoke([{"role": "user", "content": prompt}])
    parsed = _parse_jsonish(_content(resp))
    sql = normalize_readonly_sql(str(parsed.get("sql") or ""))
    return {
        "sql": sql,
        "explanation": str(parsed.get("explanation") or ""),
        "confidence": parsed.get("confidence"),
        "schema": schema_text,
    }


async def nl2sql_query(
    question: str,
    connection_id: str,
    sql_limit: int = 100,
    table_names: Optional[List[str]] = None,
) -> Dict[str, Any]:
    started = time.time()
    if not connection_id:
        return {"ok": False, "error": "CONNECTION_ID_REQUIRED", "message": "请选择数据库连接"}

    try:
        generated = await _generate_sql(question, connection_id, table_names=table_names)
        result = execute_readonly_sql(connection_id, generated["sql"], limit=sql_limit)
        result.update(
            {
                "ok": True,
                "explanation": generated.get("explanation") or "",
                "confidence": generated.get("confidence"),
                "elapsedMs": int((time.time() - started) * 1000),
            }
        )
        return result
    except Exception as first_error:
        try:
            generated = await _generate_sql(
                question,
                connection_id,
                table_names=table_names,
                repair_context=str(first_error),
            )
            result = execute_readonly_sql(connection_id, generated["sql"], limit=sql_limit)
            result.update(
                {
                    "ok": True,
                    "explanation": generated.get("explanation") or "",
                    "confidence": generated.get("confidence"),
                    "elapsedMs": int((time.time() - started) * 1000),
                    "repaired": True,
                }
            )
            return result
        except Exception as second_error:
            return {
                "ok": False,
                "error": "NL2SQL_QUERY_FAILED",
                "message": str(second_error),
                "firstError": str(first_error),
                "elapsedMs": int((time.time() - started) * 1000),
            }


async def _collect_rag_answer(
    question: str,
    citations: List[Dict[str, Any]],
    context_text: str,
    session_id: Optional[str] = None,
) -> str:
    branch = "with_context" if context_text else "no_context"
    parts: List[str] = []
    async for evt in answer_stream(
        question=question,
        citations=citations,
        context_text=context_text,
        branch=branch,
        session_id=session_id,
    ):
        if evt.get("type") == "token":
            parts.append(str(evt.get("data") or ""))
    return "".join(parts).strip()


async def vector_query(
    question: str,
    kb_id: str,
    file_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    if not kb_id:
        return {
            "mode": "vector",
            "answer": "请选择知识库后再进行向量检索。",
            "citations": [],
            "usedRetrieval": False,
            "contextText": "",
        }

    citations, context_text = await retrieve(question, kb_id, file_id)
    answer = await _collect_rag_answer(question, citations, context_text, session_id=session_id)
    return {
        "mode": "vector",
        "answer": answer,
        "citations": citations if context_text else [],
        "usedRetrieval": bool(context_text),
        "contextText": context_text,
    }


async def _summarize_sql(question: str, sql_result: Dict[str, Any]) -> str:
    if not sql_result.get("ok"):
        return f"SQL 查询失败：{sql_result.get('message') or sql_result.get('error') or '未知错误'}"
    prompt = f"""
请基于 SQL 查询结果回答用户问题。

用户问题：
{question}

生成的 SQL：
{sql_result.get('sql') or ''}

查询结果：
{_rows_to_markdown(sql_result.get('rows') or [], sql_result.get('columns') or [], max_rows=20)}

要求：直接回答问题；必要时说明结果行数；不要声称看到了未返回的数据。
""".strip()
    resp = await _get_llm().ainvoke([{"role": "user", "content": prompt}])
    return _content(resp).strip()


async def sql_query(question: str, connection_id: str, sql_limit: int = 100) -> Dict[str, Any]:
    sql_result = await nl2sql_query(question, connection_id, sql_limit=sql_limit)
    answer = await _summarize_sql(question, sql_result)
    return {
        "mode": "sql",
        "answer": answer,
        "sqlResult": sql_result,
        "usedSql": bool(sql_result.get("ok")),
        "citations": [],
        "usedRetrieval": False,
    }


async def hybrid_query(
    question: str,
    kb_id: Optional[str] = None,
    file_id: Optional[str] = None,
    connection_id: Optional[str] = None,
    sql_limit: int = 100,
) -> Dict[str, Any]:
    vector_part: Dict[str, Any] = {
        "citations": [],
        "contextText": "",
        "usedRetrieval": False,
    }
    sql_result: Dict[str, Any] = {"ok": False, "error": "CONNECTION_ID_REQUIRED", "message": "未选择数据库连接"}

    if kb_id:
        citations, context_text = await retrieve(question, kb_id, file_id)
        vector_part = {
            "citations": citations if context_text else [],
            "contextText": context_text,
            "usedRetrieval": bool(context_text),
        }
    if connection_id:
        sql_result = await nl2sql_query(question, connection_id, sql_limit=sql_limit)

    prompt = f"""
你需要综合两类证据回答用户问题：多模态文档检索上下文，以及 SQL 查询结果。

用户问题：
{question}

文档检索上下文：
{_clip(vector_part.get('contextText') or '(未使用或未检索到文档上下文)', 6000)}

SQL 查询结果：
{_sql_observation(sql_result)}

要求：
1. 优先基于证据回答，区分文档证据和数据库证据。
2. 如果某一类证据不可用，要明确说明。
3. 回答用 Markdown，简洁但完整。
""".strip()
    resp = await _get_llm().ainvoke([{"role": "user", "content": prompt}])
    return {
        "mode": "hybrid",
        "answer": _content(resp).strip(),
        "citations": vector_part.get("citations") or [],
        "usedRetrieval": bool(vector_part.get("usedRetrieval")),
        "sqlResult": sql_result,
        "usedSql": bool(sql_result.get("ok")),
    }


def _parse_agent_action(text: str) -> tuple[str, Dict[str, Any]]:
    action_match = re.search(r"Action\s*:\s*([A-Za-z_]+)", text)
    action = (action_match.group(1) if action_match else "").strip().lower()
    input_match = re.search(r"Action Input\s*:\s*(\{.*\})", text, flags=re.DOTALL)
    payload: Dict[str, Any] = {}
    if input_match:
        try:
            parsed = json.loads(input_match.group(1))
            payload = parsed if isinstance(parsed, dict) else {}
        except Exception:
            payload = {}
    return action, payload


async def agent_query(
    question: str,
    kb_id: Optional[str] = None,
    file_id: Optional[str] = None,
    connection_id: Optional[str] = None,
    sql_limit: int = 100,
) -> Dict[str, Any]:
    llm = _get_llm()
    observations: List[str] = []
    citations: List[Dict[str, Any]] = []
    sql_result: Dict[str, Any] = {}
    used_retrieval = False
    used_sql = False

    system = """
你是 ReAct 模式查询代理，可以通过工具逐步获取证据后回答。
可用工具：
- vector_retrieve：检索当前知识库中的多模态文档证据。
- nl2sql_query：把问题转换为 SQL 并查询当前数据库连接。
- final_answer：证据足够时给出最终答案。

每轮只能输出以下格式，不要输出其他内容：
Thought: ...
Action: vector_retrieve | nl2sql_query | final_answer
Action Input: {"question":"..."}
""".strip()
    scratch = ""

    for _ in range(4):
        prompt = f"""
用户问题：
{question}

当前可用上下文：
- kbId: {kb_id or '(未选择)'}
- fileId: {file_id or '(全部文件)'}
- connectionId: {connection_id or '(未选择)'}

历史观察：
{scratch or '(暂无)'}
""".strip()
        resp = await llm.ainvoke([{"role": "system", "content": system}, {"role": "user", "content": prompt}])
        text = _content(resp)
        action, payload = _parse_agent_action(text)
        tool_question = str(payload.get("question") or question)

        if action == "vector_retrieve":
            if not kb_id:
                observation = "vector_retrieve 无法执行：未选择知识库。"
            else:
                got_citations, context_text = await retrieve(tool_question, kb_id, file_id)
                citations = got_citations if context_text else citations
                used_retrieval = bool(context_text) or used_retrieval
                observation = "vector_retrieve 结果：\n" + _clip(context_text or "(未检索到相关文档上下文)", 5000)
        elif action == "nl2sql_query":
            if not connection_id:
                observation = "nl2sql_query 无法执行：未选择数据库连接。"
            else:
                sql_result = await nl2sql_query(tool_question, connection_id, sql_limit=sql_limit)
                used_sql = bool(sql_result.get("ok")) or used_sql
                observation = "nl2sql_query 结果：\n" + _sql_observation(sql_result)
        elif action == "final_answer":
            break
        else:
            observation = f"无法解析动作，模型输出为：{_clip(text, 800)}"

        observations.append(observation)
        scratch += f"\n{text}\nObservation: {observation}\n"

        if used_retrieval and used_sql:
            break

    final_prompt = f"""
请基于以下工具观察回答用户问题。

用户问题：
{question}

工具观察：
{_clip(chr(10).join(observations) or '(没有成功的工具观察)', 9000)}

要求：用 Markdown 回答；说明使用了哪些证据；不要编造 SQL 未返回的数据或文档未检索到的内容。
""".strip()
    final_resp = await llm.ainvoke([{"role": "user", "content": final_prompt}])
    return {
        "mode": "agent",
        "answer": _content(final_resp).strip(),
        "citations": citations,
        "usedRetrieval": used_retrieval,
        "sqlResult": sql_result if sql_result else None,
        "usedSql": used_sql,
        "agentTrace": observations,
    }


async def run_query(
    question: str,
    mode: str = "vector",
    kb_id: Optional[str] = None,
    file_id: Optional[str] = None,
    connection_id: Optional[str] = None,
    sql_limit: int = 100,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    question = str(question or "").strip()
    if not question:
        raise ValueError("QUERY_REQUIRED")

    normalized_mode = str(mode or "vector").strip().lower()
    if normalized_mode not in QUERY_MODES:
        raise ValueError(f"Unsupported query mode: {mode}")

    if normalized_mode == "vector":
        return await vector_query(question, str(kb_id or ""), file_id=file_id, session_id=session_id)
    if normalized_mode == "sql":
        return await sql_query(question, str(connection_id or ""), sql_limit=sql_limit)
    if normalized_mode == "hybrid":
        return await hybrid_query(
            question,
            kb_id=kb_id,
            file_id=file_id,
            connection_id=connection_id,
            sql_limit=sql_limit,
        )
    return await agent_query(
        question,
        kb_id=kb_id,
        file_id=file_id,
        connection_id=connection_id,
        sql_limit=sql_limit,
    )
