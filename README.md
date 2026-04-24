# vernier

> A vernier scale reads the digits between the digits. This plugin does the same for the claims in your papers.

Register, verify, and audit numeric claims in documents. Every empirical number in prose or captions becomes a reproducible `Claim` — value, statement, source, data paths, derivation — so numbers trace back to data, stay in sync when data updates, and drift is visible.

## What it solves

Papers and reports accumulate dozens-to-hundreds of numbers: Pearson rs, sample sizes, effect sizes, percentages. When a probe is refit or a dataset refreshed, the paper prose usually doesn't update automatically. Over a project's lifetime, numbers drift out of sync with the data that produced them, and the only way to catch it is manual proofreading.

vernier makes each number a first-class object:

- **One producer-side call** at the point the value is computed:

  ```python
  from vernier import ClaimSet

  claims = ClaimSet(source="scripts/probes/plot_cross_model_bar.py")

  r = claims.register(
      name="Gemma probe heldout r",
      value=round(final_r, 3),
      statement="A ridge probe at L32 predicts held-out utilities at Pearson r on the within-distribution split.",
      used_in=["fig:cross-model", "abstract"],
      data_paths=["results/probes/gemma/manifest.json"],
      derivation="Read `final_r` of the ridge probe at layer==32; round to 3dp.",
  )
  claims.save("paper/claims/plot_cross_model_bar.json")
  ```

- **Three generated views** over the registry:
  - `paper/numbers.tex` — `\newcommand{\gemmaProbeHeldoutR}{0.865}` per claim; `\input{numbers.tex}` in the paper, reference `\gemmaProbeHeldoutR` instead of typing `0.865`.
  - `paper/claims.md` — a human-scannable table with every claim, its statement, source, and derivation. The audit surface.
  - Per-producer sidecars at `paper/claims/*.json` — checked into git.

- **One audit command** (`vernier audit`) that diffs live sidecars against git HEAD, surfacing changed / added / removed / manual / superseded claims.

## Install

Still in early development; install from source:

```sh
uv pip install -e /path/to/vernier
```

## Claude Code plugin

vernier ships with a `/claim-log` skill (invoked as `vernier:claim-log`) that an agent can run in two modes:

- **Retrospective** — `vernier:claim-log` with no args scans recent conversation + `git diff` and registers any new numbers it finds.
- **Prospective** — `vernier:claim-log Update §3 with the layer-sweep results` runs the described task, registering every number as it writes.

The skill handles the full lifecycle: registering new claims, superseding old ones, and flagging discrepancies in a standard `CLAIMS_ISSUES.md` format with a `nature` taxonomy (discrepancy / stale / missing-data / unreconciled-source / ambiguous-provenance / manual-pending-compute / orphan).

## CLI

```sh
vernier build     # merge sidecars → numbers.tex + claims.md
vernier audit     # diff live against committed state
```

Defaults assume `paper/claims/`, `paper/claims.md`, `paper/numbers.tex`. Override via flags.

## Schema

Every claim has:

| Field | Purpose |
|---|---|
| `name` | Human-readable key; becomes the LaTeX macro slug (auto-camelCased, digits spelled out). |
| `value` | The rendered numeric (or string) value. |
| `statement` | Full declarative sentence: what does this number *mean*? |
| `source` | Producer file path. `"manual: ..."` for untraceable values. `"superseded: ..."` for retained-for-audit claims. |
| `used_in` | Labels in the document where the number appears (`"abstract"`, `"fig:cross-model"`, ...). |
| `computed_at` | Auto-filled ISO timestamp. |
| `data_paths` | Repo-relative input files. |
| `derivation` | One-line reproduction recipe. |

## Status

Early. API is small and stable; renderers are LaTeX + Markdown for now. Contributions and format renderers welcome.

## License

MIT
