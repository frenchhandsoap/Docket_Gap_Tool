from __future__ import annotations

import shutil
from pathlib import Path


def extract_text_from_pdf(
    pdf_path: str | Path,
    *,
    password: str | None = None,
    max_pages: int | None = None,
    page_separator: str = "\n\n--- PAGE {page_number} ---\n\n",
) -> str:
    """Extract selectable text from a docket PDF printout with pypdf.

    This is the first pass. It is fast and works for browser-generated PDFs with
    selectable text. For scanned/image-only PDFs, use write_pdf_text(..., ocr='auto'
    or ocr='force') to fall back to Tesseract OCR.
    """
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency guidance
        raise RuntimeError("PDF import requires pypdf. Install with: pip install pypdf") from exc

    path = Path(pdf_path)
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        if password is None:
            password = ""
        result = reader.decrypt(password)
        if result == 0:
            raise ValueError(f"Could not decrypt PDF: {path}")

    pages = reader.pages
    limit = len(pages) if max_pages is None else min(max_pages, len(pages))
    parts: list[str] = []
    for idx in range(limit):
        page = pages[idx]
        try:
            text = page.extract_text(extraction_mode="layout") or ""
        except TypeError:
            text = page.extract_text() or ""
        except Exception:
            text = page.extract_text() or ""
        if text.strip():
            if parts:
                parts.append(page_separator.format(page_number=idx + 1))
            parts.append(text)

    extracted = "".join(parts)
    extracted = _normalize_text(extracted)
    return extracted.strip() + ("\n" if extracted.strip() else "")


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def extract_text_from_pdf_ocr(
    pdf_path: str | Path,
    *,
    max_pages: int | None = None,
    dpi: int = 200,
    language: str = "eng",
    page_separator: str = "\n\n--- OCR PAGE {page_number} ---\n\n",
) -> str:
    """OCR a PDF with PyMuPDF rendering + Tesseract.

    This requires the Tesseract system binary to be installed. The package includes
    helper install scripts/instructions, but the binary is OS-specific and is not
    bundled inside the zip.
    """
    if not tesseract_available():
        raise RuntimeError(
            "Tesseract was not found on PATH. Install it, then rerun. "
            "See INSTALL_TESSERACT.md in this package."
        )
    try:
        import fitz  # PyMuPDF
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError(
            "OCR requires pymupdf, pytesseract, and pillow. Install with: "
            "pip install pymupdf pytesseract pillow"
        ) from exc

    doc = fitz.open(str(pdf_path))
    limit = doc.page_count if max_pages is None else min(max_pages, doc.page_count)
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    parts: list[str] = []
    for idx in range(limit):
        page = doc.load_page(idx)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        text = pytesseract.image_to_string(img, lang=language) or ""
        text = _normalize_text(text)
        if text.strip():
            if parts:
                parts.append(page_separator.format(page_number=idx + 1))
            parts.append(text)
    out = "".join(parts)
    return out.strip() + ("\n" if out.strip() else "")


def write_pdf_text(
    pdf_path: str | Path,
    output_text_path: str | Path,
    *,
    password: str | None = None,
    max_pages: int | None = None,
    ocr: str = "auto",
    min_selectable_chars: int = 200,
    ocr_dpi: int = 200,
    ocr_language: str = "eng",
) -> dict:
    """Extract PDF text, using OCR as backup when needed.

    ocr values:
    - auto: use OCR only when selectable text is very short or empty
    - force: skip selectable extraction and OCR every page
    - off: never OCR
    """
    ocr = (ocr or "auto").lower()
    if ocr not in {"auto", "force", "off"}:
        raise ValueError("ocr must be one of: auto, force, off")

    method = "selectable"
    selectable_text = ""
    if ocr != "force":
        selectable_text = extract_text_from_pdf(pdf_path, password=password, max_pages=max_pages)

    use_ocr = ocr == "force" or (ocr == "auto" and len(selectable_text.strip()) < min_selectable_chars)
    warnings: list[str] = []
    if use_ocr:
        try:
            text = extract_text_from_pdf_ocr(
                pdf_path,
                max_pages=max_pages,
                dpi=ocr_dpi,
                language=ocr_language,
            )
            method = "tesseract_ocr"
        except Exception as exc:
            if selectable_text.strip():
                text = selectable_text
                method = "selectable_fallback_after_ocr_error"
                warnings.append(f"OCR failed, used selectable text instead: {exc}")
            else:
                text = selectable_text
                method = "failed_empty"
                warnings.append(str(exc))
    else:
        text = selectable_text

    out = Path(output_text_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return {
        "pdf_path": str(pdf_path),
        "output_text_path": str(out),
        "characters": len(text),
        "lines": text.count("\n") + (1 if text else 0),
        "method": method,
        "tesseract_available": tesseract_available(),
        "appears_empty_or_scanned": len(text.strip()) < min_selectable_chars,
        "warnings": warnings,
    }


def _normalize_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")
