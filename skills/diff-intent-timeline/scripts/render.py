#!/usr/bin/env python3
"""render.py - render chunks.json + concepts.json into a single-file HTML
"timeline by intent" review page.  No network, no server: one self-contained
.html you can open from disk or share.

Part of the diff-intent-timeline skill (see SKILL.md).

Usage:
  python3 render.py --chunks chunks.json --concepts concepts.json \
      [--title "..."] [--subtitle "..."] [--out timeline.html] [--no-highlight]

Python 3 stdlib; syntax highlighting via pygments when installed (optional).
Diffs render GitHub-style side-by-side (old | new), with same-position
replacement pairs aligned on one row. Light + dark themes with scoped
pygments palettes ('friendly' for light, 'monokai' for dark).
"""

import argparse
import base64
import difflib
import html
import json
import re
import sys
from pathlib import Path

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")

FONT_DIR = Path(__file__).resolve().parent.parent / "fonts"


def embed_font(family, woff2_name, weight_range):
    """Inline an OFL variable font as base64 @font-face (keeps the page
    self-contained and offline). Returns '' if the file is missing."""
    p = FONT_DIR / woff2_name
    if not p.exists():
        return ""
    data = base64.b64encode(p.read_bytes()).decode()
    return (f"@font-face{{font-family:'{family}';font-style:normal;font-weight:{weight_range};"
            f"font-display:swap;src:url(data:font/woff2;base64,{data}) format('woff2')}}")


FONT_FACE = (embed_font("Inter Variable", "inter-latin.woff2", "100 900") +
             embed_font("JetBrains Mono Variable", "jbm-latin.woff2", "100 800"))

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
--add:#4ade80;--add-bg:rgba(74,222,128,.14);--del:#fda4af;--del-bg:rgba(248,113,113,.13);
--hunk:#c4b5fd;--hunk-bg:rgba(139,92,246,.12);--code:#eae8e5;--rail:#111419;
--shadow:0 1px 2px rgba(0,0,0,.4)}
*{box-sizing:border-box;margin:0;padding:0}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:4px}
button:active{transform:translateY(1px)}
details.hunk summary:focus-visible{outline-offset:-2px}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--ink);font:16px/1.6 "Inter Variable","Inter",-apple-system,
BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;-webkit-font-smoothing:antialiased}
code,kbd,.mono{font-family:"JetBrains Mono Variable","JetBrains Mono",ui-monospace,"SF Mono",
"Cascadia Code",Menlo,Consolas,monospace}
#progress{position:fixed;top:0;left:0;height:3px;width:0;background:var(--accent);z-index:60;transition:width .08s linear}
header.top{position:sticky;top:0;z-index:50;background:color-mix(in srgb,var(--bg) 88%,transparent);
backdrop-filter:blur(8px);border-bottom:1px solid var(--line);padding:14px 32px}
.top-row{display:flex;align-items:center;gap:14px;flex-wrap:wrap}
h1{font-size:19px;font-weight:700;letter-spacing:-.01em}
.subtitle{color:var(--muted);font-size:13px;margin-top:2px;max-width:760px;overflow:hidden;
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
#rail{width:248px;flex:none;position:sticky;top:84px;align-self:flex-start;height:calc(100vh - 104px);
overflow:auto;background:var(--rail);border:1px solid var(--line);border-radius:14px;padding:14px 12px}
.rail-title{font-size:11px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);
padding:2px 8px 10px}
#steps{list-style:none;position:relative}
#steps::before{content:"";position:absolute;left:18px;top:10px;bottom:0;width:2px;
background:linear-gradient(var(--line),color-mix(in srgb,var(--line) 20%,transparent))}
.step{display:flex;flex-wrap:wrap;gap:10px;align-items:flex-start;width:100%;text-align:left;background:none;border:0;
color:var(--ink);padding:7px 8px;border-radius:9px;cursor:pointer;position:relative}
.step:hover{background:var(--panel)}
.step.active{background:var(--panel);box-shadow:0 2px 8px rgba(0,0,0,.12)}
.dot{flex:none;width:22px;height:22px;border-radius:50%;background:var(--panel);border:2px solid var(--line);
color:var(--muted);font:700 11px/18px ui-monospace,monospace;text-align:center;position:relative;z-index:1}
.step.active .dot{background:var(--accent);border-color:var(--accent);color:#fff}
.sname{font-size:13px;font-weight:600;line-height:1.35;padding-top:2px}
.step.active .sname{color:var(--accent)}
.sdep{display:block;flex-basis:100%;font-size:10.5px;color:var(--muted);font-weight:500;margin-top:1px;margin-left:32px}
main{flex:1;min-width:0}
.overview{background:linear-gradient(135deg,var(--accent-soft),transparent 60%);border:1px solid var(--line);
border-left:3px solid var(--accent);border-radius:14px;padding:20px 22px;margin-bottom:26px}
.overview h2{font-size:13px;letter-spacing:.1em;text-transform:uppercase;color:var(--accent);margin-bottom:8px}
.overview p{font-size:15px;color:var(--ink);max-width:75ch}
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
svg.dag{display:block;width:100%;max-width:1100px;height:auto;margin:0 0 26px;
background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:14px}
.dag-edge{stroke:var(--muted);stroke-width:1.5}
#dag-arrow path{fill:var(--muted)}
.dag-node rect{fill:var(--panel2);stroke:var(--line);stroke-width:1}
.dag-node:hover rect{stroke:var(--accent)}
.dag-num{fill:var(--accent);font:700 12px/1 ui-monospace,monospace}
.dag-name{fill:var(--ink);font:600 12.5px/1 "Inter Variable","Inter",sans-serif}
.concept{background:var(--panel);border:1px solid var(--line);border-radius:16px;margin:0 0 30px;
overflow:hidden;box-shadow:var(--shadow);scroll-margin-top:96px}
.c-head{display:flex;gap:16px;padding:18px 22px 0;align-items:flex-start}
.c-num{flex:none;width:38px;height:38px;border-radius:11px;background:var(--accent);color:#fff;
font:700 17px/38px ui-monospace,monospace;text-align:center;box-shadow:0 2px 8px rgba(79,70,229,.35)}
.c-titles{min-width:0}
.c-titles h2{font-size:17px;font-weight:700;letter-spacing:-.01em}
.c-meta{display:flex;gap:6px;flex-wrap:wrap;margin-top:6px}
.chip.sm{font-size:11px;padding:2px 8px;border-radius:6px;background:var(--panel2);border:1px solid var(--line);
color:var(--muted);font-weight:600}
.chip.sm .plus{color:var(--add)} .chip.sm .minus{color:var(--del)}
.chip.sm.chip-layer{background:var(--accent-soft);color:var(--accent);border-color:color-mix(in srgb,var(--accent) 30%,transparent)}
.chip.sm.chip-risk{text-transform:uppercase;font-size:10px;letter-spacing:.05em}
.chip.sm.chip-risk-low{background:var(--add-bg);color:var(--add)}
.chip.sm.chip-risk-med{background:rgba(245,158,11,.12);color:#b45309}
:root[data-theme=dark] .chip.sm.chip-risk-med{color:#fbbf24}
.chip.sm.chip-risk-high{background:var(--del-bg);color:var(--del)}
.intent{margin:14px 22px 0;padding:12px 16px;background:var(--accent-soft);border-left:3px solid var(--accent);
border-radius:0 10px 10px 0;font-size:14px;color:var(--ink);max-width:75ch}
.intent .why{font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--accent);
display:block;margin-bottom:3px}
.hunks{padding:14px 22px 20px}
details.hunk{border:1px solid var(--line);border-radius:10px;margin-top:10px;background:var(--panel2);
overflow:hidden}
details.hunk[open]{box-shadow:var(--shadow)}
details.hunk summary{display:flex;gap:10px;align-items:center;cursor:pointer;padding:9px 14px;
list-style:none;user-select:none}
details.hunk summary::-webkit-details-marker{display:none}
details.hunk summary:hover{background:var(--panel)}
details.hunk summary:hover .caret{color:var(--accent)}
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
.fs-hint{margin-left:auto;display:flex;align-items:center;gap:6px;color:var(--muted);font-size:11.5px}
kbd{font:600 10.5px/1.4 "JetBrains Mono Variable",ui-monospace,monospace;padding:2px 6px;border:1px solid var(--line);
border-bottom-width:2px;border-radius:5px;background:var(--panel);color:var(--muted)}
.fs-close{font:600 12px/1 inherit;min-height:34px;padding:7px 14px;border-radius:8px;border:1px solid var(--line);
background:var(--panel);color:var(--ink);cursor:pointer}
.fs-close:hover{border-color:var(--accent);color:var(--accent)}
.fs-overlay .diff{flex:1;min-height:0;overflow:auto;border:1px solid var(--line);border-radius:12px;
background:var(--panel2);font-size:14.5px}
.fs-overlay .dl .ln{font-size:12px}
/* tour mode: spotlight one concept at a time with a floating narration bar */
button.ctl.tour-active{border-color:var(--accent);background:var(--accent-soft);color:var(--accent)}
body.tour-on .concept{opacity:.28;pointer-events:none;transition:opacity .25s}
body.tour-on svg.dag,body.tour-on .risks{opacity:.28;pointer-events:none}
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
/* side-by-side diff: 4-column grid (old-ln | old-code | new-ln | new-code) */
.diff{overflow-x:auto;border-top:1px solid var(--line);font-size:13.5px;line-height:1.5;
scrollbar-width:thin;scrollbar-color:color-mix(in srgb,var(--muted) 45%,transparent) transparent}
/* styled webkit scrollbars are classic (always visible), not macOS overlay */
.diff::-webkit-scrollbar{width:10px;height:10px}
.diff::-webkit-scrollbar-thumb{background:color-mix(in srgb,var(--muted) 45%,transparent);border-radius:5px;
border:2px solid transparent;background-clip:content-box}
.diff::-webkit-scrollbar-thumb:hover{background:color-mix(in srgb,var(--muted) 70%,transparent);
border:2px solid transparent;background-clip:content-box}
.diff::-webkit-scrollbar-track{background:transparent}
.dl{display:grid;grid-template-columns:4em minmax(0,1fr) 4em minmax(0,1fr);min-width:0}
/* GitHub split view: a deleted+added pair at the same position aligns on one
   row - red old half (left), green new half (right) */
.dl-pair .ln:nth-child(1),.dl-pair .code:nth-child(2){background:var(--del-bg)}
.dl-pair .ln:nth-child(3),.dl-pair .code:nth-child(4){background:var(--add-bg)}
.dl-pair .code:nth-child(2){color:var(--del)}
.dl-pair .code:nth-child(4){color:var(--add)}
/* intra-line word diffs (GitHub-style): deleted words struck through on a
   deeper red, added words on a deeper green */
.w-del{background:color-mix(in srgb,var(--del) 24%,transparent);text-decoration:line-through;
text-decoration-color:color-mix(in srgb,var(--del) 60%,transparent)}
.w-add{background:color-mix(in srgb,var(--add) 28%,transparent)}
.dl .ln{text-align:right;padding:0 10px;color:var(--muted);user-select:none;font-size:11px;
background:inherit;border-right:1px solid var(--line);font-variant-numeric:tabular-nums;
position:sticky;left:0}
.dl .ln:nth-child(3){left:auto;border-left:1px solid var(--line);
background:color-mix(in srgb,var(--line) 60%,transparent)}
/* gutter must be opaque: content scrolls beneath the sticky old-ln column.
   light row tints are opaque hex; dark tints are translucent, so pin solid. */
:root[data-theme=dark] .dl .ln{background:var(--panel2)}
.dl .code{padding:0 12px;white-space:pre-wrap;overflow-wrap:anywhere;color:var(--code);
font-family:"JetBrains Mono Variable","JetBrains Mono",ui-monospace,"SF Mono","Cascadia Code",Menlo,Consolas,monospace}
.dl-add{background:var(--add-bg)} .dl-add .code{color:var(--add)}
.dl-del{background:var(--del-bg)} .dl-del .code{color:var(--del)}
.dl-ctx .code{color:var(--muted)}
:root:not([data-theme=dark]) .dl-ctx .code{color:var(--code)}
.dl-hunk .code,.dl-nl .code{grid-column:1/-1;padding:2px 12px;font-weight:600}
.dl-hunk{background:var(--hunk-bg)} .dl-hunk .code{color:var(--hunk)}
.dl-nl .code{color:var(--muted);font-style:italic;font-weight:400}
.next-wrap{display:flex;justify-content:flex-end;padding:0 22px 18px}
.next-wrap.has-hunk{border-top:1px solid var(--line);margin-top:14px;padding-top:14px}
button.next{font:600 12.5px/1 inherit;padding:8px 14px;border-radius:9px;border:1px solid var(--accent);
background:var(--accent);color:#fff;cursor:pointer}
button.next:hover{filter:brightness(1.1)}
.hunks .empty{color:var(--muted);font-size:13px;padding:2px 2px 0}
footer{padding:30px;text-align:center;color:var(--muted);font-size:13px;border-top:1px solid var(--line)}
@media (max-width:900px){.layout{flex-direction:column;padding:0 14px}
header.top{padding:12px 14px}
#rail{position:static;width:auto;height:auto;max-height:none}#steps{display:flex;flex-wrap:wrap;gap:4px}
#steps::before{display:none}.step{width:auto;min-height:44px;border:1px solid var(--line);background:var(--panel);
padding:8px 14px;border-radius:999px}.dot{display:none}.sdep{margin-left:0}
button.fs,button.ctl,button.next{min-height:44px;padding:10px 16px}
details.hunk summary{min-height:44px;padding:12px 14px}}
@media (max-width:700px){.dl{grid-template-columns:2.5em minmax(0,1fr) 2.5em minmax(0,1fr)}}
@media (max-width:480px){.chips{gap:6px}.chip{font-size:11px;padding:3px 8px}
button.ctl{font-size:11.5px;padding:6px 10px}}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}#progress,.caret{transition:none}}
@media print{header.top,#rail,.next-wrap,button,.fs-overlay,.tour-bar{display:none!important}.concept{break-inside:avoid;
box-shadow:none}.layout{display:block;max-width:none;padding:0}}
"""

# light-theme syntax tokens: pygments "friendly" fails WCAG AA on 13.5px code
# (comments ~2.9:1, numbers ~3.1:1, diff add/del markers ~3.3:1). GitHub-Light
# values, all >= 4.5:1 on the pale tints. Dark keeps Monokai. Appended AFTER
# pyg_css so equal-specificity rules win.
LIGHT_TOKENS = """
:root:not([data-theme=dark]) .diff .c,
:root:not([data-theme=dark]) .diff .ch,
:root:not([data-theme=dark]) .diff .cm,
:root:not([data-theme=dark]) .diff .c1,
:root:not([data-theme=dark]) .diff .cs,
:root:not([data-theme=dark]) .diff .cpf{color:#5c6670;font-style:italic}
:root:not([data-theme=dark]) .diff .m,
:root:not([data-theme=dark]) .diff .mb,
:root:not([data-theme=dark]) .diff .mf,
:root:not([data-theme=dark]) .diff .mh,
:root:not([data-theme=dark]) .diff .mi,
:root:not([data-theme=dark]) .diff .mo,
:root:not([data-theme=dark]) .diff .il{color:#0550ae}
:root:not([data-theme=dark]) .diff .gi{color:#116329}
:root:not([data-theme=dark]) .diff .gd{color:#82071e}
"""

JS = """
(function(){
  var steps=[].slice.call(document.querySelectorAll('.step'));
  var cards=[].slice.call(document.querySelectorAll('.concept'));
  var cur=0;
  var reduceMotion=window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches;
  function setActive(i){cur=i;steps.forEach(function(s){s.classList.toggle('active',+s.dataset.index===i)});}
  function goto(i){if(i<0||i>=cards.length)return;var c=cards[i];c.querySelectorAll('details').forEach(function(d){d.open=true});
    c.scrollIntoView({behavior:reduceMotion?'auto':'smooth',block:'start'});setActive(i);
    if(tourOn){tourI=i;tourUpdate();}}
  var io=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting)setActive(+e.target.dataset.index)})},
    {rootMargin:'-30% 0px -60% 0px'});
  cards.forEach(function(c){io.observe(c)});
  setActive(0);
  steps.forEach(function(s){s.addEventListener('click',function(){goto(+s.dataset.index)})});
  document.querySelectorAll('.next').forEach(function(b){b.addEventListener('click',function(){goto(+b.dataset.next)})});
  document.addEventListener('keydown',function(e){
    if(fsOpen()){
      if(e.key==='Escape'){fsClose();e.preventDefault();}
      else if(e.key==='Tab'){e.preventDefault();if(fsOverlay)fsOverlay.querySelector('.fs-close').focus();}
      return;
    }
    if(tourOn){if(e.key==='j'||e.key==='ArrowDown'){e.preventDefault();tourGo(tourI+1);return;}
      if(e.key==='k'||e.key==='ArrowUp'){e.preventDefault();tourGo(tourI-1);return;}}
    if(e.target.closest('details,textarea,input,[contenteditable]'))return;
    if(e.key==='j'||e.key==='ArrowDown'){e.preventDefault();goto(Math.min(cur+1,cards.length-1));}
    if(e.key==='k'||e.key==='ArrowUp'){e.preventDefault();goto(Math.max(cur-1,0));}
  });
  // per-hunk fullscreen: covers the tab (overlay), not the browser
  var fsOverlay=null,fsTrigger=null;
  function fsOpen(){return !!fsOverlay&&fsOverlay.classList.contains('open')}
  function fsClose(){if(fsOverlay){fsOverlay.classList.remove('open');if(fsTrigger&&fsTrigger.focus)fsTrigger.focus();fsTrigger=null;}}
  function fsShow(hunk){
    if(!fsOverlay){
      fsOverlay=document.createElement('div');
      fsOverlay.className='fs-overlay';
      fsOverlay.setAttribute('role','dialog');
      fsOverlay.setAttribute('aria-modal','true');
      fsOverlay.innerHTML='<div class="fs-head"><span class="badge"></span><span class="fpath"></span>'
        +'<span class="fcounts"></span><span class="fs-hint"><kbd>Esc</kbd> close</span>'
        +'<button class="fs-close" type="button">Close</button></div>';
      fsOverlay.querySelector('.fs-close').addEventListener('click',fsClose);
      document.body.appendChild(fsOverlay);
    }
    var head=fsOverlay.querySelector('.fs-head');
    var badge=hunk.querySelector('.badge');
    var hb=head.querySelector('.badge');
    hb.className='badge '+badge.className.split(' ')[1];
    hb.textContent=badge.textContent;
    var fp=hunk.querySelector('.fpath').textContent;
    head.querySelector('.fpath').textContent=fp;
    head.querySelector('.fcounts').innerHTML=hunk.querySelector('.fcounts').innerHTML;
    var old=fsOverlay.querySelector('.diff');
    if(old)old.remove();
    fsOverlay.appendChild(hunk.querySelector('.diff').cloneNode(true));
    fsOverlay.setAttribute('aria-label','Fullscreen diff: '+fp);
    fsTrigger=hunk.querySelector('.fs');
    fsOverlay.classList.add('open');
    fsOverlay.querySelector('.fs-close').focus();
  }
  document.querySelectorAll('details.hunk').forEach(function(h){
    h.querySelector('.fs').addEventListener('click',function(e){
      e.preventDefault();e.stopPropagation();fsShow(h);
    });
  });
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
    if(tourBar){tourBar.remove();tourBar=null;}
    document.getElementById('tour-toggle').classList.remove('tour-active');
    document.getElementById('tour-toggle').textContent='Tour';}
  var btnTour=document.createElement('button');
  btnTour.id="tour-toggle";btnTour.className='ctl';btnTour.type='button';btnTour.textContent='Tour';
  btnTour.addEventListener('click',function(){
    if(tourOn){tourOff();}else{tourOn_();this.classList.add('tour-active');this.textContent='End tour';}
  });
  document.querySelector('.chips').appendChild(btnTour);
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
  btnTheme.setAttribute('aria-pressed',theme==='dark'?'true':'false');
  btnTheme.addEventListener('click',function(){
    theme=theme==='dark'?'light':'dark';root.dataset.theme=theme;
    btnTheme.textContent=theme==='dark'?'Light':'Dark';
    btnTheme.setAttribute('aria-pressed',theme==='dark'?'true':'false');
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
        # HtmlFormatter(nowrap=True) appends a trailing \n to every fragment;
        # strip it so highlighted cells/word-segments don't carry stray breaks
        return _pyg_hl(code, lexer, HtmlFormatter(nowrap=True)).rstrip("\n")
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


def word_diff(old, new, lang, want_hl):
    """Intra-line word diff, GitHub-style: returns (old_html, new_html) with
    changed words wrapped in w-del (old side) / w-add (new side) spans and
    unchanged words kept (syntax-highlighted when available)."""
    def tokens(s):
        return [t for t in re.split(r"(\w+|\W+)", s) if t]
    old_t, new_t = tokens(old), tokens(new)
    ops = difflib.SequenceMatcher(None, old_t, new_t, autojunk=False).get_opcodes()
    old_parts, new_parts = [], []
    for tag, i1, i2, j1, j2 in ops:
        if tag == "equal":
            old_parts.append(("", "".join(old_t[i1:i2])))
            new_parts.append(("", "".join(new_t[j1:j2])))
        elif tag == "delete":
            old_parts.append(("w-del", "".join(old_t[i1:i2])))
        elif tag == "insert":
            new_parts.append(("w-add", "".join(new_t[j1:j2])))
        else:  # replace
            old_parts.append(("w-del", "".join(old_t[i1:i2])))
            new_parts.append(("w-add", "".join(new_t[j1:j2])))

    def render(parts):
        out = []
        for wrap, text in parts:
            seg = highlight(text, lang) if want_hl else None
            seg = seg or esc(text)
            out.append(f'<span class="{wrap}">{seg}</span>' if wrap else seg)
        return "".join(out)

    return render(old_parts), render(new_parts)


def marked_to_html(marked, lang, want_hl):
    """Render a git --word-diff marked line: [-del-] -> w-del, {+add+} -> w-add;
    unchanged segments keep syntax highlighting when available."""
    parts = re.split(r"(\[-(.*?)-]|\{\+(.*?)\+\})", marked)
    out = []
    for j in range(0, len(parts), 4):
        plain = parts[j]
        if plain:
            seg = highlight(plain, lang) if want_hl else None
            out.append(seg or esc(plain))
        if j + 1 < len(parts) and parts[j + 1] is not None:
            full = parts[j + 1]
            is_del = full.startswith("[-")
            content = parts[j + 2] if is_del else parts[j + 3]
            seg = highlight(content, lang) if want_hl else None
            out.append(f'<span class="{"w-del" if is_del else "w-add"}">'
                       f'{seg or esc(content)}</span>')
    return "".join(out)


def render_hunk_rows(chunk, want_hl):
    """GitHub split-view rows: old | new. Context repeats on both sides;
    a deleted run followed by an added run is a same-position replacement
    and aligns as one row (red old half | green new half)."""
    rows = []
    lines = chunk.get("content", "").split("\n")
    m = HUNK_RE.match(lines[0]) if lines else None
    old_n, new_n = (int(m.group(1)), int(m.group(3))) if m else (0, 0)
    cells = []  # (cls, old_ln, new_ln, inner)
    if m:
        cells.append(("dl-hunk", "", "", esc(lines[0])))
    lang = chunk.get("language", "text")
    words = chunk.get("words") or {}
    for idx, line in enumerate(lines[1:], 1):
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
            tokens = highlight(code, lang)
            if tokens:
                inner = tokens
        cells.append((cls, old_ln, new_ln, inner, code, words.get(str(idx))))
    rows = []
    i, n = 0, len(cells)
    while i < n:
        cls, old_ln, new_ln, inner = cells[i][:4]
        if cls in ("dl-hunk", "dl-nl"):
            rows.append(f'<div class="dl {cls}"><span class="code">{inner}</span></div>')
            i += 1
            continue
        if cls == "dl-del" and i + 1 < n and cells[i + 1][0] == "dl-add":
            # GitHub split view: a deleted run followed by an added run is a
            # same-position replacement - align the pair row-by-row, red old
            # half on the left, green new half on the right
            j = i
            while j < n and cells[j][0] == "dl-del":
                j += 1
            k = j
            while k < n and cells[k][0] == "dl-add":
                k += 1
            dels, adds = cells[i:j], cells[j:k]
            for t in range(max(len(dels), len(adds))):
                d = dels[t] if t < len(dels) else None
                a = adds[t] if t < len(adds) else None
                if d and a:
                    if d[5] and a[5]:
                        old_html = marked_to_html(d[5], lang, want_hl)
                        new_html = marked_to_html(a[5], lang, want_hl)
                    else:
                        old_html, new_html = word_diff(d[4], a[4], lang, want_hl)
                else:
                    old_html = d[3] if d else ""
                    new_html = a[3] if a else ""
                rows.append(f'<div class="dl dl-pair"><span class="ln">{d[1] if d else ""}</span>'
                            f'<span class="code">{old_html}</span>'
                            f'<span class="ln">{a[2] if a else ""}</span>'
                            f'<span class="code">{new_html}</span></div>')
            i = k
            continue
        if cls == "dl-add":
            rows.append(f'<div class="dl {cls}"><span class="ln"></span><span class="code"></span>'
                        f'<span class="ln">{new_ln}</span><span class="code">{inner}</span></div>')
        elif cls == "dl-del":
            rows.append(f'<div class="dl {cls}"><span class="ln">{old_ln}</span><span class="code">{inner}</span>'
                        f'<span class="ln"></span><span class="code"></span></div>')
        else:
            rows.append(f'<div class="dl {cls}"><span class="ln">{old_ln}</span><span class="code">{inner}</span>'
                        f'<span class="ln">{new_ln}</span><span class="code">{inner}</span></div>')
        i += 1
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


def render_dag(concepts):
    """Layered dependency DAG as inline SVG (stdlib only). Columns are the
    longest-path depth from root concepts; edges run left -> right, except
    cycle back-edges.
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
            f'<a href="#concept-{c["id"]}" title="{esc(c.get("name") or "")}"><g class="dag-node">'
            f'<rect x="{x}" y="{y}" width="{NW}" height="{NH}" rx="9"/>'
            f'<text x="{x + 14}" y="{y + NH / 2 + 4}" class="dag-num">{c["id"]}</text>'
            f'<text x="{x + 34}" y="{y + NH / 2 + 4}" class="dag-name">{name}</text>'
            f'</g></a>')
    parts.append("</svg>")
    return "".join(parts)


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
    css_block = FONT_FACE + CSS + ("\n" + pyg_css if pyg_css else "") + LIGHT_TOKENS

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
        hunks = ("\n".join(render_hunk(c, not args.no_highlight, open_=first_open) for c in chunks_in)
                 if chunks_in else '<p class="empty">No hunks in this concept.</p>')
        if missing:
            hunks += (f'<div class="intent">[warn] missing chunks: {esc(", ".join(missing))}</div>')
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
        is_last = i == len(concepts) - 1
        nw_cls = "next-wrap" + (" has-hunk" if chunks_in else "")
        next_btn = ("" if is_last else
                    f'<div class="{nw_cls}"><button class="next" data-next="{i + 1}">'
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

    overview = ""
    if data.get("overview"):
        overview = (f'<section class="overview"><h2>Overview</h2><p>{esc(data["overview"])}</p></section>')

    dag_html = render_dag(concepts)
    body_html = "<main>" + dag_html + risks_html + overview + "\n".join(body) + "</main>"
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
