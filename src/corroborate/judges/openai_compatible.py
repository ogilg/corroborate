"""OpenAI-SDK-compatible NEAR-DUPLICATE judge. Works with OpenRouter, OpenAI,
vLLM, or anything that speaks the OpenAI chat-completions protocol.

Usage with OpenRouter:

    from corroborate.judges.openai_compatible import openai_judge

    judge = openai_judge(
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        model="anthropic/claude-opus-4.7",
    )

Plain OpenAI:

    judge = openai_judge(model="gpt-4o")  # picks up OPENAI_API_KEY
"""

from __future__ import annotations

import os
from typing import Any

from corroborate.audit import DuplicateJudge
from corroborate.claims import Claim
from corroborate.judges.anthropic import (
    _PROMPT_TEMPLATE,
    _SYSTEM,
    _format_value,
    _parse_response,
)


DEFAULT_MODEL = "anthropic/claude-opus-4.7"


def openai_judge(
    model: str = DEFAULT_MODEL,
    base_url: str | None = None,
    api_key: str | None = None,
    api_key_env: str = "OPENAI_API_KEY",
    client: Any | None = None,
    max_tokens: int = 300,
) -> DuplicateJudge:
    """Build a chat-completions-API judge.

    Defaults (``model="anthropic/claude-opus-4.7"``) are tuned for OpenRouter;
    set ``base_url="https://openrouter.ai/api/v1"`` and
    ``api_key_env="OPENROUTER_API_KEY"`` to use that backend. For plain OpenAI,
    pass e.g. ``model="gpt-4o"`` and leave the defaults.
    """
    try:
        import openai  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "corroborate.judges.openai_compatible requires the openai SDK. "
            "Install with: pip install openai"
        ) from exc

    if client is None:
        resolved_key = api_key or os.environ.get(api_key_env)
        if resolved_key is None:
            raise RuntimeError(
                f"No API key: pass api_key= or set ${api_key_env}"
            )
        client = openai.OpenAI(api_key=resolved_key, base_url=base_url)

    def _judge(pair, a: Claim, b: Claim):
        prompt = _PROMPT_TEMPLATE.format(
            a_name=a.name,
            a_value=_format_value(a.value),
            a_statement=a.statement,
            a_derivation=a.derivation or "(not recorded)",
            a_data=", ".join(a.data_paths) or "(none)",
            a_source=a.source,
            b_name=b.name,
            b_value=_format_value(b.value),
            b_statement=b.statement,
            b_derivation=b.derivation or "(not recorded)",
            b_data=", ".join(b.data_paths) or "(none)",
            b_source=b.source,
            shared=", ".join(pair.shared_data_paths) or "(none)",
        )
        response = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": prompt},
            ],
        )
        text = response.choices[0].message.content or ""
        return _parse_response(text)

    return _judge
