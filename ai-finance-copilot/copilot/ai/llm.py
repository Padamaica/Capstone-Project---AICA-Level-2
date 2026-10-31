"""Self-hosted LLM clients using only the standard library (urllib).

Providers:
    ollama             -> http://localhost:11434      (dev / small servers)
    openai_compatible  -> http://<gpu-vm>:8000/v1     (vLLM, TGI, LM Studio, llama.cpp server)
    none               -> AI disabled; rule-based commentary is used

Every request goes through `assert_local_endpoint`, so data cannot be sent to a foreign API by mistake.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from ..config import settings
from ..localisation import assert_local_endpoint


class LLMUnavailable(RuntimeError):
    pass


@dataclass
class BaseLLM:
    base_url: str
    model: str
    timeout: int = 120
    temperature: float = 0.1
    api_key: str = ""

    def _post(self, url: str, payload: dict) -> dict:
        assert_local_endpoint(url)
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode())
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            raise LLMUnavailable(f"LLM at {self.base_url} unavailable: {e}") from e

    def _get(self, url: str) -> dict:
        assert_local_endpoint(url)
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                return json.loads(r.read().decode())
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            raise LLMUnavailable(str(e)) from e

    def chat(self, system: str, user: str) -> str:  # pragma: no cover - interface
        raise NotImplementedError

    def health(self) -> bool:  # pragma: no cover - interface
        raise NotImplementedError


class OllamaLLM(BaseLLM):
    def chat(self, system: str, user: str) -> str:
        data = self._post(f"{self.base_url.rstrip('/')}/api/chat", {
            "model": self.model, "stream": False,
            "options": {"temperature": self.temperature, "num_ctx": 8192},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        })
        return data.get("message", {}).get("content", "").strip()

    def health(self) -> bool:
        try:
            tags = self._get(f"{self.base_url.rstrip('/')}/api/tags")
            return any(m.get("name", "").startswith(self.model.split(":")[0]) for m in tags.get("models", []))
        except LLMUnavailable:
            return False


class OpenAICompatibleLLM(BaseLLM):
    def _root(self) -> str:
        b = self.base_url.rstrip("/")
        return b if b.endswith("/v1") else b + "/v1"

    def chat(self, system: str, user: str) -> str:
        data = self._post(f"{self._root()}/chat/completions", {
            "model": self.model, "temperature": self.temperature,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        })
        return data["choices"][0]["message"]["content"].strip()

    def health(self) -> bool:
        try:
            self._get(f"{self._root()}/models")
            return True
        except LLMUnavailable:
            return False


def get_llm() -> BaseLLM | None:
    p = settings.llm_provider.lower()
    kw = dict(base_url=settings.llm_base_url, model=settings.llm_model, timeout=settings.llm_timeout_s,
              temperature=settings.llm_temperature, api_key=settings.llm_api_key)
    if p == "ollama":
        return OllamaLLM(**kw)
    if p in ("openai_compatible", "vllm", "tgi", "lmstudio"):
        return OpenAICompatibleLLM(**kw)
    return None
