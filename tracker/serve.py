#!/usr/bin/env python3
"""Standalone project tracker - zero dependencies, stdlib only.

Reuse in another project: copy the tracker/ folder, edit config.json
(project name, data file, orchestration dir, guard command), then:

    python3 serve.py [port]      # default 8611, binds 127.0.0.1

JSON is canonical (data/*.json); TRACKER.md is regenerated on every
save as the human-readable markdown table. Orchestration file saves
run the configured guard and restore the previous content on failure.
"""
import json
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent


class Proj:
    """One tracker instance (a <repo>/tracker dir with a config.json).
    The module-level LOCAL instance backs the CLI channel (--inbox etc.
    always act on the repo this serve.py lives in); the HTTP server can
    repoint CUR at any discovered project."""

    def __init__(self, root):
        self.root = Path(root).resolve()
        self.cfg = json.loads((self.root / "config.json").read_text())
        self.data = (self.root / self.cfg["data"]).resolve()
        self.orch = (self.root / self.cfg["orchestration_dir"]).resolve()
        # Cold storage: a feature validated by the owner is CLEANED out of
        # the live file - full Q&A/history/notes move here; the live archive
        # keeps only name + decisions + a half-sentence lesson.
        self.cold = (self.root / self.cfg.get(
            "cold", self.cfg["data"].replace(".json", "-cold.json"))).resolve()
        # Session audit trail: which implementer sessions worked each step.
        # NOT part of the live doc and never printed by --inbox.
        self.sess = (self.root / self.cfg.get(
            "sessions", self.cfg["data"].replace(".json", "-sessions.json"))).resolve()


# A bare tracker copy (fresh clone of the tool repo, or a hand-copied
# tracker/ dir) bootstraps itself so serve.py and the CLI always run:
# missing config gets a minimal one, missing data an empty board.
if not (ROOT / "config.json").exists():
    (ROOT / "config.json").write_text(json.dumps(
        {"project": ROOT.parent.name, "data": "data/board.json",
         "orchestration_dir": "../orchestration", "guard": "true"}, indent=1))
_data = ROOT / json.loads((ROOT / "config.json").read_text())["data"]
if not _data.exists():
    _data.parent.mkdir(parents=True, exist_ok=True)
    _data.write_text(json.dumps(
        {"rev": 1, "project": ROOT.parent.name, "items": [],
         "inbox": [], "archive": []}, indent=1))

LOCAL = Proj(ROOT)
CFG, DATA, ORCH, COLD, SESS = LOCAL.cfg, LOCAL.data, LOCAL.orch, LOCAL.cold, LOCAL.sess
CUR = LOCAL  # project the HTTP server currently displays

# Multi-project: the server lists every tracker found under the registry
# roots; the last project opened is remembered there and served first.
STATE_HOME = Path.home() / ".local" / "state" / "kbuba-tracker"
REG = STATE_HOME / "registry.json"


def registry():
    reg = json.loads(REG.read_text()) if REG.exists() else {}
    reg.setdefault("roots", ["~/projects"])
    return reg


def save_registry(reg):
    STATE_HOME.mkdir(parents=True, exist_ok=True)
    REG.write_text(json.dumps(reg, indent=1))


def discover(reg=None):
    """Every <root>/*/tracker/config.json under the registry roots, plus
    this serve.py's own project. Same-named projects (task worktrees of
    one repo) collapse to the copy with the newest data file."""
    reg = reg or registry()
    cand = {ROOT}
    for r in reg["roots"]:
        base = Path(r).expanduser()
        if base.is_dir():
            cand.update(p.parent for p in base.glob("*/tracker/config.json"))
    best = {}
    for tdir in cand:
        try:
            cfg = json.loads((tdir / "config.json").read_text())
            mtime = (tdir / cfg["data"]).resolve().stat().st_mtime
        except (OSError, ValueError, KeyError):
            continue
        name = cfg.get("project", tdir.parent.name)
        if name not in best or mtime > best[name][0]:
            best[name] = (mtime, {"name": name, "dir": str(tdir.resolve()),
                                  "repo": str(tdir.resolve().parent)})
    return sorted((v[1] for v in best.values()), key=lambda p: p["name"])


def sessions_all(proj=None):
    sess = proj.sess if proj else SESS
    return json.loads(sess.read_text()) if sess.exists() else []


def orch_files(proj=None):
    orch = proj.orch if proj else ORCH
    if not orch.is_dir():
        return []
    return sorted(p.name for p in orch.iterdir()
                  if p.is_file() and p.suffix in (".md", ".txt"))


def validate(doc):
    """Review Gate: Done needs all four reviews (S/D/T + Owner verified) and
    no open questions. (Stage-entry gates are enforced in the UI; questions
    raised mid-flight mark the item 'awaiting owner', not a regression.)"""
    for it in doc.get("items", []):
        open_q = [q for q in it.get("questions", []) if not q.get("answer")]
        if it.get("stage") == "Done":
            r = it.get("review", {})
            if not (r.get("story") and r.get("design") and r.get("tech")
                    and r.get("owner")):
                return (f"{it['name']}: cannot be Done until Story+Design+Tech"
                        f"+Owner review all pass (Review Gate)")
            if open_q:
                return f"{it['name']}: cannot be Done with open Conductor questions"
    return None


def clean_archive(doc, cold_path=None):
    """Owner-validated features are cleaned: the full item (questions,
    history, notes, owner-check) + its inbox events go to COLD storage;
    the live archive entry keeps only name/domain/decisions/lesson.
    Unread inbox events survive so the next agent still sees them."""
    for i, a in enumerate(doc.get("archive", [])):
        if "stage" not in a and "questions" not in a:
            continue  # already cleaned
        COLD_P = cold_path if cold_path is not None else COLD
        cold = json.loads(COLD_P.read_text()) if COLD_P.exists() else []
        cold.append({"item": a,
                     "inbox": [e for e in doc.get("inbox", [])
                               if e.get("item") == a.get("id")],
                     "archivedAt": a.get("when")})
        COLD_P.parent.mkdir(parents=True, exist_ok=True)
        COLD_P.write_text(json.dumps(cold, indent=1))
        doc["archive"][i] = {
            "id": a.get("id"), "name": a.get("name"), "domain": a.get("domain"),
            "when": a.get("when"), "lesson": a.get("lesson", ""),
            "decisions": a.get("decisions", []),
            # structural skeleton stays live so the Gantt and dependency
            # graph keep the whole project shape (X was done, preceded Y)
            "deps": a.get("deps", []), "parent": a.get("parent"),
            "days": a.get("days"), "startDay": a.get("startDay")}
        doc["inbox"] = [e for e in doc.get("inbox", [])
                        if e.get("item") != a.get("id") or not e.get("read")]


def prune_inbox(doc):
    """Keep every unread event; cap read history at 100 so the file and any
    agent context stay small."""
    inbox = doc.get("inbox", [])
    read = [e for e in inbox if e.get("read")]
    if len(read) > 100:
        drop = set(id(e) for e in read[:len(read) - 100])
        doc["inbox"] = [e for e in inbox if id(e) not in drop]


def to_markdown(doc, data_name=None):
    def cell(s):
        return str(s).replace("|", "\\|").replace("\n", " ")
    lines = [
        f"# {doc.get('project', 'Project')} - tracker",
        "",
        "Generated by tracker/serve.py on every save. Do not edit by hand;",
        "the canonical data is " + (data_name or CFG["data"]) + ".",
        "",
        "| Step / Feature | Domain | Stage | Pending Conductor Questions "
        "| Decision Log | Review S/D/T/O |",
        "|---|---|---|---|---|---|",
    ]
    for it in doc.get("items", []):
        qs = "; ".join(q["text"] for q in it.get("questions", [])
                       if not q.get("answer")) or "-"
        ds = "; ".join(it.get("decisions", [])) or "-"
        r = it.get("review", {})
        rv = "/".join("x" if r.get(k) else "."
                      for k in ("story", "design", "tech", "owner"))
        lines.append(f"| {cell(it['name'])} | {it['domain']} | {it['stage']} "
                     f"| {cell(qs)} | {cell(ds)} | {rv} |")
    arch = doc.get("archive", [])
    if arch:
        lines += ["", "## Archived (decisions + one lesson; everything else is cold)", ""]
        for a in arch:
            ds = "; ".join(a.get("decisions", []))
            lines.append(f"- **{cell(a['name'])}** ({a.get('when', '')}) - "
                         f"{cell(a.get('lesson', ''))}"
                         + (f" | decisions: {cell(ds)}" if ds else ""))
    return "\n".join(lines) + "\n"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path in ("/", "/index.html"):
            body = (ROOT / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif url.path == "/api/config":
            self._json({"project": CUR.cfg["project"],
                        "orch_files": orch_files(CUR),
                        "projects": discover(), "current": str(CUR.root)})
        elif url.path == "/api/tracker":
            self._json(json.loads(CUR.data.read_text()))
        elif url.path == "/api/sessions":
            self._json(sessions_all(CUR))
        elif url.path == "/api/tokens":
            # Estimated token weight (chars/4) of every file on an agent's
            # context path: repo CLAUDE.md + each orchestration file.
            files = {}
            claude = CUR.orch.parent / "CLAUDE.md"
            if claude.exists():
                files["CLAUDE.md"] = len(claude.read_text(errors="replace")) // 4
            for name in orch_files(CUR):
                files[name] = len((CUR.orch / name).read_text(errors="replace")) // 4
            self._json({"files": files, "note": "chars/4 estimate"})
        elif url.path == "/api/cold":
            # Owner-facing pull-up of an archived item's full frozen record.
            # Deliberate fetch only - never part of --inbox or agent context.
            iid = parse_qs(url.query).get("id", [""])[0]
            cold = json.loads(CUR.cold.read_text()) if CUR.cold.exists() else []
            self._json([c for c in cold if c.get("item", {}).get("id") == iid])
        elif url.path == "/api/orch":
            name = parse_qs(url.query).get("name", [""])[0]
            if name not in orch_files(CUR):
                return self._json({"error": "unknown file"}, 404)
            self._json({"name": name, "content": (CUR.orch / name).read_text()})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        global CUR
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length))
        except ValueError:
            return self._json({"error": "bad json"}, 400)
        if self.path == "/api/tracker":
            cur = json.loads(CUR.data.read_text())
            if body.get("rev") != cur.get("rev"):
                return self._json(
                    {"error": "stale revision - someone else saved; reloading"}, 409)
            err = validate(body)
            if err:
                return self._json({"error": err}, 400)
            body["rev"] = cur.get("rev", 0) + 1
            clean_archive(body, CUR.cold)
            prune_inbox(body)
            CUR.data.write_text(json.dumps(body, indent=1))
            (CUR.root / "TRACKER.md").write_text(to_markdown(body, CUR.cfg["data"]))
            self._json({"ok": True, "rev": body["rev"]})
        elif self.path == "/api/project":
            # Switch the displayed project; remember it as last-open.
            d = body.get("dir", "")
            if d not in {p["dir"] for p in discover()}:
                return self._json({"error": "unknown project"}, 404)
            try:
                new = Proj(d)
                json.loads(new.data.read_text())
            except (OSError, ValueError, KeyError) as e:
                return self._json({"error": f"cannot load project: {e}"}, 400)
            CUR = new
            reg = registry()
            reg["last"] = str(CUR.root)
            save_registry(reg)
            self._json({"ok": True, "project": CUR.cfg["project"]})
        elif self.path == "/api/shutdown":
            # Server binds 127.0.0.1 only. Lets `kbuba uninstall` (and any
            # local caller) stop a running instance cross-platform,
            # including manually started ones.
            self._json({"ok": True})
            import threading
            threading.Thread(target=self.server.shutdown).start()
        elif self.path == "/api/orch":
            name = body.get("name", "")
            if name not in orch_files(CUR):
                return self._json({"error": "unknown file"}, 404)
            path = CUR.orch / name
            old = path.read_text()
            path.write_text(body.get("content", ""))
            try:
                res = subprocess.run(
                    CUR.cfg["guard"], shell=True, capture_output=True, text=True,
                    cwd=(CUR.root / CUR.cfg.get("guard_cwd", ".")).resolve(),
                    timeout=60)
                out = (res.stdout + res.stderr).strip()
                ok = res.returncode == 0
            except subprocess.TimeoutExpired:
                out, ok = "guard timed out", False
            if not ok:
                path.write_text(old)  # never leave a bad ledger on disk
                return self._json({"ok": False,
                                   "output": out or "guard failed - file restored"})
            self._json({"ok": True, "output": out or "guard OK"})
        else:
            self._json({"error": "not found"}, 404)


def inbox_cli():
    """Agent-facing read channel: print every unread owner interaction in
    full, then mark it read. Agents run THIS instead of loading the whole
    tracker JSON - it is the anti-context-bloat path."""
    import datetime
    doc = json.loads(DATA.read_text())
    unread = [e for e in doc.get("inbox", []) if not e.get("read")]
    if not unread:
        print("inbox: nothing unread")
        return
    today = datetime.date.today().isoformat()
    for e in unread:
        print(f"[{e.get('when', '?')}] {e.get('item', '?')} / {e.get('kind', '?')}: "
              f"{e.get('text', '')}")
        e["read"] = True
        e["readAt"] = today
    doc["rev"] = doc.get("rev", 0) + 1
    prune_inbox(doc)
    DATA.write_text(json.dumps(doc, indent=1))
    (ROOT / "TRACKER.md").write_text(to_markdown(doc))
    print(f"-- {len(unread)} event(s) marked read (rev {doc['rev']})")


def reopen_cli(item_id, qid, text):
    """Conductor moves an answered question back to unanswered with a
    follow-up; the old exchange is kept in the question's history (the UI
    shows it collapsed)."""
    import datetime
    doc = json.loads(DATA.read_text())
    it = next(i for i in doc["items"] if i["id"] == item_id)
    q = next(x for x in it.get("questions", []) if x["id"] == qid)
    if q.get("answer"):
        q.setdefault("history", []).append(
            {"text": q["text"], "answer": q["answer"],
             "answeredAt": q.get("answeredAt")})
    q["text"] = text
    q["answer"] = None
    q["answeredAt"] = None
    q["asked"] = datetime.date.today().isoformat()
    doc["rev"] = doc.get("rev", 0) + 1
    DATA.write_text(json.dumps(doc, indent=1))
    (ROOT / "TRACKER.md").write_text(to_markdown(doc))
    print(f"reopened {item_id}/{qid} with follow-up (history: "
          f"{len(q.get('history', []))} exchange(s), rev {doc['rev']})")


def selftest():
    doc = {"project": "t", "rev": 1, "items": [{
        "id": "a", "name": "A", "domain": "Technical", "stage": "Done",
        "deps": [], "questions": [], "decisions": ["d"],
        "review": {"story": True, "design": True, "tech": True, "owner": True}}]}
    assert validate(doc) is None
    doc["items"][0]["review"]["owner"] = False
    assert "Review Gate" in validate(doc)
    doc["items"][0]["review"]["owner"] = True
    doc["items"][0]["questions"] = [{"text": "q", "answer": None}]
    assert "open Conductor questions" in validate(doc)
    doc["archive"] = [{"id": "z", "name": "Z", "domain": "Technical",
                       "lesson": "one line", "when": "2026-08-09"}]
    md = to_markdown(doc)
    assert "| A | Technical | Done | q | d | x/x/x/x |" in md
    assert "**Z** (2026-08-09) - one line" in md
    doc["inbox"] = [{"read": True, "i": i} for i in range(150)] + [{"read": False}]
    prune_inbox(doc)
    assert len(doc["inbox"]) == 101
    # archive cleaning: a full item entry is reduced; its read events purged
    import tempfile
    global COLD
    old_cold = COLD
    with tempfile.TemporaryDirectory() as td:
        COLD = Path(td) / "cold.json"
        doc2 = {"rev": 1, "archive": [
            {"id": "x", "name": "X", "domain": "Technical", "when": "2026-08-09",
             "lesson": "half a sentence", "stage": "Done", "decisions": ["d1"],
             "questions": [{"id": "q", "text": "t", "answer": "a"}], "notes": "n"}],
            "inbox": [{"item": "x", "read": True}, {"item": "x", "read": False},
                      {"item": "y", "read": True}]}
        clean_archive(doc2)
        assert "questions" not in doc2["archive"][0]
        assert doc2["archive"][0]["decisions"] == ["d1"]
        cold = json.loads(COLD.read_text())
        assert cold[0]["item"]["questions"][0]["answer"] == "a"
        assert len(cold[0]["inbox"]) == 2
        kinds = [(e["item"], e["read"]) for e in doc2["inbox"]]
        assert ("x", True) not in kinds and ("x", False) in kinds and ("y", True) in kinds
    COLD = old_cold
    # discovery: same-named projects dedupe to the newest data file
    import os
    with tempfile.TemporaryDirectory() as td:
        for sub, when in (("repoA", 100), ("repoA-worktree", 50)):
            t = Path(td) / sub / "tracker"
            t.mkdir(parents=True)
            (t / "config.json").write_text(json.dumps(
                {"project": "P!", "data": "d.json",
                 "orchestration_dir": ".", "guard": "true"}))
            (t / "d.json").write_text("{}")
            os.utime(t / "d.json", (when, when))
        ps = [p for p in discover({"roots": [td]}) if p["name"] == "P!"]
        assert len(ps) == 1 and ps[0]["dir"].endswith("repoA/tracker"), ps
    print("selftest OK")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
        sys.exit(0)
    if "--inbox" in sys.argv:
        inbox_cli()
        sys.exit(0)
    if "--reopen" in sys.argv:
        i = sys.argv.index("--reopen")
        reopen_cli(sys.argv[i + 1], sys.argv[i + 2], sys.argv[i + 3])
        sys.exit(0)
    if "--log-session" in sys.argv:
        # Conductor logs one line per finished dispatch:
        #   --log-session <item-id> <session-id> <model> <final one-liner...>
        i = sys.argv.index("--log-session")
        import datetime
        s = sessions_all()
        s.append({"item": sys.argv[i + 1], "session": sys.argv[i + 2],
                  "model": sys.argv[i + 3],
                  "when": datetime.date.today().isoformat(),
                  "summary": " ".join(sys.argv[i + 4:])})
        SESS.parent.mkdir(parents=True, exist_ok=True)
        SESS.write_text(json.dumps(s, indent=1))
        print(f"logged session for {sys.argv[i + 1]} ({len(s)} total)")
        sys.exit(0)
    if "--sessions" in sys.argv:
        # Deliberate audit read - never part of --inbox or default context.
        i = sys.argv.index("--sessions")
        item = sys.argv[i + 1]
        rows = [s for s in sessions_all() if s["item"] == item]
        for s in rows:
            print(f"[{s['when']}] {s['session']} ({s['model']}): {s['summary']}")
        print(f"-- {len(rows)} session(s) for {item}")
        sys.exit(0)
    want = int(sys.argv[1]) if len(sys.argv) > 1 else None
    reg = registry()
    last = reg.get("last")
    if last and last != str(ROOT) and Path(last, "config.json").exists():
        try:
            CUR = Proj(last)
        except (OSError, ValueError, KeyError):
            CUR = LOCAL  # stale registry entry; fall back to this repo
    reg["last"] = str(CUR.root)
    save_registry(reg)

    def is_tracker(p):
        import urllib.request
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{p}/api/config", timeout=1) as r:
                return "projects" in json.loads(r.read())
        except Exception:
            return False

    srv = port = None
    for port in ([want] if want else range(8611, 8621)):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            if is_tracker(port):
                # Clean exit so a launchd/systemd KeepAlive doesn't
                # respawn-loop against an already-running instance.
                print(f"tracker: already running at http://127.0.0.1:{port}")
                sys.exit(0)
            # port owned by some other process - try the next one
    if srv is None:
        print(f"tracker: no free port ({want or '8611-8620'})")
        sys.exit(1)
    url = f"http://127.0.0.1:{port}"
    # Record the live URL so `kbuba get-url` can always recover it.
    STATE_HOME.mkdir(parents=True, exist_ok=True)
    (STATE_HOME / "url").write_text(url)
    print(f"tracker: {url}  project={CUR.cfg['project']}  "
          f"data={CUR.data.name}  orch={CUR.orch}")
    srv.serve_forever()
    # reached via /api/shutdown: drop the url record if it is still ours
    try:
        if (STATE_HOME / "url").read_text().strip() == url:
            (STATE_HOME / "url").unlink()
    except OSError:
        pass
    print("tracker: stopped")
