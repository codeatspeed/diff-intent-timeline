---
name: diff-intent-timeline
description: Render git diffs as HTML intent-timeline review pages. Use when a PR, commit, or raw diff is large and reviewers need hunks clustered into concepts, ordered by dependency, with a progressive narrative instead of a wall of hunks.
---

# Diff Intent Timeline

Take ONE diff (a PR branch, a single commit, or a raw unified diff), cluster its
hunks into **concepts**, order the concepts as a dependency-aware **timeline**,
and render a single self-contained HTML review page: concept rail, "why this
exists" intent per concept, expandable syntax-highlighted hunks, keyboard nav.

Output = one `.html` file. No server, no network, shareable as a file.

## When to use

- A PR or commit mixes many concerns (schema + logic + API + tests + docs...).
- Reviewers must understand *why the diff is shaped this way* before reading code.
- You want a shareable review artifact for a reviewer with limited context budget.
- The user asks for "timeline by intent", "concept clustering", "progressive
  review", or "explain this diff as a story".

## Pipeline (3 steps, run in order)

All scripts are Python 3 stdlib. `pygments` is optional (syntax highlighting).

### Step 1 - Prepare: split the diff into chunks

```bash
# PR-style: base..head (head defaults to the working tree)
python3 scripts/prepare_diff.py --repo <path> --base origin/main --head feature-x

# Single commit with everything in it
python3 scripts/prepare_diff.py --repo <path> --commit <sha>

# Any unified diff (no git needed)
python3 scripts/prepare_diff.py --diff-file changes.diff
```

Writes `chunks.json` (one object per hunk: id, file, status, language, line
ranges, +/- counts, raw content, truncated flag) and `summary.json` (files,
totals, languages, skipped binaries). Options: `--context N`, `--max-chunk-bytes`
(default 6000), `--out DIR`.

Read `summary.json` first. If `totals.chunks` is very large (>~250), split the
diff by directory or by file groups and run the pipeline per part - do not try
to cluster hundreds of hunks in one pass.

### Step 2 - Cluster: YOU (the agent) author concepts.json

Read `chunks.json`. Group chunks into concepts. Write `concepts.json`:

```json
{
  "overview": "2-3 sentences summarizing the whole change for the top card.",
  "concepts": [
    {
      "id": 1,
      "name": "Orders table migration",
      "intent": "One or two sentences: why this piece exists, what problem it solves.",
      "depends_on": [],
      "chunks": ["c0001", "c0002"]
    }
  ]
}
```

**id** = timeline position (1..N). **name** = short noun phrase
("JWT auth middleware"), not a sentence. **intent** = plain-language rationale.
**depends_on** = ids the reviewer must read first. **chunks** = chunk ids.

Clustering rules:

- A concept is one coherent intent: shared file, shared symbol, or shared purpose.
- Order concepts as a timeline: foundation before consumer. Default template:
  config/schema/migrations -> domain logic -> infrastructure (db, auth, cache)
  -> API/entrypoints -> UI -> tests -> docs/CI. `depends_on` overrides; keep
  changes to the same file in one concept.
- Every chunk is assigned exactly once. Chunks that fit nowhere go in a final
  "Housekeeping" concept - never drop a hunk silently.
- 3-8 concepts is the sweet spot. More means the diff itself should have been
  split into commits - say so in `overview`.

Honesty rules (non-negotiable):

- `intent` must be grounded in what the code shows. If the rationale is not
  evident, write `[inferred: ...]` or `[verify: ...]`. Never invent a rationale.
- If a hunk mixes concerns, say so in its concept's intent instead of forcing it.
- Do not editorialize or flatter the author. State what the change does.

### Step 3 - Render: produce the HTML

```bash
python3 scripts/render.py --chunks chunks.json --concepts concepts.json \
  --title "orders-service: implement order flow" --out timeline.html
```

Flags: `--subtitle "..."`, `--no-highlight`. Unassigned chunks are appended
automatically as a final "Unassigned chunks" concept (with a warning) - but
assign deliberately in step 2; the auto-concept is a safety net, not a workflow.

## Verification

1. Every chunk id appears in exactly one concept: `jq` or a quick script over
   chunks.json + concepts.json.
2. `depends_on` edges agree with obvious symbol flow (imports, calls, data flow).
3. The HTML opens cleanly from disk (`file://`) with no console errors - check
   the rail highlights as you scroll, expand/collapse works, j/k navigates.

## Pitfalls

- Binary files are skipped by prepare and listed in `summary.json.skipped_binaries`.
- Renames: `-M` is on; a pure rename is one chunk with status "renamed".
- Huge hunks are truncated with a `@@ ...TRUNCATED... @@` marker
  (`chunk.truncated = true`) - if a truncated chunk matters, fetch the full
  hunk with `git diff -U3 <ref>` before clustering it.
- `--diff-file` accepts any unified diff (works outside git repos).
- Escaping is handled by the renderer; never hand-inject HTML into concepts.json.
- On narrow screens the rail collapses to chips; keyboard nav still works.
