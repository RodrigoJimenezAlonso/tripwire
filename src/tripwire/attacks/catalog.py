"""Load and validate the attack catalog and planted documents (both YAML, shipped with the code)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from tripwire.corpus.chunk import Chunk
from tripwire.judge.detectors import DETECTORS

HERE = Path(__file__).parent
CATEGORIES = ("direct_injection", "indirect_injection", "numeric_poisoning", "leakage")
PLANTED_PREFIX = "planted:"


@dataclass(frozen=True)
class Attack:
    id: str
    category: str
    title: str
    question: str
    success: tuple[dict, ...]
    planted: tuple[str, ...] = field(default_factory=tuple)
    gold: str | None = None


def load_planted(path: Path = HERE / "planted.yaml") -> dict[str, Chunk]:
    return load_planted_docs(yaml.safe_load(path.read_text(encoding="utf-8"))["docs"])


def load_planted_docs(docs: list[dict]) -> dict[str, Chunk]:
    out: dict[str, Chunk] = {}
    for d in docs:
        if d["id"] in out:
            raise ValueError(f"duplicate planted id {d['id']}")
        out[d["id"]] = Chunk(id=f"{PLANTED_PREFIX}{d['id']}", doc_id=d["doc_id"],
                             page=int(d["page"]), text=d["text"].strip())
    return out


def load_attacks(path: Path = HERE / "catalog.yaml",
                 planted: dict[str, Chunk] | None = None) -> list[Attack]:
    planted = load_planted() if planted is None else planted
    attacks = []
    for raw in yaml.safe_load(path.read_text(encoding="utf-8"))["attacks"]:
        a = Attack(id=raw["id"], category=raw["category"], title=raw["title"],
                   question=raw["question"].strip(), success=tuple(raw["success"]),
                   planted=tuple(raw.get("planted") or ()), gold=raw.get("gold"))
        if a.category not in CATEGORIES:
            raise ValueError(f"{a.id}: unknown category {a.category}")
        if not a.success:
            raise ValueError(f"{a.id}: no success detectors")
        for spec in a.success:
            if spec.get("type") not in DETECTORS:
                raise ValueError(f"{a.id}: unknown detector {spec.get('type')}")
        missing = [p for p in a.planted if p not in planted]
        if missing:
            raise ValueError(f"{a.id}: unknown planted docs {missing}")
        attacks.append(a)
    ids = [a.id for a in attacks]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate attack ids")
    return attacks


def load_catalog(name: str = "catalog") -> tuple[list[Attack], dict[str, Chunk]]:
    """Attacks from attacks/<name>.yaml. A catalog may bring its own planted `docs:`, which are
    added to the shared planted.yaml (ids must not clash)."""
    path = HERE / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"no attack catalog {path}")
    planted = load_planted()
    own = yaml.safe_load(path.read_text(encoding="utf-8")).get("docs")
    if own:
        extra = load_planted_docs(own)
        clash = set(extra) & set(planted)
        if clash:
            raise ValueError(f"{name}: planted ids already used in planted.yaml: {sorted(clash)}")
        planted = {**planted, **extra}
    return load_attacks(path, planted=planted), planted


def is_planted(chunk: Chunk) -> bool:
    return chunk.id.startswith(PLANTED_PREFIX)
