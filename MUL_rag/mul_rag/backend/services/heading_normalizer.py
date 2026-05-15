from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any, Mapping, Optional


_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_MD_HEADING_RE = re.compile(r"^(\s{0,3})(#{1,6})\s*(.*?)\s*#*\s*$")
_TOC_TITLE_RE = re.compile(r"^\s*目\s*录\s*$")
_TOC_ENTRY_RE = re.compile(
    r"^\s*"
    r"(?:"
    r"\d+[、.．]\s*|"
    r"[一二三四五六七八九十百千万]+[、.．]\s*|"
    r"第[一二三四五六七八九十百千万\d]+[章节篇部分]\s*"
    r")"
    r".*"
    r"(?:\.{2,}|。{2,}|…{2,}|·{2,}|\. *\.|_{2,}|[-—]{2,})"
    r".*\d+\s*$"
)

_TOP_NUMBERED_RE = re.compile(r"^\d+\s*[、．.]\s*\S+")
_DOTTED_NUMBERED_RE = re.compile(r"^(\d+(?:[.．]\d+){1,})(?:[.．])?\s*\S+")
_CHAPTER_RE = re.compile(r"^第[一二三四五六七八九十百千万\d]+[章节篇部分]\s*\S*")
_CHINESE_TOP_RE = re.compile(r"^[一二三四五六七八九十]+[、．.]\s*\S+")
_CHINESE_PAREN_RE = re.compile(r"^[（(][一二三四五六七八九十\d]+[）)]\s*\S+")
_ARABIC_PAREN_RE = re.compile(r"^[（(]\d+[）)]\s*\S+")


def _strip_heading_marker(line: str) -> tuple[str, Optional[int], str]:
    """Return (content_without_hash, original_heading_level, indentation)."""
    match = _MD_HEADING_RE.match(line)
    if not match:
        return line.strip(), None, ""
    indent, hashes, text = match.groups()
    return text.strip(), len(hashes), indent


def _looks_like_table_or_markup(text: str) -> bool:
    return (
        not text
        or text.startswith("|")
        or text.startswith("<")
        or text.startswith("!")
        or text.startswith("---")
        or text.startswith("\\pagebreak")
    )


def _is_toc_title(text: str) -> bool:
    return bool(_TOC_TITLE_RE.match(text or ""))


def _is_toc_entry(text: str) -> bool:
    return bool(_TOC_ENTRY_RE.match(text or ""))


def _heading_level_from_numbering(text: str) -> Optional[int]:
    if _looks_like_table_or_markup(text) or _is_toc_entry(text):
        return None

    if _CHAPTER_RE.match(text) or _CHINESE_TOP_RE.match(text):
        return 1

    dotted_match = _DOTTED_NUMBERED_RE.match(text)
    if dotted_match:
        number = dotted_match.group(1).replace("．", ".")
        return min(number.count(".") + 1, 3)

    # Must be checked after dotted numbering: "1.1 ..." is not a top-level title.
    if _TOP_NUMBERED_RE.match(text):
        return 1

    if _CHINESE_PAREN_RE.match(text):
        return 2

    if _ARABIC_PAREN_RE.match(text):
        return 3

    return None


def normalize_markdown_headings(md_text: str) -> str:
    """Normalize Markdown headings before chunking.

    The parser outputs from MinerU, OLMOCR, and the baseline parser are not
    consistent about Markdown heading depth. This normalizer ignores the
    original depth for numbered titles and reconstructs the level from the
    numbering pattern instead.
    """
    normalized: list[str] = []
    in_code_fence = False
    in_toc = False

    for line in md_text.splitlines():
        if _FENCE_RE.match(line):
            in_code_fence = not in_code_fence
            normalized.append(line)
            continue

        if in_code_fence:
            normalized.append(line)
            continue

        text, original_level, indent = _strip_heading_marker(line)
        stripped = text.strip()

        if _is_toc_title(stripped):
            normalized.append(f"{indent}# 目录")
            in_toc = True
            continue

        if in_toc:
            if stripped.startswith("\\pagebreak"):
                in_toc = False
                normalized.append(line)
                continue
            if not stripped or _is_toc_entry(stripped):
                normalized.append(stripped if original_level else line)
                continue

            # A real numbered heading after the TOC means the content has started.
            if _heading_level_from_numbering(stripped):
                in_toc = False
            else:
                normalized.append(stripped if original_level else line)
                continue

        level = _heading_level_from_numbering(stripped)
        if level:
            normalized.append(f"{indent}{'#' * level} {stripped}")
            continue

        # For non-numbered headings, keep the parser's original heading marker
        # as a fallback. Numbered headings above are always rebuilt by rule.
        if original_level:
            level = min(original_level, 3)
            normalized.append(f"{indent}{'#' * level} {stripped}")
        else:
            normalized.append(line)

    return "\n".join(normalized)


def is_toc_metadata(metadata: Mapping[str, Any]) -> bool:
    return any(_is_toc_title(str(metadata.get(f"Header {level}") or "")) for level in range(1, 4))


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize Markdown heading levels before indexing.")
    parser.add_argument("input", type=Path, help="Input Markdown file")
    parser.add_argument("-o", "--output", type=Path, help="Output path. Defaults to stdout.")
    args = parser.parse_args()

    text = args.input.read_text(encoding="utf-8")
    normalized = normalize_markdown_headings(text)
    if args.output:
        args.output.write_text(normalized, encoding="utf-8")
    else:
        print(normalized)


if __name__ == "__main__":
    main()
