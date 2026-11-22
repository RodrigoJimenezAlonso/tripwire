from pathlib import Path

import pytest

from tripwire.gold import load_gold

ITEM = """
  - id: {id}
    doc_id: sika-ar-2025
    question: "q"
    answer: "a"
    value: 1.0
    unit: "%"
    {pages}
    verified: {verified}
"""


def write(tmp_path: Path, *items: str) -> Path:
    p = tmp_path / "gold.yaml"
    p.write_text("items:\n" + "".join(items), encoding="utf-8")
    return p


def test_unverified_items_are_skipped_by_default(tmp_path):
    path = write(tmp_path,
                 ITEM.format(id="a", pages="pages: [5, 2]", verified="true"),
                 ITEM.format(id="b", pages="pages: [7]", verified="false"))
    assert [i.id for i in load_gold(path)] == ["a"]
    assert [i.id for i in load_gold(path, include_unverified=True)] == ["a", "b"]


def test_single_page_format_still_loads(tmp_path):
    path = write(tmp_path, ITEM.format(id="a", pages="page: 5", verified="true"))
    assert load_gold(path)[0].pages == (5,)


def test_duplicate_ids_rejected(tmp_path):
    path = write(tmp_path,
                 ITEM.format(id="a", pages="pages: [5]", verified="true"),
                 ITEM.format(id="a", pages="pages: [6]", verified="true"))
    with pytest.raises(ValueError):
        load_gold(path)


def test_real_gold_file_loads():
    items = load_gold(Path("data/gold/gold.yaml"), include_unverified=True)
    assert len(items) >= 10
    assert all(i.pages for i in items)
