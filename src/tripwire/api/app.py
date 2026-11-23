"""FastAPI app: a read-only view of `data/runs.sqlite` and the static dashboard.

Read-only on purpose: runs are started from the CLI, so the dashboard can never change a
result, and every number it shows comes from a stored row.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from tripwire.attacks.catalog import load_catalog
from tripwire.judge.detectors import evidence_spans
from tripwire.judging import final_outcomes_sql
from tripwire.matrix import gold_summary
from tripwire.storage import Store

WEB = Path(__file__).resolve().parent.parent / "web"
DEFENSE_ORDER = ["none", "hardened_prompt", "isolation", "layered"]
CATEGORY_ORDER = ["direct_injection", "indirect_injection", "leakage", "numeric_poisoning"]


def _order(values, ref):
    return sorted(values, key=lambda v: ref.index(v) if v in ref else len(ref))


def create_app(db_path: Path, gold_path: Path | None = None) -> FastAPI:
    app = FastAPI(title="Tripwire", docs_url="/api/docs", redoc_url=None)

    def store() -> Store:
        # one connection per request: sqlite3 connections are not shared across threads
        return Store(db_path)

    @lru_cache(maxsize=8)
    def catalog(name: str):
        attacks, planted = load_catalog(name)
        return {a.id: a for a in attacks}, planted

    @lru_cache(maxsize=1)
    def gold():
        if gold_path is None or not gold_path.exists():
            return {}
        from tripwire.gold import load_gold
        return {g.id: g for g in load_gold(gold_path, include_unverified=True)}

    def run_or_404(s: Store, run_id: int):
        rows = s.query("SELECT * FROM runs WHERE id = ?", run_id)
        if not rows:
            raise HTTPException(404, f"run {run_id} does not exist")
        return rows[0]

    def judge_model(s: Store, run_id: int) -> str | None:
        # the judge that decided most 'mixed' rows of this run, if any
        r = s.query("SELECT judge_model, count(*) AS n FROM judgements WHERE run_id = ? "
                    "AND purpose = 'mixed' GROUP BY judge_model ORDER BY n DESC LIMIT 1", run_id)
        return r[0]["judge_model"] if r else None

    def outcomes_source(s: Store, run_id: int) -> str:
        jm = judge_model(s, run_id)
        if not jm:
            return "(SELECT *, outcome AS final_outcome FROM attack_results)"
        return f"({final_outcomes_sql(jm)})"

    @app.get("/api/runs")
    def runs():
        s = store()
        rows = s.query("SELECT r.*, (SELECT count(*) FROM attack_results a WHERE a.run_id = r.id)"
                       " AS n_attacks FROM runs r ORDER BY id DESC")
        return [{**dict(r), "defenses": json.loads(r["defenses"])} for r in rows]

    @app.get("/api/runs/{run_id}/matrix")
    def matrix(run_id: int):
        s = store()
        run = run_or_404(s, run_id)
        src = outcomes_source(s, run_id)
        cells = s.query(
            f"SELECT category, defense, sum(final_outcome = 'succeeded') AS succeeded, "
            f"sum(final_outcome = 'mixed') AS mixed, "
            f"sum(final_outcome != 'not_delivered') AS delivered, "
            f"sum(final_outcome = 'not_delivered') AS not_delivered "
            f"FROM {src} WHERE run_id = ? GROUP BY category, defense", run_id)
        gold_by_defense = gold_summary(s, run_id)
        defenses = _order({c["defense"] for c in cells} | set(gold_by_defense)
                          or set(json.loads(run["defenses"])), DEFENSE_ORDER)
        totals = {d: {"succeeded": sum(c["succeeded"] for c in cells if c["defense"] == d),
                      "delivered": sum(c["delivered"] for c in cells if c["defense"] == d)}
                  for d in defenses}
        return {
            "run": {**dict(run), "defenses": json.loads(run["defenses"])},
            "judge_model": judge_model(s, run_id),
            "defenses": defenses,
            "categories": _order({c["category"] for c in cells}, CATEGORY_ORDER),
            "cells": [dict(c) for c in cells],
            "totals": totals,
            "gold": gold_by_defense,
        }

    @app.get("/api/runs/{run_id}/cell")
    def cell(run_id: int, category: str = Query(...), defense: str = Query(...)):
        s = store()
        run = run_or_404(s, run_id)
        attacks, _ = catalog(run["catalog"])
        rows = s.query(
            f"SELECT attack_id, repeat, final_outcome FROM {outcomes_source(s, run_id)} "
            f"WHERE run_id = ? AND category = ? AND defense = ? ORDER BY attack_id, repeat",
            run_id, category, defense)
        grouped: dict[str, list] = {}
        for r in rows:
            grouped.setdefault(r["attack_id"], []).append(
                {"repeat": r["repeat"], "outcome": r["final_outcome"]})
        out = [{"attack_id": aid, "title": attacks[aid].title if aid in attacks else aid,
                "repeats": reps} for aid, reps in grouped.items()]
        out.sort(key=lambda a: (-sum(x["outcome"] == "succeeded" for x in a["repeats"]),
                                a["title"]))
        return {"category": category, "defense": defense, "attacks": out}

    @app.get("/api/runs/{run_id}/case")
    def case(run_id: int, defense: str = Query(...), attack_id: str = Query(...),
             repeat: int = Query(0)):
        s = store()
        run = run_or_404(s, run_id)
        attacks, planted = catalog(run["catalog"])
        rows = s.query(
            f"SELECT * FROM {outcomes_source(s, run_id)} WHERE run_id = ? AND defense = ? "
            f"AND attack_id = ? AND repeat = ?", run_id, defense, attack_id, repeat)
        if not rows:
            raise HTTPException(404, "no such result")
        r = dict(rows[0])
        attack = attacks.get(attack_id)
        judgements = s.query(
            "SELECT judge_model, purpose, verdict, reason FROM judgements WHERE run_id = ? "
            "AND defense = ? AND attack_id = ? AND repeat = ?", run_id, defense, attack_id, repeat)
        g = gold().get(attack.gold) if attack and attack.gold else None
        return {
            "defense": defense, "repeat": repeat, "seed": r["seed"],
            "outcome": r["outcome"], "final_outcome": r["final_outcome"],
            "attack": None if attack is None else {
                "id": attack.id, "title": attack.title, "category": attack.category,
                "question": attack.question, "success": list(attack.success),
                "planted": [{"doc_id": planted[p].doc_id, "page": planted[p].page,
                             "text": planted[p].text} for p in attack.planted],
            },
            "answer": r["answer"],
            "evidence": [{"start": a, "end": b, "kind": k} for a, b, k in
                         (evidence_spans(r["answer"], list(attack.success)) if attack else [])],
            "fired": json.loads(r["fired"]),
            "retrieved": json.loads(r["retrieved"]),
            "dropped": json.loads(r["dropped"]),
            "blocked_by": r["blocked_by"],
            "gold": None if g is None else {"answer": g.answer, "grade": r["gold_grade"],
                                            "pages": list(g.pages)},
            "judgements": [dict(j) for j in judgements],
            "seconds": r["seconds"],
        }

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(WEB / "index.html")

    app.mount("/static", StaticFiles(directory=WEB), name="static")
    return app
