# diff-intent-timeline

An AI skill that turns one big git diff into a **reviewable story**: hunks are
clustered into *concepts*, concepts are ordered as a dependency-aware *timeline*,
and the result is rendered as a single self-contained HTML page with a concept
rail, "why this exists" intents, expandable syntax-highlighted hunks, and
keyboard navigation.

Works on any input a diff can come from:

- a PR branch (`--base origin/main --head feature-x`)
- a single commit that has everything in it (`--commit <sha>`)
- a raw unified diff file (`--diff-file changes.diff`) — no git repo needed

**Output = one `.html` file.** No server, no network, no dependencies beyond
Python 3 (pygments optional, for syntax highlighting).

[See a live sample render →](docs/preview.html)

## Why

Large diffs are reviewed in the order git happened to emit them. This skill
re-orders the diff by *intent*: first the schema, then the plumbing that uses
it, then the domain logic, then the API, then tests and docs — so a reviewer
reads the change the way the author should have committed it, without the
author having to split it first.

## Install

Requires the [`skills`](https://www.npmjs.com/package/skills) CLI
(vercel-labs/skills — works with Hermes, OpenCode, Claude Code, Codex, and 70+
other agents):

```bash
# global install to all your agents
npx skills add codeatspeed/diff-intent-timeline --skill diff-intent-timeline -g -y

# or just this one agent
npx skills add codeatspeed/diff-intent-timeline --skill diff-intent-timeline -a opencode -y

# project-local
npx skills add codeatspeed/diff-intent-timeline --skill diff-intent-timeline -y

# install without installing - generate a prompt / start an agent
npx skills use codeatspeed/diff-intent-timeline --skill diff-intent-timeline
```

## Usage

Any agent that has loaded the skill runs the 3-step pipeline. All intermediates (chunks, concepts, summary) and the final HTML land in a per-run **work dir** under `~/.cache/diff-intent-timeline/` — never inside the repo being analyzed. Pass `--out` to override:

```bash
# 1. split the diff into chunks (JSON) — prints the work dir path
python3 scripts/prepare_diff.py --repo . --commit HEAD

# 2. agent reads chunks.json (in the work dir), authors concepts.json next to it
#    (cluster hunks into concepts; see SKILL.md for the rules)

# 3. render the HTML (defaults to timeline.html next to --chunks)
python3 scripts/render.py --chunks <workdir>/chunks.json --concepts <workdir>/concepts.json \
  --title "orders-service: implement order flow"
```

Open `timeline.html` in any browser. `j`/`k` move between concepts, the rail
tracks your position, dark mode is automatic with a manual toggle.

### concepts.json

```json
{
  "overview": "2-3 sentences summarizing the whole change.",
  "concepts": [
    {
      "id": 1,
      "name": "Orders table migration",
      "intent": "Why this piece exists, in plain words. Mark [inferred] when unsure.",
      "depends_on": [],
      "chunks": ["c0001", "c0002"]
    }
  ]
}
```

The agent is instructed to keep intents grounded in the code, mark inferred
rationales, assign every chunk exactly once, and order concepts foundation →
consumer.

## Scripts

| Script | Purpose |
| --- | --- |
| `scripts/prepare_diff.py` | git diff / commit / unified diff → `chunks.json` + `summary.json` (one chunk per hunk, rename-aware, binary-safe, truncation-safe) |
| `scripts/render.py` | `chunks.json` + `concepts.json` → single-file HTML timeline |

## Requirements

- **Python 3.9+** — the scripts are stdlib-only.
- **git CLI** — needed only for `--repo` / `--base` / `--commit` modes.
  `--diff-file` mode reads any unified diff and works without git.
- **pygments** *(optional)* — syntax highlighting inside the diff. Without it
  the page renders with plain add/remove/context coloring.
- **node** *(optional)* — used only by `test/verify.py` for the inline-JS
  syntax check; skipped when absent.
- The `skills` CLI itself needs **Node.js 18+** (`npx`).

## Test

Self-contained verification (generates its own throwaway git repo, runs the
whole pipeline, checks HTML invariants). No network, no external deps beyond
Python 3 (pygments + node used opportunistically):

```bash
python3 test/verify.py        # exit 0 = all green
hermes verify --json          # same, via the hermes CLI (records evidence)
```

## License

MIT © 2026 codeatspeed
