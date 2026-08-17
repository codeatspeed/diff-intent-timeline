#!/usr/bin/env python3
"""prepare_diff.py - extract a git diff into LLM-ready hunk chunks.

Part of the diff-review skill (see SKILL.md).

Input modes (choose one):
  --repo PATH --base REF [--head REF]   git diff base..worktree (or base..head)
  --repo PATH --commit SHA              diff of a single commit
  --pr URL                              fetch a pull-request diff over the network
  --diff-file PATH                      any unified diff file

Output: chunks.json + summary.json in --out dir (default: cwd).
Each chunk = one hunk of the diff, capped to --max-chunk-bytes.
Python 3 stdlib only.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")

LANG_MAP = {
    ".ts": "typescript", ".tsx": "tsx", ".js": "javascript", ".mjs": "javascript",
    ".cjs": "javascript", ".jsx": "jsx", ".go": "go", ".py": "python",
    ".sql": "sql", ".json": "json", ".yaml": "yaml", ".yml": "yaml",
    ".toml": "toml", ".md": "markdown", ".markdown": "markdown", ".html": "html",
    ".htm": "html", ".css": "css", ".scss": "scss", ".sh": "bash", ".bash": "bash",
    ".zsh": "bash", ".rs": "rust", ".java": "java", ".c": "c", ".h": "c",
    ".cpp": "cpp", ".hpp": "cpp", ".cc": "cpp", ".rb": "ruby", ".php": "php",
    ".kt": "kotlin", ".kts": "kotlin", ".swift": "swift", ".cs": "csharp",
    ".vue": "vue", ".svelte": "svelte", ".dockerfile": "docker", ".tf": "terraform",
    ".proto": "protobuf", ".graphql": "graphql", ".xml": "xml", ".svg": "xml",
    ".ipynb": "json",
}
DOCKERFILE = re.compile(r"(^|/)(Dockerfile)(\.\w+)?$")
MAKEFILE = re.compile(r"(^|/)(Makefile)$")


def guess_lang(path):
    if not path:
        return "text"
    p = path.lower()
    if DOCKERFILE.search(p) or MAKEFILE.search(p):
        return "makefile" if MAKEFILE.search(p) else "docker"
    return LANG_MAP.get(Path(p).suffix, "text")


def run(cmd, cwd=None):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if p.returncode != 0:
        sys.exit(f"command failed: {' '.join(cmd)}\n{p.stderr}")
    return p.stdout


PR_RE = re.compile(r"^(https?://[^/]+)/([^/]+)/([^/]+)/pull/(\d+)/?$")
PR_DIFF_RE = re.compile(r"^(https?://[^/]+)/([^/]+)/([^/]+)/pull/(\d+)\.diff$")


def pr_diff_url(url):
    """Map a pull-request URL to its unified-diff URL, or None if it isn't one."""
    if PR_DIFF_RE.match(url):
        return url
    m = PR_RE.match(url)
    return url + ".diff" if m else None


def auth_headers(url):
    """Auth headers for private-repo fetches, read from env tokens.

    The plain HTTP fetch never consults git credential helpers or SSH keys,
    so private repos need an explicit token: GH_TOKEN/GITHUB_TOKEN for
    GitHub, GITLAB_TOKEN/CI_JOB_TOKEN for GitLab. Alternatively embed the
    token in the URL (https://<TOKEN>@github.com/...), which urllib turns
    into Basic auth."""
    host = (urllib.parse.urlsplit(url).netloc or "").lower()
    if "github" in host:
        tok = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if tok:
            return {"Authorization": f"Bearer {tok}"}
    elif "gitlab" in host:
        tok = os.environ.get("GITLAB_TOKEN") or os.environ.get("CI_JOB_TOKEN")
        if tok:
            return {"PRIVATE-TOKEN": tok}
    return {}


def fetch_pr_diff(url):
    """Fetch a PR's unified diff over the network. Public repos work with a
    plain GET; private repos need a token (see auth_headers). The rendered
    page stays self-contained/offline - only the input is fetched."""
    diff_url = pr_diff_url(url)
    if not diff_url:
        sys.exit(f"not a pull-request URL: {url} "
                 f"(expected https://<host>/<owner>/<repo>/pull/<N>)")
    try:
        req = urllib.request.Request(diff_url, headers=auth_headers(diff_url))
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        sys.exit(f"failed to fetch {diff_url}: {e}\n"
                 f"  public repo: plain fetch works. Private repo: set "
                 f"GH_TOKEN/GITHUB_TOKEN (or GITLAB_TOKEN), or embed the token "
                 f"in the URL: https://<TOKEN>@github.com/owner/repo/pull/N")


def get_diff(args):
    if args.pr:
        return fetch_pr_diff(args.pr)
    if args.diff_file:
        return Path(args.diff_file).read_text(encoding="utf-8", errors="replace")
    repo = args.repo or "."
    diff_args = ["git", "-C", repo, "diff", "--no-color", "--no-ext-diff", "-M",
                 f"-U{args.context}"]
    if args.commit:
        diff_args = ["git", "-C", repo, "show", "--format=", "--no-color",
                     "--no-ext-diff", "-M", f"-U{args.context}", args.commit]
    elif args.base:
        diff_args += [args.base]
        if args.head:
            diff_args += [args.head]
    else:
        sys.exit("need one of: --pr, --commit, --base (with optional --head), --diff-file")
    return run(diff_args)


def truncate_lines(lines, max_bytes):
    """Cap a hunk's content; keep head+tail with a marker. Returns (lines, truncated)."""
    size = sum(len(l) + 1 for l in lines)
    if size <= max_bytes:
        return lines, False
    half = max_bytes // 2
    head, tail, acc = [], [], 0
    for l in lines:
        if acc + len(l) + 1 <= half:
            head.append(l); acc += len(l) + 1
        else:
            break
    acc = 0
    for l in reversed(lines):
        if acc + len(l) + 1 <= half:
            tail.append(l); acc += len(l) + 1
        else:
            break
    tail.reverse()
    marker = f"@@ ...TRUNCATED: {size} bytes in original hunk... @@"
    return head + [marker] + tail, True


def parse_word_marks(word_diff_text):
    """Parse `git diff --word-diff=plain` into per-hunk marker records.

    word-diff=plain emits each changed line ONCE with inline markers
    ([-deleted-] / {+added+}). Returns a list aligned with the normal
    parse's chunks: each element is a list of (old_marked, new_marked)
    tuples, or None when the text has no markers."""
    hunk_records, cur = [], []
    in_hunk = False
    for raw in word_diff_text.splitlines():
        line = raw.rstrip("\n")
        if line.startswith("diff --git "):
            in_hunk = False
            continue
        if line.startswith("@@"):
            if cur:
                hunk_records.append(cur)
                cur = []
            in_hunk = True
            continue
        if not in_hunk:
            continue
        if line.startswith(("---", "+++", "index", "new file", "deleted file",
                            "similarity", "rename", "Binary", "GIT binary")):
            continue
        if "[-" in line or "{+" in line:
            old_marked = re.sub(r"\{\+.*?\+\}", "", line)
            new_marked = re.sub(r"\[-.*?-\]", "", line)
            cur.append((old_marked, new_marked))
    if cur:
        hunk_records.append(cur)
    return hunk_records or None


def attach_word_marks(chunks, word_diff_text):
    """Match git word-diff markers to the plain-diff content lines (by order:
    records carry deletions on the old side, additions on the new side) and
    store chunk['words'] = {line_index: marked_line}. Content-identical lines
    without markers are left unmatched (render falls back to difflib)."""
    records = parse_word_marks(word_diff_text)
    if not records:
        return
    for chunk, recs in zip(chunks, records):
        if not recs:
            continue
        lines = chunk["content"].split("\n")
        del_idx = [i for i, l in enumerate(lines)
                   if l.startswith("-") and not l.startswith("---")]
        add_idx = [i for i, l in enumerate(lines)
                   if l.startswith("+") and not l.startswith("+++")]
        word_map, di, ai = {}, 0, 0
        for old_marked, new_marked in recs:
            if "[-" in old_marked and di < len(del_idx):
                word_map[str(del_idx[di])] = old_marked
                di += 1
            if "{+" in new_marked and ai < len(add_idx):
                word_map[str(add_idx[ai])] = new_marked
                ai += 1
        if word_map:
            chunk["words"] = word_map


def parse(diff_text, max_chunk_bytes):
    files, cur = [], None
    for raw in diff_text.splitlines():
        line = raw.rstrip("\n")
        if line.startswith("diff --git "):
            if cur:
                files.append(cur)
            cur = {"old": None, "new": None, "status": "modified",
                   "chunks": [], "skipped": False, "binary": False}
        elif cur is None:
            continue
        elif line.startswith("--- "):
            cur["old"] = None if line[4:] == "/dev/null" else line[4:]
        elif line.startswith("+++ "):
            cur["new"] = None if line[4:] == "/dev/null" else line[4:]
        elif line.startswith("new file mode"):
            cur["status"] = "added"
        elif line.startswith("deleted file mode"):
            cur["status"] = "deleted"
        elif line.startswith("rename from "):
            cur["status"] = "renamed"; cur["old"] = line[len("rename from "):]
        elif line.startswith("rename to "):
            cur["new"] = line[len("rename to "):]
        elif line.startswith("Binary files") or line.startswith("GIT binary patch"):
            cur["binary"] = True; cur["skipped"] = True
        elif cur["skipped"]:
            continue
        elif line.startswith("@@"):
            m = HUNK_RE.match(line)
            if not m:
                continue
            old_s, old_c = int(m.group(1)), int(m.group(2) or 1)
            new_s, new_c = int(m.group(3)), int(m.group(4) or 1)
            cur["chunks"].append({
                "old_start": old_s, "old_count": old_c,
                "new_start": new_s, "new_count": new_c,
                "section": m.group(5).strip(), "lines": [line],
            })
        elif cur["chunks"]:
            cur["chunks"][-1]["lines"].append(line)
    if cur:
        files.append(cur)

    chunks, skipped_binaries = [], []
    cid = 1
    for f in files:
        if f["binary"]:
            skipped_binaries.append({"old": f["old"], "new": f["new"]})
            continue
        display = f["new"] or f["old"]
        for h in f["chunks"]:
            lines, truncated = truncate_lines(h["lines"], max_chunk_bytes)
            added = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
            removed = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
            chunks.append({
                "id": f"c{cid:04d}",
                "file": display,
                "old_file": f["old"],
                "status": f["status"],
                "language": guess_lang(display),
                "old_start": h["old_start"], "old_count": h["old_count"],
                "new_start": h["new_start"], "new_count": h["new_count"],
                "section": h["section"],
                "added": added, "removed": removed,
                "truncated": truncated,
                "content": "\n".join(lines),
            })
            cid += 1

    files_out = []
    for f in files:
        if f["binary"]:
            continue
        a = sum(c["added"] for c in chunks if (c["file"] == (f["new"] or f["old"])))
        r = sum(c["removed"] for c in chunks if (c["file"] == (f["new"] or f["old"])))
        files_out.append({
            "path": f["new"] or f["old"], "status": f["status"],
            "added": a, "removed": r,
        })
    return chunks, files_out, skipped_binaries


def main():
    ap = argparse.ArgumentParser(description="Split a git diff into hunk chunks (JSON).")
    ap.add_argument("--repo", help="path to git repo (default: cwd)")
    ap.add_argument("--base", help="base ref, e.g. origin/main or HEAD")
    ap.add_argument("--head", help="head ref (default: working tree)")
    ap.add_argument("--commit", help="single commit sha to diff (parent..commit)")
    ap.add_argument("--diff-file", help="read a raw unified diff from this file")
    ap.add_argument("--pr", help="pull-request URL to diff (fetched over the network; "
                                 "e.g. https://github.com/owner/repo/pull/123)")
    ap.add_argument("--context", type=int, default=3, help="context lines (default 3)")
    ap.add_argument("--max-chunk-bytes", type=int, default=6000,
                    help="per-hunk content cap (default 6000)")
    ap.add_argument("--out", default=None,
                    help="output dir (default: per-run work dir under ~/.cache/diff-review; "
                         "pass --out to write into the repo instead)")
    args = ap.parse_args()

    diff_text = get_diff(args)
    if not diff_text.strip():
        sys.exit("no diff produced - check refs (empty repo? identical trees?)")

    chunks, files_out, skipped = parse(diff_text, args.max_chunk_bytes)
    # word-level diff markers (GitHub-style intra-line highlights): git modes
    # run a second `--word-diff=plain` pass; --diff-file/--pr input may itself
    # carry markers, otherwise render falls back to difflib
    word_text = diff_text if (args.diff_file or args.pr) else None
    if word_text is None:
        try:
            wargs = ["git", "-C", args.repo or ".", "diff", "--no-color", "--no-ext-diff", "-M",
                     "--word-diff=plain", f"-U{args.context}"]
            if args.commit:
                wargs = ["git", "-C", args.repo or ".", "show", "--format=", "--no-color",
                         "--no-ext-diff", "-M", "--word-diff=plain", f"-U{args.context}", args.commit]
            elif args.base:
                wargs += [args.base]
                if args.head:
                    wargs += [args.head]
            word_text = run(wargs)
        except SystemExit:
            word_text = None
    attach_word_marks(chunks, word_text or "")
    if args.out:
        out = Path(args.out)
    else:
        cache = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
        if args.pr:
            m = PR_RE.match(args.pr) or PR_DIFF_RE.match(args.pr)
            slug = f"{m.group(2)}-{m.group(3)}" if m else "pr"
        else:
            slug = os.path.basename(os.path.abspath(args.repo)) if args.repo else "diff"
        out = cache / "diff-review" / f"{slug}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    out.mkdir(parents=True, exist_ok=True)

    langs = {}
    for c in chunks:
        langs[c["language"]] = langs.get(c["language"], 0) + 1

    summary = {
        "source": {
            "repo": os.path.abspath(args.repo) if args.repo else ".",
            "mode": ("pr " + args.pr) if args.pr
                    else ("commit " + args.commit) if args.commit
                    else ("base " + (args.base or "HEAD") + (".." + args.head if args.head else "..worktree")),
            "diff_file": args.diff_file,
        },
        "totals": {
            "files": len(files_out),
            "chunks": len(chunks),
            "added": sum(c["added"] for c in chunks),
            "removed": sum(c["removed"] for c in chunks),
        },
        "files": files_out,
        "languages": langs,
        "skipped_binaries": skipped,
    }
    (out / "chunks.json").write_text(json.dumps(chunks, indent=1, ensure_ascii=False))
    (out / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False))

    print(f"chunks.json  : {out / 'chunks.json'}")
    print(f"summary.json : {out / 'summary.json'}")
    print(json.dumps(summary["totals"], indent=1))
    if skipped:
        print(f"NOTE: {len(skipped)} binary file(s) skipped: "
              + ", ".join(s["new"] or s["old"] for s in skipped))
    if len(chunks) > 250:
        print("WARNING: many chunks; consider clustering per-directory or splitting the diff.")


if __name__ == "__main__":
    main()
