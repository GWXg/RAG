from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen


DESIGN_KB_ID = "钻井设计资料"
SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
MAIN_FILE_SUFFIXES = [
    ".pdf",
    ".docx",
    ".doc",
    ".xlsx",
    ".xls",
    ".csv",
    *sorted(SUPPORTED_IMAGE_SUFFIXES),
    ".json",
    ".jsonl",
    ".las",
]
GENERATED_KB_FILE_NAMES = {
    "output.md",
    "parse_meta.json",
    "extracted_tables.json",
    "image_metadata.json",
    "image_captions.json",
    "image_summaries.json",
}
FENGYE_WELL_PATTERN = re.compile(r"(?:DXFY|丰页)\s*([0-9A-Za-z]+(?:-[0-9A-Za-z]+)+HF)", re.IGNORECASE)
CHINESE_WELL_PATTERN = re.compile(
    r"(?<![\w\u4e00-\u9fff])([\u4e00-\u9fff]{1,8}[0-9A-Za-z]+(?:-[0-9A-Za-z]+)*(?:平[0-9A-Za-z]+)?井)"
)
CATEGORY_ORDER = {
    "地质设计": 0,
    "钻井工程设计": 1,
    "钻井井史报告": 2,
    "钻井日志": 3,
    "测井数据": 4,
    "综合录井": 5,
    "其他资料": 99,
}
STANDARD_OBJECT_KEYWORDS = [
    "陆上石油天然气",
    "海上石油天然气",
    "非常规油气",
    "已开发油田",
    "油气层",
    "页岩气",
    "煤层气",
    "致密油气",
    "陆上丛式同台井",
    "海上钻井",
    "海上固井",
    "套管侧钻井",
    "浅层大位移井",
    "大位移井",
    "小井眼",
    "水平井",
    "定向井",
    "直井",
    "固井",
    "钻井液",
    "钻井设备",
    "钻井队",
    "钻机",
    "钻头",
    "井控",
    "井场设备",
    "井场",
    "取心",
    "岩石",
    "个体防护装备",
    "个体防护",
    "HSE",
    "钻井现场",
    "钻井质量",
    "钻井工程设计",
]
STANDARD_OBJECT_FALLBACK = "其他规范对象"
GENERIC_STANDARD_OBJECTS = {
    "",
    "规范类文档",
    "规范文档",
    "标准规范",
    STANDARD_OBJECT_FALLBACK,
}
STANDARD_OBJECT_CACHE_NAME = ".file_manager_standard_objects.json"
STANDARD_UNIT_FALLBACK = "未明确油田/采油厂"
STANDARD_UNIT_ALIASES = [
    ("胜利", "胜利油田"),
    ("中原", "中原油田"),
    ("江汉", "江汉油田"),
    ("河南", "河南油田"),
    ("华北", "华北油田"),
    ("华东", "华东油田"),
    ("西北", "西北油田"),
    ("西南", "西南油气田"),
    ("东北", "东北油田"),
    ("塔河", "塔河油田"),
    ("普光", "普光气田"),
    ("川东北", "川东北地区"),
]
STANDARD_PLANT_ALIASES = [
    ("胜采", "胜利采油厂"),
    ("现河", "现河采油厂"),
    ("滨南", "滨南采油厂"),
    ("东辛", "东辛采油厂"),
    ("河口", "河口采油厂"),
    ("孤东", "孤东采油厂"),
    ("孤岛", "孤岛采油厂"),
    ("纯梁", "纯梁采油厂"),
    ("桩西", "桩西采油厂"),
    ("临盘", "临盘采油厂"),
    ("鲁明", "鲁明采油厂"),
    ("乐安", "乐安采油厂"),
]


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _read_json_value(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_kb_name(kb_dir: Path) -> str:
    meta = _read_json(kb_dir / "meta.json")
    return str(meta.get("name") or kb_dir.name)


def _find_main_file(file_dir: Path) -> Optional[Path]:
    for suffix in MAIN_FILE_SUFFIXES:
        matches = sorted(
            path
            for path in file_dir.iterdir()
            if path.is_file()
            and path.suffix.lower() == suffix
            and path.name not in GENERATED_KB_FILE_NAMES
        )
        if matches:
            return matches[0]
    matches = sorted(
        path
        for path in file_dir.iterdir()
        if path.is_file() and path.name not in GENERATED_KB_FILE_NAMES
    )
    return matches[0] if matches else None


def _file_type(path: Optional[Path]) -> str:
    suffix = path.suffix.lower() if path else ""
    if suffix == ".pdf":
        return "pdf"
    if suffix in {".doc", ".docx"}:
        return "word"
    if suffix in {".xlsx", ".xls", ".csv"}:
        return "excel"
    if suffix == ".las":
        return "las"
    if suffix in SUPPORTED_IMAGE_SUFFIXES:
        return "image"
    return "unknown"


def _read_parse_method(file_dir: Path, file_type: str) -> Dict[str, str]:
    meta = _read_json(file_dir / "parse_meta.json")
    parse_method = str(meta.get("parseMethod") or "")
    parser_name = str(meta.get("parser") or "")
    if not parse_method:
        if file_type == "excel":
            parse_method = "pandas"
            parser_name = "Pandas"
        elif file_type == "las":
            parse_method = "las"
            parser_name = "LAS"
        elif (file_dir / "mineru").exists():
            parse_method = "mineru"
            parser_name = "MinerU"
        elif (file_dir / "output.md").exists():
            parse_method = "original"
            parser_name = "Unstructured"
    return {"parseMethod": parse_method, "parser": parser_name}


def _table_count(file_dir: Path) -> int:
    data = _read_json_value(file_dir / "extracted_tables.json")
    tables = data.get("tables") if isinstance(data, dict) else None
    if isinstance(tables, list):
        return len(tables)
    if isinstance(data, list):
        return len(data)
    return 0


def _page_count(file_dir: Path) -> int:
    page_dir = file_dir / "pages" / "original"
    if not page_dir.exists():
        return 0
    try:
        return len(list(page_dir.glob("page-*.png")))
    except Exception:
        return 0


def _indexed_file_ids(data_root: Path, kb_id: str) -> set[str]:
    db_path = data_root / kb_id / "metadata.db"
    if not db_path.exists():
        return set()
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            cur = conn.cursor()
            cur.execute("SELECT DISTINCT entity_key FROM embeddings")
            return {str(row[0]) for row in cur.fetchall() if row and row[0]}
        finally:
            conn.close()
    except Exception:
        return set()


def _normalize_well_id(value: str) -> str:
    well_id = re.sub(r"\s+", "", str(value or "")).strip()
    if well_id.upper().startswith("DXFY"):
        return f"丰页{well_id[4:].upper()}"
    if well_id.startswith("丰页") and well_id.upper().endswith("HF"):
        return f"丰页{well_id[2:].upper()}"
    return well_id


def _extract_well_ids(value: str) -> List[str]:
    text = str(value or "")
    well_ids: List[str] = []
    seen = set()

    def add(well_id: str) -> None:
        normalized = _normalize_well_id(well_id)
        if normalized and normalized not in seen:
            seen.add(normalized)
            well_ids.append(normalized)

    for match in FENGYE_WELL_PATTERN.finditer(text):
        add(f"丰页{match.group(1)}")

    for match in CHINESE_WELL_PATTERN.finditer(text):
        candidate = match.group(1)
        if candidate.startswith("丰页") or candidate.upper().startswith("DXFY"):
            continue
        add(candidate)

    return well_ids


def _extract_well_id(value: str) -> Optional[str]:
    well_ids = _extract_well_ids(value)
    return well_ids[0] if well_ids else None


def _well_aliases(well_id: str) -> List[str]:
    aliases = [well_id]
    if well_id.startswith("丰页"):
        code = well_id.replace("丰页", "", 1)
        aliases.append(f"DXFY{code}")
    return aliases


def _document_category(kb_id: str, kb_name: str, file_name: str) -> str:
    text = f"{kb_id} {kb_name} {file_name}"
    if "地质设计" in text:
        return "地质设计"
    if "工程设计" in text:
        return "钻井工程设计"
    if "井史" in text:
        return "钻井井史报告"
    if "日志" in text or "井日志" in text:
        return "钻井日志"
    if "测井" in text:
        return "测井数据"
    if "录井" in text:
        return "综合录井"
    return kb_name or "其他资料"


def _clean_standard_title(file_name: str) -> str:
    title = Path(str(file_name or "")).stem
    title = re.sub(r"[_+]+", " ", title)
    title = re.sub(r"\s+", " ", title).strip()
    title = re.sub(r"^(?:QSH|Q/SH|SY/T|SY|GB/T|GB|AQ)\s*[0-9A-Za-z_. -]+-?\d{4}\s*", "", title, flags=re.IGNORECASE)
    title = re.sub(r"^\d{8}-\d+\s*", "", title)
    title = re.sub(r"[（(]带水印[）)]", "", title)
    return title.strip(" -_：:")


def _normalize_standard_object(value: str) -> str:
    obj = re.sub(r"[\s\"'“”‘’`]+", "", str(value or ""))
    obj = re.split(r"[，,;；/、]", obj)[0].strip()
    obj = obj.strip("：:。.!！?？-—_")
    if obj in GENERIC_STANDARD_OBJECTS:
        return ""
    if not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", obj):
        return ""
    if len(obj) > 24:
        return ""
    return obj


def _standard_object(file_name: str) -> str:
    title = _clean_standard_title(file_name)
    compact_title = re.sub(r"\s+", "", title)
    for keyword in STANDARD_OBJECT_KEYWORDS:
        if keyword in compact_title:
            return keyword

    part_match = re.search(r"第\s*\d+\s*部分[：:]\s*([^：:，,。\s]{2,24})", title)
    if part_match:
        part_object = _normalize_standard_object(part_match.group(1))
        if part_object:
            return part_object

    noun_match = re.search(r"([\u4e00-\u9fffA-Za-z0-9]{2,24}?)(?:技术要求|工艺技术|推荐作法|作业规程|操作规程|设计与施工|配套标准|设置|条件|方法|要求)", compact_title)
    if noun_match:
        noun_object = _normalize_standard_object(noun_match.group(1))
        if noun_object:
            return noun_object

    return STANDARD_OBJECT_FALLBACK


def _normalize_standard_unit(value: str) -> str:
    unit = re.sub(r"[\s\"'“”‘’`]+", "", str(value or ""))
    unit = re.split(r"[，,;；/、]", unit)[0].strip()
    unit = re.sub(r"^第\d+部分", "", unit)
    unit = unit.strip("：:。.!！?？-—_")
    if not unit or unit in {"规范类文档", "标准规范", STANDARD_UNIT_FALLBACK}:
        return ""
    if len(unit) > 24:
        return ""
    return unit


def _standard_unit(file_name: str) -> str:
    title = _clean_standard_title(file_name)
    compact_title = re.sub(r"\s+", "", title)

    if "油田企业" in compact_title:
        return "油田企业通用"
    if "已开发油田" in compact_title:
        return "已开发油田"
    if "非常规油气田" in compact_title:
        return "非常规油气田"
    if "非常规油气" in compact_title:
        return "非常规油气"

    for alias, unit in STANDARD_PLANT_ALIASES:
        if alias in compact_title:
            return unit

    plant_match = re.search(
        r"([\u4e00-\u9fffA-Za-z0-9]{2,18}?(?:采油厂|采气厂|采油气厂|采油管理区|采气管理区|作业区))",
        compact_title,
    )
    if plant_match:
        unit = _normalize_standard_unit(plant_match.group(1))
        if unit:
            return unit

    field_match = re.search(r"([\u4e00-\u9fffA-Za-z0-9]{2,18}?(?:油气田|油田|气田))", compact_title)
    if field_match:
        unit = _normalize_standard_unit(field_match.group(1))
        if unit:
            return unit

    region_match = re.search(r"([\u4e00-\u9fffA-Za-z0-9]{2,18}?(?:地区|区块|油区))", compact_title)
    if region_match:
        unit = _normalize_standard_unit(region_match.group(1))
        if unit:
            return unit

    for alias, unit in STANDARD_UNIT_ALIASES:
        if alias in compact_title:
            return unit

    return STANDARD_UNIT_FALLBACK


def _standard_cache_path(data_root: Path) -> Path:
    return data_root / STANDARD_OBJECT_CACHE_NAME


def _load_standard_object_cache(data_root: Path) -> Dict[str, str]:
    data = _read_json(_standard_cache_path(data_root))
    items = data.get("items") if isinstance(data, dict) else {}
    if not isinstance(items, dict):
        return {}
    cache: Dict[str, str] = {}
    for key, value in items.items():
        normalized = _normalize_standard_object(str(value))
        if normalized:
            cache[str(key)] = normalized
    return cache


def _write_standard_object_cache(data_root: Path, cache: Dict[str, str]) -> None:
    path = _standard_cache_path(data_root)
    try:
        payload = {"items": dict(sorted(cache.items()))}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        print(f"[file-manager] Failed to write standard object cache: {exc}")


def _parse_ollama_standard_objects(text: str) -> Dict[str, str]:
    raw = str(text or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw)
    data: Any = None
    try:
        data = json.loads(raw)
    except Exception:
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
            except Exception:
                data = None
    if not isinstance(data, dict):
        return {}

    result: Dict[str, str] = {}
    items = data.get("items")
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id") or "").strip()
            obj = _normalize_standard_object(str(item.get("object") or item.get("对象") or ""))
            if item_id and obj:
                result[item_id] = obj
    else:
        for item_id, obj_value in data.items():
            obj = _normalize_standard_object(str(obj_value))
            if obj:
                result[str(item_id)] = obj
    return result


def _classify_standard_objects_with_ollama(items: List[Dict[str, str]]) -> Dict[str, str]:
    if not items:
        return {}
    enabled = os.getenv("FILE_MANAGER_USE_OLLAMA", "auto").strip().lower()
    if enabled in {"0", "false", "no", "off", "disabled"}:
        return {}

    base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    model = os.getenv("FILE_MANAGER_OLLAMA_MODEL", os.getenv("QUERY_AGENT_MODEL", os.getenv("MODEL_NAME", "qwen2.5:7b")))
    timeout = float(os.getenv("FILE_MANAGER_OLLAMA_TIMEOUT", "45"))
    prompt = (
        "你是石油钻井设计规范文档分类助手。请根据文件名判断每份规范主要面向的对象、场景或工艺，"
        "对象必须是简短名词短语，不要返回“规范类文档”“标准规范”“其他”。\n"
        "优先抽取文件名中真正被规范的对象，例如：陆上石油天然气、海上石油天然气、非常规油气、"
        "水平井、定向井、井控、钻井液、固井、钻井设备、井场设备、钻头、取心、油气层。\n"
        "只输出 JSON，不要解释。格式：{\"items\":[{\"id\":\"0\",\"object\":\"对象\"}]}\n\n"
        f"文件列表：\n{json.dumps(items, ensure_ascii=False)}"
    )
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
    }
    request = Request(
        f"{base_url}/api/generate",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        return _parse_ollama_standard_objects(str(data.get("response") or ""))
    except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"[file-manager] Ollama standard object classification skipped: {exc}")
        return {}


def _apply_ollama_standard_objects(documents: List[Dict[str, Any]], data_root: Path) -> None:
    if not documents:
        return

    cache = _load_standard_object_cache(data_root)
    changed = False
    pending: List[Dict[str, str]] = []
    key_to_doc: Dict[str, Dict[str, Any]] = {}

    for doc in documents:
        file_name = str(doc.get("fileName") or doc.get("fileId") or "")
        cache_key = file_name
        cached = cache.get(cache_key)
        if cached:
            doc["standardObject"] = cached
            doc["standardObjectSource"] = "ollama-cache"
            continue

        rule_object = str(doc.get("standardObject") or _standard_object(file_name))
        doc["standardObject"] = rule_object
        item_id = str(len(pending))
        pending.append(
            {
                "id": item_id,
                "fileName": file_name,
                "title": _clean_standard_title(file_name),
                "ruleObject": rule_object,
            }
        )
        key_to_doc[item_id] = doc

    try:
        batch_size = max(1, int(os.getenv("FILE_MANAGER_OLLAMA_BATCH_SIZE", "24")))
    except ValueError:
        batch_size = 24
    for offset in range(0, len(pending), batch_size):
        batch = pending[offset : offset + batch_size]
        classified = _classify_standard_objects_with_ollama(batch)
        if not classified:
            break
        for item in batch:
            item_id = item["id"]
            obj = classified.get(item_id)
            doc = key_to_doc.get(item_id)
            if not doc or not obj:
                continue
            file_name = str(doc.get("fileName") or doc.get("fileId") or "")
            doc["standardObject"] = obj
            doc["standardObjectSource"] = "ollama"
            cache[file_name] = obj
            changed = True

    if changed:
        _write_standard_object_cache(data_root, cache)


def _is_standard_kb(kb_id: str, kb_name: str) -> bool:
    return "规范" in kb_id or "规范" in kb_name


def _list_kbs(data_root: Path, reserved_data_dirs: Iterable[str]) -> List[Dict[str, str]]:
    reserved = set(reserved_data_dirs)
    if not data_root.exists():
        return []
    kbs: List[Dict[str, str]] = []
    for kb_dir in sorted(data_root.iterdir(), key=lambda path: path.name):
        if not kb_dir.is_dir() or kb_dir.name in reserved:
            continue
        kbs.append({"kbId": kb_dir.name, "kbName": _read_kb_name(kb_dir)})
    return kbs


def _list_kb_documents(data_root: Path, kb_id: str, kb_name: str, indexed_file_ids: Optional[set[str]] = None) -> List[Dict[str, Any]]:
    files_root = data_root / kb_id / "files"
    if not files_root.exists():
        return []
    indexed_ids = indexed_file_ids if indexed_file_ids is not None else _indexed_file_ids(data_root, kb_id)
    documents: List[Dict[str, Any]] = []
    for file_dir in sorted(files_root.iterdir(), key=lambda path: path.name):
        if not file_dir.is_dir():
            continue
        main_file = _find_main_file(file_dir)
        # 读取不存在的 fileId 曾会遗留空工作目录；它们不是知识库文件，不能进入文件管理列表。
        if main_file is None:
            continue
        file_name = main_file.name if main_file else file_dir.name
        file_type = _file_type(main_file)
        table_count = _table_count(file_dir)
        parse_info = _read_parse_method(file_dir, file_type)
        has_parsed = (file_dir / "output.md").exists() or (file_type in {"excel", "las", "image"} and main_file is not None)
        well_ids = _extract_well_ids(" ".join([kb_id, kb_name, file_dir.name, file_name]))
        documents.append(
            {
                "kbId": kb_id,
                "kbName": kb_name,
                "fileId": file_dir.name,
                "fileName": file_name,
                "type": file_type,
                "hasParsed": has_parsed,
                "hasTables": table_count > 0,
                "tableCount": table_count,
                "pageCount": _page_count(file_dir),
                "parseMethod": parse_info["parseMethod"],
                "parser": parse_info["parser"],
                "isIndexed": file_dir.name in indexed_ids,
                "category": _document_category(kb_id, kb_name, file_name),
                "wellId": well_ids[0] if well_ids else None,
                "wellIds": well_ids,
            }
        )
    return documents


def _category_sort_key(item: Dict[str, Any]) -> Any:
    category = str(item.get("category") or "")
    return (CATEGORY_ORDER.get(category, 50), category)


def _document_sort_key(item: Dict[str, Any]) -> Any:
    return (*_category_sort_key(item), str(item.get("fileName") or item.get("fileId") or ""))


def _standard_group_sort_key(item: Dict[str, Any]) -> Any:
    name = str(item.get("object") or "")
    return (name == STANDARD_UNIT_FALLBACK, name)


def _build_standard_groups(documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    group_map: Dict[str, Dict[str, Any]] = {}
    for doc in documents:
        file_name = str(doc.get("fileName") or doc.get("fileId") or "")
        standard_unit = str(doc.get("standardUnit") or _standard_unit(file_name))
        doc["standardUnit"] = standard_unit
        if standard_unit not in group_map:
            group_map[standard_unit] = {
                "object": standard_unit,
                "documentCount": 0,
                "documents": [],
            }
        group_map[standard_unit]["documents"].append(doc)

    groups = sorted(group_map.values(), key=_standard_group_sort_key)
    for group in groups:
        group["documents"].sort(key=_document_sort_key)
        group["documentCount"] = len(group["documents"])
    return groups


def build_well_file_manager(
    data_root: Path,
    reserved_data_dirs: Iterable[str],
    design_kb_id: str = DESIGN_KB_ID,
) -> Dict[str, Any]:
    kbs = _list_kbs(data_root, reserved_data_dirs)
    well_map: Dict[str, Dict[str, Any]] = {}
    well_order: List[str] = []
    standards: List[Dict[str, Any]] = []
    unmatched: List[Dict[str, Any]] = []

    def ensure_well(well_id: str) -> Dict[str, Any]:
        if well_id not in well_map:
            well_map[well_id] = {
                "wellId": well_id,
                "aliases": _well_aliases(well_id),
                "documentCount": 0,
                "categories": [],
                "_categoryMap": {},
                "_documentKeys": set(),
            }
            well_order.append(well_id)
        return well_map[well_id]

    for kb in kbs:
        indexed_ids = _indexed_file_ids(data_root, kb["kbId"])
        docs = _list_kb_documents(data_root, kb["kbId"], kb["kbName"], indexed_ids)
        if _is_standard_kb(kb["kbId"], kb["kbName"]):
            for doc in docs:
                file_name = str(doc.get("fileName") or doc.get("fileId") or "")
                doc["category"] = "规范类文档"
                doc["standardObject"] = _standard_object(file_name)
                doc["standardUnit"] = _standard_unit(file_name)
                doc["standardObjectSource"] = "rule"
                standards.append(doc)
            continue

        for doc in docs:
            well_ids = [item for item in doc.get("wellIds", []) if isinstance(item, str) and item]
            if not well_ids and isinstance(doc.get("wellId"), str) and doc.get("wellId"):
                well_ids = [str(doc["wellId"])]
            if not well_ids:
                unmatched.append(doc)
                continue
            for well_id in well_ids:
                well = ensure_well(well_id)
                document_key = (str(doc.get("kbId") or ""), str(doc.get("fileId") or ""))
                if document_key in well["_documentKeys"]:
                    continue
                well["_documentKeys"].add(document_key)
                category = str(doc.get("category") or "其他资料")
                category_map = well["_categoryMap"]
                if category not in category_map:
                    category_map[category] = {"category": category, "documents": []}
                category_map[category]["documents"].append(doc)

    wells: List[Dict[str, Any]] = []
    for well_id in well_order:
        well = well_map[well_id]
        categories = sorted(well["_categoryMap"].values(), key=_category_sort_key)
        document_count = 0
        for category in categories:
            category["documents"].sort(key=_document_sort_key)
            document_count += len(category["documents"])
        wells.append(
            {
                "wellId": well["wellId"],
                "aliases": well["aliases"],
                "documentCount": document_count,
                "categories": categories,
            }
        )

    standards.sort(key=_document_sort_key)
    _apply_ollama_standard_objects(standards, data_root)
    standard_groups = _build_standard_groups(standards)
    unmatched.sort(key=_document_sort_key)
    return {
        "sourceKbId": "全部知识库",
        "standardsKbId": next((item["kbId"] for item in kbs if _is_standard_kb(item["kbId"], item["kbName"])), ""),
        "wellCount": len(wells),
        "documentCount": sum(item["documentCount"] for item in wells),
        "wells": wells,
        "standards": {
            "category": "规范类文档",
            "documentCount": len(standards),
            "documents": standards,
            "groups": standard_groups,
        },
        "unmatched": unmatched,
    }
