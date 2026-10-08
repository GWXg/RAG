# services/pdf_service.py
from __future__ import annotations
import os, io, math, json, re, shutil, time, shlex, subprocess
from pathlib import Path
from typing import Dict, Any, List
from html import unescape as html_unescape
from urllib.parse import urlparse, unquote
import fitz
from PIL import Image
import matplotlib
matplotlib.use("Agg")  # 服务器无头
import matplotlib.pyplot as plt
import matplotlib.patches as patches

from langchain_unstructured import UnstructuredLoader
from unstructured.partition.pdf import partition_pdf
from html2text import html2text
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage
import base64
import requests

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
VISION_MODEL_NAME = os.getenv("OLLAMA_VISION_MODEL", "llava:7b")

# 统一的根目录：每个 kbId 一个子目录；文件存放在 kbId/files/<fileId>/ 下
DATA_ROOT = Path("data")

# OLMOCR 配置
OLMOCR_ENDPOINT = os.getenv("OLMOCR_ENDPOINT", "http://127.0.0.1:8005/v1/chat/completions")
OLMOCR_MODEL = os.getenv("OLMOCR_MODEL", "olmocr")
OLMOCR_TIMEOUT = int(os.getenv("OLMOCR_TIMEOUT", "180"))
OLMOCR_MAX_TOKENS = int(os.getenv("OLMOCR_MAX_TOKENS", "8000"))
OLMOCR_TARGET_LONGEST_IMAGE_DIM = int(os.getenv("OLMOCR_TARGET_LONGEST_IMAGE_DIM", "1288"))
MINERU_CMD = os.getenv("MINERU_CMD", "mineru")
MINERU_BACKEND = os.getenv("MINERU_BACKEND", "pipeline")
MINERU_METHOD = os.getenv("MINERU_METHOD", "")
MINERU_LANG = os.getenv("MINERU_LANG", "")
MINERU_TIMEOUT = int(os.getenv("MINERU_TIMEOUT", "3600"))
MINERU_EXTRA_ARGS = os.getenv("MINERU_EXTRA_ARGS", "")
MINERU_MODEL_SOURCE = os.getenv("MINERU_MODEL_SOURCE", "")
OLMOCR_PROMPT = (
    "Attached is one page of a document that you must process. "
    "Just return the plain text representation of this document as if you were reading it naturally.\n"
    "Convert equations to LateX and tables to HTML.\n"
    "If there are any figures or charts, label them with the following markdown syntax "
    "![Alt text describing the contents of the figure](page_startx_starty_width_height.png)\n"
    "Return your output as markdown, with a front matter section on top specifying values for the "
    "primary_language, is_rotation_valid, rotation_correction, is_table, and is_diagram parameters."
)

def _post_olmocr(payload: Dict[str, Any]) -> requests.Response:
    """Post to local OLMOCR without inheriting HTTP proxy env vars."""
    host = urlparse(OLMOCR_ENDPOINT).hostname
    with requests.Session() as session:
        if host in {"127.0.0.1", "localhost", "::1", "0.0.0.0"}:
            session.trust_env = False
        return session.post(OLMOCR_ENDPOINT, json=payload, timeout=OLMOCR_TIMEOUT)

def sanitize_filename(name: str) -> str:
    """将字符串转换为安全的文件名"""
    # 移除无效字符
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    # 合并空白
    name = re.sub(r'\s+', " ", name).strip()
    # 限制长度，防止 Errno 36 File name too long (取前50个字符)
    if len(name) > 50:
        name = name[:50].strip()
    return name

_CAPTION_NUM_RE = r"[\dA-Za-z〇零一二三四五六七八九十百千万两]+(?:[.\-–—_][\dA-Za-z〇零一二三四五六七八九十百千万两]+)*"
_IMAGE_CAPTION_RE = re.compile(rf"^(?:图(?:表)?\s*{_CAPTION_NUM_RE}|Fig\.?\s*{_CAPTION_NUM_RE}|Figure\s+{_CAPTION_NUM_RE})", re.IGNORECASE)
_TABLE_CAPTION_RE = re.compile(rf"^(?:表\s*{_CAPTION_NUM_RE}|Tab\.?\s*{_CAPTION_NUM_RE}|Table\s+{_CAPTION_NUM_RE})", re.IGNORECASE)

def _clean_caption_candidate(text: str) -> str:
    text = html_unescape(str(text or ""))
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text)
    text = re.sub(r"^\s*[-*+]\s+", "", text)
    text = re.sub(r"\s+", " ", text).strip(" \t|")
    return text.strip()

def _is_caption(text: str, kind: str) -> bool:
    caption = _clean_caption_candidate(text)
    if not caption or len(caption) > 180:
        return False
    pattern = _TABLE_CAPTION_RE if kind == "table" else _IMAGE_CAPTION_RE
    return bool(pattern.match(caption))

def _unique_filename_from_caption(directory: Path, caption: str, suffix: str, current_name: str = "") -> str:
    base = sanitize_filename(_clean_caption_candidate(caption)) or sanitize_filename(Path(current_name).stem) or "untitled"
    suffix = suffix if suffix.startswith(".") else f".{suffix}"
    filename = f"{base}{suffix}"
    counter = 1
    while (directory / filename).exists() and filename != current_name:
        filename = f"{base}_{counter}{suffix}"
        counter += 1
    return filename

def _rename_file_with_caption(directory: Path, filename: str, caption: str) -> str:
    caption = _clean_caption_candidate(caption)
    if not caption:
        return filename

    old_path = directory / filename
    new_filename = _unique_filename_from_caption(directory, caption, old_path.suffix or Path(filename).suffix, current_name=filename)
    new_path = directory / new_filename
    if old_path.exists() and old_path != new_path:
        old_path.rename(new_path)
        return new_filename
    return filename

def _nearest_caption_in_lines(lines: List[str], kind: str, reverse: bool = False, max_lines: int = 6) -> str:
    iterable = reversed(lines[-max_lines:]) if reverse else lines[:max_lines]
    for line in iterable:
        caption = _clean_caption_candidate(line)
        if _is_caption(caption, kind):
            return caption
    return ""

def _caption_from_html_table(table_html: str) -> str:
    match = re.search(r"<caption[^>]*>(.*?)</caption>", table_html or "", flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return _clean_caption_candidate(match.group(1))

def _find_caption_near_elements(elements: List[Any], index: int, kind: str, page_num: int = None) -> str:
    if kind == "table":
        ranges = (
            range(index - 1, max(-1, index - 8), -1),
            range(index + 1, min(len(elements), index + 6)),
        )
    else:
        ranges = (
            range(index + 1, min(len(elements), index + 20)),
            range(index - 1, max(-1, index - 6), -1),
        )

    for nearby in ranges:
        for j in nearby:
            el = elements[j]
            cat = getattr(el, "category", None)
            if cat in {"Header", "Footer", "PageNumber"}:
                continue

            meta = getattr(el, "metadata", None)
            candidate_page = getattr(meta, "page_number", None) if meta else None
            if page_num and candidate_page and candidate_page != page_num:
                continue

            caption = _clean_caption_candidate(getattr(el, "text", "") or "")
            if kind == "image" and cat == "FigureCaption" and caption:
                return caption
            if _is_caption(caption, kind):
                return caption
    return ""

def kb_dir(kb_id: str) -> Path:
    d = DATA_ROOT / kb_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def kb_files_dir(kb_id: str) -> Path:
    d = kb_dir(kb_id) / "files"
    d.mkdir(parents=True, exist_ok=True)
    return d


def workdir(kb_id: str, file_id: str) -> Path:
    """某个知识库下某个文件的工作目录。"""
    d = kb_files_dir(kb_id) / file_id
    d.mkdir(parents=True, exist_ok=True)
    return d

def _workdir_path(kb_id: str, file_id: str) -> Path:
    """只计算工作目录路径，供读取操作使用，避免查询不存在的文件时创建空目录。"""
    return DATA_ROOT / kb_id / "files" / file_id

def kb_metadata_path(kb_id: str) -> Path:
    return kb_dir(kb_id) / "meta.json"

def read_kb_metadata(kb_id: str) -> Dict[str, Any]:
    path = kb_metadata_path(kb_id)
    if path.exists():
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
            meta.setdefault("kbId", kb_id)
            return meta
        except Exception:
            pass
    return {"kbId": kb_id, "name": kb_id}

def write_kb_metadata(kb_id: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    data = {"kbId": kb_id, **meta}
    path = kb_metadata_path(kb_id)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data

def dir_original_pages(kb_id: str, file_id: str) -> Path:
    p = workdir(kb_id, file_id) / "pages" / "original"
    p.mkdir(parents=True, exist_ok=True); return p

def dir_parsed_pages(kb_id: str, file_id: str) -> Path:
    p = workdir(kb_id, file_id) / "pages" / "parsed"
    p.mkdir(parents=True, exist_ok=True); return p

def original_pdf_path(kb_id: str, file_id: str, filename: str = None) -> Path:
    """
    返回主文件的路径 (PDF, Excel, CSV)。
    如果提供了 filename，则使用该文件名（用于保存时）。
    如果不提供 filename，则尝试查找目录下已存在的主文件（用于读取时）。
    """
    wd = workdir(kb_id, file_id) if filename else _workdir_path(kb_id, file_id)
    if filename:
        return wd / filename
    
    # 尝试查找现有的文件
    for ext in ["*.pdf", "*.docx", "*.doc", "*.xlsx", "*.xls", "*.csv"]:
        files = list(wd.glob(ext))
        if files:
            return files[0]
            
    # 默认回退到 file_id 作为文件名 (假设是 PDF)
    return wd / file_id

def markdown_output(kb_id: str, file_id: str) -> Path:
    return _workdir_path(kb_id, file_id) / "output.md"

def parse_metadata_path(kb_id: str, file_id: str) -> Path:
    return _workdir_path(kb_id, file_id) / "parse_meta.json"

def read_parse_metadata(kb_id: str, file_id: str) -> Dict[str, Any]:
    path = parse_metadata_path(kb_id, file_id)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def write_parse_metadata(kb_id: str, file_id: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    data = {"updatedAt": int(time.time()), **meta}
    path = parse_metadata_path(kb_id, file_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return data

def images_dir(kb_id: str, file_id: str) -> Path:
    p = workdir(kb_id, file_id) / "images"
    p.mkdir(parents=True, exist_ok=True); return p

def extract_embedded_images(kb_id: str, file_id: str, overwrite: bool = False) -> Dict[int, List[str]]:
    """提取 PDF 内嵌图片，返回 page -> image names。"""
    pdf_path = str(original_pdf_path(kb_id, file_id))
    img_dir = images_dir(kb_id, file_id)
    image_map: Dict[int, List[str]] = {}

    with fitz.open(pdf_path) as doc:
        for page_num, page in enumerate(doc, start=1):
            image_map[page_num] = []
            for img_index, img in enumerate(page.get_images(full=True), start=1):
                xref = img[0]
                img_path = img_dir / f"page{page_num}_img{img_index}.png"
                if img_path.exists() and not overwrite:
                    image_map[page_num].append(img_path.name)
                    continue
                pix = fitz.Pixmap(doc, xref)
                if pix.n < 5:
                    pix.save(str(img_path))
                else:
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                    pix.save(str(img_path))
                image_map[page_num].append(img_path.name)

    return image_map

def tables_dir(kb_id: str, file_id: str) -> Path:
    p = workdir(kb_id, file_id) / "tables"
    p.mkdir(parents=True, exist_ok=True); return p

def extracted_tables_path(kb_id: str, file_id: str) -> Path:
    return workdir(kb_id, file_id) / "extracted_tables.json"

def image_metadata_path(kb_id: str, file_id: str) -> Path:
    return workdir(kb_id, file_id) / "image_metadata.json"

def _image_page_num_from_name(name: str) -> int:
    match = re.search(r"page[-_]?0*(\d+)", name or "", flags=re.IGNORECASE)
    if not match:
        return 0
    try:
        return int(match.group(1))
    except Exception:
        return 0

def _load_image_metadata(kb_id: str, file_id: str) -> Dict[str, Dict[str, Any]]:
    path = image_metadata_path(kb_id, file_id)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("images"), dict):
            return data["images"]
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}

def _save_image_metadata(kb_id: str, file_id: str, metadata: Dict[str, Dict[str, Any]]) -> None:
    image_metadata_path(kb_id, file_id).write_text(
        json.dumps({"images": metadata}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

def _make_image_meta(img_name: str, page_num: int = 0, caption: str = "", original_name: str = "") -> Dict[str, Any]:
    return {
        "img_name": img_name,
        "page_num": int(page_num or _image_page_num_from_name(original_name or img_name)),
        "caption": _clean_caption_candidate(caption),
        "original_name": original_name or img_name,
    }

def _resolve_image_page_num(
    image_metadata: Dict[str, Dict[str, Any]],
    img_name: str,
    fallback_to_filename: bool = True,
) -> int:
    meta = image_metadata.get(img_name, {})
    try:
        page_num = int(meta.get("page_num") or 0)
    except Exception:
        page_num = 0
    if page_num > 0:
        return page_num
    return _image_page_num_from_name(img_name) if fallback_to_filename else 0

def _mineru_content_list_files(root: Path) -> List[Path]:
    files: List[Path] = []
    seen = set()
    for pattern in ("*content_list_v2.json", "*content_list.json"):
        for path in sorted(root.rglob(pattern)):
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            files.append(path)
    return files

def _mineru_primary_content_list_files(root: Path) -> List[Path]:
    content_files = sorted(root.rglob("*content_list_v2.json"))
    if content_files:
        return content_files
    return sorted(root.rglob("*content_list.json"))

def _mineru_image_page_map(kb_id: str, file_id: str) -> Dict[str, int]:
    meta = read_parse_metadata(kb_id, file_id)
    if str(meta.get("parseMethod") or "").lower() != "mineru":
        return {}

    mineru_root = workdir(kb_id, file_id) / "mineru"
    content_files = _mineru_content_list_files(mineru_root)
    if not content_files:
        return {}

    page_map: Dict[str, int] = {}
    for json_file in content_files:
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        for item, fallback_page_idx in _mineru_content_items(data):
            if _mineru_item_type(item) not in {"image", "chart", "figure"}:
                continue

            asset_ref = _mineru_image_asset_ref(item)
            page_num = _mineru_page_num(item, fallback_page_idx)
            if not asset_ref or page_num <= 0:
                continue

            ref_name = Path(unquote(asset_ref)).name
            if ref_name:
                page_map[ref_name] = page_num
            page_map[asset_ref] = page_num

    return page_map

def _repair_mineru_image_pages(kb_id: str, file_id: str, image_metadata: Dict[str, Dict[str, Any]]) -> bool:
    page_map = _mineru_image_page_map(kb_id, file_id)
    if not page_map:
        return False

    changed = False
    for img_name, meta in image_metadata.items():
        candidate_keys = [
            meta.get("original_name") or "",
            img_name,
        ]
        fixed_page = 0
        for key in candidate_keys:
            if not key:
                continue
            fixed_page = page_map.get(Path(str(key)).name) or page_map.get(str(key)) or 0
            if fixed_page:
                break

        if fixed_page <= 0:
            continue

        try:
            current_page = int(meta.get("page_num") or 0)
        except Exception:
            current_page = 0

        if current_page != fixed_page:
            meta["page_num"] = fixed_page
            changed = True

    if changed:
        _save_image_metadata(kb_id, file_id, image_metadata)

    return changed

def _reset_extracted_images(kb_id: str, file_id: str) -> Path:
    img_dir = images_dir(kb_id, file_id)
    for pattern in ("*.png", "*.jpg", "*.jpeg", "*.webp", "*.bmp"):
        for old_img in img_dir.glob(pattern):
            try:
                old_img.unlink()
            except Exception:
                pass
    for old_meta in [
        image_metadata_path(kb_id, file_id),
        workdir(kb_id, file_id) / "image_captions.json",
        workdir(kb_id, file_id) / "image_summaries.json",
    ]:
        try:
            old_meta.unlink(missing_ok=True)
        except Exception:
            pass
    return img_dir

def _flatten_column_name(col) -> str:
    if isinstance(col, tuple):
        parts = [str(c).strip() for c in col if str(c).strip() and not str(c).startswith("Unnamed")]
        return " / ".join(parts) if parts else "Column"
    name = str(col).strip()
    return name if name and not name.startswith("Unnamed") else "Column"

def _dedupe_columns(columns: List[Any]) -> List[str]:
    seen = {}
    out = []
    for idx, col in enumerate(columns):
        base = _flatten_column_name(col) or f"Column_{idx}"
        count = seen.get(base, 0)
        seen[base] = count + 1
        out.append(base if count == 0 else f"{base}_{count + 1}")
    return out

def _clean_table_df(df):
    import pandas as pd

    df = df.copy()
    df.columns = _dedupe_columns(list(df.columns))
    df = df.replace([float("inf"), float("-inf")], pd.NA)
    df = df.dropna(how="all").dropna(axis=1, how="all")
    df = df.astype(object).where(pd.notnull(df), None)
    return df

def _save_pdf_tables(kb_id: str, file_id: str, tables: List[Dict[str, Any]]) -> Dict[str, Any]:
    tables = _merge_cross_page_tables(kb_id, file_id, tables)
    out_path = extracted_tables_path(kb_id, file_id)
    out_path.write_text(json.dumps({"tables": tables}, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"tables": tables}

def get_pdf_tables(kb_id: str, file_id: str) -> List[Dict[str, Any]]:
    path = extracted_tables_path(kb_id, file_id)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("tables", [])
    except Exception:
        return []

def _save_df_as_pdf_table(
    df,
    kb_id: str,
    file_id: str,
    table_no: int,
    page_num: int = None,
    table_name: str = "",
) -> Dict[str, Any]:
    df = _clean_table_df(df)
    if df.empty:
        return {}

    out_dir = tables_dir(kb_id, file_id)
    display_name = _clean_caption_candidate(table_name) or f"Table {table_no}"
    csv_name = _unique_filename_from_caption(out_dir, display_name, ".csv")
    table_id = Path(csv_name).stem
    df.to_csv(out_dir / csv_name, index=False, encoding="utf-8-sig")

    return {
        "table_id": table_id,
        "name": display_name,
        "page_num": page_num,
        "csv_path": f"tables/{csv_name}",
        "columns": list(df.columns),
        "rows": df.to_dict(orient="records"),
    }

def _table_pages(table: Dict[str, Any]) -> List[int]:
    pages = table.get("page_nums")
    if isinstance(pages, list):
        out = []
        for p in pages:
            try:
                out.append(int(p))
            except Exception:
                pass
        if out:
            return sorted(set(out))
    page = table.get("page_num")
    try:
        return [int(page)] if page else []
    except Exception:
        return []

def _is_fallback_table_name(name: str) -> bool:
    return bool(re.fullmatch(r"Table\s+\d+", str(name or "").strip(), flags=re.IGNORECASE))

def _normalize_table_name_for_merge(name: str) -> str:
    name = _clean_caption_candidate(name)
    name = re.sub(r"[\s_]*(?:续表|continued|cont\.?)\s*$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"_\d+$", "", name)
    return re.sub(r"\s+", "", name).lower()

def _normalize_column_name_for_merge(name: str) -> str:
    return re.sub(r"\s+", "", str(name or "").strip()).lower()

def _table_columns_compatible(prev: Dict[str, Any], cur: Dict[str, Any]) -> bool:
    prev_cols = [_normalize_column_name_for_merge(c) for c in prev.get("columns", [])]
    cur_cols = [_normalize_column_name_for_merge(c) for c in cur.get("columns", [])]
    if not prev_cols or not cur_cols or len(prev_cols) != len(cur_cols):
        return False
    return prev_cols == cur_cols

def _should_merge_cross_page_table(prev: Dict[str, Any], cur: Dict[str, Any]) -> bool:
    prev_pages = _table_pages(prev)
    cur_pages = _table_pages(cur)
    if not prev_pages or not cur_pages:
        return False
    if min(cur_pages) != max(prev_pages) + 1:
        return False
    if not _table_columns_compatible(prev, cur):
        return False

    prev_name = str(prev.get("name") or "")
    cur_name = str(cur.get("name") or "")
    prev_norm = _normalize_table_name_for_merge(prev_name)
    cur_norm = _normalize_table_name_for_merge(cur_name)
    prev_fallback = _is_fallback_table_name(prev_name)
    cur_fallback = _is_fallback_table_name(cur_name)

    if prev_norm and cur_norm and prev_norm == cur_norm and not (prev_fallback and cur_fallback):
        return True
    if re.search(r"续表|continued|cont\.?", cur_name, flags=re.IGNORECASE):
        return True
    if cur_fallback and prev.get("rows"):
        return True
    if prev_fallback and cur_fallback:
        return True
    return False

def _drop_repeated_header_rows(rows: List[Dict[str, Any]], columns: List[str]) -> List[Dict[str, Any]]:
    if not rows or not columns:
        return rows
    first = rows[0]
    matches = 0
    for col in columns:
        value = str(first.get(col, "") or "").strip()
        if _normalize_column_name_for_merge(value) == _normalize_column_name_for_merge(col):
            matches += 1
    if matches >= max(1, math.ceil(len(columns) * 0.7)):
        return rows[1:]
    return rows

def _rewrite_table_csv(kb_id: str, file_id: str, table: Dict[str, Any]) -> None:
    import pandas as pd

    rel_path = table.get("csv_path")
    if not rel_path:
        return
    out_path = workdir(kb_id, file_id) / rel_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(table.get("rows", []), columns=table.get("columns", [])).to_csv(
        out_path,
        index=False,
        encoding="utf-8-sig",
    )

def _remove_table_csv(kb_id: str, file_id: str, table: Dict[str, Any]) -> None:
    rel_path = table.get("csv_path")
    if not rel_path:
        return
    try:
        (workdir(kb_id, file_id) / rel_path).unlink(missing_ok=True)
    except Exception:
        pass

def _merge_table_records(prev: Dict[str, Any], cur: Dict[str, Any]) -> Dict[str, Any]:
    columns = list(prev.get("columns", []))
    cur_rows = _drop_repeated_header_rows(list(cur.get("rows", [])), columns)
    prev["rows"] = list(prev.get("rows", [])) + cur_rows
    prev_pages = _table_pages(prev)
    cur_pages = _table_pages(cur)
    merged_pages = sorted(set(prev_pages + cur_pages))
    if merged_pages:
        prev["page_num"] = merged_pages[0]
        prev["page_nums"] = merged_pages
    merged_from = list(prev.get("merged_from", [prev.get("table_id")]))
    if cur.get("table_id") not in merged_from:
        merged_from.append(cur.get("table_id"))
    prev["merged_from"] = [x for x in merged_from if x]
    return prev

def _merge_cross_page_tables(kb_id: str, file_id: str, tables: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if os.getenv("MERGE_CROSS_PAGE_TABLES", "1").lower() in {"0", "false", "no"}:
        return tables

    merged: List[Dict[str, Any]] = []
    for table in tables:
        if merged and _should_merge_cross_page_table(merged[-1], table):
            merged[-1] = _merge_table_records(merged[-1], table)
            _rewrite_table_csv(kb_id, file_id, merged[-1])
            _remove_table_csv(kb_id, file_id, table)
        else:
            pages = _table_pages(table)
            if pages:
                table.setdefault("page_nums", pages)
            merged.append(table)
    return merged

def _extract_tables_from_html(
    html: str,
    kb_id: str,
    file_id: str,
    page_num: int = None,
    start_index: int = 0,
    table_name: str = "",
) -> List[Dict[str, Any]]:
    if not html or "<table" not in html.lower():
        return []

    import pandas as pd

    try:
        dfs = pd.read_html(io.StringIO(html))
    except Exception as e:
        print(f"Failed to parse HTML table: {e}")
        return []

    table_matches = list(re.finditer(r"<table\b.*?</table>", html, flags=re.IGNORECASE | re.DOTALL))

    saved_tables = []
    for idx, raw_df in enumerate(dfs):
        table_no = start_index + len(saved_tables) + 1
        caption = table_name
        if idx < len(table_matches):
            match = table_matches[idx]
            before = html[:match.start()].splitlines()
            caption = (
                _caption_from_html_table(match.group(0))
                or _nearest_caption_in_lines(before, "table", reverse=True)
                or table_name
            )
        if caption and len(dfs) > 1:
            caption = f"{caption}_{idx + 1}"
        record = _save_df_as_pdf_table(raw_df, kb_id, file_id, table_no, page_num, table_name=caption)
        if record:
            saved_tables.append(record)

    return saved_tables

def _extract_tables_from_markdown(
    text: str,
    kb_id: str,
    file_id: str,
    page_num: int = None,
    start_index: int = 0,
    table_name: str = "",
) -> List[Dict[str, Any]]:
    import pandas as pd

    def is_separator(line: str) -> bool:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        return bool(cells) and all(re.fullmatch(r":?-{3,}:?", c or "") for c in cells)

    lines = text.splitlines()
    saved_tables = []
    i = 0
    while i < len(lines) - 1:
        table_start = i
        header = lines[i].strip()
        sep = lines[i + 1].strip()
        if "|" not in header or not is_separator(sep):
            i += 1
            continue

        headers = [c.strip() or f"Column_{idx}" for idx, c in enumerate(header.strip("|").split("|"))]
        rows = []
        i += 2
        while i < len(lines) and "|" in lines[i]:
            row_cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
            if len(row_cells) < len(headers):
                row_cells.extend([""] * (len(headers) - len(row_cells)))
            rows.append(row_cells[:len(headers)])
            i += 1

        if rows:
            table_no = start_index + len(saved_tables) + 1
            df = pd.DataFrame(rows, columns=headers)
            caption = (
                _nearest_caption_in_lines(lines[:table_start], "table", reverse=True)
                or table_name
            )
            record = _save_df_as_pdf_table(df, kb_id, file_id, table_no, page_num, table_name=caption)
            if record:
                saved_tables.append(record)
        else:
            i += 1

    return saved_tables

def _is_figure_caption_text(text: str) -> bool:
    text = (text or "").strip()
    if not text:
        return False
    # 图名通常位于图片下方，以“图”开头；兼容英文 Figure。
    return bool(re.search(r"(?:^|\s)(图\s*\d[\w\-–—_.]*|Figure\s*\d[\w\-–—_.]*)", text, re.IGNORECASE))

def _summarize_word_image_caption(text: str) -> str:
    """从 Word 图片上方说明段落中提炼一个短图片名。"""
    text = _clean_caption_candidate(text)
    if not text:
        return ""

    text = re.sub(r"^(?:如下图所示|如图所示|见下图|见图|下图为|下图是|该图为|该图是|图中所示)[:：，,\s]*", "", text)
    text = re.sub(r"(?:如下图所示|如图所示|见下图|见图|如下图|如下)$", "", text).strip(" ，,。；;：:")
    text = re.sub(r"^(?:本图|该图|下图|上图|图片|图像)\s*(?:展示|显示|反映|表示|为|是)[:：，,\s]*", "", text)

    patterns = [
        r"([\u4e00-\u9fffA-Za-z0-9（）()《》\-–—_.]{2,60}(?:示意图|结构图|剖面图|曲线图|关系图|流程图|分布图|柱状图|轨迹图|井眼轨迹|图版|照片|截图|图片))",
        r"(?:为|是|展示|显示|反映|表示|说明|给出|绘制|形成|得到)\s*([\u4e00-\u9fffA-Za-z0-9（）()《》\-–—_.]{2,50})",
        r"(?:关于|有关|针对)\s*([\u4e00-\u9fffA-Za-z0-9（）()《》\-–—_.]{2,50})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            candidate = _clean_caption_candidate(match.group(1)).strip(" ，,。；;：:")
            if 2 <= len(candidate) <= 60:
                return candidate

    sentences = re.split(r"[。；;.!?！？]\s*", text)
    sentences = [s.strip(" ，,：:") for s in sentences if s.strip(" ，,：:")]
    if not sentences:
        return ""

    preferred_keywords = ("示意", "结构", "剖面", "曲线", "关系", "流程", "分布", "轨迹", "照片", "图")
    preferred = next((s for s in sentences if any(k in s for k in preferred_keywords)), sentences[0])
    if len(preferred) > 60:
        preferred = preferred[:60].rstrip(" ，,。；;：:")
    return preferred

def _normalize_image_title(title: str, max_len: int = 50) -> str:
    title = _clean_caption_candidate(title)
    if not title:
        return ""
    title = re.sub(r"^(?:Image|Figure|图片|图像)[:：\-\s]*", "", title, flags=re.IGNORECASE).strip()
    title = re.sub(r"\s+", " ", title).strip(" ，,。；;：:")

    figure_match = re.search(r"(图\s*[\dA-Za-z〇零一二三四五六七八九十百千万两][^。；;\n]*|Figure\s*[\dA-Za-z][^。；;\n]*)", title, re.IGNORECASE)
    if figure_match:
        title = figure_match.group(1).strip()
        repeated_caption = re.search(
            r"(.+?)\s+(?=图\s*[\dA-Za-z〇零一二三四五六七八九十百千万两]|Figure\s*[\dA-Za-z])",
            title,
            re.IGNORECASE,
        )
        if repeated_caption:
            title = repeated_caption.group(1).strip()

    title = re.split(r"[\r\n。；;!?！？]", title, maxsplit=1)[0].strip(" ，,。；;：:")
    title = re.sub(r"\s+(?=图\s*[\dA-Za-z〇零一二三四五六七八九十百千万两])", " ", title)
    if len(title) > max_len:
        title = title[:max_len].rstrip(" ，,。；;：:-_")
    return title

def _figure_caption_from_text(text: str) -> str:
    text = _clean_caption_candidate(text)
    if not _is_figure_caption_text(text):
        return ""
    return _normalize_image_title(text)

def _vision_image_title(image_path: Path) -> str:
    if not image_path or not Path(image_path).exists():
        return ""
    try:
        b64_img = base64.b64encode(Path(image_path).read_bytes()).decode("utf-8")
        chat = ChatOllama(model=VISION_MODEL_NAME, temperature=0, base_url=OLLAMA_BASE_URL)
        msg = chat.invoke([
            HumanMessage(
                content=[
                    {
                        "type": "text",
                        "text": (
                            "请根据图片内容生成一个简短中文图片名称，用于文件命名。"
                            "要求：不要超过20个汉字；不要包含句号、解释、引号；"
                            "优先使用“主题+图/示意图/结构图/曲线图”等命名。"
                        ),
                    },
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_img}"}},
                ]
            )
        ])
        return _normalize_image_title(str(getattr(msg, "content", "") or ""))
    except Exception as e:
        print(f"[image_title] vision title failed for {image_path}: {e}")
        return ""

def _figure_caption_candidates_from_text(text: str) -> List[str]:
    candidates: List[str] = []
    for raw_line in (text or "").splitlines():
        line = _clean_caption_candidate(raw_line)
        if not line:
            continue

        for match in re.finditer(r"(?:^|\s)(图\s*\d[\w\-–—_.]*.*|Figure\s*\d[\w\-–—_.]*.*)", line, re.IGNORECASE):
            candidate = _normalize_image_title(match.group(1))
            if candidate and candidate not in candidates:
                candidates.append(candidate)

        for alt_text, _ in re.findall(r"!\[([^\]]*)\]\(([^)]+)\)", line):
            alt = _clean_caption_candidate(alt_text)
            if not alt:
                continue
            if re.search(r"alt text describing|image|figure", alt, re.IGNORECASE) and len(alt) < 60:
                continue
            alt = _normalize_image_title(alt)
            if alt not in candidates:
                candidates.append(alt)

    return candidates

def _find_image_caption_below(elements: List[Any], image_index: int, page_num: int | None = None) -> str:
    """
    图片标题通常在图片下方。自当前 Image 元素之后持续向下查找，
    可跨到下一页，直到找到以“图”或 “Figure” 开头的文本。
    """
    for next_el in elements[image_index + 1:]:
        next_cat = getattr(next_el, "category", None)
        next_text = (getattr(next_el, "text", "") or "").strip()
        meta = getattr(next_el, "metadata", None)
        candidate_page = getattr(meta, "page_number", None) if meta else None

        if page_num and candidate_page:
            if candidate_page < page_num:
                continue
            if candidate_page > page_num + 1:
                break

        if not next_text:
            continue
        if next_cat in ["Header", "Footer", "PageNumber"]:
            continue
        caption = _figure_caption_from_text(next_text)
        if caption:
            return caption

    return ""

def _find_image_caption_above(elements: List[Any], image_index: int, page_num: int | None = None) -> str:
    """
    图片标题位于图片上方时，从当前 Image 元素之前向上查找。
    """
    for prev_el in reversed(elements[:image_index]):
        prev_cat = getattr(prev_el, "category", None)
        prev_text = (getattr(prev_el, "text", "") or "").strip()
        meta = getattr(prev_el, "metadata", None)
        candidate_page = getattr(meta, "page_number", None) if meta else None

        if page_num and candidate_page and candidate_page != page_num:
            break

        if not prev_text:
            continue
        if prev_cat in ["Header", "Footer", "PageNumber"]:
            continue
        caption = _figure_caption_from_text(prev_text)
        if caption:
            return caption

    return ""

def _summarize_image_text_above(elements: List[Any], image_index: int, page_num: int | None = None, max_items: int = 6) -> str:
    nearby_texts: List[str] = []
    for prev_el in reversed(elements[:image_index]):
        prev_cat = getattr(prev_el, "category", None)
        prev_text = _clean_caption_candidate(getattr(prev_el, "text", "") or "")
        meta = getattr(prev_el, "metadata", None)
        candidate_page = getattr(meta, "page_number", None) if meta else None

        if page_num and candidate_page and candidate_page != page_num:
            break
        if not prev_text or prev_cat in ["Header", "Footer", "PageNumber"]:
            continue
        if getattr(prev_el, "category", None) == "Image":
            break
        nearby_texts.append(prev_text)
        if len(nearby_texts) >= max_items:
            break

    if not nearby_texts:
        return ""
    nearby_texts = list(reversed(nearby_texts))
    return _normalize_image_title(_summarize_word_image_caption("。".join(nearby_texts)))

def _resolve_element_image_title(
    elements: List[Any],
    image_index: int,
    page_num: int | None = None,
    image_path: Path | None = None,
) -> str:
    return (
        _find_image_caption_below(elements, image_index, page_num)
        or _find_image_caption_above(elements, image_index, page_num)
        or _summarize_image_text_above(elements, image_index, page_num)
        or _vision_image_title(image_path)
    )

def _figure_captions_from_text(text: str) -> List[str]:
    return _figure_caption_candidates_from_text(text)

def _mineru_content_items(data: Any, fallback_page_idx: int | None = None):
    """Yield MinerU content-list items with optional 0-based page index."""
    if isinstance(data, list):
        for item in data:
            yield from _mineru_content_items(item, fallback_page_idx)
        return

    if not isinstance(data, dict):
        return

    yield data, fallback_page_idx

    for key in ("content_list", "items", "blocks"):
        value = data.get(key)
        if value:
            yield from _mineru_content_items(value, fallback_page_idx)

    pages = data.get("pages")
    if isinstance(pages, list):
        for page_idx, page in enumerate(pages):
            yield from _mineru_content_items(page, page_idx)

def _mineru_item_type(item: Dict[str, Any]) -> str:
    return str(
        item.get("type")
        or item.get("block_type")
        or item.get("category")
        or item.get("label")
        or ""
    ).strip().lower()

def _mineru_page_num(item: Dict[str, Any], fallback_page_idx: int | None = None) -> int:
    for key in ("page_idx", "page_index"):
        if key in item:
            try:
                return int(item[key]) + 1
            except Exception:
                pass
    content = item.get("content")
    if isinstance(content, dict):
        for key in ("page_idx", "page_index"):
            if key in content:
                try:
                    return int(content[key]) + 1
                except Exception:
                    pass
    for key in ("page_num", "page_number"):
        if key in item:
            try:
                page_num = int(item[key])
                return page_num + 1 if page_num == 0 else page_num
            except Exception:
                pass
    if fallback_page_idx is not None:
        return int(fallback_page_idx) + 1
    return 0

def _mineru_field(item: Dict[str, Any], *keys: str) -> Any:
    content = item.get("content")
    for key in keys:
        if key in item and item[key] not in (None, "", []):
            return item[key]
        if isinstance(content, dict) and key in content and content[key] not in (None, "", []):
            return content[key]
    return None

def _mineru_image_asset_ref(item: Dict[str, Any]) -> str:
    ref = _mineru_field(item, "img_path", "image_path", "path")
    if ref:
        return str(ref)

    content = item.get("content")
    if isinstance(content, dict):
        image_source = content.get("image_source")
        if isinstance(image_source, dict):
            nested_ref = image_source.get("path")
            if nested_ref:
                return str(nested_ref)
    return ""

def _mineru_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        parts = [_mineru_text(item) for item in value]
        return "\n".join(part for part in parts if part.strip())
    if isinstance(value, dict):
        preferred = (
            "text",
            "content",
            "title_content",
            "paragraph_content",
            "math_content",
            "code_content",
            "algorithm_content",
            "list_items",
        )
        parts = [_mineru_text(value[key]) for key in preferred if key in value]
        if not parts:
            parts = [_mineru_text(v) for v in value.values()]
        return "\n".join(part for part in parts if part.strip())
    return ""

def _mineru_caption(item: Dict[str, Any], *keys: str) -> str:
    for key in keys:
        caption = _clean_caption_candidate(_mineru_text(_mineru_field(item, key)))
        if caption:
            return caption
    return ""

def _mineru_table_html(item: Dict[str, Any]) -> str:
    for key in ("table_body", "table_content", "table_html", "html"):
        value = _mineru_field(item, key)
        if isinstance(value, str) and "<table" in value.lower():
            return value
    return ""

def _resolve_mineru_asset_path(asset_ref: str, source_dir: Path, mineru_out_dir: Path) -> Path | None:
    if not asset_ref:
        return None
    raw_ref = unquote(str(asset_ref).strip().strip("\"'"))
    if not raw_ref or "://" in raw_ref:
        return None
    candidate = Path(raw_ref)
    if candidate.is_absolute() and candidate.exists():
        return candidate

    candidates = [
        source_dir / raw_ref,
        source_dir.parent / raw_ref,
        mineru_out_dir / raw_ref,
        mineru_out_dir / candidate.name,
    ]
    for path in candidates:
        if path.exists():
            return path

    matches = list(mineru_out_dir.rglob(candidate.name))
    return matches[0] if matches else None

def _convert_doc_to_docx(source_path: Path) -> Path:
    if source_path.suffix.lower() != ".doc":
        return source_path

    target_path = source_path.with_suffix(".docx")
    try:
        if target_path.exists():
            source_mtime = source_path.stat().st_mtime
            target_mtime = target_path.stat().st_mtime
            if target_mtime >= source_mtime:
                return target_path
            target_path.unlink()
    except Exception:
        pass

    cmd = [
        "soffice",
        "--headless",
        "--convert-to",
        "docx",
        "--outdir",
        str(source_path.parent),
        str(source_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=MINERU_TIMEOUT)
    if proc.returncode != 0:
        raise RuntimeError(f"DOC 转换为 DOCX 失败: {proc.stderr[-2000:] or proc.stdout[-2000:]}")
    if not target_path.exists():
        raise RuntimeError(f"DOC 转换完成但未找到输出文件: {target_path}")
    return target_path

def _convert_office_to_pdf(source_path: Path) -> Path:
    suffix = source_path.suffix.lower()
    if suffix not in {".doc", ".docx"}:
        return source_path

    target_dir = source_path.parent / "_converted"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{source_path.stem}.pdf"
    try:
        if target_path.exists() and target_path.stat().st_mtime >= source_path.stat().st_mtime:
            return target_path
        if target_path.exists():
            target_path.unlink()
    except Exception:
        pass

    cmd = [
        "soffice",
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        str(target_dir),
        str(source_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=MINERU_TIMEOUT)
    if proc.returncode != 0:
        raise RuntimeError(f"Word 转换为 PDF 失败: {proc.stderr[-2000:] or proc.stdout[-2000:]}")
    if not target_path.exists():
        matches = sorted(target_dir.glob("*.pdf"))
        if matches:
            return matches[0]
        raise RuntimeError(f"Word 转换完成但未找到输出 PDF: {target_path}")
    return target_path

def _infer_mineru_caption_from_items(
    items: List[tuple[Dict[str, Any], int | None]],
    image_index: int,
    direction: str,
    page_num: int | None = None,
    max_items: int = 8,
    summarize_nearby_text: bool = False,
) -> str:
    if direction == "above":
        index_range = range(image_index - 1, max(-1, image_index - max_items - 1), -1)
    else:
        index_range = range(image_index + 1, min(len(items), image_index + 1 + max_items))

    nearby_texts: List[str] = []
    for candidate_index in index_range:
        candidate_item, fallback_page_idx = items[candidate_index]
        candidate_page = _mineru_page_num(candidate_item, fallback_page_idx) or 0
        if page_num and candidate_page and candidate_page != page_num:
            break

        candidate_type = _mineru_item_type(candidate_item)
        if candidate_type in {"header", "footer", "page_number", "aside_text", "page_header", "page_footer"}:
            continue
        if candidate_type in {"image", "chart", "figure"}:
            break

        candidate_text = _clean_caption_candidate(
            _mineru_text(
                _mineru_field(
                    candidate_item,
                    "text",
                    "content",
                    "title_content",
                    "paragraph_content",
                    "math_content",
                    "code_content",
                )
            )
        )
        if _is_figure_caption_text(candidate_text):
            return candidate_text
        if summarize_nearby_text and candidate_text:
            nearby_texts.append(candidate_text)

    if summarize_nearby_text and nearby_texts:
        if direction == "above":
            nearby_texts = list(reversed(nearby_texts))
        return _summarize_word_image_caption("。".join(nearby_texts))

    return ""

def _mineru_item_context_text(item: Dict[str, Any]) -> str:
    return _clean_caption_candidate(
        _mineru_text(
            _mineru_field(
                item,
                "text",
                "content",
                "title_content",
                "paragraph_content",
                "math_content",
                "code_content",
            )
        )
    )

def _find_mineru_caption_down(
    items: List[tuple[Dict[str, Any], int | None]],
    image_index: int,
    page_num: int | None = None,
    max_items: int = 24,
) -> str:
    for candidate_index in range(image_index + 1, min(len(items), image_index + 1 + max_items)):
        candidate_item, fallback_page_idx = items[candidate_index]
        candidate_page = _mineru_page_num(candidate_item, fallback_page_idx) or 0
        if page_num and candidate_page:
            if candidate_page < page_num:
                continue
            if candidate_page > page_num + 1:
                break

        candidate_type = _mineru_item_type(candidate_item)
        if candidate_type in {"header", "footer", "page_number", "aside_text", "page_header", "page_footer"}:
            continue
        caption = _figure_caption_from_text(_mineru_item_context_text(candidate_item))
        if caption:
            return caption
    return ""

def _find_mineru_caption_or_summary_up(
    items: List[tuple[Dict[str, Any], int | None]],
    image_index: int,
    page_num: int | None = None,
    max_items: int = 8,
) -> str:
    nearby_texts: List[str] = []
    for candidate_index in range(image_index - 1, max(-1, image_index - max_items - 1), -1):
        candidate_item, fallback_page_idx = items[candidate_index]
        candidate_page = _mineru_page_num(candidate_item, fallback_page_idx) or 0
        if page_num and candidate_page and candidate_page != page_num:
            break

        candidate_type = _mineru_item_type(candidate_item)
        if candidate_type in {"header", "footer", "page_number", "aside_text", "page_header", "page_footer"}:
            continue
        if candidate_type in {"image", "chart", "figure"}:
            break

        candidate_text = _mineru_item_context_text(candidate_item)
        caption = _figure_caption_from_text(candidate_text)
        if caption:
            return caption
        if candidate_text:
            nearby_texts.append(candidate_text)

    if nearby_texts:
        nearby_texts = list(reversed(nearby_texts))
        return _normalize_image_title(_summarize_word_image_caption("。".join(nearby_texts)))
    return ""

def _infer_mineru_image_title(
    items: List[tuple[Dict[str, Any], int | None]],
    image_index: int,
    page_num: int | None,
    image_path: Path | None,
    explicit_caption: str = "",
) -> str:
    explicit_caption = _normalize_image_title(explicit_caption)
    if explicit_caption:
        return explicit_caption
    return (
        _find_mineru_caption_down(items, image_index, page_num)
        or _find_mineru_caption_or_summary_up(items, image_index, page_num)
        or _vision_image_title(image_path)
    )

def _infer_caption_from_markdown_lines(
    lines: List[str],
    line_index: int,
    direction: str,
    max_lines: int = 6,
    summarize_nearby_text: bool = False,
) -> str:
    if direction == "above":
        index_range = range(line_index - 1, max(-1, line_index - max_lines - 1), -1)
    else:
        index_range = range(line_index + 1, min(len(lines), line_index + 1 + max_lines))

    nearby_texts: List[str] = []
    for candidate_index in index_range:
        candidate_text = _clean_caption_candidate(lines[candidate_index])
        caption = _figure_caption_from_text(candidate_text)
        if caption:
            return caption
        if summarize_nearby_text and candidate_text:
            nearby_texts.append(candidate_text)

    if summarize_nearby_text and nearby_texts:
        if direction == "above":
            nearby_texts = list(reversed(nearby_texts))
        return _normalize_image_title(_summarize_word_image_caption("。".join(nearby_texts)))

    return ""

def _infer_markdown_image_title(lines: List[str], line_index: int, image_path: Path | None = None) -> str:
    return (
        _infer_caption_from_markdown_lines(lines, line_index, "below", max_lines=20, summarize_nearby_text=False)
        or _infer_caption_from_markdown_lines(lines, line_index, "above", max_lines=8, summarize_nearby_text=False)
        or _infer_caption_from_markdown_lines(lines, line_index, "above", max_lines=8, summarize_nearby_text=True)
        or _vision_image_title(image_path)
    )

def _copy_mineru_image(src_path: Path, img_dir: Path, caption: str, index: int) -> str:
    filename = _unique_filename_from_caption(
        img_dir,
        caption or src_path.stem or f"mineru_image_{index}",
        ".png",
    )
    target = img_dir / filename
    try:
        with Image.open(src_path) as im:
            if im.mode not in {"RGB", "RGBA"}:
                im = im.convert("RGB")
            im.save(target, format="PNG")
    except Exception:
        shutil.copy2(src_path, target)
    return filename

def _register_mineru_image(
    asset_ref: str,
    src_path: Path,
    img_dir: Path,
    caption: str,
    page_num: int,
    index: int,
    image_captions: Dict[str, str],
    image_metadata: Dict[str, Dict[str, Any]],
    image_asset_map: Dict[str, str],
) -> str:
    existing = image_asset_map.get(asset_ref) or image_asset_map.get(src_path.name)
    if existing:
        return existing

    img_name = _copy_mineru_image(src_path, img_dir, caption, index)
    clean_caption = _clean_caption_candidate(caption)
    if clean_caption:
        image_captions[img_name] = clean_caption
    image_metadata[img_name] = _make_image_meta(
        img_name,
        page_num=page_num,
        caption=clean_caption,
        original_name=src_path.name,
    )
    for key in {asset_ref, unquote(asset_ref), src_path.name, str(src_path)}:
        if key:
            image_asset_map[key] = img_name
    return img_name

def _rewrite_mineru_markdown_image_links(text: str, image_asset_map: Dict[str, str]) -> str:
    def repl(match):
        alt = match.group(1)
        ref = unquote(match.group(2).strip())
        key = ref.split("#", 1)[0].split("?", 1)[0]
        img_name = image_asset_map.get(key) or image_asset_map.get(Path(key).name)
        if not img_name:
            return match.group(0)
        return f"![{alt}](./images/{img_name})"

    return re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", repl, text or "")

def _collect_mineru_outputs(
    kb_id: str,
    file_id: str,
    mineru_out_dir: Path,
    img_dir: Path,
    caption_direction: str = "below",
):
    summarize_caption_text = caption_direction == "above"
    image_captions: Dict[str, str] = {}
    image_metadata: Dict[str, Dict[str, Any]] = {}
    image_asset_map: Dict[str, str] = {}
    extracted_tables: List[Dict[str, Any]] = []
    md_parts: List[str] = []
    image_index = 0

    content_files = _mineru_primary_content_list_files(mineru_out_dir)
    content_items: List[tuple[Dict[str, Any], int | None]] = []
    for json_file in content_files:
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"Failed to read MinerU content list {json_file}: {e}")
            continue

        content_items.extend(list(_mineru_content_items(data)))

    for item_index, (item, fallback_page_idx) in enumerate(content_items):
        item_type = _mineru_item_type(item)
        page_num = _mineru_page_num(item, fallback_page_idx)

        if item_type in {"image", "chart", "figure"}:
            asset_ref = _mineru_image_asset_ref(item)
            src_path = _resolve_mineru_asset_path(str(asset_ref or ""), mineru_out_dir, mineru_out_dir)
            caption = _infer_mineru_image_title(
                content_items,
                item_index,
                page_num or None,
                src_path,
                explicit_caption=_mineru_caption(item, "image_caption", "chart_caption", "caption", "title"),
            )
            if not caption:
                caption = _infer_mineru_caption_from_items(
                    content_items,
                    item_index,
                    direction=caption_direction,
                    page_num=page_num or None,
                    summarize_nearby_text=summarize_caption_text,
                )
            if src_path:
                image_index += 1
                img_name = _register_mineru_image(
                    str(asset_ref or src_path.name),
                    src_path,
                    img_dir,
                    caption,
                    page_num,
                    image_index,
                    image_captions,
                    image_metadata,
                    image_asset_map,
                )
                alt = caption or "Image"
                md_parts.append(f"![{alt}](./images/{img_name})")
                if caption:
                    md_parts.append(f"*{caption}*")
            continue

        if item_type == "table":
            caption = _mineru_caption(item, "table_caption", "caption", "title")
            html = _mineru_table_html(item)
            if html:
                extracted_tables.extend(
                    _extract_tables_from_html(
                        html,
                        kb_id,
                        file_id,
                        page_num=page_num or None,
                        start_index=len(extracted_tables),
                        table_name=caption,
                    )
                )
                if caption:
                    md_parts.append(caption)
                md_parts.append(html2text(html))
            else:
                text = _mineru_text(_mineru_field(item, "table_body", "table_content", "text", "content"))
                if text:
                    extracted_tables.extend(
                        _extract_tables_from_markdown(
                            text,
                            kb_id,
                            file_id,
                            page_num=page_num or None,
                            start_index=len(extracted_tables),
                            table_name=caption,
                        )
                    )
                    if caption:
                        md_parts.append(caption)
                    md_parts.append(text)
            continue

        if item_type in {"header", "footer", "page_number", "aside_text", "page_header", "page_footer"}:
            continue

        text = _mineru_text(
            _mineru_field(
                item,
                "text",
                "content",
                "title_content",
                "paragraph_content",
                "math_content",
                "code_content",
            )
        )
        text = text.strip()
        if text:
            md_parts.append(text)

    return {
        "markdown": "\n\n".join(part.strip() for part in md_parts if part and part.strip()),
        "image_captions": image_captions,
        "image_metadata": image_metadata,
        "image_asset_map": image_asset_map,
        "tables": extracted_tables,
    }

def _collect_mineru_markdown_images(
    md_pages: List[str],
    md_files: List[Path],
    mineru_out_dir: Path,
    img_dir: Path,
    collected: Dict[str, Any],
    caption_direction: str = "below",
) -> None:
    image_captions = collected["image_captions"]
    image_metadata = collected["image_metadata"]
    image_asset_map = collected["image_asset_map"]
    image_index = len(image_metadata)
    summarize_caption_text = caption_direction == "above"

    for page_idx, content in enumerate(md_pages):
        source_dir = md_files[page_idx].parent if page_idx < len(md_files) else mineru_out_dir
        lines = (content or "").splitlines()
        for line_idx, line in enumerate(lines):
            for alt, ref in re.findall(r"!\[([^\]]*)\]\(([^)]+)\)", line):
                clean_ref = unquote(ref.strip())
                if image_asset_map.get(clean_ref) or image_asset_map.get(Path(clean_ref).name):
                    continue
                src_path = _resolve_mineru_asset_path(clean_ref, source_dir, mineru_out_dir)
                if not src_path:
                    continue
                caption = _normalize_image_title(alt)
                if not _is_caption(caption, "image"):
                    caption = _infer_markdown_image_title(lines, line_idx, src_path)
                    if not caption:
                        caption = ""
                image_index += 1
                _register_mineru_image(
                    clean_ref,
                    src_path,
                    img_dir,
                    caption,
                    page_idx + 1,
                    image_index,
                    image_captions,
                    image_metadata,
                    image_asset_map,
                )

def save_upload(kb_id: str, file_id: str, upload_bytes: bytes, filename: str) -> Dict[str, Any]:
    """保存上传的文件，并返回页数（如果是 PDF）"""
    # 清理旧内容但保留 metadata
    wd = workdir(kb_id, file_id)
    for entry in wd.iterdir():
        if entry.is_dir():
            shutil.rmtree(entry, ignore_errors=True)
        else:
            try:
                entry.unlink()
            except Exception:
                pass

    # kb 元数据不存在时写入默认
    meta_path = kb_metadata_path(kb_id)
    if not meta_path.exists():
        write_kb_metadata(kb_id, {"name": kb_id, "createdAt": int(time.time())})

    # 使用原始文件名保存
    file_path = original_pdf_path(kb_id, file_id, filename)
    file_path.write_bytes(upload_bytes)
    
    pages = 0
    if filename.lower().endswith('.pdf'):
        try:
            with fitz.open(file_path) as doc:
                pages = doc.page_count
        except Exception as e:
            print(f"Error reading PDF page count: {e}")
            
    return {"kbId": kb_id, "fileId": file_id, "name": filename, "pages": pages}

def _page_render_matrix(page, dpi: int = 144, target_longest_dim: int | None = None) -> fitz.Matrix:
    if target_longest_dim:
        longest = max(float(page.rect.width), float(page.rect.height))
        if longest > 0:
            scale = target_longest_dim / longest
            return fitz.Matrix(scale, scale)
    return fitz.Matrix(dpi/72, dpi/72)

def render_original_pages(kb_id: str, file_id: str, dpi: int = 144, target_longest_dim: int | None = None):
    """把原始 PDF 渲染为 PNG，存到 pages/original/"""
    pdf_path = original_pdf_path(kb_id, file_id)
    out_dir = dir_original_pages(kb_id, file_id)
    with fitz.open(pdf_path) as doc:
        for idx, page in enumerate(doc, start=1):
            mat = _page_render_matrix(page, dpi=dpi, target_longest_dim=target_longest_dim)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            (out_dir / f"page-{idx:04d}.png").write_bytes(pix.tobytes("png"))

def _plot_boxes_to_ax(ax, pix, segments):
    category_to_color = {
        "Title": "orchid",
        "Image": "forestgreen",
        "Table": "tomato",
    }
    categories = set()
    for seg in segments:
        points = seg["coordinates"]["points"]
        lw = seg["coordinates"]["layout_width"]
        lh = seg["coordinates"]["layout_height"]
        scaled = [(x * pix.width / lw, y * pix.height / lh) for x, y in points]
        color = category_to_color.get(seg.get("category"), "deepskyblue")
        categories.add(seg.get("category", "Text"))
        poly = patches.Polygon(scaled, linewidth=1, edgecolor=color, facecolor="none")
        ax.add_patch(poly)

    legend_handles = [patches.Patch(color="deepskyblue", label="Text")]
    for cat, color in category_to_color.items():
        if cat in categories:
            legend_handles.append(patches.Patch(color=color, label=cat))
    ax.legend(handles=legend_handles, loc="upper right")

def render_parsed_pages_with_boxes(kb_id: str, file_id: str, docs_local: List[Dict[str, Any]], dpi: int = 144):
    """
    根据 UnstructuredLoader 的 metadata（含坐标）在原图上叠框，输出到 pages/parsed/
    """
    pdf_path = original_pdf_path(kb_id, file_id)
    out_dir = dir_parsed_pages(kb_id, file_id)
    with fitz.open(pdf_path) as doc:
        # 预聚合：按 page_number 分组 segments
        segments_by_page: Dict[int, List[Dict[str, Any]]] = {}
        for d in docs_local:
            meta = d.metadata if hasattr(d, "metadata") else d["metadata"]
            pno = meta.get("page_number")
            if pno is None: continue
            segments_by_page.setdefault(pno, []).append(meta)

        for page_number in range(1, doc.page_count + 1):
            page = doc.load_page(page_number - 1)
            mat = _page_render_matrix(page, dpi=dpi)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            pil = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            fig, ax = plt.subplots(1, figsize=(10, 10))
            ax.imshow(pil)
            ax.axis("off")
            _plot_boxes_to_ax(ax, pix, segments_by_page.get(page_number, []))
            fig.tight_layout()
            fig.savefig(out_dir / f"page-{page_number:04d}.png", bbox_inches="tight", pad_inches=0)
            plt.close(fig)

def unstructured_segments(kb_id: str, file_id: str) -> List[Any]:
    """用 UnstructuredLoader 产生高分辨率布局段"""
    # 查找实际的 PDF 文件路径
    pdf_path = str(original_pdf_path(kb_id, file_id))
    loader = UnstructuredLoader(
        file_path=pdf_path,
        strategy="hi_res",
        infer_table_structure=True,
        ocr_languages="chi_sim+eng",
        ocr_engine="paddleocr",  # 如果装不上可换成 'auto' 或注释掉
    )
    out = []
    for d in loader.lazy_load():
        out.append(d)
    return out

def pdf_to_markdown(kb_id: str, file_id: str):
    # 查找实际的 PDF 文件路径
    pdf_path = str(original_pdf_path(kb_id, file_id))
    out_md = markdown_output(kb_id, file_id)
    img_dir = _reset_extracted_images(kb_id, file_id)

    elements = partition_pdf(
        filename=pdf_path,
        infer_table_structure=True,
        strategy="hi_res",
        ocr_languages="chi_sim+eng",
        ocr_engine="paddleocr"  # 同上
    )

    # 提取图片
    image_map = {}
    image_metadata: Dict[str, Dict[str, Any]] = {}
    with fitz.open(pdf_path) as doc:
        for page_num, page in enumerate(doc, start=1):
            image_map[page_num] = []
            for img_index, img in enumerate(page.get_images(full=True), start=1):
                xref = img[0]
                pix = fitz.Pixmap(doc, xref)
                img_path = img_dir / f"page{page_num}_img{img_index}.png"
                if pix.n < 5:
                    pix.save(str(img_path))
                else:
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                    pix.save(str(img_path))
                image_map[page_num].append(img_path.name)  # 只保存文件名
                image_metadata[img_path.name] = _make_image_meta(img_path.name, page_num=page_num)

    md_lines: List[str] = []
    inserted_images = set()
    image_captions = {} # filename -> caption
    extracted_tables: List[Dict[str, Any]] = []

    for i, el in enumerate(elements):
        cat = getattr(el, "category", None)
        text = (getattr(el, "text", "") or "").strip()
        meta = getattr(el, "metadata", None)
        page_num = getattr(meta, "page_number", None) if meta else None

        if not text and cat != "Image":
            continue

        if cat == "Title" and text.startswith("- "):
            md_lines.append(text + "\n")
        elif cat == "Title":
            md_lines.append(f"# {text}\n")
        elif cat in ["Header", "Subheader"]:
            md_lines.append(f"## {text}\n")
        elif cat == "Table":
            table_caption = _find_caption_near_elements(elements, i, "table", page_num=page_num)
            html = getattr(meta, "text_as_html", None) if meta else None
            if html:
                extracted_tables.extend(
                    _extract_tables_from_html(
                        html,
                        kb_id,
                        file_id,
                        page_num=page_num,
                        start_index=len(extracted_tables),
                        table_name=table_caption,
                    )
                )
                md_lines.append(html2text(html) + "\n")
            else:
                extracted_tables.extend(
                    _extract_tables_from_markdown(
                        text or "",
                        kb_id,
                        file_id,
                        page_num=page_num,
                        start_index=len(extracted_tables),
                        table_name=table_caption,
                    )
                )
                md_lines.append((text or "") + "\n")
        elif cat == "Image" and page_num:
            # 改进：每个 Image 元素只消耗一张图片，避免多图连排时第一张图吞掉所有图片
            # 查找当前页未插入的第一张图片
            target_img = None
            for name in image_map.get(page_num, []):
                if (page_num, name) not in inserted_images:
                    target_img = name
                    break
            
            if target_img:
                original_img_name = target_img
                original_meta = image_metadata.pop(original_img_name, _make_image_meta(original_img_name, page_num=page_num))
                caption = _resolve_element_image_title(elements, i, page_num=page_num, image_path=img_dir / target_img)
                if caption:
                    target_img = _rename_file_with_caption(img_dir, target_img, caption)
                    md_lines.append(f"![Image: {caption}](./images/{target_img})\n")
                    md_lines.append(f"*{caption}*\n")
                    image_captions[target_img] = caption
                else:
                    md_lines.append(f"![Image](./images/{target_img})\n")
                image_metadata[target_img] = _make_image_meta(
                    target_img,
                    page_num=original_meta.get("page_num") or page_num,
                    caption=caption,
                    original_name=original_meta.get("original_name") or original_img_name,
                )
                inserted_images.add((page_num, original_img_name))
        else:
            md_lines.append(text + "\n")

    out_md.write_text("\n".join(md_lines), encoding="utf-8")
    
    # 保存提取到的图片标题映射
    caption_path = workdir(kb_id, file_id) / "image_captions.json"
    caption_path.write_text(json.dumps(image_captions, ensure_ascii=False, indent=2), encoding="utf-8")
    _save_image_metadata(kb_id, file_id, image_metadata)
    _save_pdf_tables(kb_id, file_id, extracted_tables)
    
    return {"markdown": out_md.name, "images_dir": "images", "tables": len(extracted_tables)}

def encode_image(image_path):
    """Getting the base64 string"""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")

def summarize_images(kb_id: str, file_id: str):
    """对提取的图片进行摘要"""
    img_dir = images_dir(kb_id, file_id)
    if not img_dir.exists():
        return []
    
    summary_path = workdir(kb_id, file_id) / "image_summaries.json"
    
    # 加载图片标题映射
    caption_map = {}
    caption_file = workdir(kb_id, file_id) / "image_captions.json"
    if caption_file.exists():
        try:
            caption_map = json.loads(caption_file.read_text(encoding="utf-8"))
        except:
            pass
    image_metadata = _load_image_metadata(kb_id, file_id)
    _repair_mineru_image_pages(kb_id, file_id, image_metadata)
    
    summaries = []
    # 使用 llava:7b 进行图片理解
    print(f"Start summarizing images for {file_id} using {VISION_MODEL_NAME} ({OLLAMA_BASE_URL})...")
    try:
        chat = ChatOllama(model=VISION_MODEL_NAME, temperature=0, base_url=OLLAMA_BASE_URL)
    except Exception as e:
        print(f"Failed to load {VISION_MODEL_NAME}: {e}")
        return []
    
    images = sorted(list(img_dir.glob("*.png")))
    
    # 定义单个图片处理函数
    def process_single_image(img_path):
        try:
            b64_img = encode_image(img_path)
            name = img_path.name
            meta = image_metadata.get(name, {})
            page_num = _resolve_image_page_num(image_metadata, name)
            
            caption = meta.get("caption") or caption_map.get(name, "")
            # 提示词为中文，要求生成中文描述
            prompt = "请详细描述这张图片的内容，重点关注图片中的文字、图表结构和关键信息，以便于后续的检索。"
            "请直接输出描述内容，不要包含'这张图片展示了'等废话,并且严格要求用中文。"
            if caption:
                prompt += f" 该图片的标题是: '{caption}'。请结合标题对图片进行描述。"

            # 每个线程独立实例化一个 ChatOllama 对象，避免潜在的并发冲突
            local_chat = ChatOllama(model=VISION_MODEL_NAME, temperature=0, base_url=OLLAMA_BASE_URL)
            msg = local_chat.invoke([
                HumanMessage(
                    content=[
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}},
                    ]
                )
            ])
            print(f"Summarized {name}")
            
            # 将标题强制拼接到摘要前，确保检索时能匹配到
            final_summary = msg.content
            if caption:
                final_summary = f"Caption: {caption}\nDescription: {final_summary}"

            return {
                "img_name": name,
                "summary": final_summary,
                "page_num": page_num
            }
        except Exception as e:
            print(f"Error summarizing {img_path.name}: {e}")
            return None

    # 使用 ThreadPoolExecutor 并发处理
    import concurrent.futures
    # 根据机器性能调整 max_workers，Ollama 并发能力取决于显存
    max_workers = 3 
    print(f"Processing {len(images)} images with {max_workers} workers...")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(process_single_image, images))
    
    # 过滤失败的结果
    summaries = [r for r in results if r is not None]
            
    summary_path.write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")
    return summaries

def get_image_summaries(kb_id: str, file_id: str) -> List[Dict[str, Any]]:
    """获取图片摘要列表"""
    summary_path = workdir(kb_id, file_id) / "image_summaries.json"
    if summary_path.exists():
        try:
            summaries = json.loads(summary_path.read_text(encoding="utf-8"))
            image_metadata = _load_image_metadata(kb_id, file_id)
            _repair_mineru_image_pages(kb_id, file_id, image_metadata)
            changed = False
            for item in summaries:
                name = item.get("img_name", "")
                meta = image_metadata.get(name, {})
                fixed_page = _resolve_image_page_num(image_metadata, name)
                try:
                    current_page = int(item.get("page_num") or 0)
                except Exception:
                    current_page = 0
                if current_page != fixed_page:
                    item["page_num"] = fixed_page
                    changed = True
                item["source_page_num"] = fixed_page
                if meta:
                    item["original_img_name"] = meta.get("original_name") or name
            if changed:
                summary_path.write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")
            return summaries
        except:
            pass
    
    # Fallback: 如果没有摘要文件，构建基础列表
    img_dir = images_dir(kb_id, file_id)
    if not img_dir.exists():
        return []
    
    # 尝试加载 Captions
    caption_map = {}
    caption_file = workdir(kb_id, file_id) / "image_captions.json"
    if caption_file.exists():
        try:
            caption_map = json.loads(caption_file.read_text(encoding="utf-8"))
        except:
            pass
    image_metadata = _load_image_metadata(kb_id, file_id)
    _repair_mineru_image_pages(kb_id, file_id, image_metadata)

    fallback_list = []
    for img_file in sorted(img_dir.glob("*.png")):
        name = img_file.name
        meta = image_metadata.get(name, {})
        p_num = _resolve_image_page_num(image_metadata, name)
        
        caption = meta.get("caption") or caption_map.get(name, "")
        fallback_list.append({
            "img_name": name,
            "summary": caption or "(未生成详细摘要)",
            "page_num": p_num,
            "source_page_num": p_num,
            "original_img_name": meta.get("original_name") or name,
        })
    
    return fallback_list

def save_image_summaries(kb_id: str, file_id: str, summaries: List[Dict[str, Any]]) -> bool:
    """保存图片摘要列表"""
    summary_path = workdir(kb_id, file_id) / "image_summaries.json"
    try:
        summary_path.write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception as e:
        print(f"Failed to save summaries: {e}")
        return False

def _caption_file_path(kb_id: str, file_id: str) -> Path:
    return workdir(kb_id, file_id) / "image_captions.json"

def _load_image_captions(kb_id: str, file_id: str) -> Dict[str, str]:
    path = _caption_file_path(kb_id, file_id)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def _save_image_captions(kb_id: str, file_id: str, captions: Dict[str, str]) -> None:
    _caption_file_path(kb_id, file_id).write_text(
        json.dumps(captions, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

def _normalize_user_image_filename(raw_name: str, current_name: str = "") -> str:
    """Normalize a user edited image filename while keeping it inside images/."""
    name = str(raw_name or "").strip()
    if not name:
        raise ValueError("图片文件名不能为空")
    if "/" in name or "\\" in name:
        raise ValueError("图片文件名不能包含路径分隔符")

    current_suffix = Path(current_name or "").suffix
    suffix = Path(name).suffix or current_suffix or ".png"
    if not suffix.startswith("."):
        suffix = f".{suffix}"
    suffix = suffix.lower()
    allowed_suffixes = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
    if suffix not in allowed_suffixes:
        raise ValueError(f"不支持的图片扩展名: {suffix}")

    stem = Path(name).stem if Path(name).suffix else name
    safe_stem = sanitize_filename(stem)
    if not safe_stem:
        raise ValueError("图片文件名不能为空")
    return f"{safe_stem}{suffix}"

def _rewrite_markdown_image_refs(
    kb_id: str,
    file_id: str,
    renamed: Dict[str, str],
    deleted: set,
) -> None:
    md_path = markdown_output(kb_id, file_id)
    if not md_path.exists() or (not renamed and not deleted):
        return

    text = md_path.read_text(encoding="utf-8")

    def replace_match(match):
        alt_text = match.group(1)
        prefix = match.group(2)
        raw_path = match.group(3).strip()
        suffix = match.group(4)
        image_name = Path(unquote(raw_path)).name
        if image_name in deleted:
            return ""
        if image_name in renamed:
            return f"![{alt_text}]({prefix}{renamed[image_name]}{suffix})"
        return match.group(0)

    pattern = re.compile(r"!\[([^\]]*)\]\((\./images/|images/)([^)#?]+)([^)]*)\)")
    updated = pattern.sub(replace_match, text)
    if updated != text:
        md_path.write_text(updated, encoding="utf-8")

def apply_image_manifest_update(kb_id: str, file_id: str, summaries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Apply frontend image edits: delete omitted images, rename files, and save summaries."""
    if not isinstance(summaries, list):
        raise ValueError("summaries 必须是列表")

    current_summaries = get_image_summaries(kb_id, file_id)
    current_by_name = {
        str(item.get("img_name") or ""): item
        for item in current_summaries
        if item.get("img_name")
    }
    current_names = set(current_by_name.keys())

    normalized_rows: List[Dict[str, Any]] = []
    desired_names = set()
    kept_old_names = set()

    for item in summaries:
        if not isinstance(item, dict):
            raise ValueError("图片记录格式不正确")

        old_name = str(
            item.get("old_img_name")
            or item.get("base_img_path")
            or item.get("img_name")
            or ""
        ).strip()
        if not old_name:
            raise ValueError("缺少原始图片文件名")
        if old_name not in current_by_name:
            raise ValueError(f"未找到图片记录: {old_name}")

        new_name = _normalize_user_image_filename(item.get("img_name") or old_name, old_name)
        if new_name in desired_names:
            raise ValueError(f"图片文件名重复: {new_name}")

        desired_names.add(new_name)
        kept_old_names.add(old_name)
        normalized_rows.append({"old_name": old_name, "new_name": new_name, "item": item})

    deleted_names = current_names - kept_old_names
    rename_map = {
        row["old_name"]: row["new_name"]
        for row in normalized_rows
        if row["old_name"] != row["new_name"]
    }

    img_dir = images_dir(kb_id, file_id).resolve()
    existing_targets = set()
    for row in normalized_rows:
        old_name = row["old_name"]
        new_name = row["new_name"]
        new_path = (img_dir / new_name).resolve()
        try:
            new_path.relative_to(img_dir)
        except ValueError:
            raise ValueError(f"无效的图片文件名: {new_name}")
        if new_path.exists() and new_name != old_name and new_name not in rename_map:
            raise ValueError(f"图片文件名已存在: {new_name}")
        existing_targets.add(new_name)

    temp_map: Dict[str, Path] = {}
    for idx, (old_name, new_name) in enumerate(rename_map.items()):
        old_path = (img_dir / old_name).resolve()
        if not old_path.exists():
            raise FileNotFoundError(f"图片文件不存在: {old_name}")
        tmp_path = img_dir / f".rename_tmp_{int(time.time() * 1000)}_{idx}{old_path.suffix}"
        old_path.rename(tmp_path)
        temp_map[old_name] = tmp_path

    try:
        for old_name, tmp_path in temp_map.items():
            new_name = rename_map[old_name]
            new_path = img_dir / new_name
            if new_path.exists():
                raise ValueError(f"图片文件名已存在: {new_name}")
            tmp_path.rename(new_path)
    except Exception:
        for old_name, tmp_path in temp_map.items():
            if tmp_path.exists():
                tmp_path.rename(img_dir / old_name)
        raise

    deleted_count = 0
    for old_name in deleted_names:
        old_path = (img_dir / old_name).resolve()
        try:
            old_path.relative_to(img_dir)
        except ValueError:
            continue
        if old_path.exists():
            old_path.unlink()
            deleted_count += 1

    image_metadata = _load_image_metadata(kb_id, file_id)
    image_captions = _load_image_captions(kb_id, file_id)

    for old_name in deleted_names:
        image_metadata.pop(old_name, None)
        image_captions.pop(old_name, None)

    clean_summaries: List[Dict[str, Any]] = []
    for row in normalized_rows:
        old_name = row["old_name"]
        new_name = row["new_name"]
        item = row["item"]
        original = current_by_name[old_name]

        meta = image_metadata.pop(old_name, None) or {}
        caption = image_captions.pop(old_name, meta.get("caption", ""))
        if caption:
            image_captions[new_name] = caption

        try:
            page_num = int(item.get("page_num") or item.get("source_page_num") or original.get("page_num") or 0)
        except Exception:
            page_num = 0
        if page_num <= 0:
            page_num = _resolve_image_page_num(image_metadata, new_name)

        meta.update(
            {
                "img_name": new_name,
                "page_num": page_num,
                "caption": meta.get("caption") or caption,
                "original_name": meta.get("original_name") or original.get("original_img_name") or old_name,
            }
        )
        image_metadata[new_name] = meta

        clean_item = {
            "img_name": new_name,
            "summary": str(item.get("summary") if item.get("summary") is not None else original.get("summary", "")),
            "page_num": page_num,
            "source_page_num": page_num,
            "original_img_name": meta.get("original_name") or old_name,
        }
        if item.get("bbox") is not None:
            clean_item["bbox"] = item.get("bbox")
        elif original.get("bbox") is not None:
            clean_item["bbox"] = original.get("bbox")
        clean_summaries.append(clean_item)

    _save_image_metadata(kb_id, file_id, image_metadata)
    _save_image_captions(kb_id, file_id, image_captions)
    if not save_image_summaries(kb_id, file_id, clean_summaries):
        raise RuntimeError("保存图片摘要失败")
    _rewrite_markdown_image_refs(kb_id, file_id, rename_map, deleted_names)

    return {
        "updated": len(clean_summaries),
        "renamed": len(rename_map),
        "deleted": deleted_count,
    }

def _olmocr_page(img_path: Path) -> str:
    """调用 olmocr 模型解析单页图片"""
    def to_data_uri(p: Path) -> str:
        with open(p, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        return f"data:image/png;base64,{b64}"

    content = [
        {
            "type": "text",
            "text": OLMOCR_PROMPT,
        },
        {
            "type": "image_url",
            "image_url": {
                "url": to_data_uri(img_path),
                "detail": "auto"
            },
        },
    ]

    payload = {
        "model": OLMOCR_MODEL,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.2,
        "max_tokens": OLMOCR_MAX_TOKENS,
    }

    try:
        r = _post_olmocr(payload)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"Error in olmocr for {img_path}: {e}")
        return f"\n\n<!-- OCR ERROR: {e} -->\n\n"

def pdf_to_markdown_olmocr(kb_id: str, file_id: str):
    """使用 olmocr 模型将 PDF 转换为 Markdown"""
    # 1. 确保图片已提取 (用于 summarize_images)
    pdf_path = str(original_pdf_path(kb_id, file_id))
    img_dir = _reset_extracted_images(kb_id, file_id)
    image_metadata: Dict[str, Dict[str, Any]] = {}
    
    # 复用 fitz 提取图片逻辑，确保 images 目录下有图片
    with fitz.open(pdf_path) as doc:
        for page_num, page in enumerate(doc, start=1):
            for img_index, img in enumerate(page.get_images(full=True), start=1):
                xref = img[0]
                img_path = img_dir / f"page{page_num}_img{img_index}.png"
                if not img_path.exists(): # 避免重复提取
                    pix = fitz.Pixmap(doc, xref)
                    if pix.n < 5:
                        pix.save(str(img_path))
                    else:
                        pix = fitz.Pixmap(fitz.csRGB, pix)
                        pix.save(str(img_path))
                image_metadata[img_path.name] = _make_image_meta(img_path.name, page_num=page_num)

    # 2. 遍历 pages/original 下的页面图片进行 OCR
    # 页面图片已在 run_full_parse_pipeline 中通过 render_original_pages 生成，此处无需重复渲染
    page_dir = dir_original_pages(kb_id, file_id)
    pages = sorted(list(page_dir.glob("page-*.png")))
    
    md_pages = []
    image_captions = {} # filename -> caption
    print(f"Starting olmocr parse for {file_id}, {len(pages)} pages...")

    # 获取所有图片并按 PyMuPDF 提取时记录的所在页分组；不再从改名后的文件名反推页码。
    page_images_map = {}
    for img_name, meta in image_metadata.items():
        p_num = int(meta.get("page_num") or 0)
        if p_num > 0:
            page_images_map.setdefault(p_num, []).append(img_name)

    # 简单串行
    for i, p in enumerate(pages, start=1):
        print(f"OCR processing {p.name}...")
        content = _olmocr_page(p)
        md_pages.append(content)

        # 尝试从 content 中提取图片标题
        # 简单的启发式：查找以 "图" 或 "Figure" 开头的行
        # 这里的 i 对应页码 (假设 pages 是按顺序 page-0001.png ...)
        current_page_imgs = sorted(page_images_map.get(i, []))
        
        if current_page_imgs:
            captions = _figure_caption_candidates_from_text(content)
            
            # 简单的 1对1 映射或顺序映射
            # 如果只有一个图片，取第一个找到的标题
            if len(current_page_imgs) == 1 and captions:
                image_captions[current_page_imgs[0]] = _normalize_image_title(captions[0])
            # 如果有多个图片和多个标题，按顺序尝试映射
            elif len(current_page_imgs) > 1 and len(captions) > 0:
                for img_idx, img_name in enumerate(current_page_imgs):
                    if img_idx < len(captions):
                        image_captions[img_name] = _normalize_image_title(captions[img_idx])
        
    # 补充处理：如果图片和图名跨页，继续从当前页及后续页查找“图...”标题。
    page_caption_map = {
        page_no: _figure_captions_from_text(content)
        for page_no, content in enumerate(md_pages, start=1)
    }
    used_caption_keys = set()
    for page_no in sorted(page_images_map.keys()):
        for img_name in sorted(page_images_map.get(page_no, [])):
            if img_name in image_captions:
                continue
            found_caption = ""
            for search_page in range(page_no, len(md_pages) + 1):
                for cap_idx, cap in enumerate(page_caption_map.get(search_page, [])):
                    cap_key = (search_page, cap_idx)
                    if cap_key in used_caption_keys:
                        continue
                    found_caption = cap
                    used_caption_keys.add(cap_key)
                    break
                if found_caption:
                    break
            if found_caption:
                image_captions[img_name] = _normalize_image_title(found_caption)

    for page_no in sorted(page_images_map.keys()):
        for img_name in sorted(page_images_map.get(page_no, [])):
            if img_name in image_captions:
                image_captions[img_name] = _normalize_image_title(image_captions[img_name])
                continue
            title = _vision_image_title(img_dir / img_name)
            if title:
                image_captions[img_name] = title

    full_md = "\n\n\\pagebreak\n\n".join(md_pages)
    
    out_md = markdown_output(kb_id, file_id)
    out_md.write_text(full_md, encoding="utf-8")

    extracted_tables = []
    for page_num, content in enumerate(md_pages, start=1):
        extracted_tables.extend(
            _extract_tables_from_html(
                content,
                kb_id,
                file_id,
                page_num=page_num,
                start_index=len(extracted_tables),
            )
        )
        extracted_tables.extend(
            _extract_tables_from_markdown(
                content,
                kb_id,
                file_id,
                page_num=page_num,
                start_index=len(extracted_tables),
            )
        )

    # 重命名图片文件以匹配提取到的标题
    final_captions = {}
    for img_name, caption in image_captions.items():
        original_meta = image_metadata.pop(img_name, _make_image_meta(img_name))
        new_img_name = _rename_file_with_caption(img_dir, img_name, caption)
        final_captions[new_img_name] = caption
        image_metadata[new_img_name] = _make_image_meta(
            new_img_name,
            page_num=original_meta.get("page_num") or _image_page_num_from_name(img_name),
            caption=caption,
            original_name=original_meta.get("original_name") or img_name,
        )
            
    image_captions = final_captions

    # 保存提取到的图片标题映射
    caption_path = workdir(kb_id, file_id) / "image_captions.json"
    caption_path.write_text(json.dumps(image_captions, ensure_ascii=False, indent=2), encoding="utf-8")
    _save_image_metadata(kb_id, file_id, image_metadata)
    _save_pdf_tables(kb_id, file_id, extracted_tables)
    
    return {"markdown": out_md.name, "images_dir": "images", "tables": len(extracted_tables)}

def pdf_to_markdown_mineru(kb_id: str, file_id: str):
    """调用外部 MinerU CLI 解析 PDF，并收集 Markdown、图片与表格结果。"""
    file_wd = workdir(kb_id, file_id).resolve()
    source_path = original_pdf_path(kb_id, file_id)
    pdf_path = _convert_office_to_pdf(source_path)
    img_dir = _reset_extracted_images(kb_id, file_id).resolve()

    try:
        pdf_path = pdf_path.resolve()
    except Exception:
        pdf_path = pdf_path

    if not pdf_path.exists():
        raise RuntimeError(f"MinerU 无法找到输入文件: {pdf_path}")

    caption_direction = "below"

    mineru_out_dir = file_wd / "mineru"
    if mineru_out_dir.exists():
        shutil.rmtree(mineru_out_dir, ignore_errors=True)
    mineru_out_dir.mkdir(parents=True, exist_ok=True)

    cmd = shlex.split(MINERU_CMD) + ["-p", str(pdf_path), "-o", str(mineru_out_dir)]
    if MINERU_BACKEND:
        cmd.extend(["-b", MINERU_BACKEND])
    if MINERU_METHOD:
        cmd.extend(["-m", MINERU_METHOD])
    if MINERU_LANG:
        cmd.extend(["-l", MINERU_LANG])
    if MINERU_EXTRA_ARGS:
        cmd.extend(shlex.split(MINERU_EXTRA_ARGS))

    if "/envs/mul_rag/" in str(cmd[0]):
        raise RuntimeError(
            f"MINERU_CMD 当前指向主项目环境：{cmd[0]}。"
            "请创建独立 mineru 环境，并设置 "
            "MINERU_CMD=/home/lrn/anaconda3/envs/mineru/bin/mineru"
        )

    env = os.environ.copy()
    for proxy_key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        env.pop(proxy_key, None)
    env.setdefault("NO_PROXY", "127.0.0.1,localhost,::1")
    env.setdefault("no_proxy", "127.0.0.1,localhost,::1")
    if MINERU_MODEL_SOURCE:
        env["MINERU_MODEL_SOURCE"] = MINERU_MODEL_SOURCE

    print(f"Starting MinerU parse for {file_id}: {' '.join(cmd)}")
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(file_wd),
            env=env,
            text=True,
            capture_output=True,
            timeout=MINERU_TIMEOUT,
        )
    except FileNotFoundError as e:
        raise RuntimeError(
            "未找到 MinerU 命令。请安装独立 MinerU 环境，并设置 "
            "MINERU_CMD，例如：MINERU_CMD='/home/lrn/anaconda3/envs/mineru/bin/mineru'"
        ) from e

    if proc.stdout:
        print(proc.stdout)
    if proc.stderr:
        print(proc.stderr)
    if proc.returncode != 0:
        raise RuntimeError(f"MinerU 解析失败，退出码 {proc.returncode}: {proc.stderr[-2000:]}")

    collected = _collect_mineru_outputs(
        kb_id,
        file_id,
        mineru_out_dir,
        img_dir,
        caption_direction=caption_direction,
    )

    md_pages = []
    md_files = sorted(mineru_out_dir.rglob("*.md"))
    for md_file in md_files:
        try:
            md_pages.append(md_file.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            md_pages.append(md_file.read_text(encoding="utf-8", errors="ignore"))

    if md_pages:
        _collect_mineru_markdown_images(
            md_pages,
            md_files,
            mineru_out_dir,
            img_dir,
            collected,
            caption_direction=caption_direction,
        )
        md_pages = [
            _rewrite_mineru_markdown_image_links(content, collected["image_asset_map"])
            for content in md_pages
        ]
    elif collected["markdown"]:
        md_pages = [collected["markdown"]]
    else:
        raise RuntimeError(f"MinerU 未生成 Markdown 或 content_list 输出，输出目录：{mineru_out_dir}")

    full_md = "\n\n\\pagebreak\n\n".join(md_pages)
    out_md = markdown_output(kb_id, file_id)
    out_md.write_text(full_md, encoding="utf-8")

    extracted_tables = list(collected["tables"])
    if not extracted_tables:
        for page_num, content in enumerate(md_pages, start=1):
            extracted_tables.extend(
                _extract_tables_from_html(
                    content,
                    kb_id,
                    file_id,
                    page_num=page_num,
                    start_index=len(extracted_tables),
                )
            )
            extracted_tables.extend(
                _extract_tables_from_markdown(
                    content,
                    kb_id,
                    file_id,
                    page_num=page_num,
                    start_index=len(extracted_tables),
                )
            )

    caption_path = workdir(kb_id, file_id) / "image_captions.json"
    caption_path.write_text(
        json.dumps(collected["image_captions"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _save_image_metadata(kb_id, file_id, collected["image_metadata"])
    _save_pdf_tables(kb_id, file_id, extracted_tables)
    return {"markdown": out_md.name, "images_dir": "images", "tables": len(extracted_tables)}

def run_full_parse_pipeline(kb_id: str, file_id: str, method: str = "original", progress_callback=None) -> Dict[str, Any]:
    """
    完整流程：原始页图渲染 → 解析 (original/olmocr/mineru) → 输出 Markdown
    返回用于 /status 的统计或元信息
    """
    method_key = (method or "original").strip().lower().replace("-", "_")
    if method_key in {"magic_pdf", "magicpdf", "mineru_pdf"}:
        method_key = "mineru"
    if method_key not in {"original", "olmocr", "mineru"}:
        raise ValueError(f"Unsupported parse method: {method}")

    source_path = original_pdf_path(kb_id, file_id)
    original_source_suffix = source_path.suffix.lower()
    source_suffix = source_path.suffix.lower()
    if source_suffix in {".doc", ".docx"} and method_key != "mineru":
        print(f"[parse] Word document detected, switching method {method_key} -> mineru")
        method_key = "mineru"

    if progress_callback: progress_callback(25)
    if source_suffix == ".pdf":
        render_target = OLMOCR_TARGET_LONGEST_IMAGE_DIM if method_key == "olmocr" else None
        render_original_pages(kb_id, file_id, target_longest_dim=render_target)
    
    if progress_callback: progress_callback(40)
    
    if method_key == "olmocr":
        md_info = pdf_to_markdown_olmocr(kb_id, file_id)
        # olmocr 模式下，unstructured_segments 和 render_parsed_pages_with_boxes 可能不需要，或者无法对应
        # 但为了保持一致性，如果需要叠框图，需要坐标信息，olmocr 不返回坐标。
        # 所以跳过 render_parsed_pages_with_boxes
    elif method_key == "mineru":
        md_info = pdf_to_markdown_mineru(kb_id, file_id)
    else:
        docs = unstructured_segments(kb_id, file_id)
        if progress_callback: progress_callback(60)
        render_parsed_pages_with_boxes(kb_id, file_id, docs)
        md_info = pdf_to_markdown(kb_id, file_id)

    write_parse_metadata(
        kb_id,
        file_id,
        {
            "parseMethod": method_key,
            "sourceType": original_source_suffix.lstrip(".") or "unknown",
            "normalizedSourceType": source_suffix.lstrip(".") or "unknown",
            "parser": "MinerU" if method_key == "mineru" else ("OLMOCR" if method_key == "olmocr" else "Unstructured"),
        },
    )
    
    if progress_callback: progress_callback(80)
    
    # 新增：生成图片摘要 (两种模式都支持，只要 images 目录下有图片)
    summarize_images(kb_id, file_id)
    
    if progress_callback: progress_callback(95)
    
    # 获取所有提取的图片列表
    images_list = []
    img_dir = images_dir(kb_id, file_id)
    if img_dir.exists():
        images_list = [f.name for f in img_dir.glob("*.png")]
        
    return {"md": md_info["markdown"], "images": images_list}

def delete_workdir(kb_id: str, file_id: str) -> bool:
    """删除某知识库下某文件的工作目录"""
    import shutil
    # 直接构造路径，避免调用 workdir() 产生创建目录的副作用
    d = kb_files_dir(kb_id) / file_id
    if d.exists():
        try:
            shutil.rmtree(d)
            return True
        except Exception as e:
            print(f"Error deleting workdir {d}: {e}")
            return False
    return True
