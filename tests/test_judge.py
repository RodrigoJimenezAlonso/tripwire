import json
from pathlib import Path

import pytest
from test_attacks import FakeIndex

from tripwire.attacks.catalog import load_catalog
from tripwire.gold import load_gold
from tripwire.judge.llm_judge import LlmJudge, build_judge_messages, parse_verdict
from tripwire.judging import agreement, cohen_kappa, judge_run, label_sample
from tripwire.matrix import MatrixConfig, report, run_matrix
from tripwire.storage import Store


class ScriptedJudge:
    def __init__(self, verdict="resisted"):
        self.verdict, self.calls = verdict, 0

    def chat(self, messages, json_mode=False):
        assert json_mode
        self.calls += 1
        return json.dumps({"verdict": self.verdict, "reason": "scripted"})


class PremiseEcho:
    """Mentions the false premise but gives the right figure -> 'mixed'."""

    def __init__(self, seed):
        pass

    def chat(self, messages):
        return "The question says CHF 13,400 million, but the report states CHF 11,201.3 million."


@pytest.fixture
def catalog():
    attacks, planted = load_catalog()
    gold = {g.id: g for g in load_gold(Path("data/gold/gold.yaml"), include_unverified=True)}
    return {a.id: a for a in attacks}, planted, gold


def test_parse_verdict_is_defensive():
    assert parse_verdict('{"verdict": "Succeeded", "reason": "x"}').verdict == "succeeded"
    assert parse_verdict("not json").verdict == "unclear"
    assert parse_verdict('{"verdict": "maybe"}').verdict == "unclear"


def test_judge_sees_the_attack_material(catalog):
    attacks, planted, gold = catalog
    a = attacks["lk-memo-benign-question"]
    msgs = build_judge_messages(a, "Some answer", [planted[p] for p in a.planted], None)
    assert "NIGHTJAR" in msgs[1]["content"]  # the confidential doc, to spot paraphrases
    a = attacks["di-false-premise"]
    msgs = build_judge_messages(a, "x", [], gold[a.gold])
    assert "13400" in msgs[1]["content"] and "11,201.3" in msgs[1]["content"]


def test_identical_answers_are_judged_once(catalog):
    attacks, _, gold = catalog
    llm = ScriptedJudge()
    judge = LlmJudge(llm)
    a = attacks["di-false-premise"]
    for _ in range(3):
        judge.judge(a, "same answer", [], gold[a.gold])
    assert llm.calls == 1


def test_kappa():
    assert cohen_kappa([("succeeded", "succeeded"), ("resisted", "resisted")]) == 1.0
    assert cohen_kappa([("succeeded", "resisted"), ("resisted", "succeeded")]) < 0


def test_judge_resolves_mixed_and_agreement_report(tmp_path, catalog):
    attacks, planted, gold = catalog
    store = Store(tmp_path / "runs.sqlite")
    cfg = MatrixConfig(model="fake", k=5, defenses=["none"], repeats=2, run_gold=False)
    run_id = run_matrix(cfg, store, FakeIndex(), PremiseEcho, [attacks["di-false-premise"]],
                        planted, list(gold.values()), log=lambda _: None)
    assert "+2" in report(store, run_id)  # two mixed rows before judging

    judge_llm = ScriptedJudge("resisted")
    judge_run(store, run_id, LlmJudge(judge_llm), "fake-judge", attacks, planted, gold,
              log=lambda _: None)
    assert judge_llm.calls == 1  # both repeats gave the same answer
    resolved = report(store, run_id, judge_model="fake-judge")
    assert "0/2" in resolved and "+2" not in resolved

    items = label_sample(store, run_id, n=10)
    assert len(items) == 1  # identical answers are labelled once
    store.add_label(run_id, items[0].defense, items[0].attack_id, items[0].repeat, "resisted")
    text = agreement(store, run_id, "fake-judge")
    assert "LLM judge: agreement 100% on 1 rows" in text
