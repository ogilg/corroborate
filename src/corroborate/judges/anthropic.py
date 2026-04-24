"""Claude-based NEAR-DUPLICATE judge. Requires the ``anthropic`` SDK.

Usage:

    from corroborate import audit
    from corroborate.judges.anthropic import anthropic_judge

    report = audit(
        claims_dir,
        repo_root,
        paper_sources=[...],
        duplicate_judge=anthropic_judge(),
    )
"""

from __future__ import annotations

import re
from typing import Any

from corroborate.audit import DUPLICATE_VERDICTS, DuplicateJudge, DuplicateVerdict
from corroborate.claims import Claim, ClaimValue


DEFAULT_MODEL = "claude-opus-4-7"

_SYSTEM = (
    "You audit a scientific paper's numeric claim registry. Two claims have "
    "been flagged as candidates for consolidation because they share a raw "
    "data path and have close numeric values. Decide whether they actually "
    "measure the same quantity."
)

_PROMPT_TEMPLATE = """\
Claim A
  name:      {a_name}
  value:     {a_value}
  statement: {a_statement}
  derivation: {a_derivation}
  data_paths: {a_data}
  source:    {a_source}

Claim B
  name:      {b_name}
  value:     {b_value}
  statement: {b_statement}
  derivation: {b_derivation}
  data_paths: {b_data}
  source:    {b_source}

Shared data path(s): {shared}

Verdict taxonomy (pick exactly one):
- duplicate:     Same quantity. The two derivations describe the same
                 operation on the same data, even if names or wrappers differ.
                 Pick this if one can safely be retired.
- complementary: Related quantities with a known structural relationship
                 (decomposition vs aggregate, fixed-layer vs argmax, signed
                 vs absolute, per-group vs pooled). Both worth keeping.
- unrelated:     Values are close by coincidence; derivations compute
                 genuinely different things.
- uncertain:     Derivations too vague to call, or you need more context.

Respond in a single line with the verdict, a colon, and one sentence of
rationale. No preamble, no markdown. Examples:

  duplicate: Both read final_r at layer 32 from the same Gemma manifest; argmax of the sweep equals the canonical layer.
  complementary: First is the per-type decomposition, second is the aggregate across types; related by construction.
  unrelated: Values happen to round close but derivations filter on disjoint subsets.
  uncertain: Derivation B doesn't specify the aggregation axis.
"""


_LINE_RE = re.compile(
    r"^\s*(duplicate|complementary|unrelated|uncertain)\s*[:\-.\s]\s*(.+?)\s*$",
    re.IGNORECASE | re.DOTALL,
)


def _format_value(v: ClaimValue) -> str:
    """Compact repr for structured values so the prompt stays readable."""
    if isinstance(v, dict):
        s = repr(v)
        return s if len(s) <= 400 else s[:397] + "..."
    return repr(v)


def _parse_response(text: str) -> tuple[DuplicateVerdict, str]:
    m = _LINE_RE.match(text)
    if m:
        verdict = m.group(1).lower()
        if verdict in DUPLICATE_VERDICTS:
            return verdict, m.group(2).strip()
    return "uncertain", f"could not parse verdict from: {text.strip()[:200]}"


def anthropic_judge(
    model: str = DEFAULT_MODEL,
    client: Any | None = None,
    max_tokens: int = 300,
) -> DuplicateJudge:
    """Build a Claude-backed DuplicateJudge. Requires ``anthropic`` installed.

    The returned callable closes over a single client instance — reuses the
    HTTP connection across pairs.
    """
    try:
        import anthropic  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "corroborate.judges.anthropic requires the anthropic SDK. "
            "Install with: pip install anthropic"
        ) from exc

    if client is None:
        client = anthropic.Anthropic()

    def _judge(pair, a: Claim, b: Claim) -> tuple[DuplicateVerdict, str]:
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
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text
        return _parse_response(text)

    return _judge
