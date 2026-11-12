from __future__ import annotations

import json

import httpx

from searchjob.llm import LLMClient


def fake_llm(*replies: str, status: int = 200) -> tuple[LLMClient, list[dict]]:
    """LLMClient que responde em sequência com ``replies`` e registra as requisições."""
    sent: list[dict] = []
    queue = list(replies)

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        content = queue.pop(0) if queue else ""
        return httpx.Response(
            status, json={"choices": [{"message": {"role": "assistant", "content": content}}]}
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return LLMClient("http://llm.test/v1", "modelo-teste", client=client), sent


def offline_llm() -> LLMClient:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return LLMClient("http://llm.test/v1", "modelo-teste", client=client)
