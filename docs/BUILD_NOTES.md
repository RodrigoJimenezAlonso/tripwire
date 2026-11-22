# Build notes - explain it back

Short notes on each piece, so every design choice can be explained in an interview. Rewrite them in your own words as you go.

## Phase 1 - corpus

- **sources.yaml + fetch.py**: three public 2025 annual reports (Swiss Re, Sika, UBS). The PDFs are not committed; we store a SHA-256 per file so any result can be traced to the exact document that was indexed.
- **parse.py**: PyMuPDF, page by page. Keeps the page number because every answer must be checkable against a page.
  - Found issue: the Sika PDF has `\x08` control characters glued to figures (`11,201.3\x08-4.8%`). They are stripped in `clean()` (with a test), otherwise correct answers would be marked wrong.
  - Chart pages produce runs of axis numbers (`1,600 / 1,800 / 2,000`). Kept on purpose: they are realistic distractors and a likely source of wrong-number answers worth measuring.
- **chunk.py**: ~1,200 characters with 200 overlap, never crossing a page, cutting at line breaks so table rows stay whole. Trade-off: some chunks are small, but page citations stay exact.
- Result: 992 pages -> ~4,000 chunks.

Questions to be ready for:
- Why character-based and not token-based chunking? (simple, model-independent, good enough for a baseline; tokens matter when you are close to the context limit)
- Why not cross pages? (citation accuracy; tables rarely span pages)
- What would you change for production? (table-aware extraction, layout model, dedupe repeated headers/footers)

## Phase 2 - the RAG under test

- **Embeddings**: FastEmbed + `BAAI/bge-small-en-v1.5` (384 dims, CPU, ONNX). Planned `nomic-embed-text` via Ollama, but Ollama's model storage (Cloudflare R2) was unreachable from my network; Hugging Face worked. FastEmbed is Qdrant's own library, so it fits. Queries use `query_embed` (bge adds its retrieval instruction to queries, not to documents).
- **Index**: Qdrant in embedded mode (`data/qdrant`, no server). Point ids are UUIDv5 of the readable chunk id, so re-indexing is idempotent. Indexing 3,997 chunks took ~9 min on CPU (GPU or a smaller batch size would be next).
- **LLM**: `qwen3:8b` through Ollama's HTTP API directly (no SDK, every request visible). `temperature=0`, fixed `seed`, `think=false` so runs are repeatable and only the final answer is graded.
- **Prompt**: `build_messages()` is a separate function because the defenses in phase 4 replace it. System prompt asks for page citations and for an explicit "not in the reports" when the answer is missing.
- **Numeric grader** (`judge/numbers.py`): normalises "CHF 11,201.3 mn", "11.2 billion", "11'201.3 million", unicode minus, % before comparing (0.5% relative tolerance). Grades: correct / wrong / abstained / no_number. Years alone don't count as a stated figure.
- First real query: "What were Sika's consolidated net sales in 2025?" -> "CHF 11,201.3 million [sika-ar-2025 p.2]" (correct; ~25 s on the RTX 2080 Ti).

Questions to be ready for:
- Why grade numbers with rules instead of an LLM judge? (cheap, deterministic, no judge bias; the LLM judge is only for cases rules can't decide)
- Why 0.5% tolerance? (models round: "11.2 billion" for 11,201.3 mn must count; a chart-axis "11,000" must not)
- Weakness: if the answer states several numbers and one matches, it's "correct" even if it highlights the wrong one. Acceptable for a baseline; noted as a limitation.
