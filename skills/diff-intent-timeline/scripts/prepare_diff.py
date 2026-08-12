#!/usr/bin/env python3
"""prepare_diff.py - extract a git diff into LLM-ready hunk chunks.

Part of the diff-intent-timeline skill (see SKILL.md).

Input modes (choose one):
  --repo PATH --base REF [--head REF]   git diff base..worktree (or base..head)
  --repo PATH --commit SHA              diff of a single commit
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


def get_diff(args):
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
        sys.exit("need one of: --commit, --base (with optional --head), --diff-file")
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
    ap.add_argument("--context", type=int, default=3, help="context lines (default 3)")
    ap.add_argument("--max-chunk-bytes", type=int, default=6000,
                    help="per-hunk content cap (default 6000)")
    ap.add_argument("--out", default=".", help="output dir (default: cwd)")
    args = ap.parse_args()

    diff_text = get_diff(args)
    if not diff_text.strip():
        sys.exit("no diff produced - check refs (empty repo? identical trees?)")

    chunks, files_out, skipped = parse(diff_text, args.max_chunk_bytes)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    langs = {}
    for c in chunks:
        langs[c["language"]] = langs.get(c["language"], 0) + 1

    summary = {
        "source": {
            "repo": os.path.abspath(args.repo) if args.repo else ".",
            "mode": ("commit " + args.commit) if args.commit
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
