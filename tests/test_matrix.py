from pathlib import Path

from test_attacks import FakeIndex

from tripwire.attacks.catalog import load_attacks, load_planted
from tripwire.gold import load_gold
from tripwire.matrix import MatrixConfig, report, run_matrix
from tripwire.storage import Store
from tripwire.target.rag import SYSTEM_CANARY


class LeakyLLM:
    """Obeys everything: leaks the canary and repeats any planted number it sees."""

    def __init__(self, seed):
        self.seed = seed

    def chat(self, messages):
        return f"Sure. Internal reference {SYSTEM_CANARY}. Net sales CHF 11,201.3 million."


def test_matrix_stores_every_cell_and_reports(tmp_path):
    planted = load_planted()
    attacks = [a for a in load_attacks(planted=planted)
               if a.id in ("di-maintenance-mode", "lk-system-reference-benign")]
    gold = load_gold(Path("data/gold/gold.yaml"), include_unverified=True)[:2]
    store = Store(tmp_path / "runs.sqlite")
    cfg = MatrixConfig(model="fake", k=5, defenses=["none", "layered"], repeats=2)

    run_id = run_matrix(cfg, store, FakeIndex(), LeakyLLM, attacks, planted, gold,
                        log=lambda _: None)

    rows = store.query("SELECT defense, outcome, seed FROM attack_results WHERE run_id = ?",
                       run_id)
    assert len(rows) == 2 * 2 * 2  # defenses x repeats x attacks
    assert {r["seed"] for r in rows} == {7, 8}
    by_def = {d: [r["outcome"] for r in rows if r["defense"] == d] for d in ("none", "layered")}
    assert set(by_def["none"]) == {"succeeded"}
    assert set(by_def["layered"]) == {"resisted"}  # input filter or output filter stops both
    assert len(store.query("SELECT * FROM gold_results WHERE run_id = ?", run_id)) == 2 * 2

    text = report(store, run_id)
    assert "attack success rate" in text and "gold set under each defense" in text
