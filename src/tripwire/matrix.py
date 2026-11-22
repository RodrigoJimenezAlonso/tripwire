"""Attack x defense x repeat matrix, plus the gold set under each defense.

A defense that blocks every attack by refusing everything is useless, so each defense is also
scored on the gold set: the security gain is only worth reporting next to its accuracy cost.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from tripwire.attacks.catalog import Attack
from tripwire.attacks.planted import EmbeddingIndex, PlantedRetriever
from tripwire.attacks.run import run_attack
from tripwire.corpus.chunk import Chunk
from tripwire.defenses import get_defense
from tripwire.gold import GoldItem
from tripwire.judge.numbers import grade
from tripwire.storage import Store
from tripwire.target.rag import Chat, RagPipeline

BASE_SEED = 7


@dataclass
class MatrixConfig:
    model: str
    k: int
    defenses: list[str]
    repeats: int = 3
    gold_repeats: int = 1
    run_attacks: bool = True
    run_gold: bool = True


def run_matrix(cfg: MatrixConfig, store: Store, base: EmbeddingIndex,
               make_llm: Callable[[int], Chat], attacks: list[Attack],
               planted: dict[str, Chunk], gold_items: list[GoldItem],
               log: Callable[[str], None] = print, note: str | None = None,
               catalog: str = "catalog") -> int:
    run_id = store.new_run(cfg.model, cfg.k, cfg.repeats, cfg.defenses, note=note,
                           catalog=catalog)
    gold = {g.id: g for g in gold_items}
    for name in cfg.defenses:
        defense = get_defense(name)
        if cfg.run_attacks:
            for rep in range(cfg.repeats):
                llm = make_llm(BASE_SEED + rep)
                for a in attacks:
                    t0 = time.perf_counter()
                    r = run_attack(a, base, llm, planted, gold, k=cfg.k, defense=defense)
                    store.add_attack(run_id, {
                        "defense": name, "attack_id": r.id, "category": r.category,
                        "repeat": rep, "seed": BASE_SEED + rep, "outcome": r.outcome,
                        "fired": r.fired, "delivered": int(r.delivered),
                        "blocked_by": r.blocked_by, "dropped": r.dropped,
                        "gold_grade": r.gold_grade, "answer": r.answer,
                        "retrieved": r.retrieved, "seconds": time.perf_counter() - t0})
                    log(f"[{name} #{rep}] {r.outcome:13} {r.id}")
        if cfg.run_gold:
            for rep in range(cfg.gold_repeats):
                # same retriever as the attacks, with nothing planted
                rag = RagPipeline(PlantedRetriever(base, []), make_llm(BASE_SEED + rep),
                                  k=cfg.k, defense=defense)
                for item in gold_items:
                    t0 = time.perf_counter()
                    ans = rag.answer(item.question)
                    g = "blocked" if ans.blocked_by else grade(ans.text, item.value, item.unit)
                    page_hit = any(h.chunk.doc_id == item.doc_id and h.chunk.page in item.pages
                                   for h in ans.hits)
                    store.add_gold(run_id, {
                        "defense": name, "gold_id": item.id, "difficulty": item.difficulty,
                        "verified": int(item.verified), "repeat": rep, "seed": BASE_SEED + rep,
                        "grade": g, "page_hit": int(page_hit), "blocked_by": ans.blocked_by,
                        "answer": ans.text,
                        "retrieved": [f"{h.chunk.doc_id}:p{h.chunk.page}" for h in ans.hits],
                        "seconds": time.perf_counter() - t0})
                    log(f"[{name} gold #{rep}] {g:10} {item.id}")
    return run_id


def report(store: Store, run_id: int, judge_model: str | None = None) -> str:
    """Plain-text summary: attack success rate per category x defense, then gold accuracy.

    With a judge model, `mixed` rows are resolved by that judge's verdicts, and audit
    disagreements are listed as possible detector misses."""
    from tripwire.judging import final_outcomes_sql

    lines = []
    run = store.query("SELECT * FROM runs WHERE id = ?", run_id)[0]
    lines.append(f"run {run_id}  {run['started_at']}  model={run['model']} k={run['k']} "
                 f"repeats={run['repeats']} catalog={run['catalog']} commit={run['git_commit']}")
    source = "attack_results"
    if judge_model:
        source = (f"(SELECT run_id, defense, attack_id, category, repeat, "
                  f"final_outcome AS outcome FROM ({final_outcomes_sql(judge_model)}))")
        lines.append(f"mixed outcomes resolved by judge {judge_model}")
    defenses = [r["defense"] for r in store.query(
        "SELECT DISTINCT defense FROM attack_results WHERE run_id = ? "
        "UNION SELECT DISTINCT defense FROM gold_results WHERE run_id = ?", run_id, run_id)]
    order = ["none", "hardened_prompt", "isolation", "layered"]
    defenses.sort(key=lambda d: order.index(d) if d in order else 99)

    asr = store.query(
        "SELECT category, defense, "
        "  sum(outcome = 'succeeded') AS s, sum(outcome = 'mixed') AS m, "
        "  sum(outcome != 'not_delivered') AS d "
        f"FROM {source} WHERE run_id = ? GROUP BY category, defense", run_id)
    if asr:
        cell = {(r["category"], r["defense"]): r for r in asr}
        cats = sorted({r["category"] for r in asr})
        lines.append("\nattack success rate (succeeded / delivered; +mixed)")
        lines.append(f"{'':20}" + "".join(f"{d:>18}" for d in defenses))
        for c in cats:
            row = f"{c:20}"
            for d in defenses:
                r = cell.get((c, d))
                if not r or not r["d"]:
                    row += f"{'-':>18}"
                    continue
                txt = f"{r['s']}/{r['d']} {100 * r['s'] / r['d']:3.0f}%" + (
                    f" +{r['m']}" if r["m"] else "")
                row += f"{txt:>18}"
            lines.append(row)
        total = store.query(
            "SELECT defense, sum(outcome = 'succeeded') AS s, sum(outcome != 'not_delivered') AS d"
            f" FROM {source} WHERE run_id = ? GROUP BY defense", run_id)
        t = {r["defense"]: r for r in total}
        row = f"{'ALL':20}"
        for d in defenses:
            r = t.get(d)
            txt = f"{r['s']}/{r['d']} {100 * r['s'] / r['d']:3.0f}%" if r and r["d"] else "-"
            row += f"{txt:>18}"
        lines.append(row)
        if judge_model:
            misses = store.query(
                "SELECT defense, attack_id, repeat, reason FROM judgements WHERE run_id = ? "
                "AND judge_model = ? AND purpose = 'audit' AND verdict = 'succeeded' "
                "ORDER BY defense, attack_id, repeat", run_id, judge_model)
            lines.append(f"\npossible detector misses (judge says succeeded, detectors did not): "
                         f"{len(misses)}")
            lines += [f"  [{m['defense']} #{m['repeat']}] {m['attack_id']}: {m['reason']}"
                      for m in misses]

    gold = store.query(
        "SELECT defense, count(*) AS n, sum(grade = 'correct') AS c, sum(grade = 'wrong') AS w, "
        "  sum(grade = 'blocked') AS b, sum(page_hit) AS p "
        "FROM gold_results WHERE run_id = ? GROUP BY defense", run_id)
    if gold:
        g = {r["defense"]: r for r in gold}
        lines.append("\ngold set under each defense")
        for label, key in (("correct", "c"), ("wrong", "w"), ("blocked", "b"),
                           ("page retrieved", "p")):
            row = f"{label:20}"
            for d in defenses:
                r = g.get(d)
                row += f"{(f'{r[key]}/{r["n"]}' if r else '-'):>18}"
            lines.append(row)
    return "\n".join(lines)
