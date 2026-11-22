"""Download the public reports listed in sources.yaml."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import httpx
import yaml

SOURCES_FILE = Path(__file__).with_name("sources.yaml")


@dataclass(frozen=True)
class Source:
    id: str
    company: str
    sector: str
    year: int
    url: str


def load_sources(path: Path = SOURCES_FILE) -> list[Source]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [Source(**doc) for doc in data["documents"]]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fetch_all(raw_dir: Path, force: bool = False) -> dict[str, str]:
    """Download every source PDF into raw_dir. Returns {doc_id: sha256}."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, str] = {}
    headers = {"User-Agent": "tripwire-corpus-fetch/0.1"}
    with httpx.Client(follow_redirects=True, timeout=120, headers=headers) as client:
        for src in load_sources():
            target = raw_dir / f"{src.id}.pdf"
            if force or not target.exists():
                resp = client.get(src.url)
                resp.raise_for_status()
                if not resp.content.startswith(b"%PDF"):
                    raise ValueError(f"{src.id}: URL did not return a PDF")
                target.write_bytes(resp.content)
            manifest[src.id] = sha256(target)
    (raw_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
