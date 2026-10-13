"""Simple local keyword retrieval over policy / SOP / guideline files (.docx and .pdf).

No embeddings and no vector database: documents are split into chunks by heading and ranked with BM25.
Every result carries the real file name and section (or page), so a citation is never invented.
"""
from __future__ import annotations

import logging
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

MAX_CHUNK_CHARS = 1400
MIN_CHUNK_CHARS = 40
EXCERPT_CHARS = 900
STOPWORDS = frozenset(
    "the and for are was were with that this from have has had not but all can will its their they them than then "
    "into over under per out any may must should shall each also more most such only other these those been being "
    "which while within about above below between both does did done doing our your you who whom what when where "
    "why how yet one two".split()
)
_DOC_CODE = re.compile(r"([A-Z]{2,4}(?:-[A-Z]{2,4})?-\d{3})")
_NUMBERED_HEADING = re.compile(r"^\d+(\.\d+)*[.)]?\s+\S")
_WORD = re.compile(r"[a-z][a-z0-9&']{2,}")


def tokenize(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.lower()) if w not in STOPWORDS]


def _looks_like_heading(text: str) -> bool:
    return len(text) <= 90 and not text.endswith(".") and bool(_NUMBERED_HEADING.match(text))


# --------------------------------------------------------------------------------------------- parsing
def _docx_blocks(path: Path) -> list[tuple[str, str]]:
    """Return [(kind, text)] in document order, kind is 'heading' or 'text'."""
    import docx  # python-docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    document = docx.Document(str(path))
    blocks: list[tuple[str, str]] = []
    for child in document.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            p = Paragraph(child, document)
            text = p.text.strip()
            if not text:
                continue
            style = (p.style.name or "") if p.style is not None else ""
            blocks.append(("heading" if style.lower().startswith("heading") or _looks_like_heading(text) else "text", text))
        elif tag == "tbl":
            table = Table(child, document)
            for row in table.rows:
                cells: list[str] = []
                for cell in row.cells:
                    t = cell.text.strip().replace("\n", " ")
                    if t and (not cells or cells[-1] != t):   # merged cells repeat their text
                        cells.append(t)
                if cells:
                    blocks.append(("text", " | ".join(cells)))
    return blocks


def _pdf_pages(path: Path) -> list[tuple[int, str]]:
    from pypdf import PdfReader

    return [(i, (page.extract_text() or "")) for i, page in enumerate(PdfReader(str(path)).pages, start=1)]


def _chunks_from_docx(path: Path) -> list[dict[str, Any]]:
    chunks, section, buf = [], "Introduction", []

    def flush():
        text = "\n".join(buf).strip()
        if len(text) >= MIN_CHUNK_CHARS:
            chunks.append({"section": section, "page": None, "text": text})
        buf.clear()

    for kind, text in _docx_blocks(path):
        if kind == "heading":
            flush()
            section = text
        else:
            if sum(len(b) for b in buf) + len(text) > MAX_CHUNK_CHARS:
                flush()
            buf.append(text)
    flush()
    return chunks


def _chunks_from_pdf(path: Path) -> list[dict[str, Any]]:
    chunks = []
    section = "Introduction"
    for page_no, text in _pdf_pages(path):
        buf: list[str] = []
        start_section = section

        def flush():
            body = "\n".join(buf).strip()
            if len(body) >= MIN_CHUNK_CHARS:
                chunks.append({"section": start_section, "page": page_no, "text": body})
            buf.clear()

        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            if _looks_like_heading(line):
                flush()
                section = start_section = line
            elif sum(len(b) for b in buf) + len(line) > MAX_CHUNK_CHARS:
                flush()
                start_section = section
                buf.append(line)
            else:
                buf.append(line)
        flush()
    return chunks


# ----------------------------------------------------------------------------------------------- index
class PolicyIndex:
    def __init__(self, directories: list[Path]):
        self.directories = [Path(d) for d in directories]
        self.chunks: list[dict[str, Any]] = []
        self.files: list[str] = []
        self.warnings: list[str] = []
        self._tf: list[Counter] = []
        self._df: Counter = Counter()
        self._avg_len = 1.0
        self._build()

    def _build(self) -> None:
        for directory in self.directories:
            if not directory.is_dir():
                self.warnings.append(f"Policy folder not found: {directory}")
                continue
            for path in sorted(directory.iterdir()):
                if path.name.startswith("~$") or path.suffix.lower() not in (".docx", ".pdf"):
                    continue
                try:
                    parts = _chunks_from_docx(path) if path.suffix.lower() == ".docx" else _chunks_from_pdf(path)
                except ImportError as exc:
                    self.warnings.append(f"{path.name} skipped: missing library ({exc.name}). pip install python-docx pypdf")
                    continue
                except Exception as exc:  # noqa: BLE001 - a broken file must not stop the others
                    self.warnings.append(f"{path.name} could not be read: {exc}")
                    continue
                match = _DOC_CODE.search(path.stem)
                code = match.group(1) if match else None
                self.files.append(path.name)
                for n, part in enumerate(parts, start=1):
                    self.chunks.append({"chunk_id": f"{path.stem}#{n}", "source_file": path.name,
                                        "doc_code": code, **part})
        for c in self.chunks:
            tokens = tokenize(c["section"]) * 2 + tokenize(c["text"])      # headings count double
            tf = Counter(tokens)
            self._tf.append(tf)
            self._df.update(tf.keys())
        total = sum(sum(tf.values()) for tf in self._tf)
        self._avg_len = (total / len(self._tf)) if self._tf else 1.0

    def search(self, query: str, k: int = 4, doc_code: str | None = None) -> list[dict[str, Any]]:
        terms = tokenize(query)
        if not terms or not self.chunks:
            return []
        n_docs, k1, b = len(self.chunks), 1.5, 0.75
        scored = []
        for chunk, tf in zip(self.chunks, self._tf):
            length = sum(tf.values()) or 1
            score = 0.0
            for term in set(terms):
                f = tf.get(term, 0)
                if not f:
                    continue
                idf = math.log(1 + (n_docs - self._df[term] + 0.5) / (self._df[term] + 0.5))
                score += idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * length / self._avg_len))
            if score <= 0:
                continue
            if doc_code and chunk["doc_code"] == doc_code:
                score *= 1.8                                            # the finding names this document
            scored.append((score, chunk))
        scored.sort(key=lambda x: -x[0])
        results = []
        for score, c in scored[:k]:
            text = c["text"]
            results.append({
                "chunk_id": c["chunk_id"], "source_file": c["source_file"], "doc_code": c["doc_code"],
                "section": c["section"], "page": c["page"],
                "text": text if len(text) <= EXCERPT_CHARS else text[:EXCERPT_CHARS].rsplit(" ", 1)[0] + " ...",
                "score": round(score, 3),
            })
        return results

    def summary(self) -> dict[str, Any]:
        return {"documents": len(self.files), "chunks": len(self.chunks), "files": self.files,
                "warnings": self.warnings}


_index: PolicyIndex | None = None


def get_index() -> PolicyIndex:
    global _index
    if _index is None:
        _index = PolicyIndex(settings.POLICY_DOC_DIRS)
    return _index


def reset_index() -> None:
    global _index
    _index = None


def retrieve_for_finding(finding: dict[str, Any], question: str | None = None, k: int = 4) -> list[dict[str, Any]]:
    hints = finding.get("retrieval_hints") or {}
    query = " ".join([finding.get("title", ""), finding.get("metric") or "", *hints.get("keywords", []),
                      question or ""])
    return get_index().search(query, k=k, doc_code=hints.get("process_id"))
