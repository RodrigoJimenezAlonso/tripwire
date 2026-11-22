"""Minimal Ollama chat client over plain HTTP (no SDK, so every request is visible and easy to log)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import httpx

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


@dataclass
class OllamaChat:
    model: str = "qwen3:8b"
    host: str = "http://localhost:11434"
    temperature: float = 0.0
    seed: int = 7  # fixed seed + temperature 0 so runs are repeatable
    timeout: float = 180.0
    _client: httpx.Client = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._client = httpx.Client(base_url=self.host, timeout=self.timeout)

    def chat(self, messages: list[dict[str, str]], json_mode: bool = False) -> str:
        body = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": False,  # qwen3 reasoning traces off: we grade the final answer only
            "options": {"temperature": self.temperature, "seed": self.seed},
        }
        if json_mode:
            body["format"] = "json"  # Ollama constrains decoding to valid JSON
        resp = self._client.post("/api/chat", json=body)
        resp.raise_for_status()
        content = resp.json()["message"]["content"]
        return _THINK.sub("", content).strip()
