"""Cliente mínimo para qualquer servidor de LLM compatível com a API da OpenAI.

Funciona com Ollama (CPU no Proxmox), LM Studio / llama.cpp com Vulkan (GPU AMD
no PC) ou qualquer outro que exponha ``/v1/chat/completions``.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

_THINK_RE = re.compile(r"<think>.*?</think>", re.S)
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


class LLMError(RuntimeError):
    pass


class LLMUnavailable(LLMError):
    """O servidor de IA não respondeu (desligado, rede, timeout)."""


class LLMClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        api_key: str = "local",
        timeout: float = 180.0,
        client: httpx.Client | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.client = client or httpx.Client(
            timeout=timeout, headers={"Authorization": f"Bearer {api_key}"}
        )

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 700,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        try:
            resp = self.client.post(f"{self.base_url}/chat/completions", json=payload)
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise LLMUnavailable(f"Servidor de IA indisponível em {self.base_url}: {exc}") from exc
        if resp.status_code >= 400:
            raise LLMError(f"Erro {resp.status_code} do servidor de IA: {resp.text[:300]}")
        try:
            content = resp.json()["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMError("Resposta do servidor de IA em formato inesperado") from exc
        return strip_reasoning(content)

    def is_available(self) -> bool:
        try:
            return self.client.get(f"{self.base_url}/models", timeout=5).status_code < 500
        except httpx.HTTPError:
            return False


def strip_reasoning(text: str) -> str:
    """Remove blocos ``<think>`` de modelos com raciocínio (ex.: Qwen3)."""
    return _THINK_RE.sub("", text).strip()


def extract_json(text: str) -> dict[str, Any]:
    """Extrai o primeiro objeto JSON de uma resposta, tolerando texto ou ``` em volta."""
    text = strip_reasoning(text)
    fenced = _FENCE_RE.search(text)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise LLMError("A IA não retornou JSON")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LLMError(f"JSON inválido retornado pela IA: {exc}") from exc
    if not isinstance(data, dict):
        raise LLMError("A IA retornou JSON que não é um objeto")
    return data
