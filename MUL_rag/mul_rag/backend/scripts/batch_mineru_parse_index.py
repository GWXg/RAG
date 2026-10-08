from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Sequence


BACKEND_DIR = Path(__file__).resolve().parents[1]
DATA_ROOT = BACKEND_DIR / "data"
DEFAULT_REPORT_DIR = BACKEND_DIR / "batch_reports"
DEFAULT_MINERU_CMD = Path("/home/lrn/anaconda3/envs/mineru/bin/mineru")

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _safe_name(value: str) -> str:
    value = re.sub(r"[^0-9A-Za-z._\-\u4e00-\u9fff]+", "_", value or "")
    value = re.sub(r"_+", "_", value).strip("._")
    return value or "batch"


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_jsonl_row(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        handle.flush()


def _discover_file_ids(kb_id: str, selected: Sequence[str]) -> List[str]:
    files_dir = DATA_ROOT / kb_id / "files"
    if not files_dir.exists():
        raise FileNotFoundError(f"Knowledge base files directory not found: {files_dir}")

    if selected:
        return [item for item in selected if item]

    return [path.name for path in sorted(files_dir.iterdir()) if path.is_dir()]


def _configure_env(args: argparse.Namespace) -> None:
    mineru_cmd = (args.mineru_cmd or os.getenv("MINERU_CMD") or "").strip()
    if not mineru_cmd and DEFAULT_MINERU_CMD.exists():
        mineru_cmd = str(DEFAULT_MINERU_CMD)
    if mineru_cmd:
        os.environ["MINERU_CMD"] = mineru_cmd

    if args.mineru_backend is not None:
        os.environ["MINERU_BACKEND"] = args.mineru_backend
    if args.mineru_method is not None:
        os.environ["MINERU_METHOD"] = args.mineru_method
    if args.mineru_lang is not None:
        os.environ["MINERU_LANG"] = args.mineru_lang
    if args.mineru_timeout:
        os.environ["MINERU_TIMEOUT"] = str(args.mineru_timeout)
    if args.mineru_extra_args is not None:
        os.environ["MINERU_EXTRA_ARGS"] = args.mineru_extra_args
    if args.ollama_base_url:
        os.environ["OLLAMA_BASE_URL"] = args.ollama_base_url
    if args.ollama_vision_model:
        os.environ["OLLAMA_VISION_MODEL"] = args.ollama_vision_model

    if not os.getenv("MINERU_MODEL_SOURCE") and (Path.home() / "mineru.json").exists():
        os.environ["MINERU_MODEL_SOURCE"] = "local"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Batch MinerU parse and index existing files in one knowledge base."
    )
    parser.add_argument("--kb-id", required=True, help="Knowledge base id.")
    parser.add_argument("--file-id", action="append", default=[], help="Process only this file id. Can be repeated.")
    parser.add_argument("--max-files", type=int, default=0, help="0 means no limit.")
    parser.add_argument("--method", default="mineru", choices=["mineru", "original", "olmocr"])
    parser.add_argument("--force-parse", action="store_true", help="Parse even when output.md already exists.")
    parser.add_argument("--index-only", action="store_true", help="Skip parsing and index existing output.md files only.")
    parser.add_argument("--parse-only", action="store_true", help="Parse files but do not build index.")
    parser.add_argument("--skip-image-summary", action="store_true", help="Skip Ollama image summarization after MinerU parse.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned files without doing work.")
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--mineru-cmd", default="", help="Path to MinerU CLI. Defaults to MINERU_CMD or the local mineru env.")
    parser.add_argument("--mineru-backend", default=None)
    parser.add_argument("--mineru-method", default=None)
    parser.add_argument("--mineru-lang", default=None)
    parser.add_argument("--mineru-timeout", type=int, default=0)
    parser.add_argument("--mineru-extra-args", default=None)
    parser.add_argument("--ollama-base-url", default="")
    parser.add_argument("--ollama-vision-model", default="")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.index_only and args.parse_only:
        parser.error("--index-only and --parse-only cannot be used together.")

    _configure_env(args)

    from services import pdf_service
    from services.index_service import build_faiss_index

    if args.skip_image_summary:
        pdf_service.summarize_images = lambda kb_id, file_id: []

    kb_id = args.kb_id.strip()
    file_ids = _discover_file_ids(kb_id, args.file_id)
    if args.max_files > 0:
        file_ids = file_ids[: args.max_files]
    if not file_ids:
        raise ValueError("No files to process.")

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    report_base = args.report_dir / f"{_safe_name(kb_id)}__mineru_parse_index__{timestamp}"
    report_jsonl = report_base.with_suffix(".jsonl")
    report_json = report_base.with_suffix(".json")

    print(
        "[batch] kb={kb} files={count} method={method} mineru_cmd={mineru} "
        "force_parse={force} index_only={index_only} parse_only={parse_only}".format(
            kb=kb_id,
            count=len(file_ids),
            method=args.method,
            mineru=os.getenv("MINERU_CMD", ""),
            force=args.force_parse,
            index_only=args.index_only,
            parse_only=args.parse_only,
        ),
        flush=True,
    )
    print(f"[batch] report_jsonl={report_jsonl}", flush=True)

    results: List[Dict[str, Any]] = []
    started_at = time.time()

    for index, file_id in enumerate(file_ids, start=1):
        item_started_at = time.time()
        record: Dict[str, Any] = {
            "fileId": file_id,
            "index": index,
            "total": len(file_ids),
            "ok": True,
            "parsed": False,
            "parseSkipped": False,
            "indexed": False,
            "indexSkipped": False,
            "startedAt": item_started_at,
        }
        print(f"[batch] {index}/{len(file_ids)} start file={file_id}", flush=True)

        try:
            source_path = pdf_service.original_pdf_path(kb_id, file_id)
            output_md = pdf_service.markdown_output(kb_id, file_id)
            parse_meta = _read_json(pdf_service.parse_metadata_path(kb_id, file_id))
            record.update(
                {
                    "sourcePath": str(source_path),
                    "sourceExists": source_path.exists(),
                    "sourceSuffix": source_path.suffix.lower(),
                    "outputExistsBefore": output_md.exists(),
                    "parseMethodBefore": parse_meta.get("parseMethod"),
                }
            )

            if not source_path.exists():
                raise FileNotFoundError(f"Source file not found: {source_path}")

            should_parse = not args.index_only and (args.force_parse or not output_md.exists())
            if args.dry_run:
                record.update(
                    {
                        "plannedParse": should_parse,
                        "plannedIndex": (not args.parse_only) and output_md.exists(),
                    }
                )
                print(
                    f"[batch] {index}/{len(file_ids)} dry-run parse={should_parse} "
                    f"index={record['plannedIndex']} source={source_path.name}",
                    flush=True,
                )
            else:
                if should_parse:
                    print(f"[batch] {index}/{len(file_ids)} parse start file={file_id}", flush=True)
                    parse_result = pdf_service.run_full_parse_pipeline(
                        kb_id,
                        file_id,
                        method=args.method,
                        progress_callback=lambda p, fid=file_id: print(
                            f"[batch] parse file={fid} progress={p}",
                            flush=True,
                        ),
                    )
                    record["parsed"] = True
                    record["parseResult"] = parse_result
                    print(f"[batch] {index}/{len(file_ids)} parse done file={file_id}", flush=True)
                else:
                    record["parseSkipped"] = True
                    print(f"[batch] {index}/{len(file_ids)} parse skip file={file_id}", flush=True)

                if args.parse_only:
                    record["indexSkipped"] = True
                else:
                    if not output_md.exists():
                        raise FileNotFoundError(f"Markdown output not found after parse: {output_md}")
                    print(f"[batch] {index}/{len(file_ids)} index start file={file_id}", flush=True)
                    index_result = build_faiss_index(kb_id, file_id)
                    record["indexResult"] = index_result
                    record["indexed"] = bool(index_result.get("ok"))
                    if not index_result.get("ok"):
                        record["ok"] = False
                        record["indexError"] = index_result.get("error", "INDEX_BUILD_ERROR")
                    print(
                        f"[batch] {index}/{len(file_ids)} index done file={file_id} "
                        f"ok={record['indexed']} chunks={index_result.get('chunks')}",
                        flush=True,
                    )

            record["outputExistsAfter"] = output_md.exists()
        except Exception as exc:
            record["ok"] = False
            record["error"] = str(exc)
            record["traceback"] = traceback.format_exc()
            print(f"[batch] {index}/{len(file_ids)} error file={file_id}: {exc}", flush=True)

        record["elapsedSeconds"] = round(time.time() - item_started_at, 3)
        results.append(record)
        _write_jsonl_row(report_jsonl, record)
        print(
            f"[batch] {index}/{len(file_ids)} done file={file_id} ok={record['ok']} "
            f"elapsed={record['elapsedSeconds']}s",
            flush=True,
        )

    summary = {
        "kbId": kb_id,
        "total": len(results),
        "ok": sum(1 for item in results if item.get("ok")),
        "failed": sum(1 for item in results if not item.get("ok")),
        "parsed": sum(1 for item in results if item.get("parsed")),
        "indexed": sum(1 for item in results if item.get("indexed")),
        "elapsedSeconds": round(time.time() - started_at, 3),
        "reportJsonl": str(report_jsonl),
        "results": results,
    }
    report_json.parent.mkdir(parents=True, exist_ok=True)
    report_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"[batch] completed ok={summary['ok']} failed={summary['failed']} "
        f"parsed={summary['parsed']} indexed={summary['indexed']} elapsed={summary['elapsedSeconds']}s",
        flush=True,
    )
    print(f"[batch] report_json={report_json}", flush=True)
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
