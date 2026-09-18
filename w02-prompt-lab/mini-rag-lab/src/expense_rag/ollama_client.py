from __future__ import annotations

import httpx

from expense_rag.config import Settings

DOCUMENT_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, settings: Settings, timeout: float = 120.0) -> None:
        self.settings = settings
        self.timeout = timeout

    def embed_document(self, text: str) -> list[float]:
        return self._embed(DOCUMENT_PREFIX + text)

    def embed_query(self, text: str) -> list[float]:
        return self._embed(QUERY_PREFIX + text)

    def generate_json(self, system: str, user: str) -> str:
        payload = {
            "model": self.settings.chat_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.0},
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(f"{self.settings.ollama_host}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        content = data.get("message", {}).get("content")
        if not content:
            raise OllamaError("Chat model returned an empty response")
        return content

    def _embed(self, prompt: str) -> list[float]:
        payload = {"model": self.settings.embed_model, "prompt": prompt}
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.settings.ollama_host}/api/embeddings",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        embedding = data.get("embedding")
        if not embedding:
            raise OllamaError("Embedding model returned an empty vector")
        if len(embedding) != self.settings.embed_dim:
            raise OllamaError(
                f"Expected embedding dim {self.settings.embed_dim}, got {len(embedding)}"
            )
        return [float(value) for value in embedding]
