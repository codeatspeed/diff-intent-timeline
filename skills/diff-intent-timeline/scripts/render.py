#!/usr/bin/env python3
"""render.py - render chunks.json + concepts.json into a single-file HTML
"timeline by intent" review page.  No network, no server: one self-contained
.html you can open from disk or share.

Part of the diff-intent-timeline skill (see SKILL.md).

Usage:
  python3 render.py --chunks chunks.json --concepts concepts.json \
      [--title "..."] [--subtitle "..."] [--out timeline.html] [--no-highlight]

Python 3 stdlib; syntax highlighting via pygments when installed (optional).
Diffs render GitHub-style side-by-side (old | new). Light + dark themes with
scoped pygments palettes ('friendly' for light, 'monokai' for dark).
"""

import argparse
import html
import json
import re
import sys
from pathlib import Path

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")

STATUS_META = {
    "added": ("A", "add"), "modified": ("M", "mod"), "deleted": ("D", "del"),
    "renamed": ("R", "ren"),
}

CSS = """
:root{--bg:#f6f5f2;--panel:#fff;--panel2:#fbfaf7;--ink:#1c1b19;--muted:#6f6b63;
--line:#e6e3db;--accent:#4f46e5;--accent-soft:#eef0ff;--add:#15803d;--add-bg:#f0fdf4;
--del:#b91c1c;--del-bg:#fef2f2;--hunk:#7c3aed;--hunk-bg:#f6f1fd;--code:#141310;
--rail:#f0efeb;--shadow:0 1px 2px rgba(20,19,16,.06)}
:root[data-theme=dark]{--bg:#0e1013;--panel:#15181d;--panel2:#12151a;--ink:#eae8e5;
--muted:#a8adb5;--line:#2a3038;--accent:#818cf8;--accent-soft:rgba(99,102,241,.15);
--add:#4ade80;--add-bg:rgba(74,222,128,.10);--del:#fda4af;--del-bg:rgba(248,113,113,.13);
--hunk:#c4b5fd;--hunk-bg:rgba(139,92,246,.12);--code:#eae8e5;--rail:#111419;
--shadow:0 1px 2px rgba(0,0,0,.4)}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--ink);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",
Roboto,"Inter","Helvetica Neue",Arial,sans-serif;-webkit-font-smoothing:antialiased}
code,kbd,.mono{font-family:ui-monospace,"SF Mono","Cascadia Code","JetBrains Mono",Menlo,Consolas,monospace}
#progress{position:fixed;top:0;left:0;height:3px;width:0;background:var(--accent);z-index:60;transition:width .08s linear}
header.top{position:sticky;top:0;z-index:50;background:color-mix(in srgb,var(--bg) 88%,transparent);
backdrop-filter:blur(8px);border-bottom:1px solid var(--line);padding:14px 32px}
.top-row{display:flex;align-items:center;gap:14px;flex-wrap:wrap}
h1{font-size:19px;font-weight:700;letter-spacing:-.01em}
.subtitle{color:var(--muted);font-size:12.5px;margin-top:2px;max-width:760px;overflow:hidden;
text-overflow:ellipsis;white-space:nowrap}
.chips{margin-left:auto;display:flex;gap:8px;flex-wrap:wrap}
.chip{font-size:12px;font-weight:600;padding:4px 10px;border-radius:999px;background:var(--panel);
border:1px solid var(--line);color:var(--muted);white-space:nowrap}
.chip b{color:var(--ink)}
.chip .plus{color:var(--add)} .chip .minus{color:var(--del)}
button.ctl{font:600 12.5px/1 inherit;padding:6px 12px;border-radius:8px;border:1px solid var(--line);
background:var(--panel);color:var(--ink);cursor:pointer}
button.ctl:hover{border-color:var(--accent);color:var(--accent)}
.layout{display:flex;gap:28px;margin:26px auto 0;padding:0 32px;width:100%}
#rail{width:248px;flex:none;position:sticky;top:84px;align-self:flex-start;max-height:calc(100vh - 100px);
overflow:auto;background:var(--rail);border:1px solid var(--line);border-radius:14px;padding:14px 12px}
.rail-title{font-size:11px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);
padding:2px 8px 10px}
#steps{list-style:none;position:relative}
#steps::before{content:"";position:absolute;left:18px;top:10px;bottom:10px;width:2px;background:var(--line)}
.step{display:flex;gap:10px;align-items:flex-start;width:100%;text-align:left;background:none;border:0;
color:var(--ink);padding:7px 8px;border-radius:9px;cursor:pointer;position:relative}
.step:hover{background:var(--panel)}
.step.active{background:var(--panel);box-shadow:var(--shadow)}
.dot{flex:none;width:22px;height:22px;border-radius:50%;background:var(--panel);border:2px solid var(--line);
color:var(--muted);font:700 11px/18px ui-monospace,monospace;text-align:center;position:relative;z-index:1}
.step.active .dot{background:var(--accent);border-color:var(--accent);color:#fff}
.sname{font-size:12.5px;font-weight:600;line-height:1.35;padding-top:2px}
.step.active .sname{color:var(--accent)}
.sdep{display:block;font-size:10.5px;color:var(--muted);font-weight:500;margin-top:1px}
main{flex:1;min-width:0}
.overview{background:linear-gradient(135deg,var(--accent-soft),transparent 60%);border:1px solid var(--line);
border-left:3px solid var(--accent);border-radius:14px;padding:20px 22px;margin-bottom:26px}
.overview h2{font-size:13px;letter-spacing:.1em;text-transform:uppercase;color:var(--accent);margin-bottom:8px}
.overview p{font-size:14.5px;color:var(--ink)}
.concept{background:var(--panel);border:1px solid var(--line);border-radius:16px;margin:0 0 30px;
overflow:hidden;box-shadow:var(--shadow)}
.c-head{display:flex;gap:16px;padding:18px 22px 0;align-items:flex-start}
.c-num{flex:none;width:38px;height:38px;border-radius:11px;background:var(--accent);color:#fff;
font:700 17px/38px ui-monospace,monospace;text-align:center;box-shadow:0 2px 8px rgba(79,70,229,.35)}
.c-titles{min-width:0}
.c-titles h2{font-size:17px;font-weight:700;letter-spacing:-.01em}
.c-meta{display:flex;gap:6px;flex-wrap:wrap;margin-top:6px}
.chip.sm{font-size:11px;padding:2px 8px;border-radius:6px;background:var(--panel2);border:1px solid var(--line);
color:var(--muted);font-weight:600}
.chip.sm .plus{color:var(--add)} .chip.sm .minus{color:var(--del)}
.intent{margin:14px 22px 0;padding:12px 16px;background:var(--accent-soft);border-left:3px solid var(--accent);
border-radius:0 10px 10px 0;font-size:14px;color:var(--ink)}
.intent .why{font-size:10.5px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--accent);
display:block;margin-bottom:3px}
.hunks{padding:14px 22px 20px}
details.hunk{border:1px solid var(--line);border-radius:10px;margin-top:10px;background:var(--panel2);
overflow:hidden}
details.hunk[open]{box-shadow:var(--shadow)}
details.hunk summary{display:flex;gap:10px;align-items:center;cursor:pointer;padding:9px 14px;
list-style:none;user-select:none}
details.hunk summary::-webkit-details-marker{display:none}
summary .caret{color:var(--muted);font-size:11px;transition:transform .15s;width:10px}
details.hunk[open] summary .caret{transform:rotate(90deg)}
.badge{flex:none;font:700 10px/1 ui-monospace,monospace;padding:3px 7px;border-radius:5px}
.badge.add{background:var(--add-bg);color:var(--add);border:1px solid color-mix(in srgb,var(--add) 30%,transparent)}
.badge.mod{background:rgba(245,158,11,.12);color:#b45309;border:1px solid rgba(245,158,11,.35)}
:root[data-theme=dark] .badge.mod{color:#fbbf24}
.badge.del{background:var(--del-bg);color:var(--del);border:1px solid color-mix(in srgb,var(--del) 30%,transparent)}
.badge.ren{background:rgba(139,92,246,.12);color:var(--hunk);border:1px solid color-mix(in srgb,var(--hunk) 35%,transparent)}
.fpath{font:600 12.5px/1.4 ui-monospace,monospace;word-break:break-all}
.fcounts{margin-left:auto;font:600 11px ui-monospace,monospace;white-space:nowrap}
.fcounts .plus{color:var(--add)} .fcounts .minus{color:var(--del)} .fcounts .sep{color:var(--muted)}
button.fs{font:600 11px/1 ui-monospace,monospace;padding:4px 8px;border-radius:6px;border:1px solid var(--line);
background:var(--panel);color:var(--muted);cursor:pointer;white-space:nowrap}
button.fs:hover{border-color:var(--accent);color:var(--accent)}
/* tab-fullscreen overlay: covers the viewport, not the browser chrome */
.fs-overlay{position:fixed;inset:0;z-index:100;background:var(--bg);display:none;flex-direction:column;
padding:18px 32px 24px}
.fs-overlay.open{display:flex}
.fs-head{display:flex;align-items:center;gap:10px;padding-bottom:14px;border-bottom:1px solid var(--line);
margin-bottom:14px;flex-wrap:wrap}
.fs-head .fpath{font-size:14px}
.fs-close{margin-left:auto;font:600 12px/1 inherit;padding:6px 12px;border-radius:8px;border:1px solid var(--line);
background:var(--panel);color:var(--ink);cursor:pointer}
.fs-close:hover{border-color:var(--accent);color:var(--accent)}
.fs-overlay .diff{flex:1;min-height:0;overflow:auto;border:1px solid var(--line);border-radius:12px;
background:var(--panel2);font-size:14px}
/* side-by-side diff: 4-column grid (old-ln | old-code | new-ln | new-code) */
.diff{overflow-x:auto;border-top:1px solid var(--line);font-size:13px;line-height:1.5;
scrollbar-width:thin;scrollbar-color:color-mix(in srgb,var(--muted) 45%,transparent) transparent}
/* styled webkit scrollbars are classic (always visible), not macOS overlay */
.diff::-webkit-scrollbar{width:10px;height:10px}
.diff::-webkit-scrollbar-thumb{background:color-mix(in srgb,var(--muted) 45%,transparent);border-radius:5px;
border:2px solid transparent;background-clip:content-box}
.diff::-webkit-scrollbar-thumb:hover{background:color-mix(in srgb,var(--muted) 70%,transparent);
border:2px solid transparent;background-clip:content-box}
.diff::-webkit-scrollbar-track{background:transparent}
.dl{display:grid;grid-template-columns:4em minmax(0,1fr) 4em minmax(0,1fr);min-width:0}
/* add-only hunks have an empty old pane; collapse it so code gets full width */
.dl-own{grid-template-columns:0 0 4em minmax(0,1fr)}
.dl .ln{text-align:right;padding:0 10px;color:var(--muted);user-select:none;font-size:11px;
background:inherit;border-right:1px solid var(--line);
position:sticky;left:0}
.dl .ln:nth-child(3){left:auto}
/* gutter must be opaque: content scrolls beneath the sticky old-ln column.
   light row tints are opaque hex; dark tints are translucent, so pin solid. */
:root[data-theme=dark] .dl .ln{background:var(--panel2)}
.dl .code{padding:0 12px;white-space:pre-wrap;overflow-wrap:anywhere;color:var(--code);font-family:inherit}
.dl-add{background:var(--add-bg)} .dl-add .code{color:var(--add)}
.dl-del{background:var(--del-bg)} .dl-del .code{color:var(--del)}
.dl-ctx .code{color:var(--muted)}
.dl-hunk .code,.dl-nl .code{grid-column:1/-1;padding:2px 12px;font-weight:600}
.dl-hunk{background:var(--hunk-bg)} .dl-hunk .code{color:var(--hunk)}
.dl-nl .code{color:var(--muted);font-style:italic;font-weight:400}
.next-wrap{display:flex;justify-content:flex-end;padding:0 22px 18px}
button.next{font:600 12.5px/1 inherit;padding:8px 14px;border-radius:9px;border:1px solid var(--accent);
background:var(--accent);color:#fff;cursor:pointer}
button.next:hover{filter:brightness(1.1)}
footer{padding:30px;text-align:center;color:var(--muted);font-size:13px}
@media (max-width:900px){.layout{flex-direction:column;padding:0 14px}
header.top{padding:12px 14px}
#rail{position:static;width:auto;max-height:none}#steps{display:flex;flex-wrap:wrap;gap:4px}
#steps::before{display:none}.step{width:auto}.dot{display:none}}
@media print{header.top,#rail,.next-wrap,button{display:none!important}.concept{break-inside:avoid;
box-shadow:none}.layout{display:block;max-width:none;padding:0}}
"""

JS = """
(function(){
  var steps=[].slice.call(document.querySelectorAll('.step'));
  var cards=[].slice.call(document.querySelectorAll('.concept'));
  var cur=0;
  function setActive(i){cur=i;steps.forEach(function(s){s.classList.toggle('active',+s.dataset.index===i)});}
  function goto(i){if(i<0||i>=cards.length)return;var c=cards[i];c.querySelectorAll('details').forEach(function(d){d.open=true});
    c.scrollIntoView({behavior:'smooth',block:'start'});setActive(i);}
  var io=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting)setActive(+e.target.dataset.index)})},
    {rootMargin:'-30% 0px -60% 0px'});
  cards.forEach(function(c){io.observe(c)});
  setActive(0);
  steps.forEach(function(s){s.addEventListener('click',function(){goto(+s.dataset.index)})});
  document.querySelectorAll('.next').forEach(function(b){b.addEventListener('click',function(){goto(+b.dataset.next)})});
  document.addEventListener('keydown',function(e){
    if(fsOpen()){
      if(e.key==='Escape'){fsClose();e.preventDefault();}
      return;
    }
    if(e.target.closest('details,textarea,input,[contenteditable]'))return;
    if(e.key==='j'||e.key==='ArrowDown'){e.preventDefault();goto(Math.min(cur+1,cards.length-1));}
    if(e.key==='k'||e.key==='ArrowUp'){e.preventDefault();goto(Math.max(cur-1,0));}
  });
  // per-hunk fullscreen: covers the tab (overlay), not the browser
  var fsOverlay=null;
  function fsOpen(){return !!fsOverlay&&fsOverlay.classList.contains('open')}
  function fsClose(){if(fsOverlay)fsOverlay.classList.remove('open')}
  function fsShow(hunk){
    if(!fsOverlay){
      fsOverlay=document.createElement('div');
      fsOverlay.className='fs-overlay';
      fsOverlay.innerHTML='<div class="fs-head"><span class="badge"></span><span class="fpath"></span>'
        +'<span class="fcounts"></span><button class="fs-close" type="button">Close</button></div>';
      fsOverlay.querySelector('.fs-close').addEventListener('click',fsClose);
      document.body.appendChild(fsOverlay);
    }
    var head=fsOverlay.querySelector('.fs-head');
    var badge=hunk.querySelector('.badge');
    var hb=head.querySelector('.badge');
    hb.className='badge '+badge.className.split(' ')[1];
    hb.textContent=badge.textContent;
    head.querySelector('.fpath').textContent=hunk.querySelector('.fpath').textContent;
    head.querySelector('.fcounts').innerHTML=hunk.querySelector('.fcounts').innerHTML;
    var old=fsOverlay.querySelector('.diff');
    if(old)old.remove();
    fsOverlay.appendChild(hunk.querySelector('.diff').cloneNode(true));
    fsOverlay.classList.add('open');
  }
  document.querySelectorAll('details.hunk').forEach(function(h){
    h.querySelector('.fs').addEventListener('click',function(e){
      e.preventDefault();e.stopPropagation();fsShow(h);
    });
  });
  var bar=document.getElementById('progress');
  window.addEventListener('scroll',function(){var h=document.documentElement;
    bar.style.width=(h.scrollTop/(h.scrollHeight-h.clientHeight)*100)+'%';},{passive:true});
  var btnAll=document.getElementById('expand-all');
  btnAll.addEventListener('click',function(){
    var all=[].slice.call(document.querySelectorAll('details.hunk'));
    var anyClosed=all.some(function(d){return !d.open});
    all.forEach(function(d){d.open=anyClosed});
    btnAll.textContent=anyClosed?'Collapse all':'Expand all';
  });
  var btnTheme=document.getElementById('theme');
  var root=document.documentElement,stored=null;
  try{stored=localStorage.getItem('dit-theme')}catch(e){}
  var theme=stored||(window.matchMedia&&matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');
  root.dataset.theme=theme;
  btnTheme.textContent=theme==='dark'?'Light':'Dark';
  btnTheme.addEventListener('click',function(){
    theme=theme==='dark'?'light':'dark';root.dataset.theme=theme;
    btnTheme.textContent=theme==='dark'?'Light':'Dark';
    try{localStorage.setItem('dit-theme',theme)}catch(e){}
  });
})();
"""


def esc(s):
    return html.escape(str(s), quote=True)


def load_json(path, label):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        sys.exit(f"{label} not found: {path}")


def highlight(code, lang):
    if lang in ("text", "makefile"):
        return None
    try:
        from pygments import highlight as _pyg_hl
        from pygments.formatters import HtmlFormatter
        from pygments.lexers import get_lexer_by_name
        lexer = get_lexer_by_name(lang, stripall=False)
        return _pyg_hl(code, lexer, HtmlFormatter(nowrap=True))
    except Exception:
        return None


def scope_css(css, scope):
    """Prefix every selector in pygments-generated CSS with a theme scope."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)  # pygments appends /* token */ comments
    out = []
    for rule in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        sels, decls = rule
        scoped = ",".join(f"{scope} {s.strip()}" for s in sels.split(",") if s.strip())
        out.append(f"{scoped}{{{decls}}}")
    return "\n".join(out)


def render_hunk_rows(chunk, want_hl):
    """Side-by-side rows: old | new. Context shows on both sides, deletions
    only on the old side, additions only on the new side."""
    rows = []
    lines = chunk.get("content", "").split("\n")
    m = HUNK_RE.match(lines[0]) if lines else None
    old_n, new_n = (int(m.group(1)), int(m.group(3))) if m else (0, 0)
    cells = []  # (cls, old_ln, new_ln, inner)
    if m:
        cells.append(("dl-hunk", "", "", esc(lines[0])))
    for line in lines[1:]:
        if not line:
            continue
        if line.startswith("\\"):
            cells.append(("dl-nl", "", "", esc(line)))
            continue
        if line.startswith("@@"):
            cells.append(("dl-hunk", "", "", esc(line)))
            continue
        if line.startswith("+"):
            code, cls, old_ln, new_ln = line[1:], "dl-add", "", new_n
            new_n += 1
        elif line.startswith("-"):
            code, cls, old_ln, new_ln = line[1:], "dl-del", old_n, ""
            old_n += 1
        else:
            code, cls, old_ln, new_ln = (line[1:] if line.startswith(" ") else line,
                                         "dl-ctx", old_n, new_n)
            old_n += 1
            new_n += 1
        inner = esc(code)
        if cls in ("dl-add", "dl-del") and want_hl:
            tokens = highlight(code, chunk.get("language", "text"))
            if tokens:
                inner = tokens
        cells.append((cls, old_ln, new_ln, inner))
    content_cells = [c for c in cells if c[0] in ("dl-add", "dl-del", "dl-ctx")]
    own = " dl-own" if content_cells and all(c[0] == "dl-add" for c in content_cells) else ""
    rows = []
    for cls, old_ln, new_ln, inner in cells:
        if cls in ("dl-hunk", "dl-nl"):
            rows.append(f'<div class="dl {cls}"><span class="code">{inner}</span></div>')
        elif cls == "dl-add":
            rows.append(f'<div class="dl {cls}{own}"><span class="ln"></span><span class="code"></span>'
                        f'<span class="ln">{new_ln}</span><span class="code">{inner}</span></div>')
        elif cls == "dl-del":
            rows.append(f'<div class="dl {cls}{own}"><span class="ln">{old_ln}</span><span class="code">{inner}</span>'
                        f'<span class="ln"></span><span class="code"></span></div>')
        else:
            rows.append(f'<div class="dl {cls}{own}"><span class="ln">{old_ln}</span><span class="code">{inner}</span>'
                        f'<span class="ln">{new_ln}</span><span class="code">{inner}</span></div>')
    return "\n".join(rows)


def render_hunk(chunk, want_hl, open_=False):
    badge, bcls = STATUS_META.get(chunk.get("status", "modified"), ("M", "mod"))
    rows = render_hunk_rows(chunk, want_hl)
    return (f'<details class="hunk"{" open" if open_ else ""}><summary><span class="caret">&#9654;</span>'
            f'<span class="badge {bcls}">{badge}</span>'
            f'<span class="fpath">{esc(chunk["file"])}</span>'
            f'<span class="fcounts"><span class="plus">+{chunk.get("added", 0)}</span>'
            f'<span class="sep"> </span><span class="minus">-{chunk.get("removed", 0)}</span></span>'
            f'<button class="fs" type="button" title="Open hunk fullscreen">Fullscreen</button>'
            f'</summary><div class="diff">{rows}</div></details>')


def main():
    ap = argparse.ArgumentParser(description="Render intent-timeline HTML from chunks + concepts.")
    ap.add_argument("--chunks", required=True, help="chunks.json from prepare_diff.py")
    ap.add_argument("--concepts", required=True, help="concepts.json (agent-authored)")
    ap.add_argument("--title", default="Diff Intent Timeline")
    ap.add_argument("--subtitle", default="")
    ap.add_argument("--out", default=None,
                    help="output HTML path (default: timeline.html next to --chunks)")
    ap.add_argument("--no-highlight", action="store_true")
    args = ap.parse_args()

    chunks = load_json(args.chunks, "chunks")
    data = load_json(args.concepts, "concepts")
    concepts = data.get("concepts")
    if not concepts:
        sys.exit("concepts.json has no 'concepts' array - see SKILL.md schema")

    pyg_css = ""
    if not args.no_highlight:
        try:
            from pygments.formatters import HtmlFormatter
            pyg_css = (scope_css(HtmlFormatter(style="friendly").get_style_defs(".diff"),
                                 ":root:not([data-theme=dark])") + "\n" +
                       scope_css(HtmlFormatter(style="monokai").get_style_defs(".diff"),
                                 ":root[data-theme=dark]"))
        except Exception:
            pyg_css = ""
    css_block = CSS + ("\n" + pyg_css if pyg_css else "")

    by_id = {c["id"]: c for c in chunks}
    assigned = set()
    total_add = total_del = 0
    for c in chunks:
        total_add += c.get("added", 0)
        total_del += c.get("removed", 0)

    # auto-append unassigned chunks as a final concept so no hunk is lost
    for conept in concepts:
        for cid in conept.get("chunks", []):
            assigned.add(cid)
    orphans = [c for c in chunks if c["id"] not in assigned]
    if orphans:
        concepts = list(concepts) + [{
            "id": max((c.get("id", 0) for c in concepts), default=0) + 1,
            "name": "Unassigned chunks",
            "intent": "[auto] Chunks not assigned to any concept by the agent. "
                      "Review these explicitly - they may reveal a missed concept.",
            "depends_on": [], "chunks": [c["id"] for c in orphans],
        }]

    rail_steps, body = [], []
    for i, conept in enumerate(concepts):
        n = conept["id"]
        chunks_in = [by_id[cid] for cid in conept.get("chunks", []) if cid in by_id]
        missing = [cid for cid in conept.get("chunks", []) if cid not in by_id]
        ca = sum(c.get("added", 0) for c in chunks_in)
        cr = sum(c.get("removed", 0) for c in chunks_in)
        files = sorted({c["file"] for c in chunks_in})
        deps = conept.get("depends_on") or []
        dep_txt = "builds on " + ", ".join(f"#{d}" for d in deps) if deps else "foundation"
        first_open = n == 1 and len(chunks_in) <= 4
        hunks = "\n".join(
            render_hunk(c, not args.no_highlight, open_=first_open) for c in chunks_in)
        if missing:
            hunks += (f'<div class="intent">[warn] missing chunks: {esc(", ".join(missing))}</div>')
        meta = (f'<span class="chip sm">{len(files)} file{"s" if len(files) != 1 else ""}</span>'
                f'<span class="chip sm"><span class="plus">+{ca}</span>'
                f'<span class="sep"> </span><span class="minus">-{cr}</span></span>'
                f'<span class="chip sm">{len(chunks_in)} hunk{"s" if len(chunks_in) != 1 else ""}</span>'
                f'<span class="chip sm">{esc(dep_txt)}</span>')
        rail_steps.append(
            f'<li><button class="step" data-index="{i}"><span class="dot">{n}</span>'
            f'<span class="sname">{esc(conept["name"])}</span></button></li>')
        is_last = i == len(concepts) - 1
        next_btn = ("" if is_last else
                    f'<div class="next-wrap"><button class="next" data-next="{i + 1}">'
                    f'Next concept &#8595;</button></div>')
        body.append(f'''<article class="concept" id="concept-{n}" data-index="{i}">
<div class="c-head"><div class="c-num">{n}</div><div class="c-titles">
<h2>{esc(conept["name"])}</h2><div class="c-meta">{meta}</div></div></div>
<p class="intent"><span class="why">Why this exists</span>{esc(conept.get("intent", ""))}</p>
<div class="hunks">{hunks}</div>
{next_btn}
</article>''')

    subtitle = args.subtitle or ""
    try:
        summ = json.loads(Path(args.chunks).with_name("summary.json").read_text(encoding="utf-8"))
        src = summ.get("source", {})
        if not subtitle and src:
            subtitle = f"{src.get('repo', '')}  &middot;  {src.get('mode', '')}"
    except Exception:
        pass

    chips = (f'<span class="chip"><b>{len(concepts)}</b> concepts</span>'
             f'<span class="chip"><b>{len(chunks)}</b> hunks</span>'
             f'<span class="chip"><b class="plus">+{total_add}</b> <b class="minus">-{total_del}</b></span>')

    overview = ""
    if data.get("overview"):
        overview = (f'<section class="overview"><h2>Overview</h2><p>{esc(data["overview"])}</p></section>')

    body_html = "<main>" + overview + "\n".join(body) + "</main>"
    footer = ("<footer>diff-intent-timeline &middot; single-file review page"
              " &middot; generated from chunks.json + concepts.json</footer>")

    html_doc = ("""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title><style>__CSS__</style></head>
<body><div id="progress"></div>
<header class="top"><div class="top-row">
<div><h1>__TITLE__</h1><div class="subtitle">__SUBTITLE__</div></div>
<div class="chips">__CHIPS__<button class="ctl" id="expand-all">Expand all</button>
<button class="ctl" id="theme">Dark</button></div>
</div></header>
<div class="layout"><nav id="rail"><div class="rail-title">Timeline &middot; review order</div>
<ol id="steps">__STEPS__</ol></nav>
__BODY__
</div>
__FOOTER__
<script>__JS__</script></body></html>""")
    html_doc = (html_doc.replace("__TITLE__", esc(args.title))
                .replace("__SUBTITLE__", subtitle)
                .replace("__CHIPS__", chips)
                .replace("__STEPS__", "\n".join(rail_steps))
                .replace("__BODY__", body_html)
                .replace("__FOOTER__", footer)
                .replace("__CSS__", css_block)
                .replace("__JS__", JS))
    out_path = Path(args.out) if args.out else (Path(args.chunks).resolve().parent / "timeline.html")
    out_path.write_text(html_doc, encoding="utf-8")
    print(f"wrote {out_path.resolve()}")


if __name__ == "__main__":
    main()
