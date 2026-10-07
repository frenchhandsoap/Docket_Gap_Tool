from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class ArtifactRow:
    case_folder: str
    path: str
    filename: str
    extension: str
    entry_number: int | None
    matched_rule: str | None


ENTRY_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Entry", re.compile(r"\bEntry\s*#?\s*0*([0-9]{1,6})\b", re.I)),
    ("Document", re.compile(r"\bDoc(?:ument)?\s*#?\s*0*([0-9]{1,6})\b", re.I)),
    ("Docket", re.compile(r"\bDocket\s*#?\s*0*([0-9]{1,6})\b", re.I)),
    # Filename-level leading number only. We intentionally do not scan the full
    # path for this pattern because generic parent folders like "New folder (3)"
    # were being misread as docket entry 3.
    ("Leading", re.compile(r"^\s*0*([0-9]{1,6})(?:[_\-\s.])", re.I)),
]


GENERIC_WRAPPER_RE = re.compile(
    r"^(new folder(?: \([0-9]+\))?|download(?:s|ed)?|documents?|pdfs?|files?|dockets?|case files?|bankruptcy|export)$",
    re.I,
)


def is_generic_wrapper(name: str) -> bool:
    return bool(GENERIC_WRAPPER_RE.match((name or "").strip()))


def extract_entry_number(filename_or_path: str) -> tuple[int | None, str | None]:
    """Extract docket entry number from a filename, not generic parent folders."""
    # Use the base filename by default so parent folders with numbers do not
    # create false downloaded entries.
    text = Path(filename_or_path.replace("\\", "/")).name
    for name, pat in ENTRY_PATTERNS:
        m = pat.search(text)
        if m:
            try:
                return int(m.group(1)), name
            except ValueError:
                return None, None
    return None, None


def _choose_case_folder(path: str, common_root: str | None, second_level_count: int, default_case_folder: str | None = None) -> str:
    parts = [p for p in path.replace("\\", "/").split("/") if p]
    if not parts:
        return default_case_folder or ""

    if default_case_folder:
        # A nested case ZIP often contains files directly or under another
        # generic wrapper. Keep the case ZIP stem as the case folder unless the
        # inner archive clearly contains multiple real case folders.
        if len(parts) == 1:
            return default_case_folder
        if is_generic_wrapper(parts[0]) or parts[0].casefold() == default_case_folder.casefold():
            return default_case_folder
        if second_level_count <= 1:
            return default_case_folder

    if len(parts) == 1:
        return default_case_folder or ""

    # Normal layout: Case Folder / file.pdf
    if len(parts) == 2:
        if default_case_folder and is_generic_wrapper(parts[0]):
            return default_case_folder
        return parts[0]

    # Generic outer wrapper: New folder (3) / Akorn / Entry 1.pdf
    if common_root and parts[0] == common_root:
        if second_level_count > 1 or is_generic_wrapper(common_root):
            return parts[1]

    return default_case_folder or parts[0]


def _common_shape(paths: list[str]) -> tuple[str | None, int]:
    split_paths = [[p for p in path.replace("\\", "/").split("/") if p] for path in paths]
    first_parts = {parts[0] for parts in split_paths if len(parts) >= 2}
    common_root = next(iter(first_parts)) if len(first_parts) == 1 else None
    second_parts = {parts[1] for parts in split_paths if len(parts) >= 3 and (common_root is None or parts[0] == common_root)}
    return common_root, len(second_parts)


def iter_zip_artifacts(zip_path: str | Path, extensions: Iterable[str] = (".pdf", ".zip")) -> list[ArtifactRow]:
    """Inventory docket artifacts inside a ZIP.

    Supports three common layouts:
    1. Case Folder / 123.pdf
    2. Generic Wrapper / Case Folder / 123.pdf
    3. Generic Wrapper / Case Folder.zip / 123.pdf  (nested case ZIPs)

    Entry-level ZIPs are counted as downloaded artifacts only when their ZIP
    filename itself contains an entry number, e.g. "Entry 123.zip". Case bundle
    ZIPs such as "Akorn.zip" are opened and inventoried instead.
    """
    ext_set = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in extensions}
    rows: list[ArtifactRow] = []
    with zipfile.ZipFile(zip_path) as zf:
        rows.extend(_iter_zipfile(zf, ext_set=ext_set, prefix="", default_case_folder=None, depth=0))
    return rows


def _iter_zipfile(
    zf: zipfile.ZipFile,
    *,
    ext_set: set[str],
    prefix: str,
    default_case_folder: str | None,
    depth: int,
) -> list[ArtifactRow]:
    rows: list[ArtifactRow] = []
    infos = [info for info in zf.infolist() if not info.is_dir()]
    relevant_paths = [info.filename for info in infos if Path(info.filename).suffix.lower() in ext_set]
    common_root, second_level_count = _common_shape(relevant_paths)

    for info in infos:
        suffix = Path(info.filename).suffix.lower()
        if suffix not in ext_set:
            continue

        full_path = f"{prefix}{info.filename}" if not prefix else f"{prefix}/{info.filename}"
        filename = Path(info.filename).name
        entry, rule = extract_entry_number(filename)

        if suffix == ".zip":
            # First try to treat non-entry ZIPs as nested case containers.
            nested_rows: list[ArtifactRow] = []
            if depth < 3 and entry is None:
                try:
                    data = zf.read(info)
                    with zipfile.ZipFile(io.BytesIO(data)) as nested:
                        nested_default = Path(filename).stem
                        if is_generic_wrapper(nested_default):
                            nested_default = default_case_folder or nested_default
                        nested_rows = _iter_zipfile(
                            nested,
                            ext_set=ext_set,
                            prefix=full_path,
                            default_case_folder=nested_default,
                            depth=depth + 1,
                        )
                except Exception:
                    nested_rows = []
            if nested_rows:
                rows.extend(nested_rows)
                continue
            # If it was not a readable nested case ZIP but has an entry number,
            # count it as an entry-level downloaded artifact.
            if entry is None:
                continue

        case_folder = _choose_case_folder(info.filename, common_root, second_level_count, default_case_folder)
        rows.append(
            ArtifactRow(
                case_folder=case_folder,
                path=full_path,
                filename=filename,
                extension=suffix,
                entry_number=entry,
                matched_rule=rule,
            )
        )
    return rows


def case_downloaded_entries(zip_path: str | Path, case_folder: str, extensions: Iterable[str] = (".pdf", ".zip")) -> tuple[set[int], list[ArtifactRow]]:
    rows = iter_zip_artifacts(zip_path, extensions)
    norm_target = case_folder.casefold()
    selected = [r for r in rows if r.case_folder.casefold() == norm_target]
    downloaded = {r.entry_number for r in selected if r.entry_number is not None}
    return downloaded, selected


def summarize_zip(zip_path: str | Path, extensions: Iterable[str] = (".pdf", ".zip")) -> list[dict]:
    rows = iter_zip_artifacts(zip_path, extensions)
    by_case: dict[str, list[ArtifactRow]] = {}
    for row in rows:
        by_case.setdefault(row.case_folder, []).append(row)
    out: list[dict] = []
    for case, case_rows in sorted(by_case.items()):
        entries = sorted({r.entry_number for r in case_rows if r.entry_number is not None})
        out.append(
            {
                "case_folder": case,
                "artifact_files": len(case_rows),
                "unique_docket_entries": len(entries),
                "min_entry": entries[0] if entries else None,
                "max_entry": entries[-1] if entries else None,
                "unmatched_artifacts": sum(1 for r in case_rows if r.entry_number is None),
            }
        )
    return out
