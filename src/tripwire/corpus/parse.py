"""PDF -> per-page text. Page numbers are kept so every answer can cite where it came from."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf


@dataclass(frozen=True)
class Page:
    doc_id: str
    page: int  # 1-based, as printed by PDF viewers
    text: str


_WS = re.compile(r"[ \t ]+")
_BLANK_LINES = re.compile(r"\n{3,}")
# Some report PDFs (e.g. Sika 2025) embed control characters such as \x08 right after figures:
# "11,201.3\x08-4.8%". Left in, they make a correct number look wrong to the checker.
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean(text: str) -> str:
    text = _CONTROL.sub(" ", text)
    text = text.replace("­", "")  # soft hyphens break number matching
    text = _WS.sub(" ", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    return _BLANK_LINES.sub("\n\n", text).strip()


def parse_pdf(path: Path, doc_id: str) -> list[Page]:
    pages: list[Page] = []
    with pymupdf.open(path) as doc:
        for i, page in enumerate(doc, start=1):
            text = clean(page.get_text("text"))
            if text:
                pages.append(Page(doc_id=doc_id, page=i, text=text))
    return pages
