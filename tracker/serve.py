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
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent

# Path.read_text/write_text default to the LOCALE encoding — cp1252 on Windows.
# Every file this server touches is UTF-8, and getting that wrong is not a
# cosmetic bug here: reading a UTF-8 French ledger as cp1252 returns SILENTLY
# corrupted text (no exception), and /api/orch writes that corruption back when
# the guard refuses. Writing crashes outright on anything cp1252 lacks — U+2460
# ① and U+2466 ⑦, which is how this project's own audit findings are numbered.
# Both proved on 2026-08-13. Patched at the source rather than at 37 call sites,
# so a new call site cannot reintroduce it.
def _force_utf8():
    """Make UTF-8 the default for this PROCESS's text I/O and console.

    Called only when this file is run as a script (below). It mutates
    `pathlib.Path` and reconfigures the console, which is right for a
    single-purpose script and wrong for a library: importing this module used
    to change `Path.read_text` for every other package in the process, and any
    co-resident caller writing the idiomatic `p.read_text("utf-8")` positionally
    would then die on "got multiple values for argument 'encoding'". Under
    import the module now leaves the process alone; the few reads and writes
    that happen at import time name their encoding explicitly instead.
    """
    _read_text, _write_text = Path.read_text, Path.write_text

    def _utf8_read(self, *a, **k):
        if not a and "encoding" not in k:
            k["encoding"] = "utf-8"
        return _read_text(self, *a, **k)

    def _utf8_write(self, data, *a, **k):
        if not a and "encoding" not in k:
            k["encoding"] = "utf-8"
        return _write_text(self, data, *a, **k)

    Path.read_text, Path.write_text = _utf8_read, _utf8_write

    # The console is cp1252 here too, and it crashed the CLI *after* a
    # successful write - a non-zero exit on work that had landed, which invites
    # a retry that writes it twice. Reporting must never be able to fail the
    # thing it reports on: replace what the terminal cannot draw, never raise.
    for _s in (sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    _force_utf8()


class Proj:
    """One tracker instance (a <repo>/tracker dir with a config.json).
    The module-level LOCAL instance backs the CLI channel (--inbox etc.
    always act on the repo this serve.py lives in); the HTTP server can
    repoint CUR at any discovered project."""

    def __init__(self, root):
        self.root = Path(root).resolve()
        # encoding named explicitly: this runs at IMPORT time, where
        # _force_utf8() has deliberately not been applied (see its docstring).
        self.cfg = json.loads(
            (self.root / "config.json").read_text(encoding="utf-8"))
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
#
# This WRITES, at import as well as on run - so importing this module into a
# directory that is not a tracker creates files there. Kept, because Proj()
# below needs a config to exist and every real caller is the script; but every
# read and write here names its encoding, because _force_utf8() has not been
# applied on the import path.
if not (ROOT / "config.json").exists():
    (ROOT / "config.json").write_text(json.dumps(
        {"project": ROOT.parent.name, "data": "data/board.json",
         "orchestration_dir": "../orchestration",
         "guard": "exit 0"}, indent=1),  # no-op passer valid in sh AND cmd.exe
        encoding="utf-8")
_data = ROOT / json.loads(
    (ROOT / "config.json").read_text(encoding="utf-8"))["data"]
if not _data.exists():
    _data.parent.mkdir(parents=True, exist_ok=True)
    _data.write_text(json.dumps(
        {"rev": 1, "project": ROOT.parent.name, "items": [],
         "inbox": [], "archive": []}, indent=1), encoding="utf-8")

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
                    encoding="utf-8", errors="replace",
                    cwd=(CUR.root / CUR.cfg.get("guard_cwd", ".")).resolve(),
                    timeout=60)
                out = ((res.stdout or "") + (res.stderr or "")).strip()
                ok = res.returncode == 0
            # text=True without encoding decodes the guard's own output with the
            # LOCALE codec. The guard speaks French and prints U+201D and ①, so
            # cp1252 raised inside subprocess's reader thread, run() returned
            # stdout=None, and the TypeError that followed escaped do_POST -
            # meaning the restore below never ran and a ledger the guard had
            # REFUSED stayed on disk. Belt and braces: decode explicitly above,
            # and never let a reporting failure skip the restore.
            except (subprocess.TimeoutExpired, OSError, ValueError) as exc:
                out, ok = f"guard could not be run: {exc}", False
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
    doc, base = _load()
    it = _find(doc, item_id)
    q = next((x for x in it.get("questions", []) if x.get("id") == qid), None)
    if q is None:
        sys.exit(f"no question {qid} on {item_id} "
                 f"(has: {', '.join(x.get('id', '?') for x in it.get('questions', [])) or 'none'})")
    if q.get("answer"):
        q.setdefault("history", []).append(
            {"text": q["text"], "answer": q["answer"],
             "answeredAt": q.get("answeredAt")})
    q["text"] = text
    q["answer"] = None
    q["answeredAt"] = None
    q["asked"] = datetime.date.today().isoformat()
    # Ungated for the same reason as --ask: reopening records that an answer was
    # not understood, and a channel that can refuse THAT is worse than useless.
    # It goes through _commit so it gets the rev check and the atomic mirror
    # write, which it did not have when it wrote DATA directly.
    _commit(doc, f"reopened {item_id}/{qid} with follow-up (history: "
                 f"{len(q.get('history', []))} exchange(s))", base, gate=False)


# --- agent-facing WRITE channel (added 2026-08-13; not upstream kbuba) -------
# Board-first is a rule an agent must be able to OBEY. Upstream ships no command
# that creates or moves an item, so the only write paths were the browser (which
# validate() guards) and hand-editing board.json (which nothing guards) - and an
# agent in a cloud session cannot reach 127.0.0.1 at all. These three take the
# SAME validate() the HTTP save takes, and refuse what is the owner's alone.

DOMAINS = ("User Story", "Product Design", "Technical", "Cross-Functional")
STAGES = ("Discovery", "Speced", "Implementation", "Review", "Done")


def _commit(doc, said, base_rev, gate=True):
    """Compare-and-swap on rev, run the Review Gate, write, mirror.

    `gate=False` is for --ask only: a question is information, and a channel
    that can REFUSE to record "I don't know" leaves the agent with guess or
    abort - the two outcomes the channel exists to prevent.
    """
    if gate:
        err = validate(doc)
        if err:
            sys.exit(f"refused: {err}")
    # The browser's save is protected by a rev check (HTTP 409). Without the
    # same check here, a CLI write silently destroyed an owner edit made while
    # the command was running AND landed on the same rev the browser held, so
    # the browser's next save was not detected as stale either.
    on_disk = json.loads(DATA.read_text()).get("rev") if DATA.exists() else None
    if on_disk != base_rev:
        sys.exit(f"refused: the board moved while this command ran "
                 f"(rev {base_rev} -> {on_disk}). Re-read it and try again.")
    doc["rev"] = base_rev + 1
    # Render BEFORE either write: to_markdown on hostile input used to raise
    # after board.json was already committed and after TRACKER.md had been
    # truncated by open(...,'w'), leaving a 0-byte mirror beside a moved board.
    md = to_markdown(doc)
    blob = json.dumps(doc, indent=1)
    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(blob)
    tmp = ROOT / "TRACKER.md.tmp"
    tmp.write_text(md)
    tmp.replace(ROOT / "TRACKER.md")
    print(f"{said} (rev {doc['rev']})")


def _load():
    doc = json.loads(DATA.read_text())
    return doc, doc.get("rev", 0)


def _find(doc, item_id):
    it = next((i for i in doc.get("items", []) if i.get("id") == item_id), None)
    if it is None:
        sys.exit(f"no item {item_id}")
    return it


def _next_id(doc):
    used = {i.get("id") for i in doc.get("items", [])} | {
        a.get("id") for a in doc.get("archive", [])}
    n = 1
    while f"T-{n:03d}" in used:
        n += 1
    return f"T-{n:03d}"


def add_item_cli(name, domain, stage="Discovery"):
    if not name or not name.strip():
        sys.exit("a board item needs a name")
    if domain not in DOMAINS:
        sys.exit("domain must be one of: " + ", ".join(DOMAINS))
    if stage not in STAGES:
        sys.exit("stage must be one of: " + ", ".join(STAGES))
    if stage not in ("Discovery", "Speced"):
        sys.exit(f"refused: an item is not CREATED at {stage}. Planning before "
                 "execution means it starts at Discovery or Speced and MOVES; "
                 "creating it further along is back-filling, and the board is "
                 "never back-filled.")
    doc, base = _load()
    iid = _next_id(doc)
    doc.setdefault("items", []).append(
        {"id": iid, "name": name, "domain": domain, "stage": stage,
         "deps": [], "questions": [], "decisions": [],
         "review": {"story": False, "design": False, "tech": False,
                    "owner": False}})
    _commit(doc, f"added {iid} '{name}' [{domain}] at {stage}", base)


def set_stage_cli(item_id, stage):
    if stage not in STAGES:
        sys.exit("stage must be one of: " + ", ".join(STAGES))
    doc, base = _load()
    it = _find(doc, item_id)          # look up FIRST: a refusal that depends on
    #                                   statement order is a refusal a harmless
    #                                   refactor can delete without a test noticing
    if stage == "Done":
        sys.exit("refused: Done is the owner's. He gives it in the board after "
                 "he has LOOKED. Leave the item at Review and hand him the URL.")
    was = it.get("stage")
    it["stage"] = stage
    _commit(doc, f"{item_id} {was} -> {stage}", base)


def ask_cli(item_id, text):
    """A question PAUSES the item - that is the whole mechanism. An agent that
    would otherwise guess writes here and stops.

    Ungated on purpose (_commit gate=False): validate() is whole-document, so an
    unrelated item left invalid by --reopen used to refuse this command with a
    message naming a DIFFERENT item. Refusing to record "I don't know" is the
    one failure this channel must never have.
    """
    import datetime
    if not text or not text.strip():
        sys.exit("a question needs text")
    doc, base = _load()
    it = _find(doc, item_id)
    qs = it.setdefault("questions", [])
    qid = f"q{len(qs) + 1}"
    qs.append({"id": qid, "text": text, "answer": None, "answeredAt": None,
               "asked": datetime.date.today().isoformat()})
    note = ""
    if it.get("stage") == "Done":
        note = " - NOTE: it was Done, so this reopens it in effect; say so"
    _commit(doc, f"asked {item_id}/{qid} - the item now waits on the owner{note}",
            base, gate=False)


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
        # compare path components, not a slash-styled suffix: discover()
        # returns native separators (backslashes on Windows)
        assert len(ps) == 1 and Path(ps[0]["dir"]).parts[-2:] == ("repoA", "tracker"), ps
    # The CLI write channel, exercised against a REAL board.
    #
    # The first version of this probed the refusal with an item id that could
    # never exist ("anything"). An adversarial pass on 2026-08-13 showed that a
    # mutant reading `if stage == "Done" and item_id == "anything"` PASSED this
    # test while the gate stood wide open on a genuine item, which reached
    # Done | x/x/x/x. A refusal is only tested in the state it exists to
    # protect: a real item at Review with all four reviews already ticked.
    global DATA, ROOT
    import shutil
    import tempfile
    _dataP, _rootP = DATA, ROOT
    _tmp = Path(tempfile.mkdtemp(prefix="kbuba-cli-"))
    ROOT, DATA = _tmp, _tmp / "board.json"
    try:
        DATA.write_text(json.dumps({
            "rev": 7, "project": "t", "inbox": [], "archive": [],
            "items": [{"id": "T-001", "name": "Ready for his eye",
                       "domain": "Technical", "stage": "Review", "deps": [],
                       "questions": [], "decisions": [],
                       "review": {"story": True, "design": True,
                                  "tech": True, "owner": True}}]}))
        for call, must_say in (
                (lambda: set_stage_cli("T-001", "Done"), "Done is the owner's"),
                (lambda: add_item_cli("x", "Technical", "Done"), "back-filling"),
                (lambda: add_item_cli("x", "Technical", "Review"), "back-filling"),
                (lambda: add_item_cli("x", "Nonsense"), "domain must be"),
                (lambda: add_item_cli("   ", "Technical"), "needs a name"),
                (lambda: set_stage_cli("T-404", "Review"), "no item T-404")):
            try:
                call()
            except SystemExit as e:
                assert must_say in str(e), (must_say, str(e))
            else:
                raise AssertionError(f"expected a refusal mentioning {must_say!r}")

        # The happy paths, so "same gate, bumps rev, writes the mirror" is
        # DEMONSTRATED rather than asserted - both refusals above return before
        # anything is written, so they prove nothing about the write.
        set_stage_cli("T-001", "Implementation")
        assert json.loads(DATA.read_text())["rev"] == 8
        ask_cli("T-001", "does this reach the owner?")
        _doc = json.loads(DATA.read_text())
        assert _doc["rev"] == 9 and _doc["items"][0]["questions"][0]["answer"] is None
        assert "does this reach the owner?" in (ROOT / "TRACKER.md").read_text()

        # Stale-rev refusal: the browser's 409, on this path.
        DATA.write_text(json.dumps({**_doc, "rev": 99}))
        try:
            _commit(_doc, "must not land", 9)
        except SystemExit as e:
            assert "moved while this command ran" in str(e), str(e)
        else:
            raise AssertionError("a stale rev must refuse")
        assert json.loads(DATA.read_text())["rev"] == 99, "refused write still landed"
    finally:
        DATA, ROOT = _dataP, _rootP
        shutil.rmtree(_tmp, ignore_errors=True)
    assert _next_id({"items": [{"id": "T-001"}], "archive": [{"id": "T-002"}]}) == "T-003"

    # UTF-8 round-trip. Seen to FAIL before it was trusted: under the locale
    # default this write raised UnicodeEncodeError on ① and this read returned
    # 'déj�' for 'déjà'. Both characters are this project's own vocabulary.
    import tempfile
    _p = Path(tempfile.gettempdir()) / "kbuba-utf8-probe.md"
    _fr = "# Registre\n\nTrouvaille ① — le trop-versé, déjà vérifié.\n"
    _p.write_text(_fr)
    assert _p.read_text() == _fr, "UTF-8 round-trip broken"
    # Bytes are compared for ENCODING only: Windows text mode also turns \n into
    # \r\n, so a byte-for-byte compare against _fr fails on line endings and
    # says nothing about the codec. Decode-then-check is the honest test.
    _raw = _p.read_bytes().decode("utf-8")          # raises if not UTF-8
    assert "①" in _raw and "déjà" in _raw, "non-ASCII lost on the way out"
    assert b"\xc3\xa9" in _p.read_bytes(), "é is not UTF-8 on disk"
    _p.unlink()

    print("selftest OK")


USAGE = """tracker/serve.py - board server and agent channel

  serve.py [port]                       serve the board (default 8611)
  serve.py --inbox                      unread owner events, stamps receipts
  serve.py --add-item "<name>" "<domain>" ["<stage>"]
  serve.py --set-stage <item-id> "<stage>"      (Done is the owner's)
  serve.py --ask <item-id> <question...>        (pauses the item)
  serve.py --reopen <item-id> <qid> "<follow-up>"
  serve.py --log-session <item-id> <session-id> <model> <one-liner...>
  serve.py --sessions <item-id>
  serve.py --selftest
"""


def _arg(args, n, what):
    if len(args) <= n:
        sys.exit(f"{USAGE}\nmissing argument: {what}")
    return args[n]


if __name__ == "__main__":
    # Dispatch on argv[1] ALONE. `"--inbox" in sys.argv` scanned the whole
    # command line, so a question whose TEXT mentioned another flag ran that
    # flag instead: `--ask T-1 does this cover --inbox events` marked the
    # owner's unread messages read, never recorded the question, and exited 0 -
    # telling the agent it had succeeded at work it had not done. Free text
    # belongs to exactly one command and must never be able to name another.
    cmd = sys.argv[1] if len(sys.argv) > 1 else None
    rest = sys.argv[2:]
    if cmd in ("-h", "--help"):
        print(USAGE)
        sys.exit(0)
    if cmd == "--selftest":
        selftest()
        sys.exit(0)
    if cmd == "--inbox":
        inbox_cli()
        sys.exit(0)
    if cmd == "--reopen":
        reopen_cli(_arg(rest, 0, "<item-id>"), _arg(rest, 1, "<qid>"),
                   _arg(rest, 2, "<follow-up>"))
        sys.exit(0)
    if cmd == "--add-item":
        add_item_cli(_arg(rest, 0, '"<name>"'), _arg(rest, 1, '"<domain>"'),
                     *rest[2:3])
        sys.exit(0)
    if cmd == "--set-stage":
        set_stage_cli(_arg(rest, 0, "<item-id>"), _arg(rest, 1, '"<stage>"'))
        sys.exit(0)
    if cmd == "--ask":
        ask_cli(_arg(rest, 0, "<item-id>"), " ".join(rest[1:]))
        sys.exit(0)
    if cmd == "--log-session":
        # Conductor logs one line per finished dispatch:
        #   --log-session <item-id> <session-id> <model> <final one-liner...>
        import datetime
        s = sessions_all()
        s.append({"item": _arg(rest, 0, "<item-id>"),
                  "session": _arg(rest, 1, "<session-id>"),
                  "model": _arg(rest, 2, "<model>"),
                  "when": datetime.date.today().isoformat(),
                  "summary": " ".join(rest[3:])})
        SESS.parent.mkdir(parents=True, exist_ok=True)
        SESS.write_text(json.dumps(s, indent=1))
        print(f"logged session for {rest[0]} ({len(s)} total)")
        sys.exit(0)
    if cmd == "--sessions":
        # Deliberate audit read - never part of --inbox or default context.
        item = _arg(rest, 0, "<item-id>")
        rows = [s for s in sessions_all() if s["item"] == item]
        for s in rows:
            print(f"[{s['when']}] {s['session']} ({s['model']}): {s['summary']}")
        print(f"-- {len(rows)} session(s) for {item}")
        sys.exit(0)
    if cmd is not None and not cmd.isdigit():
        sys.exit(f"{USAGE}\nunknown command: {cmd}")
    want = int(cmd) if cmd else None
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
    # Record the live URL for `kbuba get-url`. Line 2 is our pid so a
    # dying older instance can never delete a newer instance's record
    # (the restart race: old cleanup runs after new startup wrote it).
    STATE_HOME.mkdir(parents=True, exist_ok=True)
    (STATE_HOME / "url").write_text(f"{url}\n{os.getpid()}\n")
    print(f"tracker: {url}  project={CUR.cfg['project']}  "
          f"data={CUR.data.name}  orch={CUR.orch}")
    srv.serve_forever()
    # reached via /api/shutdown: drop the url record only if it is OURS
    # (url AND pid match - a successor may already have overwritten it)
    try:
        if (STATE_HOME / "url").read_text().split()[:2] == [url, str(os.getpid())]:
            (STATE_HOME / "url").unlink()
    except (OSError, IndexError):
        pass
    print("tracker: stopped")
