"""Hand-written gold set (data/gold/gold.yaml)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class GoldItem:
    id: str
    doc_id: str
    question: str
    answer: str
    value: float
    unit: str
    page: int
    notes: str = ""


def load_gold(path: Path) -> list[GoldItem]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    items = [GoldItem(**item) for item in data.get("items") or []]
    ids = [i.id for i in items]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate ids in gold set")
    return items
