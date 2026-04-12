from __future__ import annotations

import asyncio
import os
from typing import Any

SYSTEM_PROMPT = (
    "You are a shell assistant. Return only a command suggestion or short command sequence "
    "that addresses the user query using provided context. Do not include markdown fences."
)


def _extract_text(response: Any) -> str:
    choices = getattr(response, "choices", None) or response.get("choices", [])
    if not choices:
        return ""
    first = choices[0]
    message = getattr(first, "message", None) or first.get("message", {})
    content = getattr(message, "content", None) or message.get("content", "")
    if isinstance(content, list):
        chunks = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                chunks.append(item.get("text", ""))
        return "".join(chunks).strip()
    return str(content).strip()


async def request_suggestion(
    model: str,
    api_key: str | None,
    query: str,
    context_bundle: str,
    timeout_seconds: int = 60,
    max_output_tokens: int = 128,
) -> str:
    try:
        from litellm import acompletion
    except ImportError as exc:
        raise RuntimeError(
            "litellm is required for model calls. Reinstall unforget from the GitHub uv command in README."
        ) from exc

    if api_key:
        os.environ.setdefault("OPENAI_API_KEY", api_key)
        os.environ.setdefault("ANTHROPIC_API_KEY", api_key)
        os.environ.setdefault("GEMINI_API_KEY", api_key)
        os.environ.setdefault("GOOGLE_API_KEY", api_key)

    prompt = (
        f"User Query:\n{query}\n\n"
        f"Context Bundle:\n{context_bundle}\n"
    )
    response = await asyncio.wait_for(
        acompletion(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            timeout=timeout_seconds,
            num_retries=0,
            max_tokens=max_output_tokens,
        ),
        timeout=timeout_seconds,
    )
    return _extract_text(response)
