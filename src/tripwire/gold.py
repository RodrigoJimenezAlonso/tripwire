"""Hand-checked gold set (data/gold/gold.yaml)."""

from __future__ import annotations

from dataclasses import dataclass, field
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
    # every page that states the same fact; retrieval is a hit if any of them is retrieved
    pages: tuple[int, ...] = field(default_factory=tuple)
    difficulty: str = ""
    evidence: str = ""
    notes: str = ""
    verified: bool = False


def _item(raw: dict) -> GoldItem:
    raw = dict(raw)
    if "page" in raw:  # older single-page format
        raw["pages"] = [raw.pop("page")]
    raw["pages"] = tuple(raw.get("pages") or ())
    if not raw["pages"]:
        raise ValueError(f"{raw.get('id')}: no pages")
    return GoldItem(**raw)


def load_gold(path: Path, include_unverified: bool = False) -> list[GoldItem]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    items = [_item(raw) for raw in data.get("items") or []]
    ids = [i.id for i in items]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate ids in gold set")
    return items if include_unverified else [i for i in items if i.verified]
