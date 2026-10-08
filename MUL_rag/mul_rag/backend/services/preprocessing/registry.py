from __future__ import annotations

import importlib
import pkgutil
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

import pandas as pd


MethodRunner = Callable[[pd.DataFrame, "PreprocessContext"], Tuple[pd.DataFrame, Dict[str, Any]]]


@dataclass(frozen=True)
class PreprocessContext:
    method_id: str
    config: Dict[str, Any]
    report: Dict[str, Any]
    source_path: Path
    output_dir: Path

    @property
    def method_output_dir(self) -> Path:
        path = self.output_dir / "methods" / self.method_id
        path.mkdir(parents=True, exist_ok=True)
        return path


@dataclass(frozen=True)
class PreprocessMethod:
    id: str
    name: str
    description: str
    runner: MethodRunner
    category: str = "custom"
    method_type: str = "python"
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> Dict[str, Any]:
        data = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "type": self.method_type,
        }
        if self.metadata:
            data["metadata"] = self.metadata
        return data


_METHODS: "OrderedDict[str, PreprocessMethod]" = OrderedDict()
_DISCOVERED_PACKAGES: Set[str] = set()


def register_preprocess_method(
    *,
    method_id: str,
    name: str,
    description: str,
    runner: MethodRunner,
    category: str = "custom",
    method_type: str = "python",
    enabled: bool = True,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    if not method_id or not method_id.strip():
        raise ValueError("Preprocess method id is required.")
    if not callable(runner):
        raise TypeError(f"Runner for preprocess method {method_id!r} must be callable.")

    normalized_id = method_id.strip()
    _METHODS[normalized_id] = PreprocessMethod(
        id=normalized_id,
        name=name,
        description=description,
        runner=runner,
        category=category,
        method_type=method_type,
        enabled=enabled,
        metadata=dict(metadata or {}),
    )


def get_preprocess_method(method_id: str) -> Optional[PreprocessMethod]:
    method = _METHODS.get(str(method_id or "").strip())
    if method and method.enabled:
        return method
    return None


def get_preprocess_methods() -> List[Dict[str, Any]]:
    return [method.to_public_dict() for method in _METHODS.values() if method.enabled]


def valid_preprocess_method_ids() -> Set[str]:
    return {method.id for method in _METHODS.values() if method.enabled}


def dedupe_method_ids(methods: Iterable[str]) -> List[str]:
    known = valid_preprocess_method_ids()
    selected: List[str] = []
    seen = set()
    for method in methods or []:
        method_id = str(method or "").strip()
        if method_id in known and method_id not in seen:
            selected.append(method_id)
            seen.add(method_id)
    return selected


def run_preprocess_method(
    df: pd.DataFrame,
    method_id: str,
    context: PreprocessContext,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    method = get_preprocess_method(method_id)
    if not method:
        context.report["warnings"].append(f"Unknown preprocessing method ignored: {method_id}")
        return df, {}
    return method.runner(df, context)


def discover_preprocess_methods(package_name: str, force: bool = False) -> None:
    if package_name in _DISCOVERED_PACKAGES and not force:
        return

    package = importlib.import_module(package_name)
    package_paths = getattr(package, "__path__", None)
    if not package_paths:
        _DISCOVERED_PACKAGES.add(package_name)
        return

    for module in pkgutil.iter_modules(package_paths):
        if module.name.startswith("_") or module.name in {"base"}:
            continue
        try:
            importlib.import_module(f"{package_name}.{module.name}")
        except Exception:
            continue
    _DISCOVERED_PACKAGES.add(package_name)
