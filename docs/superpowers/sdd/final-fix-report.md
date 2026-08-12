# Final Fix Report: whole-branch review findings

**Status:** DONE
**Date:** 2026-08-12
**Branch/worktree:** `review-lenses` @ `/Users/muralinunna/CodeBay/hermes-vps/projects/diff-intent-timeline/.worktrees/review-lenses`
**Base commit (before fixes):** `6620d64 lens: document layer/risk authoring; regenerate sample (backward compatible)`

## Changes

### 1. P2 — tour spotlight misses DAG + risks callout (`skills/diff-intent-timeline/scripts/render.py`)
The tour rules dimmed only `.concept` cards; `svg.dag` and `.risks` anchors (`<a href="#concept-N">`) stayed clickable and navigated natively without syncing tour state (spotlight stuck on concept-1 while the page scrolled to concept-3, bar reading 1/6, target dimmed). Added the two selectors to the existing dim pattern, right after `body.tour-on .concept{...}`:

```css
body.tour-on svg.dag,body.tour-on .risks{opacity:.28;pointer-events:none}
```

Same opacity/`pointer-events:none` semantics as the concept rule; the `tour-current` spotlight rule is untouched.

### 2. MUST-FIX — verify.py risks-callout check (`test/verify.py`)
Replaced the bare `"Schema" in s` sub-condition with `'class="risk-badge">high</span>Schema' in s` — now asserts the risky concept NAME is linked inside a callout item (the fixture marks concept 1, named "Schema", as `risk: high`), not merely present somewhere in the page.

### 3. MUST-FIX — verify.py DAG check (`test/verify.py`)
Added `'class="dag-node"' in s` to the dag check — catches a node-less SVG shell:

```python
'<svg class="dag"' in s and "<marker" in s and 'class="dag-node"' in s and "concept-2" in s
```

### 4. MUST-FIX — render_dag docstring (`skills/diff-intent-timeline/scripts/render.py`)
Qualified the edge-direction claim. Before: `edges always run left -> right.` After:

```
longest-path depth from root concepts; edges run left -> right, except
cycle back-edges.
```

(Match with the `depth()` cycle handling above it: a `depends_on` cycle is treated as root, and back-edges render right-to-left.)

### 5. MUST-FIX — print CSS (`skills/diff-intent-timeline/scripts/render.py`)
Added `.tour-bar` to the print hide list so an active tour doesn't print a stray fixed box:

```css
@media print{header.top,#rail,.next-wrap,button,.fs-overlay,.tour-bar{display:none!important}
```

## Test commands + outputs

### `python3 test/verify.py` (from worktree root)

```
PASS dark palette scoped (monokai)
PASS dark mode keeps per-token colors
PASS inline JS parses
PASS orphan -> auto concept id=max+1 (6)
PASS no duplicate concept ids
PASS orphan hunk still rendered
PASS layer chip rendered
PASS risk chip rendered
PASS risk reason tooltip
PASS lens schema backward compatible
PASS top-risks callout lists high-risk concepts
PASS dependency graph svg present
PASS tour toggle present

0 failures / 30 checks
```

Exit code 0. Baseline before fixes (from the branch state at `6620d64`): the suite was already 30/30 on the un-fixed tree (fixes 2 and 3 tighten checks that still pass; no check was removed).

### Static confirmation of the emitted CSS (render of probe fixture)

```
tour-on dag rule: body.tour-on svg.dag,body.tour-on .risks{opacity:.28;pointer-events:none} present: True
print tour-bar rule: .tour-bar{display:none!important} present: True
```

## Browser measurements (P2 probe)

Fixture: `/tmp/dit-fixture-regen` chunks/concepts (6 concepts, `depends_on` chains `[] [1] [2] [3] [3] [4]`), rendered with `risk: high|med` + `risk_reason` added to exercise the callout (6 dag nodes, 6 risk items). Rendered to `/tmp/dit-p2-probe.html`, opened in headless Chrome, `file://`.

Real coordinate clicks (`page.$(...)` handle clicks — real mouse hit-testing, so `pointer-events` is exercised). State snapshots:

| Step | scrollY | hash | tour count | c1 current | c3 opacity | dag opacity | risks opacity |
|---|---|---|---|---|---|---|---|
| baseline (top) | 0 | `` | — | false | 1 | 1 | 1 |
| Tour started (goes to concept-1) | 627 | `` | `1 / 6` | true | 0.28 | 0.28 | 0.28 |
| scrolled back up to DAG (manual) | 0 | `` | `1 / 6` | true | 0.28 | 0.28 | 0.28 |
| **click DAG node `#concept-3` (tour ON)** | **0** | **``** | **`1 / 6`** | **true** | **0.28** | 0.28 | 0.28 |
| **click risks-callout item (tour ON)** | **0** | **``** | **`1 / 6`** | **true** | **0.28** | 0.28 | 0.28 |
| End tour (`.tour-close`) | 0 | `` | — | false | 1 | 1 | 1 |
| **click DAG node `#concept-3` (tour OFF)** | **1802** | **`#concept-3`** | — | false | 1 | 1 | 1 |

Assertions, all measured:

- DAG node click while touring: **inert** — scrollY unchanged (0), `location.hash` unchanged (``), tour count still `1 / 6`, concept-1 still `tour-current`, concept-3 stays dimmed (opacity 0.28). ✓
- Risks-callout item click while touring: **inert** — identical readings. ✓
- After End tour: `body.tour-on` removed, `.tour-bar` removed, dims cleared (all opacities back to 1). ✓
- DAG node click after End tour: **navigates natively** — `location.hash === "#concept-3"`, scrollY 0 → 1802. Links work again. ✓

(Reported reproduction — spotlight on concept-1 while page scrolls to concept-3, bar 1/6 — is no longer possible: with `pointer-events:none` on `svg.dag`/`.risks` the anchor never receives the click during a tour.)

## Deviations

None. All five findings fixed exactly as specified. `docs/preview.html` intentionally not regenerated (the review fixture lacks `layer`/`risk` fields, so the P2 dim rule is not observable there; probe fixture covers it).

## Self-review

- **Scope:** only `skills/diff-intent-timeline/scripts/render.py` and `test/verify.py` modified; nothing else touched.
- **Determinism:** renderer unchanged in behavior outside the CSS/docstring edits; suite runs cleanly to the same 30/30.
- **Backward compat:** the new tour rule only applies under `body.tour-on`; print rule adds one selector to an existing hide list; verify.py only tightened two sub-conditions, both still green.
