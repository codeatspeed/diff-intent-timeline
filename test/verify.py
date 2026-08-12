#!/usr/bin/env python3
"""Self-test for the diff-intent-timeline skill.

Generates a throwaway git repo containing ONE multi-concept commit (schema,
db layer, domain, API, tests, docs), then runs the full pipeline against it:
prepare (--commit and --diff-file modes), render, and the orphan safety net.
Asserts HTML invariants (self-contained, sequential concept ids, pygments
embedding, escaping, JS syntax when node is present).

Exit 0 = all green.  Run:  python3 test/verify.py
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "diff-intent-timeline"
TMP = Path(tempfile.mkdtemp(prefix="hermes-verify-dit-"))
fails = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        fails.append(name)


def run(cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


BASE = {
    "package.json": '{"name":"svc","version":"0.1.0","main":"src/server.js"}\n',
    "src/server.js": ('const express = require("express");\n'
                      "const app = express();\n"
                      'app.get("/health", (q, r) => r.json({ status: "ok" }));\n'
                      "module.exports = app;\n"),
    "README.md": "# svc\n",
}
FEAT = {
    "db/schema.sql": "CREATE TABLE orders (id BIGSERIAL PRIMARY KEY, total_cents INT NOT NULL);\n",
    "src/db.js": ('const { Pool } = require("pg");\n'
                  "const pool = new Pool({ connectionString: process.env.DATABASE_URL });\n"
                  "module.exports = { query: (t, p) => pool.query(t, p), pool };\n"),
    "src/orders.js": ('const { query } = require("./db");\n'
                      "async function createOrder(cents) {\n"
                      '  const r = await query("INSERT INTO orders (total_cents) VALUES ($1) RETURNING id", [cents]);\n'
                      "  return r.rows[0];\n"
                      "}\n"
                      "module.exports = { createOrder };\n"),
    "src/server.js": ('const express = require("express");\n'
                      'const { createOrder } = require("./orders");\n'
                      "const app = express();\n"
                      "app.use(express.json());\n"
                      "app.post(\"/orders\", async (q, r) => {\n"
                      "  const o = await createOrder(q.body.totalCents);\n"
                      "  r.status(201).json(o);\n"
                      "});\n"
                      'app.get("/health", (q, r) => r.json({ status: "ok" }));\n'
                      "module.exports = app;\n"),
    "test/orders.test.js": ('const t = require("node:test");\n'
                            "const a = require(\"node:assert\");\n"
                            't("createOrder", async () => { a.equal(1, 1); });\n'),
    "README.md": "# svc\n\n## POST /orders\n",
}

repo = TMP / "repo"
repo.mkdir()
run(["git", "init", "-q", "-b", "main"], cwd=repo)
for p, c in BASE.items():
    f = repo / p
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(c)
run(["git", "add", "-A"], cwd=repo)
run(["git", "commit", "-qm", "baseline"], cwd=repo)
for p, c in FEAT.items():
    f = repo / p
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(c)
run(["git", "add", "-A"], cwd=repo)
run(["git", "commit", "-qm", "feat: order creation"], cwd=repo)
head = run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()

# --- prepare: --commit mode ---
out = TMP / "c"
r = run([sys.executable, str(SKILL / "scripts/prepare_diff.py"), "--repo", str(repo),
         "--commit", head, "--out", str(out)])
check("prepare --commit exits 0", r.returncode == 0, r.stderr.strip()[:200])
chunks = json.loads((out / "chunks.json").read_text())
ids = [c["id"] for c in chunks]
check("6 chunks, ids c0001..c0006",
      len(chunks) == 6 and ids == [f"c{i:04d}" for i in range(1, 7)], str(ids))
check("chunks have content", all(c["content"].strip() for c in chunks))
check("statuses valid", all(c["status"] in ("added", "modified", "deleted", "renamed") for c in chunks))
check("line ranges sane", all(c["old_start"] >= 0 and c["new_start"] >= 1 for c in chunks))
summ = json.loads((out / "summary.json").read_text())
check("summary self-consistent", summ["totals"] == {
    "files": 6, "chunks": 6,
    "added": sum(c["added"] for c in chunks),
    "removed": sum(c["removed"] for c in chunks),
}, str(summ["totals"]))

# --- prepare: --diff-file mode (no git) ---
diff = run(["git", "-C", str(repo), "show", "--format=", "--no-color", "-M", "-U3", head]).stdout
(TMP / "d.diff").write_text(diff)
r = run([sys.executable, str(SKILL / "scripts/prepare_diff.py"), "--diff-file",
         str(TMP / "d.diff"), "--out", str(TMP / "df")])
check("prepare --diff-file exits 0", r.returncode == 0, r.stderr.strip()[:200])
check("diff-file mode == commit mode",
      [c["id"] for c in json.loads((TMP / "df/chunks.json").read_text())] == ids)

# --- render: full concepts (mapped by FILE PATH, not diff order) ---
by_file = {c["file"].lstrip("ab/"): c["id"] for c in chunks}
concepts = {
    "overview": "Adds order creation end to end: schema, db, domain, api, test, docs.",
    "concepts": [
        {"id": 1, "name": "Schema", "intent": "Persist orders.", "depends_on": [],
         "chunks": [by_file["db/schema.sql"]]},
        {"id": 2, "name": "DB layer", "intent": "Own the pool.", "depends_on": [1],
         "chunks": [by_file["src/db.js"]]},
        {"id": 3, "name": "Domain", "intent": "Insert an order.", "depends_on": [2],
         "chunks": [by_file["src/orders.js"]]},
        {"id": 4, "name": "API", "intent": "POST /orders.", "depends_on": [3],
         "chunks": [by_file["src/server.js"]]},
        {"id": 5, "name": "Tests", "intent": "Prove it works.", "depends_on": [3],
         "chunks": [by_file["test/orders.test.js"]]},
        {"id": 6, "name": "Docs", "intent": "Document the endpoint.", "depends_on": [4],
         "chunks": [by_file["README.md"]]},
    ],
}
(TMP / "concepts.json").write_text(json.dumps(concepts))
r = run([sys.executable, str(SKILL / "scripts/render.py"), "--chunks", str(out / "chunks.json"),
         "--concepts", str(TMP / "concepts.json"), "--title", "self-test", "--out", str(TMP / "t.html")])
check("render exits 0", r.returncode == 0, r.stderr.strip()[:200])
src = (TMP / "t.html").read_text()
check("html self-contained", not re.findall(r'(?:src|href)="http[^"]*"', src))
check("6 concept cards, ids 1..6 sequential",
      [int(x) for x in re.findall(r'id="concept-(\d+)"', src)] == list(range(1, 7)))
check("no unescaped brackets in code", not re.findall(r'<span class="code">[^<]*<[^/a-z!]', src))

try:
    import pygments  # noqa: F401
    check("pygments token spans", len(re.findall(r'class="(?:kd|nx|s1|c1|mi|o|w)"', src)) > 20)
    check("pygments css embedded", bool(re.findall(r'\.diff \.\w+\{color:', src)))
    check("dark theme overrides", ":root[data-theme=dark] .diff .kd" in src)
except ImportError:
    print("SKIP pygments checks (not installed)")

if shutil.which("node"):
    m = re.search(r"<script>(.*?)</script>", src, re.S)
    if m is None:
        check("inline JS present", False, "no <script> block found")
    else:
        (TMP / "j.js").write_text(m.group(1))
        r = run(["node", "--check", str(TMP / "j.js")])
        check("inline JS parses", r.returncode == 0, r.stderr.strip()[:200])
else:
    print("SKIP JS syntax check (node not installed)")

# --- orphan safety net: drop the Docs concept (README chunk) ---
# remaining max id = 5 -> auto concept must get id 6, no duplicates
c2 = json.loads((TMP / "concepts.json").read_text())
c2["concepts"] = [c for c in c2["concepts"] if by_file["README.md"] not in c.get("chunks", [])]
(TMP / "c2.json").write_text(json.dumps(c2))
r = run([sys.executable, str(SKILL / "scripts/render.py"), "--chunks", str(out / "chunks.json"),
         "--concepts", str(TMP / "c2.json"), "--out", str(TMP / "t2.html")])
s2 = (TMP / "t2.html").read_text()
check("orphan -> auto concept id=max+1 (6)",
      len(re.findall(r'class="concept"', s2)) == 6 and "Unassigned chunks" in s2
      and 'id="concept-6"' in s2 and 'id="concept-7"' not in s2)
check("no duplicate concept ids", s2.count('id="concept-6"') == 1)
check("orphan hunk still rendered", "README.md" in s2)

shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{len(fails)} failures / 24 checks")
sys.exit(1 if fails else 0)
