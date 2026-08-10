#!/usr/bin/env python3
"""kbuba - scaffold an AI Conductor/Implementer orchestration system +
tracker board into the current directory. Cross-platform, stdlib only.

    kbuba setup-folder ["Project Name"]   scaffold into the CURRENT dir
    kbuba ui                              open the tracker board
    kbuba help

setup-folder creates: CLAUDE.md/AGENTS.md agent entry points,
orchestration/ (Conductor+Implementer protocol, seed ledgers), tracker/
(board UI + agent inbox), tools/ledger-guard/, a guard pre-commit hook,
and .gitignore - wired together and guard-clean. The project name
defaults to the folder name. Templates live in <repo>/templates/; edit
them there to change what every new project gets.
"""
import json
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


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "setup-folder":
        setup_folder(sys.argv[2] if len(sys.argv) > 2 else Path.cwd().name)
    elif cmd == "ui":
        webbrowser.open("http://127.0.0.1:8611")
    else:
        print(__doc__.strip())


if __name__ == "__main__":
    main()
