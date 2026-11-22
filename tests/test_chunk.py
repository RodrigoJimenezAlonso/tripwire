import pytest

from tripwire.corpus.chunk import chunk_page
from tripwire.corpus.parse import Page, clean


def test_short_page_is_one_chunk():
    chunks = chunk_page(Page("doc", 3, "Net income USD 4.8 billion"))
    assert len(chunks) == 1
    assert chunks[0].page == 3
    assert chunks[0].id == "doc:p3:c0"


def test_long_page_overlaps_and_covers_everything():
    lines = [f"row {i}: value {i * 10}" for i in range(400)]
    page = Page("doc", 1, "\n".join(lines))
    chunks = chunk_page(page, size=500, overlap=100)
    assert len(chunks) > 1
    joined = "\n".join(c.text for c in chunks)
    for line in lines:
        assert line in joined
    assert all(c.page == 1 for c in chunks)


def test_cuts_on_line_breaks_so_table_rows_stay_whole():
    lines = [f"Revenue segment {i} | CHF {i},234 million" for i in range(100)]
    chunks = chunk_page(Page("doc", 1, "\n".join(lines)), size=400, overlap=50)
    for c in chunks[:-1]:
        assert c.text.splitlines()[-1] in lines


def test_overlap_must_be_smaller_than_size():
    with pytest.raises(ValueError):
        chunk_page(Page("doc", 1, "x" * 10), size=100, overlap=100)


def test_clean_removes_soft_hyphens_and_extra_spaces():
    assert clean("4­800  million\n\n\n\nnext") == "4800 million\n\nnext"


def test_clean_strips_control_chars_glued_to_figures():
    # real artefact from the Sika 2025 annual report
    assert clean("11,201.3\x08–4.8%") == "11,201.3 –4.8%"
