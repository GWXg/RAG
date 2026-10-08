from __future__ import annotations

from pathlib import Path


def get_preprocessed_output(kb_id: str, file_id: str) -> Path:
    from services.index_service import file_workdir

    return file_workdir(kb_id, file_id) / "preprocessed" / "standardized.csv"


def get_preprocessed_excel_output(kb_id: str, file_id: str) -> Path:
    from services.index_service import file_workdir

    return file_workdir(kb_id, file_id) / "preprocessed" / "standardized.xlsx"


def get_preprocess_report_path(kb_id: str, file_id: str) -> Path:
    from services.index_service import file_workdir

    return file_workdir(kb_id, file_id) / "preprocessed" / "report.json"
