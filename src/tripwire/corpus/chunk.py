"""Split pages into overlapping chunks.

Chunks never cross a page boundary: in annual reports a page is usually one table or one topic,
and keeping the page number exact matters more than squeezing context together.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from tripwire.corpus.parse import Page


@dataclass(frozen=True)
class Chunk:
    id: str
    doc_id: str
    page: int
    text: str

    def to_dict(self) -> dict:
        return asdict(self)


def chunk_page(page: Page, size: int = 1200, overlap: int = 200) -> list[Chunk]:
    if overlap >= size:
        raise ValueError("overlap must be smaller than size")
    text = page.text
    chunks: list[Chunk] = []
    start = 0
    n = 0
    while start < len(text):
        end = min(start + size, len(text))
        # prefer to cut at a line break so table rows stay whole
        if end < len(text):
            cut = text.rfind("\n", start + size // 2, end)
            if cut != -1:
                end = cut
        piece = text[start:end].strip()
        if piece:
            chunks.append(Chunk(id=f"{page.doc_id}:p{page.page}:c{n}", doc_id=page.doc_id,
                                page=page.page, text=piece))
            n += 1
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def chunk_pages(pages: list[Page], size: int = 1200, overlap: int = 200) -> list[Chunk]:
    return [c for p in pages for c in chunk_page(p, size, overlap)]
