---
name: corroborate:claim-audit
description: >
  Audit numeric claims by re-deriving each value from data and comparing to
  what's recorded. Argument $ARGUMENTS — optional scope (claim name, section,
  producer, or --manual/--changed/--all). Follows each claim's derivation,
  flags discrepancies with the standard `nature` taxonomy.
user-invocable: true
allowed-tools: Bash, Read, Grep, Glob, Agent, Edit, Write
---

# /corroborate:claim-audit $ARGUMENTS

Re-derive registered claims from their declared sources and data paths, and report whether each still holds. This is the **primary use of corroborate**: every other piece (sidecars, macros, audit surface) exists to make this audit possible.

Two versions of "audit" exist in the tooling:

- **Drift check** (`corroborate audit` CLI): a fast git-diff of live sidecars vs. HEAD. Catches changes, not bugs. Useful in CI.
- **This skill**: follows each claim's `derivation` against current data. Catches logic bugs, stale values, transcription errors, broken pipelines. This is the one that matters.

## Scope from `$ARGUMENTS`

- **empty** / `--all` → audit the whole registry. If the registry is large (>50 claims), prioritise:
  1. claims `used_in` the abstract or `sec:*` labels (headline prose) first,
  2. then `source="manual: ..."` claims (least verifiable),
  3. then one sampled claim per producer,
  4. skip pure `fig:*` bar-heights unless the figure itself is in scope.
- **claim name** (e.g., `"Gemma probe heldout r"`) → audit that claim only.
- **`--section <label>`** (e.g., `--section sec:shared-probe`) → all claims whose `used_in` contains the label.
- **`--source <path>`** → all claims from one producer.
- **`--manual`** → all `source` entries starting with `manual:` — try to re-derive from the cited report/data_paths rather than trust the value.
- **`--changed`** / **`--since-commit <sha>`** → claims whose sidecars changed (via `git diff paper/claims/`).
- **ambiguous** → ask the user.

## Per-claim procedure

For each claim in scope:

### 1. Load the claim record

Grep the audit surface (typical: `paper/claims.md`) or load the sidecars directly. You need: `name`, `value`, `statement`, `source`, `data_paths`, `derivation`, `computed_at`.

### 2. Classify the derivation type

Derivations fall into a few patterns — pick the one that fits:

- **read-field**: "Read `x.y.z` from file F" → direct JSON/CSV lookup.
- **aggregate**: "Mean of per-fold X" / "Pearson r on intersection of ..." → small computation over data.
- **filtered-aggregate**: "Per-condition mean across Exp1b filtered to ..." → computation with a filter.
- **transcribed**: "Value from table in report.md" / "Transcribed from X section" → text search in a committed document.
- **run-producer**: "Re-run producer.py and read field X" → reruns required to verify.
- **manual**: `source="manual: ..."` — no auto-derivation; audit statement/value coherence only.
- **superseded**: `source="superseded: ..."` — not active; confirm the replacement claim exists and carries the current value.

If the derivation doesn't match a clean pattern, flag `NEEDS_HUMAN` and move on.

### 3. Re-derive

- **read-field / aggregate / filtered-aggregate**: load the data file(s), apply the operation described in `derivation`, round as specified. Use `Bash` to run small Python snippets when the computation is non-trivial. If `data_paths` files don't exist, return `DATA_MISSING`.
- **transcribed**: `grep` the referenced report for the value. If absent, or if surrounding context contradicts the statement, flag.
- **run-producer**: if the producer is runnable locally (no GPU/network needed), run it and compare outputs. Otherwise mark `NEEDS_HUMAN` unless `--deep` is in scope.
- **manual** / **superseded**: verify the `source` string is well-formed and the `statement` is internally consistent with the value. Can't verify the value itself.

### 4. Compare and classify

| Outcome | Meaning |
|---|---|
| **PASS** | Recomputed value matches recorded to the claim's declared precision (default 3dp). Statement reads plausibly. |
| **FAIL-value** | Recomputed value differs from recorded by > precision threshold. |
| **FAIL-statement** | Value matches but the statement misdescribes what the code does (e.g., claims "within-topic" but code uses HOO). |
| **DATA_MISSING** | `data_paths` file not present; can't verify. |
| **NEEDS_HUMAN** | Derivation is complex or ambiguous; requires a domain-literate human/subagent read. |
| **MANUAL** | `source="manual: ..."`; can't auto-verify. Report the value + rationale. |
| **SUPERSEDED** | Retained for trail; note the replacement claim. |

### 5. Record

Per-claim output (compact, one line ideal):

```
[PASS]          Gemma probe heldout r = 0.865           (read final_r at L32 from manifest.json)
[FAIL-value]    Gemma refitted shift r = 0.74           (computed 0.7408; recorded 0.74 OK, but paper prose says 0.63 → issue filed)
[DATA_MISSING]  Exp3v8 AvC probe ranks                  (data_paths=activations/ood/... not synced locally)
[MANUAL]        Stated-steering phase1 baseline = 3.64  (source=manual: superseded phase-1 experiment)
[SUPERSEDED]    Old Qwen r                              (replaced by "Qwen probe heldout r" 2026-04-24)
[NEEDS_HUMAN]   Persona transfer 7x7 heatmap cells      (derivation references a filter I can't disambiguate)
```

## Filing discrepancies

Any **FAIL-value** or **FAIL-statement** → log in the project's claim-issues file (typical path: `paper/CLAIMS_ISSUES.md`; infer from repo — this project uses `paper/PAPER_ISSUES.md`). Use the standard two-table layout with `nature` taxonomy from the `claim-log` skill:

- `discrepancy` — recomputed ≠ recorded
- `stale` — recorded predates a known data refresh (check `computed_at`)
- `missing-data` — `DATA_MISSING` result
- `unreconciled-source` — claim appears derivable from multiple sources with different values
- `ambiguous-provenance` — `NEEDS_HUMAN` on provenance

ID scheme: `I-YYYY-MM-DD-N`. Short, sortable, stable.

Don't auto-fix FAILs — filing the issue is the job. Escalation to humans is the point.

## End-of-run report

Summary block:

```
Scope: <what was audited>
Total claims: <N>   PASS: <n>   FAIL: <n>   MANUAL: <n>   DATA_MISSING: <n>   NEEDS_HUMAN: <n>   SUPERSEDED: <n>

Discrepancies filed: <IDs> (see <issues file>)

Unable to verify:
  - <name>: <reason>
```

Plus per-claim lines for everything non-PASS. Never let a failure slide without at least a filed issue or a `NEEDS_HUMAN` flag.

## Efficiency

- Batch data loads: if many claims share a `data_paths` file, load once.
- Bounded per-claim budget: if a single claim's re-derivation would exceed ~10 tool calls, drop to `NEEDS_HUMAN` and let a targeted subagent handle it.
- For `--all` on a large registry: spawn parallel subagents grouped by producer (each subagent handles one producer's claims). Pass a producer and its sidecar; have it return a structured per-claim pass/fail list.

## What this skill is NOT

- Not a value fixer. Found a wrong value? File an issue — a human decides.
- Not a prose editor. Found paper prose that disagrees with the registry? File an issue.
- Not `corroborate audit` (git-diff). That's mechanical; this is substantive.
- Not a security review or a correctness proof of the underlying experiments — it audits whether registered claims still follow from their stated derivations on current data.
