from __future__ import annotations

from pathlib import Path


def extract_text_from_docx(docx_path: str | Path) -> str:
    """Extract docket-like text from a Word .docx file.

    Handles both normal paragraphs and tables. For tables, each cell is written on
    its own line so a Bloomberg-style row stored as columns like entry/date/status/
    description becomes compatible with the existing docket parser.
    """
    try:
        from docx import Document
    except ImportError as exc:  # pragma: no cover - dependency guidance
        raise RuntimeError("Word import requires python-docx. Install with: pip install python-docx") from exc

    path = Path(docx_path)
    document = Document(str(path))
    lines: list[str] = []

    # Preserve body order approximately by walking XML blocks. This lets us handle
    # docs that mix paragraphs and tables without dumping all paragraphs first.
    body = document.element.body
    for child in body.iterchildren():
        tag = child.tag.rsplit('}', 1)[-1]
        if tag == 'p':
            text = ''.join(node.text or '' for node in child.iter() if node.tag.rsplit('}', 1)[-1] == 't')
            _append_clean(lines, text)
        elif tag == 'tbl':
            for row in child.iter():
                if row.tag.rsplit('}', 1)[-1] != 'tr':
                    continue
                for cell in row.iter():
                    if cell.tag.rsplit('}', 1)[-1] != 'tc':
                        continue
                    cell_lines: list[str] = []
                    for t in cell.iter():
                        if t.tag.rsplit('}', 1)[-1] == 't' and t.text:
                            cell_lines.append(t.text)
                    _append_clean(lines, ' '.join(cell_lines))

    text = '\n'.join(lines)
    text = _normalize_text(text)
    return text.strip() + ('\n' if text.strip() else '')


def write_docx_text(docx_path: str | Path, output_text_path: str | Path) -> dict:
    text = extract_text_from_docx(docx_path)
    out = Path(output_text_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding='utf-8')
    return {
        'docx_path': str(docx_path),
        'output_text_path': str(out),
        'characters': len(text),
        'lines': text.count('\n') + (1 if text else 0),
        'method': 'python_docx',
        'warnings': [] if text.strip() else ['Word document produced no extractable text.'],
    }


def _append_clean(lines: list[str], text: str) -> None:
    text = _normalize_text(text).strip()
    if not text:
        return
    # Split embedded newlines so parser can see entry numbers/dates as lines.
    for part in text.split('\n'):
        part = part.strip()
        if part:
            lines.append(part)


def _normalize_text(text: str) -> str:
    return text.replace('\r\n', '\n').replace('\r', '\n').replace('\xa0', ' ')
