#!/usr/bin/env python3
"""kbuba - scaffold an AI Conductor/Implementer orchestration system +
tracker board into the current directory. Cross-platform, stdlib only.

    kbuba setup-folder ["Project Name"] [--no-ponytail]
                                          scaffold into the CURRENT dir
    kbuba ui                              open the tracker board
    kbuba help

setup-folder also installs the ponytail plugin (minimal-code discipline,
github.com/dietrichgebert/ponytail) with ultra as first-time default and
tells you exactly what it did; skip with --no-ponytail.

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
    print("run the board with: python3 tracker/serve.py  ->  http://127.0.0.1:8611")
    print("(multi-project switcher: repos under a registry root are discovered "
          "automatically; roots live in ~/.local/state/kbuba-tracker/registry.json)")


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


def main():
    args = [a for a in sys.argv[1:] if a != "--no-ponytail"]
    no_ponytail = "--no-ponytail" in sys.argv
    cmd = args[0] if args else "help"
    if cmd == "setup-folder":
        setup_folder(args[1] if len(args) > 1 else Path.cwd().name)
        if no_ponytail:
            print("ponytail: skipped (--no-ponytail)")
        else:
            install_ponytail()
    elif cmd == "ui":
        webbrowser.open("http://127.0.0.1:8611")
    else:
        print(__doc__.strip())


if __name__ == "__main__":
    main()
