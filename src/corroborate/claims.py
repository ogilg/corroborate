"""Core registry: Claim dataclass + ClaimSet producer-side helper.

Every numeric value rendered into a document is registered as a `Claim`.
Producers create a `ClaimSet`, call `register()` for each value (passing the
value through inline — the return value IS the registered value — so the
same number flows into the plot and into the registry), then `save()` a
sidecar JSON.

Provenance fields make claims reproducible:
  - `computed_at`: auto-filled by `register()` (UTC ISO second-precision)
  - `data_paths`: input files an auditor would read to reproduce
  - `derivation`:  one-line reproduction recipe

Deliberately renderer-agnostic — `write_*` helpers live in `corroborate.renderers`.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Union


Scalar = Union[float, int, str, bool]
Row = dict[str, Scalar]
Table = dict[str, dict[str, Scalar]]
ClaimValue = Union[Scalar, Row, Table]


def _validate_value(value: object) -> None:
    """Reject shapes we don't support. Scalars, 1-D row dicts, and 2-D table dicts only."""
    if isinstance(value, bool) or isinstance(value, (int, float, str)):
        return
    if not isinstance(value, dict):
        raise TypeError(
            f"Claim value must be a scalar (int/float/str/bool) or a dict of cells; "
            f"got {type(value).__name__}"
        )
    if not value:
        raise ValueError("Claim value dict is empty")
    for k, v in value.items():
        if not isinstance(k, str):
            raise TypeError(f"Claim value dict keys must be str; got {type(k).__name__}")
        if isinstance(v, bool) or isinstance(v, (int, float, str)):
            continue
        if not isinstance(v, dict):
            raise TypeError(
                f"Cell {k!r}: values must be scalars or inner dicts (tables); "
                f"got {type(v).__name__}"
            )
        if not v:
            raise ValueError(f"Inner table row {k!r} is empty")
        for ik, iv in v.items():
            if not isinstance(ik, str):
                raise TypeError(
                    f"Inner table row {k!r}: column keys must be str; got {type(ik).__name__}"
                )
            if isinstance(iv, bool) or isinstance(iv, (int, float, str)):
                continue
            raise TypeError(
                f"Table cell [{k!r}][{ik!r}]: must be scalar; got {type(iv).__name__}. "
                "Nesting deeper than 2 levels is not supported."
            )


@dataclass(frozen=True)
class Claim:
    name: str
    value: ClaimValue
    statement: str
    source: str
    used_in: tuple[str, ...] = ()
    computed_at: str = ""
    data_paths: tuple[str, ...] = ()
    derivation: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["used_in"] = list(self.used_in)
        d["data_paths"] = list(self.data_paths)
        return d

    @staticmethod
    def from_dict(d: dict) -> "Claim":
        return Claim(
            name=d["name"],
            value=d["value"],
            statement=d["statement"],
            source=d["source"],
            used_in=tuple(d.get("used_in", [])),
            computed_at=d.get("computed_at", ""),
            data_paths=tuple(d.get("data_paths", [])),
            derivation=d.get("derivation", ""),
        )


def _now_iso() -> str:
    """UTC ISO timestamp, second-precision, no microseconds."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class ClaimSet:
    """Collector used by producer scripts. Registers claims and writes a sidecar."""

    source: str
    claims: list[Claim] = field(default_factory=list)

    def register(
        self,
        name: str,
        value: ClaimValue,
        statement: str,
        used_in: list[str] | tuple[str, ...] = (),
        *,
        source: str | None = None,
        data_paths: list[str] | tuple[str, ...] = (),
        derivation: str = "",
    ) -> ClaimValue:
        """Record a claim and return its value so it can be used inline.

        Required:
          - name:       human-readable string; becomes the macro slug.
          - value:      the rendered number (pre-rounded by the producer).
          - statement:  declarative sentence stating what the number asserts.
          - used_in:    labels in the document where this number appears
                        ("abstract", "sec:shared-probe", "fig:cross-model").

        Optional provenance (strongly encouraged):
          - source:       overrides the ClaimSet's source. Use "manual: ..."
                          for values that are not machine-derived, or
                          "superseded: replaced by <name> on YYYY-MM-DD; <reason>"
                          when a claim is retained only for audit trail.
          - data_paths:   input files the producer reads.
          - derivation:   one-line reproduction recipe.

        `computed_at` is auto-filled with the current UTC ISO timestamp.
        """
        if any(c.name == name for c in self.claims):
            raise ValueError(f"Duplicate claim name within producer: {name!r}")
        _validate_value(value)
        self.claims.append(
            Claim(
                name=name,
                value=value,
                statement=statement,
                source=source if source is not None else self.source,
                used_in=tuple(used_in),
                computed_at=_now_iso(),
                data_paths=tuple(data_paths),
                derivation=derivation,
            )
        )
        return value

    def save(self, path: Path | str) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "source": self.source,
            "claims": [c.to_dict() for c in self.claims],
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))


def load_all(claims_dir: Path | str) -> list[Claim]:
    """Load and merge every sidecar in `claims_dir`. Raises on name collision."""
    claims_dir = Path(claims_dir)
    claims: list[Claim] = []
    seen: dict[str, str] = {}
    for sidecar in sorted(claims_dir.glob("*.json")):
        payload = json.loads(sidecar.read_text())
        for raw in payload["claims"]:
            c = Claim.from_dict(raw)
            if c.name in seen:
                raise ValueError(
                    f"Claim name collision: {c.name!r} in {sidecar.name} "
                    f"and {seen[c.name]}"
                )
            seen[c.name] = sidecar.name
            claims.append(c)
    return claims
