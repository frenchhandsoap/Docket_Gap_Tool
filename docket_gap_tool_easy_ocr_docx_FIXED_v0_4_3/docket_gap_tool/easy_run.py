from __future__ import annotations

import csv
import json
import re
import sys
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

from .analyzer import analyze_case, write_csv
from .inventory import summarize_zip
from .pdf_import import tesseract_available, write_pdf_text
from .docx_import import write_docx_text
from .workbook import make_output_workbook


@dataclass
class CaseJob:
    case_name: str
    case_folder: str
    artifact_zip: Path
    docket_pdf: Path | None = None
    docket_text: Path | None = None
    docket_docx: Path | None = None
    match_score: float | None = None
    match_note: str = ""


def main(argv: list[str] | None = None) -> int:
    root = Path.cwd()
    # When run as python -m from a different location, prefer the folder containing input/.
    if not (root / "input").exists():
        package_root = Path(__file__).resolve().parents[1]
        if (package_root / "input").exists():
            root = package_root

    input_dir = root / "input"
    artifact_dir = input_dir / "downloaded_artifacts"
    pdf_dir = input_dir / "docket_pdfs"
    text_dir = input_dir / "docket_texts"
    word_dir = input_dir / "docket_word_docs"
    config_path = root / "config" / "cases.csv"
    output_dir = root / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Docket Gap Tool - one-click run")
    print(f"Working folder: {root}")
    print(f"Tesseract OCR available: {tesseract_available()}")

    artifact_zips = sorted(artifact_dir.glob("*.zip"))
    if not artifact_zips:
        print("ERROR: No artifact ZIP found in input/downloaded_artifacts", file=sys.stderr)
        print("Put your downloaded case ZIP there and rerun.", file=sys.stderr)
        return 2

    try:
        jobs = _jobs_from_config(config_path, root, artifact_zips)
        if jobs:
            print(f"Loaded {len(jobs)} case(s) from config/cases.csv")
        else:
            jobs = _auto_match_jobs(artifact_zips, pdf_dir, text_dir, word_dir)
            print(f"Auto-matched {len(jobs)} case(s) from input folders")
    except Exception as exc:
        print(f"ERROR while building case list: {exc}", file=sys.stderr)
        return 2

    if not jobs:
        print("ERROR: No docket PDF/text/Word files found in input/docket_pdfs, input/docket_texts, or input/docket_word_docs", file=sys.stderr)
        return 2

    _write_match_report(output_dir / "auto_matched_cases.csv", jobs)
    _write_folder_summaries(output_dir, artifact_zips)

    case_rows: dict[str, list[dict]] = {}
    summaries: list[dict] = []
    all_full: list[dict] = []
    all_review: list[dict] = []
    all_skipped: list[dict] = []
    warnings: list[str] = []

    for job in jobs:
        print(f"\nAnalyzing: {job.case_name}")
        print(f"  artifact zip: {job.artifact_zip.name}")
        print(f"  case folder:  {job.case_folder}")
        if job.docket_pdf:
            print(f"  docket PDF:   {job.docket_pdf.name}")
        if job.docket_text:
            print(f"  docket text:  {job.docket_text.name}")
        if job.docket_docx:
            print(f"  docket Word:  {job.docket_docx.name}")
        if job.match_score is not None:
            print(f"  match score:  {job.match_score:.3f}")
        if job.match_score is not None and job.match_score < 0.55:
            warnings.append(f"Low-confidence match for {job.case_name}: score {job.match_score:.3f}. Review auto_matched_cases.csv.")

        docket_text_path = _materialize_docket_text(job, output_dir)
        slug = _slug(job.case_name)
        full, keep, review, skipped, summary = analyze_case(
            case_name=job.case_name,
            case_folder=job.case_folder,
            docket_text_path=docket_text_path,
            artifact_zip_path=job.artifact_zip,
            rules_path=root / "rules" / "default_rules.json",
            artifact_extensions=(".pdf", ".zip"),
        )
        summary["match_score"] = job.match_score
        summary["match_note"] = job.match_note
        case_rows[job.case_name] = keep
        summaries.append(summary)
        all_full.extend(full)
        all_review.extend(review)
        all_skipped.extend(skipped)

        write_csv(output_dir / f"{slug}_full_comparison.csv", full)
        write_csv(output_dir / f"{slug}_keep_request.csv", keep)
        write_csv(output_dir / f"{slug}_review_optional.csv", review)
        write_csv(output_dir / f"{slug}_skipped.csv", skipped)
        print(f"  final needed: {summary['final_keep_request']} ({summary['downloadable_now']} downloadable, {summary['request_needed']} request)")
        if summary.get("unknown_status"):
            warnings.append(f"{job.case_name}: {summary['unknown_status']} final rows had unknown Bloomberg status.")

    all_keep = [r for rows in case_rows.values() for r in rows]
    write_csv(output_dir / "all_final_keep_request.csv", all_keep)
    write_csv(output_dir / "all_full_comparison.csv", all_full)
    write_csv(output_dir / "all_review_optional.csv", all_review)
    write_csv(output_dir / "all_skipped.csv", all_skipped)

    audit_notes = [
        "Generated by docket-gap-tool one-click run.",
        "Downloaded artifact detection counts both .pdf and entry-level .zip files.",
        "Docket PDFs are first extracted as selectable text; Tesseract OCR is used as backup when extraction is empty/short and Tesseract is installed.",
        "Rows classified as review_optional are excluded from final sheets by default. Review all_review_optional.csv for borderline items.",
    ] + warnings

    workbook_path = output_dir / "docket_gap_download_request_by_case.xlsx"
    make_output_workbook(workbook_path, case_rows, summaries, audit_notes)

    summary_payload = {
        "workbook": str(workbook_path),
        "cases": summaries,
        "total_final_keep_request": len(all_keep),
        "total_downloadable_now": sum(1 for r in all_keep if r.get("action") == "Downloadable now"),
        "total_request_needed": sum(1 for r in all_keep if r.get("action") == "Request needed"),
        "warnings": warnings,
    }
    (output_dir / "run_summary.json").write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")

    print("\nDONE")
    print(f"Workbook: {workbook_path}")
    print(f"Total final needed: {summary_payload['total_final_keep_request']}")
    print(f"Downloadable now: {summary_payload['total_downloadable_now']}")
    print(f"Request needed: {summary_payload['total_request_needed']}")
    if warnings:
        print("\nWarnings:")
        for w in warnings:
            print(f"- {w}")
    return 0


def _jobs_from_config(config_path: Path, root: Path, default_zips: list[Path]) -> list[CaseJob]:
    if not config_path.exists():
        return []
    rows: list[dict[str, str]] = []
    with config_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if any((v or "").strip() for v in row.values()):
                rows.append({k: (v or "").strip() for k, v in row.items() if k is not None})
    jobs: list[CaseJob] = []
    for row in rows:
        if not row.get("case_name") or row.get("case_name", "").lstrip().startswith("#"):
            continue
        artifact_zip = _resolve_path(row.get("artifact_zip"), root) if row.get("artifact_zip") else (default_zips[0] if len(default_zips) == 1 else None)
        if artifact_zip is None:
            raise ValueError(f"Config row for {row.get('case_name')} needs artifact_zip because multiple zips exist.")
        docket_pdf = _resolve_path(row.get("docket_pdf"), root) if row.get("docket_pdf") else None
        docket_text = _resolve_path(row.get("docket_text"), root) if row.get("docket_text") else None
        docket_docx = _resolve_path(row.get("docket_docx"), root) if row.get("docket_docx") else None
        if sum(bool(x) for x in (docket_pdf, docket_text, docket_docx)) != 1:
            raise ValueError(f"Config row for {row.get('case_name')} needs exactly one of docket_pdf, docket_text, or docket_docx.")
        jobs.append(CaseJob(
            case_name=row["case_name"],
            case_folder=row.get("case_folder") or row["case_name"],
            artifact_zip=artifact_zip,
            docket_pdf=docket_pdf,
            docket_text=docket_text,
            docket_docx=docket_docx,
            match_note="from config/cases.csv",
        ))
    return jobs


def _auto_match_jobs(artifact_zips: list[Path], pdf_dir: Path, text_dir: Path, word_dir: Path) -> list[CaseJob]:
    def usable(p: Path) -> bool:
        stem = p.stem.casefold()
        return not (stem.startswith("put_") or stem.startswith("optional_") or stem.startswith("readme") or stem.startswith("example"))

    sources: list[tuple[Path, str]] = []
    sources.extend((p, "pdf") for p in sorted(pdf_dir.glob("*.pdf")) if usable(p))
    sources.extend((p, "text") for p in sorted(text_dir.glob("*.txt")) if usable(p))
    sources.extend((p, "docx") for p in sorted(word_dir.glob("*.docx")) if usable(p))
    if not sources:
        return []

    cases: list[tuple[Path, str]] = []
    for z in artifact_zips:
        for row in summarize_zip(z, extensions=(".pdf", ".zip")):
            folder = row.get("case_folder") or ""
            if folder:
                cases.append((z, folder))

    if not cases:
        raise ValueError("No case folders with .pdf/.zip artifacts were found in the artifact ZIP(s).")

    jobs: list[CaseJob] = []
    used_sources: set[Path] = set()
    for src, kind in sources:
        if len(sources) == 1 and len(cases) == 1:
            z, folder = cases[0]
            score = 1.0
        else:
            z, folder, score = _best_case_match(src.stem, cases)
        used_sources.add(src)
        # Use the docket source filename as the case display name. The artifact folder is
        # only used for matching downloaded entries. This avoids sheet names like
        # "New folder (3)" when a user zipped a generic parent folder.
        display_name = src.stem
        if any(j.case_name == display_name for j in jobs):
            display_name = f"{src.stem} ({folder})"
        jobs.append(CaseJob(
            case_name=display_name,
            case_folder=folder,
            artifact_zip=z,
            docket_pdf=src if kind == "pdf" else None,
            docket_text=src if kind == "text" else None,
            docket_docx=src if kind == "docx" else None,
            match_score=score,
            match_note="auto-matched by source filename to artifact case folder",
        ))
    return jobs


def _best_case_match(source_stem: str, cases: list[tuple[Path, str]]) -> tuple[Path, str, float]:
    scored = []
    for z, folder in cases:
        score = _similarity(source_stem, folder)
        # A small boost if the source stem appears in the artifact ZIP name too.
        score = max(score, _similarity(source_stem, f"{z.stem} {folder}") * 0.95)
        scored.append((score, z, folder))
    scored.sort(reverse=True, key=lambda x: x[0])
    score, z, folder = scored[0]
    return z, folder, score


def _similarity(a: str, b: str) -> float:
    na = _norm_tokens(a)
    nb = _norm_tokens(b)
    if not na or not nb:
        return 0.0
    seq = SequenceMatcher(None, " ".join(na), " ".join(nb)).ratio()
    inter = len(set(na) & set(nb))
    union = len(set(na) | set(nb)) or 1
    jaccard = inter / union
    return max(seq, jaccard)


def _norm_tokens(s: str) -> list[str]:
    s = s.casefold()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    stop = {"inc", "corp", "corporation", "llc", "l", "p", "lp", "co", "company", "docket", "printout", "case", "bk"}
    return [t for t in s.split() if t and t not in stop]


def _materialize_docket_text(job: CaseJob, output_dir: Path) -> Path:
    extracted_dir = output_dir / "_extracted_text"
    extracted_dir.mkdir(parents=True, exist_ok=True)
    if job.docket_text:
        return job.docket_text
    out = extracted_dir / f"{_slug(job.case_name)}.txt"
    if job.docket_docx:
        result = write_docx_text(job.docket_docx, out)
        if result.get("warnings"):
            print("  Word extraction warnings:")
            for w in result["warnings"]:
                print(f"    - {w}")
        print(f"  Word text method: {result.get('method')} ({result.get('characters')} chars)")
        return out
    assert job.docket_pdf is not None
    result = write_pdf_text(job.docket_pdf, out, ocr="auto")
    if result.get("warnings"):
        print("  PDF extraction warnings:")
        for w in result["warnings"]:
            print(f"    - {w}")
    print(f"  PDF text method: {result.get('method')} ({result.get('characters')} chars)")
    return out



def _write_folder_summaries(output_dir: Path, artifact_zips: list[Path]) -> None:
    rows: list[dict] = []
    for z in artifact_zips:
        for row in summarize_zip(z, extensions=(".pdf", ".zip")):
            out = {"artifact_zip": str(z), **row}
            rows.append(out)
    path = output_dir / "folder_summary.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        fieldnames = ["artifact_zip", "case_folder", "artifact_files", "unique_docket_entries", "min_entry", "max_entry", "unmatched_artifacts"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

def _write_match_report(path: Path, jobs: list[CaseJob]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["case_name", "case_folder", "artifact_zip", "docket_pdf", "docket_text", "docket_docx", "match_score", "match_note"])
        writer.writeheader()
        for j in jobs:
            writer.writerow({
                "case_name": j.case_name,
                "case_folder": j.case_folder,
                "artifact_zip": str(j.artifact_zip),
                "docket_pdf": str(j.docket_pdf or ""),
                "docket_text": str(j.docket_text or ""),
                "docket_docx": str(j.docket_docx or ""),
                "match_score": "" if j.match_score is None else f"{j.match_score:.3f}",
                "match_note": j.match_note,
            })


def _resolve_path(value: str | None, root: Path) -> Path | None:
    if not value:
        return None
    p = Path(value)
    if not p.is_absolute():
        p = root / p
    return p


def _slug(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()
    return s or "case"


if __name__ == "__main__":
    raise SystemExit(main())
