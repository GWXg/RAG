from __future__ import annotations

import hashlib
import json
import math
import re
import time
from copy import deepcopy
from difflib import SequenceMatcher, get_close_matches
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd


DEFAULT_PREPROCESS_CONFIG: Dict[str, Any] = {
    "standardVersion": "1.0",
    "datasetType": "generic_tabular",
    "headerDetection": True,
    "concatSheets": True,
    "addProvenanceColumns": True,
    "keepExtraColumns": True,
    "missingValues": ["", " ", "NA", "N/A", "null", "NULL", "None", "nan", "NaN", "--", "-", "/"],
    "dedupe": {"enabled": True, "subset": [], "keep": "first"},
    "textNormalization": {"strip": True, "collapseWhitespace": True},
    "columnSpecs": {},
}

PREPROCESS_METHODS: List[Dict[str, Any]] = [
    {
        "id": "format_standardize",
        "name": "格式标准化",
        "description": "统一表头、空值标记、空白字符和基础类型。",
        "defaultAlgorithm": "regex_rules",
        "algorithms": [
            {"id": "regex_rules", "name": "正则表达式", "description": "按现有规则统一表头、空白、空值与基础类型。"},
            {"id": "header_mapping", "name": "表头映射与字段归一", "description": "清理并映射字段名称，保留原始数据类型。"},
            {"id": "datetime_normalize", "name": "时间格式统一", "description": "识别日期时间字段并统一为标准时间类型。"},
        ],
    },
    {
        "id": "las_to_excel",
        "name": "测井曲线转表格",
        "description": "解析测井曲线、井信息和空值标记，并输出标准表格文件。",
        "defaultAlgorithm": "lasio_parse",
        "algorithms": [
            {"id": "lasio_parse", "name": "LAS 读写解析", "description": "解析 LAS 井信息、曲线和空值标记。"},
            {"id": "welly_align", "name": "曲线管理与深度对齐", "description": "按深度索引对齐多条测井曲线。"},
            {"id": "depth_resample", "name": "深度等距重采样", "description": "按统一深度间隔重采样曲线数据。"},
        ],
    },
    {
        "id": "dedupe",
        "name": "冗余数据剔除",
        "description": "剔除空行和重复记录，减少重复入库内容。",
        "defaultAlgorithm": "exact_duplicate",
        "algorithms": [
            {"id": "exact_duplicate", "name": "完全重复删除", "description": "删除完全一致的重复记录和空行。"},
            {"id": "minhash_approx", "name": "MinHash 近似去重", "description": "按文本分片签名识别近似重复记录。"},
            {"id": "record_linkage", "name": "记录链接去重", "description": "按归一化记录相似度合并重复项。"},
        ],
    },
    {
        "id": "missing_fill",
        "name": "缺失补全",
        "description": "按列类型使用中位数、众数或空串补全缺失值。",
        "defaultAlgorithm": "statistical_fill",
        "algorithms": [
            {"id": "statistical_fill", "name": "统计量填充", "description": "数值列用中位数，文本列用众数补全。"},
            {"id": "linear_interpolation", "name": "线性插值", "description": "按记录顺序对数值缺口执行线性插值。"},
            {"id": "knn_imputation", "name": "KNN 插补", "description": "利用相似样本的邻域信息补全数值缺失。"},
        ],
    },
    {
        "id": "anomaly_correct",
        "name": "异常纠错",
        "description": "对数值列按 IQR 范围自动裁剪异常值。",
        "defaultAlgorithm": "iqr",
        "algorithms": [
            {"id": "iqr", "name": "箱线图 IQR", "description": "按四分位距识别并裁剪异常值。"},
            {"id": "three_sigma", "name": "3σ 拉依达法则", "description": "按均值正负三倍标准差识别异常值。"},
            {"id": "mad", "name": "MAD 中位数绝对偏差", "description": "使用稳健统计量识别尖峰和离群点。"},
        ],
    },
    {
        "id": "unit_dimension_check",
        "name": "单位统一与量纲校验",
        "description": "识别井深、钻压、扭矩、流量、温度、压力等字段的常见单位并统一量纲。",
        "defaultAlgorithm": "combined_unit_rules",
        "algorithms": [
            {"id": "combined_unit_rules", "name": "组合单位规则", "description": "综合列名、单位列和值内单位完成换算。"},
            {"id": "label_unit_mapping", "name": "表头单位映射", "description": "根据字段名中的单位标记执行换算。"},
            {"id": "cell_unit_parsing", "name": "单元格单位解析", "description": "解析数值后的单位文本并统一量纲。"},
        ],
    },
    {
        "id": "engineering_constraint_check",
        "name": "工程范围/物理约束校验",
        "description": "校验钻压、转速、泵压、井深、流量、温度、钩载等字段的工程合理范围。",
        "defaultAlgorithm": "boundary_clip",
        "algorithms": [
            {"id": "boundary_clip", "name": "工程边界裁剪", "description": "将越界值裁剪到工程允许范围。"},
            {"id": "invalid_to_missing", "name": "越界值置空", "description": "将违反工程约束的数值标记为缺失。"},
            {"id": "constraint_flag", "name": "物理约束标记", "description": "保留原值并新增约束校验结果列。"},
        ],
    },
    {
        "id": "schema_standardize",
        "name": "维度标准统一",
        "description": "统一列名格式并补齐多表之间的字段维度。",
        "defaultAlgorithm": "schema_mapping",
        "algorithms": [
            {"id": "schema_mapping", "name": "字段维度统一", "description": "统一字段命名与输出结构。"},
            {"id": "min_max", "name": "Min-Max 归一化", "description": "将数值字段缩放到 0 到 1 区间。"},
            {"id": "z_score", "name": "Z-Score 标准化", "description": "按均值和标准差标准化数值字段。"},
        ],
    },
]

METHOD_NAME_BY_ID = {item["id"]: item["name"] for item in PREPROCESS_METHODS}
METHOD_BY_ID = {item["id"]: item for item in PREPROCESS_METHODS}


def get_preprocessed_output(kb_id: str, file_id: str) -> Path:
    from services.index_service import file_workdir

    return file_workdir(kb_id, file_id) / "preprocessed" / "standardized.csv"


def get_preprocess_report_path(kb_id: str, file_id: str) -> Path:
    from services.index_service import file_workdir

    return file_workdir(kb_id, file_id) / "preprocessed" / "report.json"


def preprocess_tabular_file(
    file_path: str | Path,
    output_dir: str | Path,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Preprocess CSV/Excel/JSON into a standardized CSV plus an audit report."""
    started_at = time.time()
    source = Path(file_path)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg = _merge_config(DEFAULT_PREPROCESS_CONFIG, config or {})
    report = _new_report(source, cfg)

    frames = _read_tables(source, cfg, report)
    if not frames:
        raise ValueError(f"No tabular data found in {source}")

    standardized_frames: List[pd.DataFrame] = []
    for sheet_name, df in frames:
        before_rows = len(df)
        df = _normalize_dataframe(df, sheet_name, cfg, report)
        report["sheets"].append({"name": sheet_name, "rowsIn": before_rows, "rowsOut": len(df)})
        standardized_frames.append(df)

    combined = pd.concat(standardized_frames, ignore_index=True, sort=False) if standardized_frames else pd.DataFrame()
    report["rowsIn"] = int(sum(item["rowsIn"] for item in report["sheets"]))
    report["columnsIn"] = sorted({col for _, frame in frames for col in map(str, frame.columns)})

    combined = _drop_empty_rows(combined, report)
    combined = _deduplicate_rows(combined, cfg, report)
    combined = _order_columns(combined, cfg)

    output_path = out_dir / "standardized.csv"
    report_path = out_dir / "report.json"
    combined.to_csv(output_path, index=False, encoding="utf-8-sig")

    report["ok"] = True
    report["rowsOut"] = int(len(combined))
    report["columnsOut"] = [str(col) for col in combined.columns]
    report["outputPath"] = str(output_path)
    report["reportPath"] = str(report_path)
    report["elapsedSeconds"] = round(time.time() - started_at, 3)

    report_path.write_text(json.dumps(_json_safe(report), ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def run_selected_preprocess_methods(
    file_path: str | Path,
    output_dir: str | Path,
    methods: List[str],
    algorithm_selections: Optional[Dict[str, str]] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run a visible, ordered preprocessing pipeline selected by the user."""
    started_at = time.time()
    source = Path(file_path)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg = _merge_config(DEFAULT_PREPROCESS_CONFIG, config or {})
    selected_methods = _dedupe_methods(methods)
    if not selected_methods:
        raise ValueError("At least one preprocessing method is required.")

    report = _new_report(source, cfg)
    report["selectedMethods"] = selected_methods
    selected_algorithms = _normalize_algorithm_selections(selected_methods, algorithm_selections or {})
    report["algorithmSelections"] = selected_algorithms
    report["methodReports"] = []

    frames = _read_tables(source, cfg, report)
    if not frames:
        raise ValueError(f"No tabular data found in {source}")

    standardized_frames: List[pd.DataFrame] = []
    for sheet_name, df in frames:
        before_rows = len(df)
        normalized = _normalize_dataframe(df, sheet_name, cfg, report)
        report["sheets"].append({"name": sheet_name, "rowsIn": before_rows, "rowsOut": len(normalized)})
        standardized_frames.append(normalized)

    combined = pd.concat(standardized_frames, ignore_index=True, sort=False) if standardized_frames else pd.DataFrame()
    report["rowsIn"] = int(sum(item["rowsIn"] for item in report["sheets"]))
    report["columnsIn"] = sorted({col for _, frame in frames for col in map(str, frame.columns)})

    for method in selected_methods:
        algorithm_id = selected_algorithms[method]
        algorithm_name = _algorithm_name(method, algorithm_id)
        before_rows = len(combined)
        before_cols = list(combined.columns)
        before_missing = int(combined.isna().sum().sum()) if not combined.empty else 0
        combined, method_ops = _apply_selected_method(combined, method, algorithm_id, cfg, report)
        after_missing = int(combined.isna().sum().sum()) if not combined.empty else 0
        report["methodReports"].append(
            {
                "method": method,
                "name": METHOD_NAME_BY_ID.get(method, method),
                "algorithm": algorithm_id,
                "algorithmName": algorithm_name,
                "status": "done",
                "progress": 100,
                "rowsIn": int(before_rows),
                "rowsOut": int(len(combined)),
                "columnsIn": len(before_cols),
                "columnsOut": len(combined.columns),
                "missingBefore": before_missing,
                "missingAfter": after_missing,
                "operations": method_ops,
            }
        )

    combined = _order_columns(combined, cfg)
    output_path = out_dir / "standardized.csv"
    report_path = out_dir / "report.json"
    combined.to_csv(output_path, index=False, encoding="utf-8-sig")

    report["ok"] = True
    report["rowsOut"] = int(len(combined))
    report["columnsOut"] = [str(col) for col in combined.columns]
    report["outputPath"] = str(output_path)
    report["reportPath"] = str(report_path)
    report["elapsedSeconds"] = round(time.time() - started_at, 3)

    report_path.write_text(json.dumps(_json_safe(report), ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _new_report(source: Path, config: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "ok": False,
        "inputPath": str(source),
        "standardVersion": config.get("standardVersion", "1.0"),
        "datasetType": config.get("datasetType", "generic_tabular"),
        "rowsIn": 0,
        "rowsOut": 0,
        "columnsIn": [],
        "columnsOut": [],
        "sheets": [],
        "operations": {
            "headersDetected": [],
            "columnsRenamed": {},
            "columnsMerged": {},
            "requiredColumnsAdded": [],
            "duplicateRowsRemoved": 0,
            "duplicateColumnsRenamed": {},
            "emptyRowsRemoved": 0,
            "missingFilled": {},
            "typeCoercions": {},
            "anomaliesCorrected": {},
            "rowsDroppedForAnomalies": 0,
            "unitConversions": {},
            "categoryCorrections": {},
            "dimensionChecks": {},
            "constraintCorrections": {},
            "monotonicCorrections": {},
        },
        "warnings": [],
    }


def _dedupe_methods(methods: Iterable[str]) -> List[str]:
    known = {item["id"] for item in PREPROCESS_METHODS}
    selected: List[str] = []
    seen = set()
    for method in methods or []:
        method_id = str(method or "").strip()
        if method_id in known and method_id not in seen:
            selected.append(method_id)
            seen.add(method_id)
    return selected


def _normalize_algorithm_selections(methods: Iterable[str], selections: Dict[str, str]) -> Dict[str, str]:
    normalized: Dict[str, str] = {}
    for method_id in methods:
        method = METHOD_BY_ID[method_id]
        algorithm_ids = {str(item["id"]) for item in method.get("algorithms", [])}
        requested = str(selections.get(method_id) or "").strip()
        default_algorithm = str(method.get("defaultAlgorithm") or "").strip()
        if requested in algorithm_ids:
            normalized[method_id] = requested
        elif default_algorithm in algorithm_ids:
            normalized[method_id] = default_algorithm
        elif algorithm_ids:
            normalized[method_id] = str(method["algorithms"][0]["id"])
        else:
            normalized[method_id] = "default"
    return normalized


def _algorithm_name(method_id: str, algorithm_id: str) -> str:
    method = METHOD_BY_ID.get(method_id, {})
    for algorithm in method.get("algorithms", []):
        if str(algorithm.get("id")) == algorithm_id:
            return str(algorithm.get("name") or algorithm_id)
    return algorithm_id


def _apply_selected_method(
    df: pd.DataFrame,
    method: str,
    algorithm: str,
    config: Dict[str, Any],
    report: Dict[str, Any],
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    if method == "format_standardize":
        return _method_format_standardize(df, config, algorithm)
    if method == "las_to_excel":
        return _method_las_to_excel(df, report, algorithm)
    if method == "dedupe":
        if algorithm == "minhash_approx":
            return _method_minhash_dedupe(df, report)
        if algorithm == "record_linkage":
            return _method_record_linkage_dedupe(df, report)
        before_empty = report["operations"].get("emptyRowsRemoved", 0)
        before_dup = report["operations"].get("duplicateRowsRemoved", 0)
        out = _drop_empty_rows(df, report)
        out = _deduplicate_rows(out, config, report)
        return out, {
            "emptyRowsRemoved": report["operations"].get("emptyRowsRemoved", 0) - before_empty,
            "duplicateRowsRemoved": report["operations"].get("duplicateRowsRemoved", 0) - before_dup,
        }
    if method == "missing_fill":
        return _method_fill_missing(df, report, algorithm)
    if method == "anomaly_correct":
        return _method_auto_correct_anomalies(df, report, algorithm)
    if method == "unit_dimension_check":
        return _method_unit_dimension_check(df, report, algorithm)
    if method == "engineering_constraint_check":
        return _method_engineering_constraint_check(df, report, algorithm)
    if method == "schema_standardize":
        return _method_schema_standardize(df, report, algorithm)
    report["warnings"].append(f"Unknown preprocessing method ignored: {method}")
    return df, {}


def _method_format_standardize(
    df: pd.DataFrame,
    config: Dict[str, Any],
    algorithm: str = "regex_rules",
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    out = df.copy()
    renamed: Dict[str, str] = {}
    cleaned_columns = []
    for col in out.columns:
        cleaned = _clean_column_name(col)
        cleaned_columns.append(cleaned)
        if cleaned != col:
            renamed[str(col)] = cleaned
    out.columns = cleaned_columns
    out = _normalize_missing_values(out, config)
    out = _normalize_text_cells(out, config)

    if algorithm == "header_mapping":
        return out, {"columnsRenamed": renamed, "mappingMode": "header"}

    converted: Dict[str, str] = {}
    for col in out.columns:
        if str(col).startswith("_source_"):
            continue
        normalized = _normalize_label(col)
        series = out[col]
        is_datetime = any(token in normalized for token in ("time", "date", "日期", "时间"))
        if is_datetime:
            parsed = pd.to_datetime(series, errors="coerce")
            if parsed.notna().sum() >= max(1, int(series.notna().sum() * 0.6)):
                out[col] = parsed
                converted[str(col)] = "datetime"
            continue
        if algorithm != "datetime_normalize" and (series.dtype == object or str(series.dtype).startswith("string")):
            numeric = _to_numeric(series)
            if numeric.notna().sum() >= max(1, int(series.notna().sum() * 0.8)):
                out[col] = numeric
                converted[str(col)] = "number"

    return out, {"columnsRenamed": renamed, "typesInferred": converted}


def _method_las_to_excel(
    df: pd.DataFrame,
    report: Dict[str, Any],
    algorithm: str = "lasio_parse",
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Finalize an already parsed LAS table using the selected curve strategy."""
    out = df.copy()
    if out.empty:
        return out, {"lasStrategy": algorithm, "curveCount": 0}

    depth_column = next(
        (column for column in out.columns if str(column).strip().lower() in {"dept", "depth", "深度", "md"}),
        out.columns[0],
    )
    out[depth_column] = pd.to_numeric(out[depth_column], errors="coerce")
    out = out.dropna(subset=[depth_column]).sort_values(depth_column).drop_duplicates(subset=[depth_column], keep="first")

    if algorithm == "depth_resample" and len(out) > 1:
        depth = out[depth_column].astype(float)
        intervals = depth.diff().dropna()
        interval = float(intervals[intervals > 0].median()) if (intervals > 0).any() else 0.0
        if interval > 0:
            sample_count = int((depth.iloc[-1] - depth.iloc[0]) / interval) + 1
            grid = pd.Index([depth.iloc[0] + index * interval for index in range(sample_count)], name=depth_column)
            indexed = out.set_index(depth_column)
            out = indexed.reindex(indexed.index.union(grid)).sort_index()
            numeric_columns = out.select_dtypes(include="number").columns
            out.loc[:, numeric_columns] = out.loc[:, numeric_columns].interpolate(method="index", limit_direction="both")
            out = out.loc[grid].reset_index()
            return out, {
                "lasStrategy": algorithm,
                "depthColumn": str(depth_column),
                "depthInterval": interval,
                "curveCount": max(0, len(out.columns) - 1),
            }

    if algorithm == "welly_align":
        curve_columns = [column for column in out.columns if column != depth_column]
        for column in curve_columns:
            out[column] = pd.to_numeric(out[column], errors="coerce")
        return out.reset_index(drop=True), {
            "lasStrategy": algorithm,
            "depthColumn": str(depth_column),
            "aligned": True,
            "curveCount": len(curve_columns),
        }

    return out.reset_index(drop=True), {
        "lasStrategy": algorithm,
        "depthColumn": str(depth_column),
        "curveCount": max(0, len(out.columns) - 1),
    }


def _row_similarity_tokens(row: pd.Series) -> set[str]:
    values = []
    for column, value in row.items():
        if str(column).startswith("_source_") or pd.isna(value):
            continue
        normalized = re.sub(r"\s+", " ", str(value).strip().lower())
        if normalized:
            values.append(normalized)
    text = "|".join(values)
    if not text:
        return set()
    if len(text) < 3:
        return {text}
    return {text[index : index + 3] for index in range(len(text) - 2)}


def _minhash_signature(tokens: set[str], size: int = 12) -> Tuple[int, ...]:
    if not tokens:
        return tuple()
    signature = []
    for seed in range(size):
        minimum = min(
            int.from_bytes(hashlib.blake2b(f"{seed}:{token}".encode("utf-8"), digest_size=8).digest(), "big")
            for token in tokens
        )
        signature.append(minimum)
    return tuple(signature)


def _record_removed_duplicates(report: Dict[str, Any], count: int) -> None:
    if count:
        report["operations"]["duplicateRowsRemoved"] = report["operations"].get("duplicateRowsRemoved", 0) + count


def _method_minhash_dedupe(df: pd.DataFrame, report: Dict[str, Any]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    out = _drop_empty_rows(df, report)
    token_sets: List[set[str]] = []
    kept_indices: List[Any] = []
    buckets: Dict[Tuple[int, Tuple[int, ...]], List[int]] = {}
    removed = 0

    for row_index, (_, row) in enumerate(out.iterrows()):
        tokens = _row_similarity_tokens(row)
        signature = _minhash_signature(tokens)
        candidate_positions: set[int] = set()
        for band in range(4):
            band_value = signature[band * 3 : (band + 1) * 3]
            candidate_positions.update(buckets.get((band, band_value), []))
        is_duplicate = False
        for position in candidate_positions:
            other = token_sets[position]
            union = tokens | other
            similarity = len(tokens & other) / len(union) if union else 1.0
            if similarity >= 0.88:
                is_duplicate = True
                break
        if is_duplicate:
            removed += 1
            continue
        position = len(token_sets)
        token_sets.append(tokens)
        kept_indices.append(out.index[row_index])
        for band in range(4):
            band_value = signature[band * 3 : (band + 1) * 3]
            buckets.setdefault((band, band_value), []).append(position)

    _record_removed_duplicates(report, removed)
    return out.loc[kept_indices].reset_index(drop=True), {"duplicateRowsRemoved": removed, "similarityThreshold": 0.88}


def _method_record_linkage_dedupe(df: pd.DataFrame, report: Dict[str, Any]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    out = _drop_empty_rows(df, report)
    kept_indices: List[Any] = []
    kept_records: List[str] = []
    removed = 0
    for row_index, (_, row) in enumerate(out.iterrows()):
        record = "|".join(sorted(_row_similarity_tokens(row)))
        recent_records = kept_records[-250:]
        if any(SequenceMatcher(None, record, candidate).ratio() >= 0.94 for candidate in recent_records):
            removed += 1
            continue
        kept_indices.append(out.index[row_index])
        kept_records.append(record)
    _record_removed_duplicates(report, removed)
    return out.loc[kept_indices].reset_index(drop=True), {"duplicateRowsRemoved": removed, "similarityThreshold": 0.94}


def _method_fill_missing(
    df: pd.DataFrame,
    report: Dict[str, Any],
    algorithm: str = "statistical_fill",
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    if algorithm == "linear_interpolation":
        return _method_linear_interpolation(df, report)
    if algorithm == "knn_imputation":
        return _method_knn_imputation(df, report)
    return _method_auto_fill_missing(df, report)


def _method_auto_fill_missing(df: pd.DataFrame, report: Dict[str, Any]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    out = df.copy()
    filled_by_col: Dict[str, int] = {}
    for col in out.columns:
        if str(col).startswith("_source_"):
            continue
        before = int(out[col].isna().sum())
        if not before:
            continue
        if pd.api.types.is_numeric_dtype(out[col]):
            value = out[col].median()
            out[col] = out[col].fillna(value if pd.notna(value) else 0)
        else:
            mode = out[col].mode(dropna=True)
            fill_value = mode.iloc[0] if not mode.empty else ""
            out[col] = out[col].fillna(fill_value)
        filled = before - int(out[col].isna().sum())
        if filled:
            filled_by_col[str(col)] = filled
            report["operations"]["missingFilled"][str(col)] = report["operations"]["missingFilled"].get(str(col), 0) + filled
    return out, {"missingFilled": filled_by_col}


def _record_missing_fills(before: pd.Series, out: pd.DataFrame, report: Dict[str, Any]) -> Dict[str, int]:
    filled_by_col: Dict[str, int] = {}
    for col in out.columns:
        before_count = int(before.get(col, 0))
        filled = before_count - int(out[col].isna().sum())
        if filled:
            filled_by_col[str(col)] = filled
            report["operations"]["missingFilled"][str(col)] = report["operations"]["missingFilled"].get(str(col), 0) + filled
    return filled_by_col


def _fill_text_columns(out: pd.DataFrame) -> None:
    for col in out.columns:
        if str(col).startswith("_source_") or pd.api.types.is_numeric_dtype(out[col]):
            continue
        mode = out[col].mode(dropna=True)
        fill_value = mode.iloc[0] if not mode.empty else ""
        out[col] = out[col].ffill().bfill().fillna(fill_value)


def _method_linear_interpolation(df: pd.DataFrame, report: Dict[str, Any]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    out = df.copy()
    before = out.isna().sum()
    for col in out.columns:
        if str(col).startswith("_source_") or not pd.api.types.is_numeric_dtype(out[col]):
            continue
        out[col] = out[col].interpolate(method="linear", limit_direction="both")
    _fill_text_columns(out)
    return out, {"missingFilled": _record_missing_fills(before, out, report), "interpolation": "linear"}


def _method_knn_imputation(df: pd.DataFrame, report: Dict[str, Any]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    out = df.copy()
    before = out.isna().sum()
    numeric_columns = [
        col
        for col in out.columns
        if not str(col).startswith("_source_") and pd.api.types.is_numeric_dtype(out[col]) and out[col].notna().any()
    ]
    if numeric_columns and len(out):
        numeric = out[numeric_columns].apply(pd.to_numeric, errors="coerce")
        means = numeric.mean()
        scales = numeric.std(ddof=0).replace(0, 1).fillna(1)
        standardized = (numeric - means) / scales
        neighbors = max(1, min(5, len(out)))
        for col in numeric_columns:
            missing_indices = numeric.index[numeric[col].isna()]
            candidate_indices = numeric.index[numeric[col].notna()]
            feature_columns = [feature for feature in numeric_columns if feature != col]
            for row_index in missing_indices:
                usable_features = [feature for feature in feature_columns if pd.notna(standardized.at[row_index, feature])]
                distances = pd.Series(dtype="float64")
                if usable_features and len(candidate_indices):
                    limited_candidates = candidate_indices[:5000]
                    differences = standardized.loc[limited_candidates, usable_features].sub(
                        standardized.loc[row_index, usable_features]
                    )
                    distances = differences.pow(2).mean(axis=1).dropna()
                if not distances.empty:
                    nearest_indices = distances.nsmallest(neighbors).index
                    value = numeric.loc[nearest_indices, col].mean()
                else:
                    value = numeric[col].median()
                numeric.at[row_index, col] = value if pd.notna(value) else 0
            out[col] = numeric[col]
    _fill_text_columns(out)
    return out, {
        "missingFilled": _record_missing_fills(before, out, report),
        "neighbors": max(1, min(5, len(out))) if len(out) else 0,
    }


def _method_auto_correct_anomalies(
    df: pd.DataFrame,
    report: Dict[str, Any],
    algorithm: str = "iqr",
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    out = df.copy()
    corrected_by_col: Dict[str, int] = {}
    for col in out.columns:
        if str(col).startswith("_source_") or not pd.api.types.is_numeric_dtype(out[col]):
            continue
        series = out[col]
        non_null = series.dropna()
        if len(non_null) < 4:
            continue
        if algorithm == "three_sigma":
            center = non_null.mean()
            spread = non_null.std(ddof=0)
            if pd.isna(spread) or spread == 0:
                continue
            lower = center - 3 * spread
            upper = center + 3 * spread
        elif algorithm == "mad":
            center = non_null.median()
            mad = (non_null - center).abs().median()
            if pd.isna(mad) or mad == 0:
                continue
            robust_sigma = 1.4826 * mad
            lower = center - 3.5 * robust_sigma
            upper = center + 3.5 * robust_sigma
        else:
            q1 = non_null.quantile(0.25)
            q3 = non_null.quantile(0.75)
            iqr = q3 - q1
            if pd.isna(iqr) or iqr == 0:
                continue
            lower = q1 - 1.5 * iqr
            upper = q3 + 1.5 * iqr
        mask = ((series < lower) | (series > upper)).fillna(False)
        count = int(mask.sum())
        if not count:
            continue
        out[col] = series.clip(lower=lower, upper=upper)
        corrected_by_col[str(col)] = count
        report["operations"]["anomaliesCorrected"][str(col)] = (
            report["operations"]["anomaliesCorrected"].get(str(col), 0) + count
        )
    return out, {"anomaliesCorrected": corrected_by_col, "detector": algorithm}


UNIT_DIMENSION_SPECS: List[Dict[str, Any]] = [
    {
        "key": "wob",
        "target": "kN",
        "aliases": ["wob", "wob_kN", "钻压", "weightonbit", "weight on bit"],
        "units": {
            "kN": {"aliases": ["kn", "千牛"], "factor": 1.0, "offset": 0.0},
            "klbf": {"aliases": ["klbf", "kip", "kips"], "factor": 4.44822, "offset": 0.0},
            "ton": {"aliases": ["ton", "tons", "吨", "tf"], "factor": 9.80665, "offset": 0.0},
        },
    },
    {
        "key": "torque",
        "target": "kN·m",
        "aliases": ["torque", "torque_kNm", "torque_kN·m", "扭矩", "扭力"],
        "units": {
            "N.m": {"aliases": ["n·m", "n.m", "nm", "n m"], "factor": 0.001, "offset": 0.0},
            "kN·m": {"aliases": ["kn·m", "kn.m", "knm", "kn m"], "factor": 1.0, "offset": 0.0},
            "ft.lbf": {"aliases": ["ft·lbf", "ft.lbf", "ft-lbf", "ftlb", "lbft"], "factor": 0.00135582, "offset": 0.0},
        },
    },
    {
        "key": "standpipe_pressure",
        "target": "MPa",
        "aliases": ["standpipe_pressure", "standpipe_pressure_MPa", "泵压", "立管压力", "pressure", "spp"],
        "units": {
            "MPa": {"aliases": ["mpa", "兆帕"], "factor": 1.0, "offset": 0.0},
            "psi": {"aliases": ["psi"], "factor": 0.00689476, "offset": 0.0},
            "bar": {"aliases": ["bar"], "factor": 0.1, "offset": 0.0},
        },
    },
    {
        "key": "flow_rate",
        "target": "L/s",
        "aliases": ["flow_rate", "flow_rate_Ls", "排量", "流量", "入口流量", "出口流量", "flow", "rate"],
        "units": {
            "L/s": {"aliases": ["l/s", "lps", "ls", "升秒", "升/秒"], "factor": 1.0, "offset": 0.0},
            "m3/min": {"aliases": ["m3/min", "m³/min", "m^3/min", "m3min", "方分", "立方米分"], "factor": 16.6667, "offset": 0.0},
            "gal/min": {"aliases": ["gal/min", "gpm", "galmin"], "factor": 0.0630902, "offset": 0.0},
        },
    },
    {
        "key": "temperature",
        "target": "℃",
        "aliases": ["temperature", "temperature_C", "温度", "temp"],
        "units": {
            "℃": {"aliases": ["℃", "°c", "c", "摄氏度"], "factor": 1.0, "offset": 0.0},
            "F": {"aliases": ["℉", "°f", "f", "华氏度"], "factor": 5.0 / 9.0, "offset": -32.0 * 5.0 / 9.0},
        },
    },
]

ENGINEERING_CONSTRAINT_SPECS: List[Dict[str, Any]] = [
    {"key": "depth_m", "aliases": ["depth_m", "井深", "测深", "深度", "depth", "md"], "min": 0, "max": 10000, "monotonic": True},
    {"key": "wob_kN", "aliases": ["wob_kN", "wob", "钻压", "weightonbit", "weight on bit"], "min": 0, "max": 500},
    {"key": "torque_kNm", "aliases": ["torque_kNm", "torque_kN·m", "torque", "扭矩", "扭力"], "min": 0, "max": 100},
    {"key": "standpipe_pressure_MPa", "aliases": ["standpipe_pressure_MPa", "standpipe_pressure", "泵压", "立管压力", "pressure", "spp"], "min": 0, "max": 70},
    {"key": "flow_rate_Ls", "aliases": ["flow_rate_Ls", "flow_rate", "排量", "流量", "入口流量", "出口流量"], "min": 0, "max": 120},
    {"key": "temperature_C", "aliases": ["temperature_C", "temperature", "温度", "temp"], "min": -40, "max": 200},
    {"key": "rpm", "aliases": ["rpm", "转速", "rotaryspeed"], "min": 0, "max": 300},
]


def _compact_token(value: Any) -> str:
    text = str(value or "").lower()
    text = text.replace("³", "3").replace("²", "2").replace("µ", "u").replace("μ", "u")
    return re.sub(r"[^0-9a-zA-Z℃℉\u4e00-\u9fff]+", "", text)


def _column_matches_alias(column: Any, aliases: Iterable[str]) -> bool:
    compact = _compact_token(column)
    return any(_compact_token(alias) and _compact_token(alias) in compact for alias in aliases)


def _unit_alias_in_text(text: str, alias: str) -> bool:
    alias_compact = _compact_token(alias)
    if not alias_compact:
        return False
    if any(ch in alias for ch in ("℃", "℉", "°")) or re.search(r"[\u4e00-\u9fff]", alias):
        return alias.lower() in text.lower() or alias_compact in _compact_token(text)
    if len(alias_compact) <= 1:
        return bool(re.search(rf"(^|[^a-z0-9]){re.escape(alias_compact)}([^a-z0-9]|$)", text.lower()))
    return alias_compact in _compact_token(text)


def _match_unit_key(raw_unit: Any, spec: Dict[str, Any]) -> Optional[str]:
    if raw_unit is None:
        return None
    raw_text = str(raw_unit).strip()
    if not raw_text:
        return None
    raw_compact = _compact_token(raw_text)
    exact_matches: List[Tuple[int, str]] = []
    contains_matches: List[Tuple[int, str]] = []
    for unit_key, unit_info in (spec.get("units") or {}).items():
        for alias in unit_info.get("aliases") or []:
            alias_compact = _compact_token(alias)
            if not alias_compact:
                continue
            if raw_compact == alias_compact:
                exact_matches.append((len(alias_compact), unit_key))
            elif alias_compact in raw_compact:
                contains_matches.append((len(alias_compact), unit_key))
    matches = exact_matches or contains_matches
    if not matches:
        return None
    return sorted(matches, reverse=True)[0][1]


def _infer_unit_from_label(column: Any, spec: Dict[str, Any]) -> Optional[str]:
    text = str(column or "")
    candidates: List[Tuple[int, str]] = []
    for unit_key, unit_info in (spec.get("units") or {}).items():
        for alias in unit_info.get("aliases") or []:
            if _unit_alias_in_text(text, alias):
                candidates.append((len(_compact_token(alias)), unit_key))
    if not candidates:
        return None
    return sorted(candidates, reverse=True)[0][1]


def _parse_number_and_unit(value: Any) -> Tuple[Optional[float], Optional[str], bool]:
    if pd.isna(value):
        return None, None, False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value), None, False
    text = str(value).strip()
    match = re.match(r"^\s*([-+]?\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*(.*?)\s*$", text)
    if not match:
        return None, None, False
    try:
        number = float(match.group(1).replace(",", ""))
    except ValueError:
        return None, None, False
    unit_text = (match.group(2) or "").strip() or None
    return number, unit_text, bool(unit_text)


def _convert_unit_value(number: float, source_unit: str, spec: Dict[str, Any]) -> float:
    unit_info = (spec.get("units") or {}).get(source_unit) or {}
    return number * float(unit_info.get("factor", 1.0)) + float(unit_info.get("offset", 0.0))


def _looks_like_unit_column(column: Any) -> bool:
    compact = _compact_token(column)
    return ("unit" in compact or "单位" in compact) and "value" not in compact and "值" not in compact


def _find_paired_unit_column(columns: Iterable[Any], value_column: Any, spec: Dict[str, Any]) -> Optional[Any]:
    column_list = list(columns)
    value_text = str(value_column)
    direct_names = []
    if value_text.endswith("_value"):
        direct_names.append(f"{value_text[:-6]}_unit")
    if value_text.endswith("Value"):
        direct_names.append(f"{value_text[:-5]}Unit")
    direct_names.append(value_text.replace("_value", "_unit").replace("value", "unit").replace("值", "单位"))

    for direct_name in direct_names:
        if direct_name == value_text:
            continue
        for col in column_list:
            if col != value_column and str(col) == direct_name:
                return col

    value_compact = _compact_token(value_column)
    for col in column_list:
        if col == value_column or not _looks_like_unit_column(col):
            continue
        col_compact = _compact_token(col)
        if any(_compact_token(alias) and _compact_token(alias) in value_compact and _compact_token(alias) in col_compact for alias in spec.get("aliases") or []):
            return col
    return None


def _method_unit_dimension_check(
    df: pd.DataFrame,
    report: Dict[str, Any],
    algorithm: str = "combined_unit_rules",
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    out = df.copy()
    converted_by_col: Dict[str, int] = {}
    checked_dimensions: Dict[str, str] = {}
    unsupported_units: Dict[str, int] = {}

    for col in out.columns:
        if str(col).startswith("_source_"):
            continue
        if _looks_like_unit_column(col):
            continue
        spec = next((item for item in UNIT_DIMENSION_SPECS if _column_matches_alias(col, item["aliases"])), None)
        if not spec:
            continue

        label_unit = _infer_unit_from_label(col, spec)
        unit_col = _find_paired_unit_column(out.columns, col, spec)
        converted_values: List[Any] = []
        normalized_units: Dict[Any, str] = {}
        converted_count = 0
        unsupported_count = 0
        changed = False

        for row_idx, value in out[col].items():
            number, cell_unit_text, had_cell_unit = _parse_number_and_unit(value)
            if number is None:
                converted_values.append(value)
                continue

            paired_unit_text = out.at[row_idx, unit_col] if unit_col is not None else None
            if algorithm == "label_unit_mapping":
                raw_unit_text = None
                source_unit = label_unit
            elif algorithm == "cell_unit_parsing":
                raw_unit_text = cell_unit_text or paired_unit_text
                source_unit = _match_unit_key(raw_unit_text, spec) if raw_unit_text is not None else None
            else:
                raw_unit_text = cell_unit_text or paired_unit_text
                source_unit = _match_unit_key(raw_unit_text, spec) if raw_unit_text is not None else label_unit
            if raw_unit_text is not None and str(raw_unit_text).strip() and not source_unit:
                unsupported_count += 1
                converted_values.append(value)
                continue
            if not source_unit:
                converted_values.append(number)
                continue

            converted = _convert_unit_value(number, source_unit, spec)
            converted_values.append(converted)
            normalized_units[row_idx] = str(spec["target"])
            if source_unit != spec["target"]:
                converted_count += 1
                changed = True
            elif had_cell_unit:
                changed = True

        if changed or converted_count or normalized_units:
            out[col] = converted_values
            if unit_col is not None and normalized_units:
                for row_idx, target_unit in normalized_units.items():
                    out.at[row_idx, unit_col] = target_unit
            converted_by_col[str(col)] = converted_count
            checked_dimensions[str(col)] = str(spec["target"])
            report["operations"]["unitConversions"][str(col)] = (
                report["operations"]["unitConversions"].get(str(col), 0) + converted_count
            )
        if unsupported_count:
            unsupported_units[str(col)] = unsupported_count

    if checked_dimensions:
        report["operations"]["dimensionChecks"].update(checked_dimensions)

    return out, {
        "unitConversions": converted_by_col,
        "dimensionChecks": checked_dimensions,
        "unsupportedUnits": unsupported_units,
        "unitStrategy": algorithm,
    }


def _method_engineering_constraint_check(
    df: pd.DataFrame,
    report: Dict[str, Any],
    algorithm: str = "boundary_clip",
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    out = df.copy()
    corrected_by_col: Dict[str, int] = {}
    monotonic_by_col: Dict[str, int] = {}

    for col in out.columns:
        if str(col).startswith("_source_"):
            continue
        spec = next((item for item in ENGINEERING_CONSTRAINT_SPECS if _column_matches_alias(col, item["aliases"])), None)
        if not spec:
            continue

        numeric = _to_numeric(out[col])
        if numeric.notna().sum() == 0:
            continue

        corrected = numeric.copy()
        correction_mask = pd.Series(False, index=corrected.index)
        lower = spec.get("min")
        upper = spec.get("max")
        if lower is not None:
            correction_mask = correction_mask | (corrected < lower).fillna(False)
        if upper is not None:
            correction_mask = correction_mask | (corrected > upper).fillna(False)

        if algorithm == "invalid_to_missing":
            corrected = corrected.mask(correction_mask)
        elif algorithm != "constraint_flag":
            corrected = corrected.clip(lower=lower, upper=upper)

        jump_factor = spec.get("jumpFactor")
        jump_delta = spec.get("jumpDelta")
        if jump_factor and jump_delta:
            prev = corrected.ffill().shift()
            jump_mask = (
                corrected.notna()
                & prev.notna()
                & (corrected.abs() > prev.abs().clip(lower=1) * float(jump_factor))
                & ((corrected - prev).abs() > float(jump_delta))
            )
            correction_mask = correction_mask | jump_mask.fillna(False)
            if algorithm == "invalid_to_missing":
                corrected = corrected.mask(jump_mask)
            elif algorithm != "constraint_flag":
                corrected = corrected.mask(jump_mask, prev)

        correction_count = int(correction_mask.sum())
        if correction_count:
            corrected_by_col[str(col)] = correction_count
            report["operations"]["constraintCorrections"][str(col)] = (
                report["operations"]["constraintCorrections"].get(str(col), 0) + correction_count
            )

        if spec.get("monotonic"):
            cumulative_max = corrected.cummax()
            monotonic_mask = (corrected.notna() & cumulative_max.notna() & (corrected < cumulative_max)).fillna(False)
            monotonic_count = int(monotonic_mask.sum())
            if monotonic_count:
                monotonic_by_col[str(col)] = monotonic_count
                if algorithm == "invalid_to_missing":
                    corrected = corrected.mask(monotonic_mask)
                elif algorithm != "constraint_flag":
                    corrected = corrected.mask(monotonic_mask, cumulative_max)
                report["operations"]["monotonicCorrections"][str(col)] = (
                    report["operations"]["monotonicCorrections"].get(str(col), 0) + monotonic_count
                )

        if algorithm == "constraint_flag":
            flag_name = f"{col}_constraint_valid"
            out[flag_name] = ~(correction_mask | monotonic_mask if spec.get("monotonic") else correction_mask)
        elif correction_count or monotonic_by_col.get(str(col)):
            out[col] = corrected

    return out, {
        "constraintCorrections": corrected_by_col,
        "monotonicCorrections": monotonic_by_col,
        "constraintStrategy": algorithm,
    }


def _method_schema_standardize(
    df: pd.DataFrame,
    report: Dict[str, Any],
    algorithm: str = "schema_mapping",
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    out = df.copy()
    if algorithm in {"min_max", "z_score"}:
        normalized_columns: List[str] = []
        skipped_columns: List[str] = []
        for col in out.columns:
            if str(col).startswith("_source_") or not pd.api.types.is_numeric_dtype(out[col]):
                continue
            series = _to_numeric(out[col])
            if algorithm == "min_max":
                minimum = series.min()
                spread = series.max() - minimum
                if pd.isna(spread) or spread == 0:
                    skipped_columns.append(str(col))
                    continue
                out[col] = (series - minimum) / spread
            else:
                mean = series.mean()
                std = series.std(ddof=0)
                if pd.isna(std) or std == 0:
                    skipped_columns.append(str(col))
                    continue
                out[col] = (series - mean) / std
            normalized_columns.append(str(col))
        return out, {
            "normalization": algorithm,
            "normalizedColumns": normalized_columns,
            "skippedConstantColumns": skipped_columns,
        }
    rename_map: Dict[str, str] = {}
    normalized_columns: List[str] = []
    for idx, col in enumerate(out.columns):
        text = _clean_column_name(col)
        if str(text).startswith("_source_"):
            normalized = str(text)
        else:
            normalized = re.sub(r"\s+", "_", text.strip().lower())
            normalized = re.sub(r"[^0-9a-zA-Z_\u4e00-\u9fff]+", "_", normalized).strip("_")
            normalized = normalized or f"column_{idx}"
        normalized_columns.append(normalized)
        if normalized != col:
            rename_map[str(col)] = normalized

    out.columns = _make_unique_columns(normalized_columns, report)
    if rename_map:
        report["operations"]["columnsRenamed"].update(rename_map)
    return out, {"columnsRenamed": rename_map, "columnsOut": [str(col) for col in out.columns]}


def _merge_config(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_config(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read_tables(source: Path, config: Dict[str, Any], report: Dict[str, Any]) -> List[Tuple[str, pd.DataFrame]]:
    suffix = source.suffix.lower()
    if suffix == ".csv":
        return [("Sheet1", _read_csv(source, header=None if config.get("headerDetection", True) else 0))]
    if suffix in {".xlsx", ".xls"}:
        return list(pd.read_excel(source, sheet_name=None, header=None if config.get("headerDetection", True) else 0).items())
    if suffix == ".jsonl":
        return [("JsonLines", pd.read_json(source, lines=True))]
    if suffix == ".json":
        data = json.loads(source.read_text(encoding="utf-8"))
        records = _json_to_records(data)
        return [("Json", pd.DataFrame(records))]
    if suffix == ".las":
        return [("LAS", _read_las(source))]
    report["warnings"].append(f"Unsupported file suffix: {suffix}")
    raise ValueError(f"Unsupported tabular file type: {suffix}")


def _read_csv(source: Path, header: Optional[int]) -> pd.DataFrame:
    encodings = ("utf-8-sig", "utf-8", "gbk")
    last_error: Optional[Exception] = None
    for encoding in encodings:
        try:
            return pd.read_csv(source, header=header, encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
    if last_error:
        raise last_error
    return pd.read_csv(source, header=header)


def _read_las(source: Path) -> pd.DataFrame:
    """Read the curve and ASCII sections of a LAS 2.x file without network-only dependencies."""
    text = ""
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            text = source.read_text(encoding=encoding)
            break
        except UnicodeDecodeError:
            continue
    if not text:
        raise ValueError(f"Unable to decode LAS file: {source.name}")

    section = ""
    curve_names: List[str] = []
    rows: List[List[float]] = []
    null_value: Optional[float] = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("~"):
            section = line[1:].strip().lower()
            continue
        if section.startswith("well") and line.upper().startswith("NULL"):
            match = re.search(r"\.\s*[^\s]*\s+([-+]?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?)", line)
            if match:
                null_value = float(match.group(1))
            continue
        if section.startswith("curve"):
            mnemonic = line.split(".", 1)[0].strip().split()[0] if "." in line else line.split()[0]
            if mnemonic:
                curve_names.append(mnemonic)
            continue
        if section.startswith("ascii") or section == "a":
            try:
                values = [float(value) for value in line.replace(",", " ").split()]
            except ValueError:
                continue
            if values:
                rows.append(values)

    if not rows:
        raise ValueError(f"LAS file contains no ASCII curve data: {source.name}")
    width = max(len(row) for row in rows)
    headers = curve_names[:width] + [f"CURVE_{index + 1}" for index in range(len(curve_names), width)]
    normalized_rows: List[List[Any]] = [headers]
    for row in rows:
        padded: List[Any] = row[:width] + [None] * max(0, width - len(row))
        if null_value is not None:
            padded = [None if isinstance(value, float) and math.isclose(value, null_value) else value for value in padded]
        normalized_rows.append(padded)
    return pd.DataFrame(normalized_rows)


def _json_to_records(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, list):
        return [item if isinstance(item, dict) else {"value": item} for item in data]
    if isinstance(data, dict):
        for key in ("records", "data", "rows", "items"):
            if isinstance(data.get(key), list):
                return _json_to_records(data[key])
        return [data]
    return [{"value": data}]


def _normalize_dataframe(df: pd.DataFrame, sheet_name: str, config: Dict[str, Any], report: Dict[str, Any]) -> pd.DataFrame:
    df = df.copy()
    if config.get("headerDetection", True):
        df = _detect_and_apply_header(df, sheet_name, report)

    df.columns = _make_unique_columns([_clean_column_name(col) for col in df.columns], report)
    df = _normalize_missing_values(df, config)
    df = _normalize_text_cells(df, config)
    df = _apply_column_standards(df, config, report)

    if config.get("addProvenanceColumns", True):
        df.insert(0, "_source_row", range(1, len(df) + 1))
        df.insert(0, "_source_sheet", sheet_name)

    return df


def _detect_and_apply_header(df: pd.DataFrame, sheet_name: str, report: Dict[str, Any]) -> pd.DataFrame:
    if df.empty:
        return df

    max_valid_cols = -1
    header_row_idx = 0
    for idx in range(min(10, len(df))):
        valid_cols = int(df.iloc[idx].count())
        if valid_cols > max_valid_cols:
            max_valid_cols = valid_cols
            header_row_idx = idx

    headers = []
    for idx, value in enumerate(df.iloc[header_row_idx]):
        label = _clean_column_name(value)
        headers.append(label or f"Column_{idx}")

    report["operations"]["headersDetected"].append(
        {"sheet": sheet_name, "rowIndex": int(header_row_idx), "validColumns": max_valid_cols}
    )
    out = df.iloc[header_row_idx + 1 :].reset_index(drop=True)
    out.columns = headers
    return out


def _clean_column_name(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    text = str(value).strip().replace("\n", " ").replace("\r", " ")
    text = re.sub(r"\s+", " ", text)
    return text


def _make_unique_columns(columns: Iterable[str], report: Dict[str, Any]) -> List[str]:
    seen: Dict[str, int] = {}
    unique: List[str] = []
    for idx, col in enumerate(columns):
        base = col or f"Column_{idx}"
        count = seen.get(base, 0)
        if count:
            new_name = f"{base}_{count + 1}"
            report["operations"]["duplicateColumnsRenamed"][new_name] = base
            unique.append(new_name)
        else:
            unique.append(base)
        seen[base] = count + 1
    return unique


def _normalize_missing_values(df: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
    missing_values = set(str(item) for item in config.get("missingValues", []))
    if not missing_values:
        return df

    def normalize(value: Any) -> Any:
        if pd.isna(value):
            return pd.NA
        if isinstance(value, str) and value.strip() in missing_values:
            return pd.NA
        return value

    return df.map(normalize)


def _normalize_text_cells(df: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
    text_cfg = config.get("textNormalization") or {}
    if not text_cfg:
        return df

    strip = bool(text_cfg.get("strip", True))
    collapse = bool(text_cfg.get("collapseWhitespace", True))

    def normalize(value: Any) -> Any:
        if not isinstance(value, str):
            return value
        text = value.strip() if strip else value
        return re.sub(r"\s+", " ", text) if collapse else text

    return df.map(normalize)


def _apply_column_standards(df: pd.DataFrame, config: Dict[str, Any], report: Dict[str, Any]) -> pd.DataFrame:
    specs: Dict[str, Dict[str, Any]] = config.get("columnSpecs") or {}
    if not specs:
        return df

    df = _rename_and_merge_columns(df, specs, config, report)

    required_added: List[str] = []
    for standard_name, spec in specs.items():
        if spec.get("required") and standard_name not in df.columns:
            df[standard_name] = pd.NA
            required_added.append(standard_name)
    report["operations"]["requiredColumnsAdded"].extend(required_added)

    rows_to_drop = pd.Series(False, index=df.index)
    for column, spec in specs.items():
        if column not in df.columns:
            continue
        df[column] = _coerce_type(df[column], column, spec, report)
        df[column], drop_mask = _apply_anomaly_policy(df[column], column, spec, report)
        rows_to_drop = rows_to_drop | drop_mask
        df[column] = _fill_missing(df[column], column, spec, report)
        df[column] = _correct_categories(df[column], column, spec, report)
        df[column] = _apply_unit_conversion(df[column], column, spec, report)

    if rows_to_drop.any():
        dropped = int(rows_to_drop.sum())
        report["operations"]["rowsDroppedForAnomalies"] += dropped
        df = df.loc[~rows_to_drop].reset_index(drop=True)

    if not config.get("keepExtraColumns", True):
        keep_cols = [col for col in specs.keys() if col in df.columns]
        provenance = [col for col in ("_source_sheet", "_source_row") if col in df.columns]
        df = df[provenance + keep_cols]

    return df


def _rename_and_merge_columns(
    df: pd.DataFrame,
    specs: Dict[str, Dict[str, Any]],
    config: Dict[str, Any],
    report: Dict[str, Any],
) -> pd.DataFrame:
    normalized_to_standard: Dict[str, str] = {}
    for standard_name, spec in specs.items():
        normalized_to_standard[_normalize_label(standard_name)] = standard_name
        for alias in spec.get("aliases") or []:
            normalized_to_standard[_normalize_label(alias)] = standard_name

    target_groups: Dict[str, List[str]] = {}
    for col in df.columns:
        target = normalized_to_standard.get(_normalize_label(col))
        if target:
            target_groups.setdefault(target, []).append(col)

    for target, source_cols in target_groups.items():
        if len(source_cols) == 1:
            source = source_cols[0]
            if source != target:
                df = df.rename(columns={source: target})
                report["operations"]["columnsRenamed"][source] = target
            continue

        merged = df[source_cols].bfill(axis=1).iloc[:, 0]
        df[target] = merged
        for source in source_cols:
            if source != target:
                df = df.drop(columns=[source])
        report["operations"]["columnsMerged"][target] = source_cols

    return df


def _normalize_label(value: Any) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"[\s_\-（）()【】\[\]:：/\\]+", "", text)


def _coerce_type(series: pd.Series, column: str, spec: Dict[str, Any], report: Dict[str, Any]) -> pd.Series:
    dtype = str(spec.get("dtype") or "").lower()
    before_na = int(series.isna().sum())
    coerced = series
    if dtype in {"number", "float", "numeric"}:
        coerced = _to_numeric(series, integer=False)
    elif dtype in {"integer", "int"}:
        coerced = _to_numeric(series, integer=True)
    elif dtype in {"datetime", "date", "time"}:
        coerced = pd.to_datetime(series, errors="coerce")
    elif dtype in {"boolean", "bool"}:
        coerced = series.map(_to_bool)
    elif dtype in {"string", "str", "text"}:
        coerced = series.astype("string")
    else:
        return series

    after_na = int(coerced.isna().sum())
    if after_na > before_na:
        report["operations"]["typeCoercions"][column] = after_na - before_na
    return coerced


def _to_numeric(series: pd.Series, integer: bool = False) -> pd.Series:
    cleaned = series.astype("string").str.replace(",", "", regex=False)
    numeric = pd.to_numeric(cleaned, errors="coerce")
    if numeric.isna().sum() > series.isna().sum():
        extracted = cleaned.str.extract(r"([-+]?\d+(?:\.\d+)?)", expand=False)
        numeric = pd.to_numeric(extracted, errors="coerce").combine_first(numeric)
    if integer:
        return numeric.round().astype("Int64")
    return numeric


def _to_bool(value: Any) -> Any:
    if pd.isna(value):
        return pd.NA
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "是", "有"}:
        return True
    if text in {"0", "false", "no", "n", "否", "无"}:
        return False
    return pd.NA


def _apply_anomaly_policy(
    series: pd.Series,
    column: str,
    spec: Dict[str, Any],
    report: Dict[str, Any],
) -> Tuple[pd.Series, pd.Series]:
    anomaly = spec.get("anomaly") or {}
    if not anomaly:
        return series, pd.Series(False, index=series.index)

    action = str(anomaly.get("action") or "null").lower()
    lower = anomaly.get("min")
    upper = anomaly.get("max")
    mask = pd.Series(False, index=series.index)
    if lower is not None:
        mask = mask | (series < lower)
    if upper is not None:
        mask = mask | (series > upper)
    mask = mask.fillna(False)
    count = int(mask.sum())
    if not count:
        return series, pd.Series(False, index=series.index)

    report["operations"]["anomaliesCorrected"][column] = report["operations"]["anomaliesCorrected"].get(column, 0) + count
    if action == "clip":
        return series.clip(lower=lower, upper=upper), pd.Series(False, index=series.index)
    if action == "drop":
        return series, mask
    corrected = series.copy()
    corrected.loc[mask] = pd.NA
    return corrected, pd.Series(False, index=series.index)


def _fill_missing(series: pd.Series, column: str, spec: Dict[str, Any], report: Dict[str, Any]) -> pd.Series:
    fill = spec.get("fill") or {}
    strategy = str(fill.get("strategy") or "").lower()
    if not strategy:
        return series

    before = int(series.isna().sum())
    if not before:
        return series

    if strategy == "constant":
        out = series.fillna(fill.get("value"))
    elif strategy == "zero":
        out = series.fillna(0)
    elif strategy == "mean":
        out = series.fillna(series.mean(numeric_only=True))
    elif strategy == "median":
        out = series.fillna(series.median(numeric_only=True))
    elif strategy == "mode":
        mode = series.mode(dropna=True)
        out = series.fillna(mode.iloc[0] if not mode.empty else pd.NA)
    elif strategy == "ffill":
        out = series.ffill()
    elif strategy == "bfill":
        out = series.bfill()
    elif strategy == "interpolate":
        out = series.interpolate(limit_direction="both")
    else:
        report["warnings"].append(f"Unknown fill strategy for {column}: {strategy}")
        return series

    filled = before - int(out.isna().sum())
    if filled:
        report["operations"]["missingFilled"][column] = report["operations"]["missingFilled"].get(column, 0) + filled
    return out


def _correct_categories(series: pd.Series, column: str, spec: Dict[str, Any], report: Dict[str, Any]) -> pd.Series:
    values = [str(v) for v in (spec.get("categories") or spec.get("allowedValues") or [])]
    if not values:
        return series
    action = str(spec.get("categoryCorrection") or "closest").lower()
    valid = set(values)
    corrections = 0

    def correct(value: Any) -> Any:
        nonlocal corrections
        if pd.isna(value):
            return value
        text = str(value)
        if text in valid:
            return text
        if action == "null":
            corrections += 1
            return pd.NA
        matches = get_close_matches(text, values, n=1, cutoff=float(spec.get("categoryCutoff", 0.82)))
        if matches:
            corrections += 1
            return matches[0]
        corrections += 1
        return pd.NA

    out = series.map(correct)
    if corrections:
        report["operations"]["categoryCorrections"][column] = corrections
    return out


def _apply_unit_conversion(series: pd.Series, column: str, spec: Dict[str, Any], report: Dict[str, Any]) -> pd.Series:
    factor = spec.get("unitFactor")
    if factor in (None, "", 1, 1.0):
        return series
    try:
        numeric_factor = float(factor)
    except (TypeError, ValueError):
        report["warnings"].append(f"Invalid unitFactor for {column}: {factor}")
        return series
    report["operations"]["unitConversions"][column] = {
        "factor": numeric_factor,
        "sourceUnit": spec.get("sourceUnit"),
        "targetUnit": spec.get("unit"),
    }
    return series * numeric_factor


def _drop_empty_rows(df: pd.DataFrame, report: Dict[str, Any]) -> pd.DataFrame:
    if df.empty:
        return df
    before = len(df)
    data_cols = [col for col in df.columns if not str(col).startswith("_source_")]
    if not data_cols:
        return df
    out = df.dropna(how="all", subset=data_cols).reset_index(drop=True)
    report["operations"]["emptyRowsRemoved"] += before - len(out)
    return out


def _deduplicate_rows(df: pd.DataFrame, config: Dict[str, Any], report: Dict[str, Any]) -> pd.DataFrame:
    dedupe = config.get("dedupe") or {}
    if not dedupe.get("enabled", True) or df.empty:
        return df

    subset = dedupe.get("subset") or config.get("primaryKeys") or []
    subset = [col for col in subset if col in df.columns]
    if not subset:
        subset = [col for col in df.columns if not str(col).startswith("_source_")]
    if not subset:
        return df

    before = len(df)
    out = df.drop_duplicates(subset=subset, keep=dedupe.get("keep", "first")).reset_index(drop=True)
    report["operations"]["duplicateRowsRemoved"] += before - len(out)
    return out


def _order_columns(df: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
    specs = config.get("columnSpecs") or {}
    provenance = [col for col in ("_source_sheet", "_source_row") if col in df.columns]
    standard_cols = [col for col in specs.keys() if col in df.columns]
    extra_cols = [col for col in df.columns if col not in set(provenance + standard_cols)]
    return df[provenance + standard_cols + extra_cols]


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if pd.isna(value):
        return None
    return value
