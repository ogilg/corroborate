---
name: corroborate:claim-log
description: >
  Log numeric claims added to a document into the claim registry. Argument
  $ARGUMENTS — optional. With no args, runs retrospectively over recent turns +
  git diff. With a prompt, runs the task prospectively and logs as it goes.
  With a file path, scopes retrospective logging to that file. Starts with
  `--commit` to also refresh macros + audit surface at the end.
user-invocable: true
allowed-tools: Bash, Read, Edit, Write, Grep, Glob, AskUserQuestion, Agent
---

# /corroborate:claim-log $ARGUMENTS

## What the claim registry does

Every empirical numeric value in a document is a **Claim**: a record with a human-readable name, the value, a declarative statement of what the number asserts, the source that produced it, the input data paths, and a one-line derivation (what to run with what to reproduce it).

Typical layout in a project using corroborate — **infer from the repo; these are defaults, not hardcoded**:

- `paper/claims/*.json` — per-producer sidecars
- `paper/claims.md` — generated audit surface (rebuilt from sidecars)
- `paper/numbers.tex` (or equivalent) — generated macros for the document
- `corroborate build` / `python -m corroborate.cli build` — rebuilds `claims.md` + macros

Producers import from the `corroborate` package (installed as a dependency):

```python
from corroborate import ClaimSet
```

If the project has no registry yet, ask before scaffolding.

## Mode inference from `$ARGUMENTS`

- **empty** → **retrospective**: scan recent conversation turns + `git diff` for numbers added or changed in documents; register each.
- **prompt-like text** ("Update §3 with the new layer sweep numbers") → **prospective**: carry out the task, registering each numeric value as you write it, then summarize.
- **single existing file path** (e.g., `paper/main.tex`) → **retrospective scoped to that file**.
- **starts with `--commit`** → retrospective + run the project's build step at the end (`corroborate build` or the project's wrapper).
- **ambiguous** → ask the user which mode.

## Registering a claim

```python
from corroborate import ClaimSet

claims = ClaimSet(source="<repo-relative path to the producer script>")

claims.register(
    name="Gemma probe heldout r",                     # human-readable key
    value=0.865,                                      # pre-rounded value
    statement=(
        "A ridge probe on Gemma-3-27B residual-stream activations at the "
        "final prompt token (layer 32) predicts held-out Thurstonian "
        "utilities at Pearson r on a within-distribution eval split."
    ),
    used_in=["fig:cross-model", "abstract"],          # labels in the document
    data_paths=["results/probes/.../manifest.json"],  # repo-relative input files
    derivation=(
        "Read `final_r` of the ridge probe with layer==32 in the manifest's "
        "`probes` array; round to 3dp."
    ),
)

claims.save("paper/claims/<sidecar_name>.json")
```

Then reference the auto-generated macro (check the generated macros file after `corroborate build`) in the document instead of the literal numeral.

**Prefer existing producers.** If a sidecar already covers the topic, add the new claim to its producer. Create a fresh compute script only when no existing producer fits.

## What counts as a claim

Register empirical findings: correlations, accuracies, probabilities, effect sizes, sample counts, percentages, thresholds.

Skip: protocol parameters (coefficients, temperatures, seeds), formatting numbers (figure widths, font sizes), citation years, section/table/figure indices, rough literary approximations.

When in doubt, register it — a claim with `source="manual: ..."` is better than a silent literal.

## Trace or freeze

Every claim needs concrete `data_paths` + `derivation`.

- **Machine-derivable**: point `data_paths` at input file(s), derivation describes read/aggregate/round.
- **Report-transcribed**: point `data_paths` at the markdown/report file, derivation says "Transcribed from <section>".
- **Untraceable** (superseded experiment, cross-experiment approximation, external reference): set `source="manual: <reason>"` and explain in `derivation`.

Never fabricate a derivation.

## Retrospective mode

1. Identify scope — from `$ARGUMENTS`, current conversation, or `git status`.
2. `git diff` the documents; extract numeric literals added or changed.
3. For each, check whether it's already registered (grep the audit file).
4. Register unregistered numbers via the best-fitting existing producer, or a new `scripts/paper/claims/` script. If provenance is unclear, ask before inventing a derivation.
5. If `--commit`: run the build step at the end.

## Prospective mode

1. Carry out the task in `$ARGUMENTS`.
2. **Before writing any numeric value**, register the claim first, then reference the macro in prose. Do not write literal numerals.
3. End-of-turn summary: claims added, sidecars modified, anything frozen manual.

## Removing or superseding claims

Claims aren't immutable. Two mechanisms:

**Delete outright** (no audit trail needed):

1. `grep` the macro slug across documents. If still referenced, **stop and swap prose first** — removing it now would break the build.
2. Delete the `register(...)` call from the producer (or the whole sidecar if one-off).
3. Rebuild.

**Mark superseded** (keep audit trail): set `source="superseded: replaced by <new claim name> on YYYY-MM-DD; <reason>"`. The claim stays in the registry; audit tools surface the status. Pair with a new claim carrying the replacement value.

Never silently change a claim's value without updating `statement` and `derivation`. Never delete a claim whose macro is still referenced.

## Flagging issues

When you find a discrepancy, conflict, or something fishy, log it in the project's claim-issues file (typical path: `paper/CLAIMS_ISSUES.md`; infer from repo — a project may already use `PAPER_ISSUES.md`). Use the standard two-table layout:

```markdown
# Claim registry issues

## Open

| ID | Where | Claim / number | Nature | Detail | Flagged |
|---|---|---|---|---|---|

## Resolved

| ID | Where | Claim / number | Resolution | Date |
|---|---|---|---|---|
```

**Nature taxonomy:**

- `discrepancy` — recomputed value disagrees with the recorded/prose value
- `stale` — value predates a known data refresh
- `missing-data` — producer can't run because inputs aren't synced
- `unreconciled-source` — value appears in multiple places with different numbers
- `ambiguous-provenance` — can't determine where the number came from
- `manual-pending-compute` — frozen manually; compute script doesn't exist yet
- `orphan` — macro still referenced but no producer/claim backs it

**ID scheme:** `I-YYYY-MM-DD-N` (date + per-day counter).

**When to flag vs silently register:**

- **Flag** when recomputed ≠ recorded, provenance is unclear, data isn't reachable, or the claim rests on an unverifiable assumption.
- **Silent register** when everything traces cleanly.

Never let a surprising number flow silently into the registry.

**Resolution:** move the row from Open to Resolved with a short decision note.

## End-of-run report

Always finish with:

- N claims added / updated / removed / superseded
- Sidecar files modified
- Any numbers flagged `manual` — with the reason
- **Issues filed** — IDs, one-line summary, location
- Path to the audit row(s) the user should review
- Whether the build step ran

If you could not confidently register or flag a number, list it explicitly. Silence is the failure mode to avoid.
