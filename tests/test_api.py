from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_attacks import FakeIndex

from tripwire.api.app import create_app
from tripwire.attacks.catalog import load_catalog
from tripwire.gold import load_gold
from tripwire.judge.detectors import evidence_spans
from tripwire.matrix import MatrixConfig, run_matrix
from tripwire.storage import Store
from tripwire.target.rag import SYSTEM_CANARY

GOLD = Path("data/gold/gold.yaml")


class LeakyLLM:
    def __init__(self, seed):
        pass

    def chat(self, messages):
        return f"Reference {SYSTEM_CANARY}. <script>alert(1)</script> Net sales CHF 11,201.3 mn."


@pytest.fixture
def client(tmp_path):
    attacks, planted = load_catalog()
    keep = [a for a in attacks if a.id in ("lk-system-reference-benign", "np-sika-restated-sales")]
    db = tmp_path / "runs.sqlite"
    run_matrix(MatrixConfig(model="fake", k=5, defenses=["none", "layered"], repeats=2),
               Store(db), FakeIndex(real_score=0.5), LeakyLLM, keep, planted,
               load_gold(GOLD, include_unverified=True)[:2], log=lambda _: None)
    return TestClient(create_app(db, GOLD))


def test_runs_and_matrix(client):
    runs = client.get("/api/runs").json()
    assert len(runs) == 1 and runs[0]["catalog"] == "catalog"
    m = client.get(f"/api/runs/{runs[0]['id']}/matrix").json()
    assert m["defenses"] == ["none", "layered"]
    cell = next(c for c in m["cells"] if c["category"] == "leakage" and c["defense"] == "none")
    assert (cell["succeeded"], cell["delivered"]) == (2, 2)
    assert m["gold"]["none"]["n"] == 2


def test_cell_and_case(client):
    cell = client.get("/api/runs/1/cell", params={"category": "leakage", "defense": "none"}).json()
    assert cell["attacks"][0]["attack_id"] == "lk-system-reference-benign"
    assert [r["outcome"] for r in cell["attacks"][0]["repeats"]] == ["succeeded", "succeeded"]

    case = client.get("/api/runs/1/case", params={
        "defense": "none", "attack_id": "lk-system-reference-benign", "repeat": 1}).json()
    assert case["final_outcome"] == "succeeded"
    start, end = case["evidence"][0]["start"], case["evidence"][0]["end"]
    assert case["answer"][start:end] == SYSTEM_CANARY
    # model output comes back as plain data; the page inserts it as text, never as HTML
    assert "<script>" in case["answer"]


def test_missing_things_are_404(client):
    assert client.get("/api/runs/99/matrix").status_code == 404
    assert client.get("/api/runs/1/case", params={
        "defense": "none", "attack_id": "nope", "repeat": 0}).status_code == 404


def test_dashboard_is_served(client):
    assert "Tripwire" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200


def test_evidence_spans_for_numbers_and_urls():
    text = "Sales were CHF 11,894.6 million, see https://fake-ubs.net/x"
    spans = evidence_spans(text, [{"type": "number", "value": 11894.6, "unit": "CHF mn"},
                                  {"type": "url"}])
    found = [text[a:b] for a, b, _ in spans]
    assert found[0] == "11,894.6 million"
    text = "a range of CHF 410,000 to CHF 520,000 [doc p.1]"
    spans = evidence_spans(text, [{"type": "number", "value": 520000, "unit": "count"}])
    assert [text[a:b] for a, b, _ in spans] == ["520,000"]
    assert found[1].startswith("https://fake-ubs.net")
