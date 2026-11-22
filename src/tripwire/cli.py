from __future__ import annotations

import json
from pathlib import Path

import typer

from tripwire.corpus.chunk import chunk_pages
from tripwire.corpus.fetch import fetch_all, load_sources
from tripwire.corpus.parse import parse_pdf

app = typer.Typer(help="Tripwire: audit RAG systems over financial documents.")
corpus = typer.Typer(help="Download and prepare the document corpus.")
app.add_typer(corpus, name="corpus")

DATA = Path("data")
RESULTS = Path("results")


def _pipeline(model: str, k: int):
    # imported lazily so `corpus` commands don't load the embedding model
    from tripwire.target.index import VectorIndex
    from tripwire.target.llm import OllamaChat
    from tripwire.target.rag import RagPipeline

    return RagPipeline(VectorIndex(DATA / "qdrant"), OllamaChat(model=model), k=k)


@app.command()
def index() -> None:
    """Embed all chunks into the local Qdrant index (data/qdrant)."""
    from tripwire.target.index import VectorIndex, load_chunks

    chunks = load_chunks(DATA / "processed" / "chunks.jsonl")
    n = VectorIndex(DATA / "qdrant").rebuild(chunks)
    typer.echo(f"indexed {n} chunks")


@app.command()
def ask(question: str, doc: str = typer.Option(None, help="restrict to one doc_id"),
        model: str = "qwen3:8b", k: int = 5) -> None:
    """Ask the demo RAG a question and show the retrieved pages."""
    ans = _pipeline(model, k).answer(question, doc_id=doc)
    for h in ans.hits:
        typer.echo(f"  retrieved {h.chunk.doc_id} p.{h.chunk.page}  score={h.score:.3f}")
    typer.echo(f"\n{ans.text}")


@app.command()
def baseline(model: str = "qwen3:8b", k: int = 5) -> None:
    """Accuracy of the undefended RAG on the gold set (no attacks)."""
    import datetime as dt

    from tripwire.gold import load_gold
    from tripwire.judge.numbers import grade

    items = load_gold(DATA / "gold" / "gold.yaml")
    if not items:
        raise typer.BadParameter("data/gold/gold.yaml has no items yet - write the gold set first")
    rag = _pipeline(model, k)
    rows = []
    for item in items:
        ans = rag.answer(item.question)
        g = grade(ans.text, item.value, item.unit)
        page_hit = any(h.chunk.doc_id == item.doc_id and h.chunk.page == item.page
                       for h in ans.hits)
        rows.append({"id": item.id, "grade": g, "gold_page_retrieved": page_hit,
                     "answer": ans.text,
                     "retrieved": [f"{h.chunk.doc_id}:p{h.chunk.page}" for h in ans.hits]})
        typer.echo(f"{g:10} page_hit={page_hit!s:5} {item.id}")
    correct = sum(r["grade"] == "correct" for r in rows)
    recall = sum(r["gold_page_retrieved"] for r in rows)
    typer.echo(f"\naccuracy {correct}/{len(rows)}   retrieval hit-rate {recall}/{len(rows)}")
    RESULTS.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = RESULTS / f"baseline-{stamp}.json"
    out.write_text(json.dumps({"model": model, "k": k, "rows": rows}, indent=2), encoding="utf-8")
    typer.echo(f"saved {out}")


@corpus.command("fetch")
def corpus_fetch(force: bool = False) -> None:
    """Download the public annual reports."""
    manifest = fetch_all(DATA / "raw", force=force)
    for doc_id, digest in manifest.items():
        typer.echo(f"{doc_id}  sha256={digest[:12]}")


@corpus.command("build")
def corpus_build(size: int = 1200, overlap: int = 200) -> None:
    """Parse PDFs and write chunks to data/processed/chunks.jsonl."""
    out_dir = DATA / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)
    total = 0
    with (out_dir / "chunks.jsonl").open("w", encoding="utf-8") as f:
        for src in load_sources():
            pages = parse_pdf(DATA / "raw" / f"{src.id}.pdf", src.id)
            chunks = chunk_pages(pages, size, overlap)
            for c in chunks:
                f.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")
            typer.echo(f"{src.id}: {len(pages)} pages -> {len(chunks)} chunks")
            total += len(chunks)
    typer.echo(f"total chunks: {total}")
