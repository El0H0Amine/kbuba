#!/usr/bin/env python3
"""kbuba - scaffold an AI Conductor/Implementer orchestration system +
tracker board into the current directory. Cross-platform, stdlib only.

    kbuba setup-folder ["Project Name"] [--no-ponytail]
                                          scaffold into the CURRENT dir and put
                                          it on the global tracker board
    kbuba register                        put an EXISTING project on the board
                                          (run inside its folder)
    kbuba get-url                         print the live tracker URL (bookmark it)
    kbuba autostart                       launch the tracker at login (mac/linux/win)
    kbuba update                          git pull this clone + restart the tracker
    kbuba uninstall [--with-ponytail]     stop tracker, remove autostart/shim/state
                                          (never deletes projects or this clone)
    kbuba ui                              open the tracker board
    kbuba help

The tracker is GLOBAL: one always-on server carries every project, and
launch-at-login is decided once at INSTALL time (install.sh asks; or run
`kbuba autostart` anytime). setup-folder installs the ponytail plugin
(minimal-code discipline, github.com/dietrichgebert/ponytail; skip with
--no-ponytail), registers the new project with the tracker wherever it
was created, and switches the live board to it. If the default port is
taken the server moves to the next free one - `kbuba get-url` finds it.

setup-folder creates: CLAUDE.md/AGENTS.md agent entry points,
orchestration/ (Conductor+Implementer protocol, seed ledgers), tracker/
(board UI + agent inbox), tools/ledger-guard/, a guard pre-commit hook,
and .gitignore - wired together and guard-clean. The project name
defaults to the folder name. Templates live in <repo>/templates/; edit
them there to change what every new project gets.
"""
import json
import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
TPL = HERE / "templates"


def run(*args, **kw):
    return subprocess.run(args, **kw)


def fill(src, dest, name):
    dest.write_text(src.read_text().replace("{{PROJECT}}", name))


def setup_folder(name):
    cwd = Path.cwd()
    for d in ("orchestration", "tracker"):
        if (cwd / d).exists():
            sys.exit(f"refusing: ./{d} already exists")

    # entry points + orchestration protocol/ledgers
    (cwd / "orchestration").mkdir()
    for f in ("CLAUDE.md", "AGENTS.md"):
        fill(TPL / f, cwd / f, name)
    for f in sorted((TPL / "orchestration").glob("*.md")):
        fill(f, cwd / "orchestration" / f.name, name)

    # ledger guard + tracker
    shutil.copytree(HERE / "tools" / "ledger-guard", cwd / "tools" / "ledger-guard",
                    ignore=shutil.ignore_patterns("__pycache__"))
    (cwd / "tracker" / "data").mkdir(parents=True)
    for f in ("serve.py", "index.html", "README.md", "install-autostart.sh"):
        shutil.copy(HERE / "tracker" / f, cwd / "tracker" / f)
    (cwd / "tracker" / "config.json").write_text(json.dumps(
        {"project": name, "data": "data/board.json",
         "orchestration_dir": "../orchestration",
         "guard": sys.executable + " tools/ledger-guard/check.py",
         "guard_cwd": ".."}, indent=1))
    (cwd / "tracker" / "data" / "board.json").write_text(json.dumps(
        {"rev": 1, "project": name, "items": [], "inbox": [], "archive": []},
        indent=1))

    # git + guard hook + gitignore
    if not (cwd / ".git").exists():
        run("git", "init", "-q")
    (cwd / ".githooks").mkdir(exist_ok=True)
    hook = cwd / ".githooks" / "pre-commit"
    shutil.copy(TPL / "githooks-pre-commit", hook)
    hook.chmod(0o755)
    run("git", "config", "core.hooksPath", ".githooks")
    if run("git", "config", "user.email", capture_output=True).returncode != 0:
        print("note: no git identity configured - set user.name/user.email "
              "before the first commit")
    gi = cwd / ".gitignore"
    tpl_gi = (TPL / "gitignore").read_text()
    gi.write_text(gi.read_text() + tpl_gi if gi.exists() else tpl_gi)

    ok = run(sys.executable, str(cwd / "tools" / "ledger-guard" / "check.py"))
    if ok.returncode != 0:
        sys.exit("scaffold created but the ledger guard failed - inspect before committing")
    print(f"scaffolded '{name}' in {cwd}")
    print("next: fill the project paragraph in CLAUDE.md, then:")
    print("  git add -A && git commit -m 'scaffold: kbuba setup-folder'")


def install_ponytail():
    """Install the ponytail plugin (minimal-code discipline, MIT,
    github.com/dietrichgebert/ponytail) and default it to ultra. An
    existing mode config is never overwritten - the user's choice wins."""
    cfg_dir = (Path(os.environ.get("APPDATA", Path.home())) / "ponytail"
               if os.name == "nt" else Path.home() / ".config" / "ponytail")
    cfg = cfg_dir / "config.json"
    if shutil.which("claude"):
        for args in (("claude", "plugin", "marketplace", "add", "DietrichGebert/ponytail"),
                     ("claude", "plugin", "install", "ponytail@ponytail")):
            r = run(*args, capture_output=True, text=True)
            out = (r.stdout + r.stderr).strip()
            if r.returncode != 0 and "already" not in out.lower():
                print(f"ponytail: '{' '.join(args[1:])}' failed - {out[-200:]}")
                print("ponytail: NOT installed; install manually (see README)")
                return
        if not cfg.exists():
            cfg_dir.mkdir(parents=True, exist_ok=True)
            cfg.write_text('{\n "defaultMode": "ultra"\n}\n')
            print("ponytail: INSTALLED, default mode ULTRA (first-time setup)")
        else:
            print("ponytail: INSTALLED (kept your existing mode config)")
        print("  change anytime: /ponytail lite|full|ultra|off  "
              f"(default lives in {cfg})")
    else:
        print("ponytail: claude CLI not found - install it in your agent:")
        print("  /plugin marketplace add DietrichGebert/ponytail")
        print("  /plugin install ponytail@ponytail")
        print(f"  then set ultra as default in {cfg}")


PY = "python" if os.name == "nt" else "python3"


def tracker_url():
    """(url, alive) - the last URL the server recorded, probed live.
    The record's first line is the URL (line 2 is the server's pid)."""
    import urllib.request
    f = Path.home() / ".local" / "state" / "kbuba-tracker" / "url"
    try:
        url = f.read_text().split()[0]
    except (OSError, IndexError):
        url = "http://127.0.0.1:8611"
    try:
        urllib.request.urlopen(url + "/api/config", timeout=1)
        return url, True
    except Exception:
        return url, False


def get_url():
    url, alive = tracker_url()
    if alive:
        print(f"tracker UI: {url}")
        print("bookmark this URL - if the usual port is ever taken, the "
              "server moves to the next free one and this command finds it")
    else:
        print(f"tracker is NOT running (last known: {url})")
        print(f"start it:  {PY} \"{HERE / 'tracker' / 'serve.py'}\"")
        print("or install launch-at-login:  kbuba autostart")
    return alive


def autostart_install():
    """Launch the tracker at login, per OS. Points at THIS clone's
    serve.py - one server carries every project via the switcher."""
    serve = HERE / "tracker" / "serve.py"
    if sys.platform == "darwin":
        r = run("bash", str(HERE / "tracker" / "install-autostart.sh"))
        ok = r.returncode == 0
    elif os.name == "nt":
        pyw = Path(sys.executable).with_name("pythonw.exe")
        exe = pyw if pyw.exists() else Path(sys.executable)
        r = run("schtasks", "/Create", "/SC", "ONLOGON", "/TN", "kbuba-tracker",
                "/TR", f'"{exe}" "{serve}"', "/F")
        ok = r.returncode == 0
    else:
        unit = Path.home() / ".config" / "systemd" / "user" / "kbuba-tracker.service"
        unit.parent.mkdir(parents=True, exist_ok=True)
        unit.write_text(f"""[Unit]
Description=kbuba project tracker

[Service]
ExecStart={sys.executable} {serve}
Restart=on-failure

[Install]
WantedBy=default.target
""")
        run("systemctl", "--user", "daemon-reload")
        ok = run("systemctl", "--user", "enable", "--now",
                 "kbuba-tracker").returncode == 0
    print("autostart: INSTALLED - tracker launches at login" if ok else
          "autostart: install FAILED (see output above) - run the tracker "
          f"manually: {PY} \"{serve}\"")
    return ok


def register_project(tdir):
    """The tracker is GLOBAL (one server, every project). Make a new
    project visible and front-most: its parent dir joins the registry
    roots (so discovery finds it wherever it was created), it becomes
    last-open, and a live server is switched to it right now."""
    import urllib.request
    tdir = Path(tdir).resolve()
    state = Path.home() / ".local" / "state" / "kbuba-tracker"
    reg_p = state / "registry.json"
    try:
        reg = json.loads(reg_p.read_text())
    except (OSError, ValueError):
        reg = {}
    reg.setdefault("roots", ["~/projects"])
    parent = str(tdir.parent.parent)
    if parent not in [str(Path(r).expanduser()) for r in reg["roots"]]:
        reg["roots"].append(parent)
    reg["last"] = str(tdir)
    state.mkdir(parents=True, exist_ok=True)
    reg_p.write_text(json.dumps(reg, indent=1))
    url, alive = tracker_url()
    if alive:
        try:
            urllib.request.urlopen(urllib.request.Request(
                url + "/api/project",
                data=json.dumps({"dir": str(tdir)}).encode()), timeout=3)
            print(f"tracker: board switched to this project - open {url} "
                  "(the header dropdown switches between projects)")
        except Exception as e:
            print(f"tracker: running at {url} but could not switch to this "
                  f"project ({e}) - reload the page and use the dropdown")
    else:
        print("tracker: NOT running. Install always-on: kbuba autostart; "
              f"or run  {PY} tracker/serve.py  in a kept-open terminal")


def stop_tracker():
    """'stopped' | 'failed' (running, but shutdown refused - e.g. a server
    from before the endpoint existed) | 'absent'. Never conflate failed
    with absent: the caller must tell the user a live process remains."""
    import urllib.request
    url, alive = tracker_url()
    if not alive:
        return "absent"
    try:
        urllib.request.urlopen(url + "/api/shutdown", data=b"{}", timeout=2)
        return "stopped"
    except Exception:
        return "failed"


def update():
    """Pull the latest kbuba into this clone, then restart the tracker so
    it serves the new code. A manually-run tracker is stopped and its
    restart command printed - projects are never touched."""
    import time
    r = run("git", "-C", str(HERE), "pull", "--ff-only",
            capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip()
    if r.returncode == 0:
        print(f"update: {out.splitlines()[-1]}")
    else:
        print(f"update: git pull failed - {out[-200:]}")
        print("update: continuing with the tracker restart anyway")
    st = stop_tracker()
    if st == "failed":
        print("tracker: running instance refused shutdown (older version?) - "
              "the restarted server will take the next free port")
    was_running = st != "absent"
    if st == "stopped":
        # the old process dies asynchronously and answers probes for a
        # beat; a successor started too early sees the zombie, exits
        # "already running", and then NOTHING is left running. Wait for
        # the port to be genuinely dead before restarting.
        for _ in range(20):
            if not tracker_url()[1]:
                break
            time.sleep(0.5)
    uid = os.getuid() if hasattr(os, "getuid") else 0
    restarted = False
    if (sys.platform == "darwin" and (Path.home() / "Library" / "LaunchAgents"
                                      / "com.projectkbuba.tracker.plist").exists()):
        restarted = run("launchctl", "kickstart", "-k",
                        f"gui/{uid}/com.projectkbuba.tracker",
                        capture_output=True).returncode == 0
    elif os.name == "nt":
        if run("schtasks", "/Query", "/TN", "kbuba-tracker",
               capture_output=True).returncode == 0:
            restarted = run("schtasks", "/Run", "/TN", "kbuba-tracker",
                            capture_output=True).returncode == 0
    elif (Path.home() / ".config" / "systemd" / "user"
          / "kbuba-tracker.service").exists():
        restarted = run("systemctl", "--user", "restart",
                        "kbuba-tracker").returncode == 0
    if restarted:
        alive = False
        for _ in range(10):
            time.sleep(0.5)
            if tracker_url()[1]:
                alive = True
                break
        if alive:
            print("tracker: restarted on the new code")
            get_url()
        else:
            # never claim a restart the poll did not witness
            print("tracker: restart command succeeded but the server did "
                  "NOT come up - start it manually: "
                  f"{PY} \"{HERE / 'tracker' / 'serve.py'}\"")
    elif was_running:
        print("tracker: stopped (it was running the old code manually) - "
              f"start it again:  {PY} \"{HERE / 'tracker' / 'serve.py'}\"")
    else:
        print("tracker: not running; nothing to restart")


def uninstall(with_ponytail):
    """Remove everything kbuba put on this machine: the running tracker,
    the autostart service, the PATH shim, the tracker state dir, and
    (only with --with-ponytail) the ponytail plugin. Scaffolded projects
    and this clone are never deleted."""
    if sys.platform == "darwin":
        run("launchctl", "bootout",
            f"gui/{os.getuid()}/com.projectkbuba.tracker", capture_output=True)
        plist = Path.home() / "Library" / "LaunchAgents" / "com.projectkbuba.tracker.plist"
        removed = plist.exists() and (plist.unlink() or True)
        print(f"autostart: {'removed' if removed else 'was not installed'}")
    elif os.name == "nt":
        if run("schtasks", "/Query", "/TN", "kbuba-tracker",
               capture_output=True).returncode != 0:
            print("autostart: was not installed")
        else:
            r = run("schtasks", "/Delete", "/F", "/TN", "kbuba-tracker",
                    capture_output=True, text=True,
                    encoding="oem", errors="replace")  # console tools emit
            # OEM (e.g. cp850 on French Windows), not the ANSI codepage
            if r.returncode == 0:
                print("autostart: removed")
            else:
                print("autostart: scheduled task EXISTS but could not be "
                      f"removed ({(r.stdout + r.stderr).strip()[-120:]}). "
                      "It was likely created elevated - run from an admin "
                      "prompt:  schtasks /Delete /F /TN kbuba-tracker")
    else:
        run("systemctl", "--user", "disable", "--now", "kbuba-tracker",
            capture_output=True)
        unit = Path.home() / ".config" / "systemd" / "user" / "kbuba-tracker.service"
        removed = unit.exists() and (unit.unlink() or True)
        print(f"autostart: {'removed' if removed else 'was not installed'}")

    print({"stopped": "tracker: stopped",
           "absent": "tracker: was not running",
           "failed": "tracker: STILL RUNNING - shutdown refused (a server "
                     "from before the shutdown endpoint?); kill the serve.py "
                     "process manually"}[stop_tracker()])

    shim = shutil.which("kbuba") or shutil.which("kbuba.cmd")
    if shim and str(HERE) in (os.path.realpath(shim) + Path(shim).read_text(errors="replace")):
        if os.name == "nt" and shim.lower().endswith(".cmd"):
            # cmd.exe errors (and exits 1) if its batch file vanishes
            # mid-run, so delete it a beat later from a detached process.
            # MUST be a single string with shell=True: list args get their
            # inner quotes backslash-escaped, which cmd.exe misparses and
            # the del target becomes garbage (verified by repro).
            subprocess.Popen(
                f'ping -n 2 127.0.0.1 >nul & del /q "{shim}"', shell=True,
                creationflags=0x00000008 | 0x00000200)  # DETACHED | NEW_GROUP
            print(f"command: {shim} removes itself in a moment")
        else:
            Path(shim).unlink()
            print(f"command: removed {shim}")
    elif shim:
        print(f"command: {shim} points at a different kbuba copy - left alone")
    else:
        print("command: no shim found on PATH")

    shutil.rmtree(Path.home() / ".local" / "state" / "kbuba-tracker",
                  ignore_errors=True)
    print("tracker state (registry, url record): removed")

    if with_ponytail and shutil.which("claude"):
        run("claude", "plugin", "uninstall", "ponytail@ponytail")
        run("claude", "plugin", "marketplace", "remove", "ponytail")
        print("ponytail: uninstalled (its ~/.config/ponytail left for you to delete)")
    else:
        print("ponytail: KEPT (other projects may use it) - remove with "
              "`kbuba uninstall --with-ponytail` or "
              "`claude plugin uninstall ponytail@ponytail`")

    print(f"\nnot deleted (yours to remove): this clone ({HERE}) "
          "and every scaffolded project")


def main():
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    cmd = args[0] if args else "help"
    if cmd == "setup-folder":
        setup_folder(args[1] if len(args) > 1 else Path.cwd().name)
        if "--no-ponytail" in flags:
            print("ponytail: skipped (--no-ponytail)")
        else:
            install_ponytail()
        # launch-at-login is decided once, at kbuba INSTALL time (the
        # tracker is global) - here we only honor an explicit flag
        if "--autostart" in flags:
            autostart_install()
        register_project(Path.cwd() / "tracker")
        print("AI agents: tell your user the tracker URL above and to "
              "BOOKMARK it; `kbuba get-url` recovers it anytime.")
    elif cmd == "register":
        # retrofit an existing project (run inside its folder)
        register_project(Path.cwd() / "tracker")
    elif cmd == "get-url":
        get_url()
    elif cmd == "autostart":
        autostart_install()
    elif cmd == "update":
        update()
    elif cmd == "uninstall":
        uninstall("--with-ponytail" in flags)
    elif cmd == "ui":
        url, alive = tracker_url()
        if alive:
            webbrowser.open(url)
        else:
            get_url()
    else:
        print(__doc__.strip())


if __name__ == "__main__":
    main()
