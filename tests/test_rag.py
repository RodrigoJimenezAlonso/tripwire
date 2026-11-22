from tripwire.corpus.chunk import Chunk
from tripwire.target.index import Hit
from tripwire.target.rag import RagPipeline, build_messages


class FakeRetriever:
    def __init__(self, hits):
        self.hits = hits
        self.calls = []

    def search(self, query, k=5, doc_id=None):
        self.calls.append((query, k, doc_id))
        return self.hits[:k]


class EchoLLM:
    def __init__(self):
        self.messages = None

    def chat(self, messages):
        self.messages = messages
        return "CHF 11,201.3 mn [sika-ar-2025 p.6]"


HIT = Hit(Chunk("sika-ar-2025:p6:c0", "sika-ar-2025", 6, "NET SALES in CHF mn 11,201.3"), 0.9)


def test_prompt_contains_source_tags_and_question():
    msgs = build_messages("What were net sales?", [HIT])
    assert msgs[0]["role"] == "system"
    assert "[sika-ar-2025 p.6]" in msgs[1]["content"]
    assert msgs[1]["content"].endswith("Question: What were net sales?")


def test_pipeline_passes_k_and_filter_and_returns_hits():
    retriever, llm = FakeRetriever([HIT]), EchoLLM()
    ans = RagPipeline(retriever, llm, k=3).answer("What were net sales?", doc_id="sika-ar-2025")
    assert retriever.calls == [("What were net sales?", 3, "sika-ar-2025")]
    assert ans.hits == [HIT]
    assert "11,201.3" in ans.text
