---
name: diff-intent-timeline
description: Render git diffs as HTML intent-timeline review pages - hunks clustered into concepts, ordered foundation-first. Use when a large PR, commit, or raw diff needs intent-ordered review, or the user asks for a timeline by intent, concept clustering, or a diff explained as a story.
---

# Diff Intent Timeline

Take ONE diff (a PR branch, a single commit, or a raw unified diff) and turn it into a single self-contained HTML review page: hunks clustered into **concepts**, ordered as a dependency-aware timeline, each concept carrying a "why this exists" **intent**, with expandable syntax-highlighted hunks and keyboard nav. Output is one `.html` file — no server, no network, shareable as a file.

## Pipeline

Three ordered steps. All scripts are Python 3 stdlib; `pygments` is optional (syntax highlighting).

### Step 1 — Prepare: split the diff into chunks

```bash
# PR-style: base..head (head defaults to the working tree)
python3 scripts/prepare_diff.py --repo <path> --base origin/main --head feature-x

# Single commit (parent..commit)
python3 scripts/prepare_diff.py --repo <path> --commit <sha>

# Any unified diff (no git needed)
python3 scripts/prepare_diff.py --diff-file changes.diff
```

Writes `chunks.json` (one object per hunk: id, file, status, language, line ranges, +/- counts, raw content, truncated flag) and `summary.json` (files, totals, languages, skipped binaries) into `--out DIR` (default: a per-run **work dir** under `~/.cache/diff-intent-timeline/` — never the target repo; these are pipeline intermediates). Flags: `--context N` (default 3), `--max-chunk-bytes` (default 6000). The script prints the work dir path — remember it for steps 2–3.

**Done when:** `chunks.json` covers every hunk and `summary.json` captures the totals. If `totals.chunks` is huge (>~250), split the diff by directory or file group and run the pipeline per part — don't cluster hundreds of hunks in one pass.

### Step 2 — Cluster: author `concepts.json`

Read `chunks.json` (in the work dir prepare printed) and group chunks into concepts. Write `concepts.json` **next to `chunks.json`** in the work dir:

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

Fields: **id** = timeline position (1..N). **name** = short noun phrase ("JWT auth middleware"), not a sentence. **intent** = plain-language rationale. **depends_on** = ids the reviewer must read first. **chunks** = chunk ids.

**Ground every intent in the code.** If the rationale isn't evident, write `[inferred: ...]` or `[verify: ...]`. If a hunk mixes concerns, say so in its concept's intent instead of forcing it. State what the change does, plainly — no flattery or editorializing.

**Clustering rules:**

- One concept = one coherent intent: shared file, shared symbol, or shared purpose.
- Order concepts **foundation-first** (foundation before consumer). Default template: config/schema/migrations → domain logic → infrastructure (db, auth, cache) → API/entrypoints → UI → tests → docs/CI. `depends_on` overrides; keep changes to the same file in one concept.
- Every chunk is assigned exactly once. Chunks that fit nowhere go in a final "Housekeeping" concept — never drop a hunk silently.
- 3–8 concepts is the sweet spot. More means the diff itself should have been split into commits — say so in `overview`.

**Done when:** every chunk id in `chunks.json` appears in exactly one concept, `depends_on` edges agree with the code's symbol flow (imports, calls, data flow), and concepts read **foundation-first**.

### Step 3 — Render: produce the HTML

```bash
python3 scripts/render.py --chunks <workdir>/chunks.json --concepts <workdir>/concepts.json \
  --title "orders-service: implement order flow"
```

Flags: `--subtitle "..."`, `--no-highlight`, `--out <path>` (the HTML defaults to `timeline.html` next to `--chunks`, i.e. the work dir — leave it there; copy it into the repo only if the user wants the preview committed). Unassigned chunks are auto-appended as a final "Unassigned chunks" concept with a warning — a safety net, not a workflow; assign deliberately in step 2.

**Done when:** the HTML opens cleanly from disk (`file://`) with no console errors — the rail highlights as you scroll, expand/collapse works, j/k navigates.

## Pitfalls

- Binary files are skipped by prepare and listed in `summary.json.skipped_binaries`.
- Renames: `-M` is on; a pure rename is one chunk with status "renamed".
- Huge hunks are truncated with a `@@ ...TRUNCATED... @@` marker (`chunk.truncated = true`) — if a truncated chunk matters, fetch the full hunk with `git diff -U3 <ref>` before clustering it.
- `--diff-file` accepts any unified diff (works outside git repos).
- Escaping is handled by the renderer; never hand-inject HTML into concepts.json.
- On narrow screens the rail collapses to chips; keyboard nav still works.
