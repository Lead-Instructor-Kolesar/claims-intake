"""Minimal Ollama call for Day 1.

This file demonstrates where Ollama returns response text, token counts,
and the stop reason. Read it, run it, then leave it unchanged.
"""

from __future__ import annotations

import httpx

from promptlab.config import Settings


def main() -> None:
    settings = Settings.from_env()
    model = settings.models["mistral"]

    response = httpx.post(
        f"{settings.ollama_base_url}/api/generate",
        json={
            "model": model.model_id,
            "prompt": "Reply with one short sentence explaining what a KYC policy is.",
            "stream": False,
            "options": {
                "temperature": 0.0,
                "num_predict": 80,
            },
        },
        timeout=180.0,
    )
    response.raise_for_status()
    payload = response.json()

    print("response:", payload.get("response"))
    print("input tokens:", payload.get("prompt_eval_count"))
    print("output tokens:", payload.get("eval_count"))
    print("stop reason:", payload.get("done_reason"))


if __name__ == "__main__":
    main()
