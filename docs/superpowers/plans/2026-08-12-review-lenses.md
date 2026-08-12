# Review Lenses (Tour, Dependency Graph, Layers, Risk) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add four review lenses to the generated HTML — a guided walkthrough tour, a clickable concept dependency graph, architecture-layer labels, and risk markers — built as pure renderer work over an additive, backward-compatible extension of `concepts.json`.

**Architecture:** `concepts.json` gains four OPTIONAL per-concept fields (`layer`, `risk`, `risk_reason`; `depends_on` already exists). `render.py` (the only script that changes besides docs) renders: (1) a hand-rolled SVG dependency DAG from `depends_on` (no mermaid, stdlib only), (2) layer chips in the rail + concept meta, (3) risk chips + a top-risks callout, (4) a Tour mode: CSS spotlight (dim non-current concepts) + a fixed floating tour bar (prev/next/progress/narration) driven by a small JS state machine. No new pipeline stages, no network, no new dependencies; the page stays a single self-contained HTML file, and rendering stays deterministic (all new content derives from agent-authored JSON).

**Tech Stack:** Python 3 stdlib (json, re, html), pygments (optional, unchanged), existing inline CSS/JS in `render.py`. Tests run via `test/verify.py` (the repo's single self-contained suite — no pytest).

## Global Constraints

- **Single-file output**: the generated HTML must remain fully self-contained — no external assets, no network, no frameworks (no mermaid, no highlight.js).
- **Python 3 stdlib only** in scripts; pygments optional and unchanged in behavior.
- **Backward compatibility**: every new `concepts.json` field is optional, and
  existing concepts.json inputs must render **without regression** — no crash, and
  every element that renders today renders unchanged (no lens chips, no top-risks
  callout when fields are absent). Lenses are *additive*: the dependency map is
  derived from the existing `depends_on` field and therefore appears whenever the
  input has ≥ 2 concepts, regardless of the new fields. Existing fixtures in this
  repo are the backward-compat test.
- **Determinism**: same inputs → byte-identical HTML. No timestamps, no randomness, no env-dependent output in the rendered page.
- **verify.py must stay green** (currently 23 checks) and gain checks for the new features.
- All user-authored text (concept names, intents, layer/risk values, chunk ids) goes through `esc()` — never raw interpolation.
- Commit after every task. Push only when the user asks.

## File Structure

- `skills/diff-intent-timeline/scripts/render.py` — ALL renderer changes (CSS string, JS string, `main()` meta-chip emission, new `render_dag()` function, tour bar emission).
- `skills/diff-intent-timeline/SKILL.md` — step 2 instructions: author `layer`/`risk` when confident (exact allowed values).
- `test/verify.py` — new checks (per task), no changes to existing checks.
- `docs/preview.html` — regenerated at the end from the reconstructed fixture (which has NO new fields → proves backward compat).
- No new files. `concepts.json` schema is documented in SKILL.md only (no separate schema file).

## Task 1: Optional schema fields → meta chips + layer in rail

**Files:**
- Modify: `skills/diff-intent-timeline/scripts/render.py` (meta emission in `main()`, rail step emission)
- Test: `test/verify.py`

**Interfaces:**
- Consumes: existing `concepts` list from `concepts.json` (each item: `id`, `name`, `intent`, `depends_on`, `chunks`).
- Produces: helper `layer_label(layer)` → str (title-cased label or `""`); meta chip markup conventions used by Tasks 2–4: layer chip `<span class="chip sm chip-layer">schema</span>`, risk chip `<span class="chip sm chip-risk chip-risk-high">high</span>`.

- [ ] **Step 1: Write the failing checks** in `test/verify.py` (append before the final print; they must fail now):

```python
# --- review-lens schema fields (optional, backward compatible) ---
cl = json.loads((TMP / "concepts.json").read_text())
cl["concepts"][0]["layer"] = "schema"
cl["concepts"][0]["risk"] = "high"
cl["concepts"][0]["risk_reason"] = "auth gate"
(TMP / "cl.json").write_text(json.dumps(cl))
r = run([sys.executable, str(SKILL / "scripts/render.py"), "--chunks", str(out / "chunks.json"),
         "--concepts", str(TMP / "cl.json"), "--title", "lens", "--out", str(TMP / "tl.html")])
s = (TMP / "tl.html").read_text()
check("layer chip rendered", 'class="chip sm chip-layer">schema<' in s)
check("risk chip rendered", "chip-risk-high" in s and "auth gate" in s)
check("risk reason tooltip", 'title="auth gate"' in s)
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 test/verify.py`
Expected: `FAIL layer chip rendered`, `FAIL risk chip rendered`, `FAIL risk reason tooltip`

- [ ] **Step 3: Implement** in `render.py` `main()`, inside the concept loop where `meta` is built, add after the existing `dep_txt` chip:

```python
        meta_parts = [
            f'<span class="chip sm">{len(files)} file{"s" if len(files) != 1 else ""}</span>',
            f'<span class="chip sm"><span class="plus">+{ca}</span>'
            f'<span class="sep"> </span><span class="minus">-{cr}</span></span>',
            f'<span class="chip sm">{len(chunks_in)} hunk{"s" if len(chunks_in) != 1 else ""}</span>',
            f'<span class="chip sm">{esc(dep_txt)}</span>',
        ]
        layer = (conept.get("layer") or "").strip().lower()
        if layer:
            meta_parts.append(f'<span class="chip sm chip-layer">{esc(layer)}</span>')
        risk = (conept.get("risk") or "").strip().lower()
        if risk in ("low", "med", "high"):
            reason = (conept.get("risk_reason") or "").strip()
            title = f' title="{esc(reason)}"' if reason else ""
            meta_parts.append(
                f'<span class="chip sm chip-risk chip-risk-{risk}"{title}>{risk}</span>')
        meta = "".join(meta_parts)
        # rail step: layer under the name via the existing (unused) .sdep rule
        sdep = f'<span class="sdep">{esc(layer)}</span>' if layer else ""
        rail_steps.append(
            f'<li><button class="step" data-index="{i}"><span class="dot">{n}</span>'
            f'<span class="sname">{esc(conept["name"])}</span>{sdep}</button></li>')
```

- [ ] **Step 4: Add the CSS** for chips (append to the CSS string, near `.chip.sm`):

```css
.chip.sm.chip-layer{background:var(--accent-soft);color:var(--accent);border-color:color-mix(in srgb,var(--accent) 30%,transparent)}
.chip-risk{text-transform:uppercase;font-size:10px;letter-spacing:.05em}
.chip-risk-low{background:var(--add-bg);color:var(--add)}
.chip-risk-med{background:rgba(245,158,11,.12);color:#b45309}
:root[data-theme=dark] .chip-risk-med{color:#fbbf24}
.chip-risk-high{background:var(--del-bg);color:var(--del)}
```

- [ ] **Step 5: Add the backward-compat check** (asserts the ORIGINAL fixture render — `t.html`, produced from `concepts.json` without new fields — shows no lens chips; this check passes both before and after implementation, so it guards regression, not TDD):

```python
check("lens schema backward compatible",
      'class="chip sm chip-layer">' not in (TMP / "t.html").read_text())
```

- [ ] **Step 6: Run the suite**

Run: `python3 test/verify.py`
Expected: all PASS (27 checks = 23 baseline + 4 new: layer chip, risk chip+reason, tooltip title, backward-compat).

- [ ] **Step 7: Commit**

```bash
git add skills/diff-intent-timeline/scripts/render.py test/verify.py
git commit -m "lens: optional layer/risk schema fields -> meta chips + rail sdep"
```

## Task 2: Top-risks callout + risk legend

**Files:**
- Modify: `skills/diff-intent-timeline/scripts/render.py` (overview section emission)
- Test: `test/verify.py`

**Interfaces:**
- Consumes: per-concept `risk`/`risk_reason` from Task 1; existing `overview` string.
- Produces: `risks_html` markup used by Task 4's tour bar (same `.risk-item` structure reused there).

- [ ] **Step 1: Failing check** in `verify.py` (uses the same `cl.json` fixture from Task 1 — it has concept[0] risk=high):

```python
check("top-risks callout lists high-risk concepts",
      'class="risks"' in s and "auth gate" in s and "Orders" in s)
```

- [ ] **Step 2: Verify failure**

Run: `python3 test/verify.py` → `FAIL top-risks callout lists high-risk concepts`

- [ ] **Step 3: Implement** in `render.py` `main()`, before `overview = ""`:

```python
    risky = [c for c in concepts
             if (c.get("risk") or "").strip().lower() in ("high", "med")]
    risks_html = ""
    if risky:
        items = []
        for c in risky:
            reason = (c.get("risk_reason") or "").strip()
            rval = (c.get("risk") or "").strip().lower()
            name = esc(c.get("name", f"Concept {c['id']}"))
            items.append(
                f'<li class="risk-item"><a href="#concept-{c["id"]}">'
                f'<span class="risk-badge">{esc(rval)}</span>{name}'
                + (f'<span class="risk-why">{esc(reason)}</span>' if reason else "")
                + '</a></li>')
        risks_html = (f'<section class="risks"><h2>Review first</h2>'
                      f'<ol>{"".join(items)}</ol></section>')
```
Place `risks_html` in the body BEFORE the overview:
`body_html = "<main>" + risks_html + overview + "\n".join(body) + "</main>"`

- [ ] **Step 4: CSS** (append near `.overview`):

```css
.risks{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--del);
border-radius:14px;padding:16px 20px;margin-bottom:26px}
.risks h2{font-size:13px;letter-spacing:.1em;text-transform:uppercase;color:var(--del);margin-bottom:10px}
.risks ol{list-style:none}
.risk-item a{display:flex;align-items:baseline;gap:10px;color:var(--ink);text-decoration:none;
padding:5px 4px;border-radius:8px;font-size:14px}
.risk-item a:hover{background:var(--panel2)}
.risk-badge{flex:none;font:700 10px/1.6 ui-monospace,monospace;text-transform:uppercase;
padding:2px 7px;border-radius:5px;background:var(--del-bg);color:var(--del)}
.risk-item a[href*="concept"] .risk-badge{background:var(--del-bg)}
.risk-why{color:var(--muted);font-size:12.5px}
@media print{.risks{display:none}}
```

- [ ] **Step 5: Run suite** → all PASS (28 checks). **Step 6: Commit**

```bash
git commit -am "lens: top-risks callout for high/med risk concepts"
```

## Task 3: Dependency graph (hand-rolled SVG DAG)

**Files:**
- Modify: `skills/diff-intent-timeline/scripts/render.py` (new `render_dag()` function + CSS + placement)
- Test: `test/verify.py`

**Interfaces:**
- Consumes: `concepts` list with `depends_on` (existing).
- Produces: `render_dag(concepts)` → str (SVG or `""` when fewer than 2 concepts); markup inserted above the overview in `main()`.
- Algorithm contract (fixed): column index = longest path from roots (no deps → 0; else `1 + max(dep columns)`); within a column, concepts stack top-to-bottom in `depends_on` order then id order; edges drawn left→right from dep node right-center to dependent node left-center with an arrowhead marker. Node = `<a href="#concept-N">` wrapping a rect + number + truncated name.

- [ ] **Step 1: Failing check** in `verify.py`:

```python
check("dependency graph svg present",
      '<svg class="dag"' in s and "<marker" in s and "concept-2" in s)
```

- [ ] **Step 2: Verify failure** → `FAIL dependency graph svg present`

- [ ] **Step 3: Implement** `render_dag(concepts)` in `render.py` (module level, before `main`):

```python
def render_dag(concepts):
    """Layered dependency DAG as inline SVG (stdlib only). Columns are the
    longest-path depth from root concepts; edges always run left -> right.
    Returns '' when there are fewer than 2 concepts (nothing to map)."""
    if len(concepts) < 2:
        return ""
    by_id = {c["id"]: c for c in concepts}
    deps = {c["id"]: [d for d in (c.get("depends_on") or [])
                      if d in by_id and d != c["id"]] for c in concepts}
    memo, visiting = {}, set()

    def depth(cid):
        if cid in memo:
            return memo[cid]
        if cid in visiting:  # depends_on cycle (agent-authored): treat as root
            return 0
        visiting.add(cid)
        memo[cid] = 0 if not deps[cid] else 1 + max((depth(d) for d in deps[cid]), default=0)
        visiting.discard(cid)
        return memo[cid]

    cols = {}
    for c in concepts:
        cols.setdefault(depth(c["id"]), []).append(c)
    for col in cols:
        cols[col].sort(key=lambda c: (min((deps[c["id"]] or [0])), c["id"]))
    NW, NH, GX, GY, CX = 180, 34, 22, 16, 70  # node w/h, gaps, column gap
    pos, col_h = {}, {}
    for col in sorted(cols):
        yy = GY
        for c in cols[col]:
            pos[c["id"]] = (GX + col * (NW + CX), yy)
            yy += NH + GY
        col_h[col] = yy
    width = GX * 2 + max(cols) * (NW + CX) + NW
    height = max(col_h.values())
    parts = [f'<svg class="dag" viewBox="0 0 {width} {height}" '
             f'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Concept dependency map">']
    parts.append('<defs><marker id="dag-arrow" viewBox="0 0 10 10" refX="9" refY="5" '
                 'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
                 '<path d="M0,0 L10,5 L0,10 z"/></marker></defs>')
    for c in concepts:
        for d in deps[c["id"]]:
            x1, y1 = pos[d][0] + NW, pos[d][1] + NH / 2
            x2, y2 = pos[c["id"]][0], pos[c["id"]][1] + NH / 2
            parts.append(f'<line class="dag-edge" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                         f'marker-end="url(#dag-arrow)"/>')
    for c in concepts:
        x, y = pos[c["id"]]
        name = esc((c.get("name") or "")[:24])
        parts.append(
            f'<a href="#concept-{c["id"]}"><g class="dag-node">'
            f'<rect x="{x}" y="{y}" width="{NW}" height="{NH}" rx="9"/>'
            f'<text x="{x + 14}" y="{y + NH / 2 + 4}" class="dag-num">{c["id"]}</text>'
            f'<text x="{x + 34}" y="{y + NH / 2 + 4}" class="dag-name">{name}</text>'
            f'</g></a>')
    parts.append("</svg>")
    return "".join(parts)
```

- [ ] **Step 4: Wire into main()** — insert before the overview:

```python
    dag_html = render_dag(concepts)
    body_html = "<main>" + dag_html + risks_html + overview + "\n".join(body) + "</main>"
```

- [ ] **Step 5: CSS** (append near `.overview`):

```css
svg.dag{display:block;width:100%;max-width:1100px;height:auto;margin:0 0 26px;
background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:14px}
.dag-edge{stroke:var(--muted);stroke-width:1.5}
#dag-arrow path{fill:var(--muted)}
.dag-node rect{fill:var(--panel2);stroke:var(--line);stroke-width:1}
.dag-node:hover rect{stroke:var(--accent)}
.dag-num{fill:var(--accent);font:700 12px/1 ui-monospace,monospace}
.dag-name{fill:var(--ink);font:600 12.5px/1 "Inter Variable","Inter",sans-serif}
```

- [ ] **Step 6: Run suite** → all PASS (29 checks). Also sanity-run the layout offline:

```bash
python3 -c "
import sys; sys.path.insert(0, 'skills/diff-intent-timeline/scripts')
import render as R
cs = [{'id':1,'name':'a','depends_on':[],'intent':''},
      {'id':2,'name':'b','depends_on':[1],'intent':''},
      {'id':3,'name':'c','depends_on':[1,2],'intent':''},
      {'id':4,'name':'d','depends_on':[],'intent':''}]
svg = R.render_dag(cs)
assert '<svg class="dag"' in svg and 'concept-1' in svg and 'concept-3' in svg
assert R.render_dag(cs[:1]) == ''  # single concept: no map
cyc = [{'id':1,'depends_on':[2],'intent':''},{'id':2,'depends_on':[1],'intent':''}]
assert R.render_dag(cyc) != ''    # depends_on cycle must not crash
print('dag ok')"
```

- [ ] **Step 7: Commit**

```bash
git add skills/diff-intent-timeline/scripts/render.py test/verify.py
git commit -m "lens: clickable dependency DAG (hand-rolled SVG, stdlib only)"
```

## Task 4: Tour mode (spotlight + floating tour bar)

**Files:**
- Modify: `skills/diff-intent-timeline/scripts/render.py` (CSS string, JS string)
- Test: `test/verify.py`

**Interfaces:**
- Consumes: existing `cards`/`steps` arrays and `goto(i)`/`setActive(i)` in the inline JS; concept cards as rendered.
- Produces: `#tour-toggle` header button; `body.tour-on` class; `.tour-bar` element (JS-created); `.tour-current` concept class. Contract: with tour ON, exactly one `.concept` is `.tour-current`; all others are dimmed (`opacity .28`, `pointer-events none`); the bar shows `N / total`, current name, intent (truncated), and Prev/Next/Close; `j`/`k` advance the tour; rail clicks and `goto()` jump the tour to the target concept.

- [ ] **Step 1: Failing check** in `verify.py` (the existing suite check already
parses the inline JS, so only the toggle presence is asserted here):

```python
check("tour toggle present", 'id="tour-toggle"' in s)
```

- [ ] **Step 2: Verify failure** → `FAIL tour toggle present`

- [ ] **Step 3: Implement CSS** (append near the `.fs-overlay` rules):

```css
button.ctl.tour-active{border-color:var(--accent);background:var(--accent-soft);color:var(--accent)}
body.tour-on .concept{opacity:.28;pointer-events:none;transition:opacity .25s}
body.tour-on .concept.tour-current{opacity:1;pointer-events:auto;box-shadow:0 0 0 3px var(--accent)}
.tour-bar{position:fixed;left:50%;bottom:16px;transform:translateX(-50%);z-index:95;display:flex;
align-items:center;gap:12px;max-width:min(760px,92vw);padding:10px 16px;border-radius:14px;
border:1px solid var(--line);background:color-mix(in srgb,var(--panel) 92%,transparent);
backdrop-filter:blur(8px);box-shadow:0 8px 24px rgba(0,0,0,.18)}
.tour-count{font:700 11px/1 ui-monospace,monospace;color:var(--muted);white-space:nowrap}
.tour-title{font:600 13.5px/1.3 "Inter Variable","Inter",sans-serif;white-space:nowrap;overflow:hidden;
text-overflow:ellipsis;max-width:220px}
.tour-intent{font-size:12px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;
white-space:nowrap;max-width:260px}
.tour-bar button{font:600 12px/1 inherit;padding:6px 10px;border-radius:8px;border:1px solid var(--line);
background:var(--panel);color:var(--ink);cursor:pointer;white-space:nowrap}
.tour-bar button:hover:not(:disabled){border-color:var(--accent);color:var(--accent)}
.tour-bar button:disabled{opacity:.4;cursor:default}
```

- [ ] **Step 4: Implement JS** (append inside the IIFE, after the fullscreen block):

```js
  // tour mode: spotlight one concept at a time with a floating narration bar
  var tourOn=false,tourI=0,tourBar=null;
  function tourCur(){return tourI<cards.length?cards[tourI]:null}
  function tourUpdate(){
    if(!tourBar)return;
    var c=tourCur();
    cards.forEach(function(x){x.classList.toggle('tour-current',x===c)});
    var prev=tourBar.querySelector('.tour-prev'),next=tourBar.querySelector('.tour-next');
    prev.disabled=tourI<=0;next.disabled=tourI>=cards.length-1;
    if(c){
      tourBar.querySelector('.tour-count').textContent=(tourI+1)+' / '+cards.length;
      var h=c.querySelector('h2');
      tourBar.querySelector('.tour-title').textContent=h?h.textContent:'';
      var it=c.querySelector('.intent');
      tourBar.querySelector('.tour-intent').textContent=it?it.textContent.replace(/^Why this exists/,'').trim():'';
    }
  }
  function tourGo(i){
    if(!tourOn)return;
    tourI=Math.max(0,Math.min(cards.length-1,i));
    goto(tourI);
    tourUpdate();
  }
  function tourBuild(){
    if(tourBar)return;
    tourBar=document.createElement('div');
    tourBar.className='tour-bar';
    tourBar.innerHTML='<button class="tour-prev" type="button">&#8592;</button>'
      +'<span class="tour-count"></span>'
      +'<span class="tour-title"></span><span class="tour-intent"></span>'
      +'<button class="tour-next" type="button">&#8594;</button>'
      +'<button class="tour-close" type="button">End tour</button>';
    tourBar.querySelector('.tour-prev').addEventListener('click',function(){tourGo(tourI-1)});
    tourBar.querySelector('.tour-next').addEventListener('click',function(){tourGo(tourI+1)});
    tourBar.querySelector('.tour-close').addEventListener('click',tourOff);
    document.body.appendChild(tourBar);
  }
  function tourOn_(){tourBuild();tourOn=true;document.body.classList.add('tour-on');tourGo(0);}
  function tourOff(){tourOn=false;document.body.classList.remove('tour-on');
    cards.forEach(function(x){x.classList.remove('tour-current')});
    document.getElementById('tour-toggle').classList.remove('tour-active');
    document.getElementById('tour-toggle').textContent='Tour';}
  var btnTour=document.createElement('button');
  btnTour.id='tour-toggle';btnTour.className='ctl';btnTour.type='button';btnTour.textContent='Tour';
  btnTour.addEventListener('click',function(){
    if(tourOn){tourOff();}else{tourOn_();this.classList.add('tour-active');this.textContent='End tour';}
  });
  document.querySelector('.chips').appendChild(btnTour);
```
In the existing keydown handler, before the `if(e.target.closest(...))` line, add:
```js
    if(tourOn){if(e.key==='j'||e.key==='ArrowDown'){e.preventDefault();tourGo(tourI+1);return;}
      if(e.key==='k'||e.key==='ArrowUp'){e.preventDefault();tourGo(tourI-1);return;}}
```
In `goto()`, add a tour sync line (so rail clicks and Next-concept buttons advance the tour when on):
```js
    if(tourOn){tourI=i;tourUpdate();}
```

- [ ] **Step 5: Run suite** → all PASS (30 checks). **Step 6: Browser smoke** (manual, in the existing headless browser session):

Open `docs/preview.html` (regenerated in Task 6) or a temp render; click `Tour`; assert: one `.tour-current`, others dimmed, bar shows `1 / N`, Next advances and scrolls, `j`/`k` advance, `End tour` restores. **Step 7: Commit**

```bash
git add skills/diff-intent-timeline/scripts/render.py test/verify.py
git commit -m "lens: guided tour mode (spotlight + floating narration bar)"
```

## Task 5: SKILL.md authoring guidance + regenerate preview + final regression

**Files:**
- Modify: `skills/diff-intent-timeline/SKILL.md`, `docs/preview.html` (regenerated)
- Test: `test/verify.py`

- [ ] **Step 1: SKILL.md** — in Step 2 (Cluster), after the `depends_on` sentence, add:

> **Optional lens fields** (skip when unsure — the page still works without them):
> `"layer"` — one of `schema | infra | domain | api | test | docs | other` (the
> architecture layer this concept lives in; the rail and meta show it).
> `"risk"` — `low | med | high` plus `"risk_reason"` (one line: what breaks or
> what to check — auth, money, parsing, concurrency, data migrations, etc.).
> High/med concepts are collected into a "Review first" callout on the page.

- [ ] **Step 2: Regenerate the sample** (fixture has no lens fields — proves backward compat):

```bash
python3 skills/diff-intent-timeline/scripts/render.py \
  --chunks /tmp/dit-fixture-regen/chunks.json \
  --concepts /tmp/dit-fixture-regen/concepts.json \
  --title "orders-service: implement order placement flow" \
  --subtitle "/tmp/dit-fixture  &middot;  commit HEAD" --out docs/preview.html
```

- [ ] **Step 3: Full regression + browser sanity**

Run: `python3 test/verify.py` → all PASS (30 checks). Then in the browser: open the regenerated `docs/preview.html` — assert: the dependency map IS present (the fixture's `depends_on` chains `[],[1],[2],[3],[3],[4]` give 6 concepts → `render_dag` returns an SVG; it must be visible above the overview and its nodes clickable to `#concept-N`), NO lens chips or risk callout (fixture has no `layer`/`risk` fields → backward compat), and the Tour toggle exists and works on a 6-concept page (Next stays enabled through concept 6, then disabled).

- [ ] **Step 4: Commit**

```bash
git add skills/diff-intent-timeline/SKILL.md docs/preview.html
git commit -m "lens: document layer/risk authoring; regenerate sample (backward compatible)"
```

---

## Self-Review (performed by plan author before handing to reviewer)

- **Spec coverage:** tour ✓ (Task 4), graph ✓ (Task 3), layers ✓ (Tasks 1+5), risk ✓ (Tasks 1+2+5), schema extension ✓ (Task 1), backward compat ✓ (Tasks 1+5), single-file/determinism ✓ (constraints, no new assets), verify.py checks per feature ✓.
- **Placeholders:** none. (The adversarial pass removed the Task 1 placeholder and the `run(input=)` node check.)
- **Type consistency:** `render_dag(concepts)` used in main() (Task 3) matches definition; `risks_html`/`dag_html` ordering in `body_html` consistent; tour JS names (`tourGo/tourOn_/tourOff/tourUpdate/tourBuild/tourCur`) consistent across steps; `chip-layer`/`chip-risk-*` classes consistent between Task 1 emission and CSS.
- **Risk noted for reviewer:** `tourGo` calls `goto()` which calls `setActive` — rail highlight follows tour ✓ intended; `tourI` vs `cur` divergence when user scrolls manually mid-tour is acceptable (next/prev re-anchor). SVG `<a>` inside inline SVG on `file://` — anchors work in Chrome; verify in Task 6 smoke.
