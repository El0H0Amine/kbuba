# kbuba - AI orchestration system + project tracker

A complete working method for running a software project with AI agents,
scaffolded into any folder with one command. Zero dependencies beyond
Python 3 and git; no pip installs, no build step.

Two pieces:

- **Orchestration protocol** - a Conductor/Implementer role system for AI
  agents: one Conductor conversation owns specs, dispatch, and review;
  Implementer conversations each execute exactly one self-contained task
  packet. Project memory lives on disk in guarded markdown ledgers
  (STATE / DECISIONS / DEFECTS / HANDOFFS), so any conversation can be
  killed at any moment with zero information loss. A pre-commit guard
  blocks ledger corruption and unbounded growth.
- **Tracker** - a zero-dependency web board (stdlib Python server + one
  HTML file): lifecycle table, Gantt/dependency charts, owner
  question/answer flow with read-receipts, owner review gates, and an
  agent inbox CLI. It auto-discovers every project on your machine and
  switches between them from a header dropdown.

## Install (instructions for you, the AI agent)

The human gave you this repo so you can set up the `kbuba` command on
their machine. Clone it somewhere permanent, then create the command:

**macOS / Linux:**

```sh
git clone https://github.com/El0H0Amine/kbuba ~/projects/kbuba
bash ~/projects/kbuba/install.sh
```

`install.sh` ends by deciding tracker launch-at-login. Run
non-interactively it prints the question for you to relay: **ask the
user**, then run `kbuba autostart` on yes, or tell them to keep
`python3 tracker/serve.py` running in a terminal on no. Same question
applies on Windows after creating the shim.

**Windows:** clone the repo, then create `kbuba.cmd` in a directory on
`PATH` (e.g. `%LOCALAPPDATA%\Microsoft\WindowsApps`) containing:

```bat
@python "C:\path\to\kbuba\kbuba.py" %*
```

Everything the CLI does is plain Python (`kbuba.py`) - if a shim is not
possible, `python3 /path/to/kbuba.py setup-folder` is equivalent.

## Create a project - the exact flow

**macOS / Linux:**

```sh
mkdir my-project && cd my-project
kbuba setup-folder "My Project"     # name defaults to the folder name
```

**Windows (PowerShell or cmd):**

```bat
mkdir my-project & cd my-project
kbuba setup-folder "My Project"
```

The tracker is **global** - one always-on server carries every project,
so launch-at-login is decided once at *install* time (`install.sh` asks;
`kbuba autostart` installs it anytime: LaunchAgent on macOS, systemd
user unit on Linux, Task Scheduler logon task on Windows). If you
declined, run `python3 tracker/serve.py` in a **separate terminal and
keep it open** while you work (`python` on Windows).

`setup-folder` registers the new project with the global tracker
wherever the folder was created (its parent directory joins the
discovery roots) and switches the live board to it - so opening the
tracker right after shows THIS project, and the header dropdown now
lists all of them. For a project scaffolded before this existed, run
`kbuba register` inside its folder to put it on the board.

Then start a Conductor: open an AI conversation in the folder whose
first message contains `ROLE=CONDUCTOR` plus your product intent. Every
other conversation is an Implementer and waits for a task packet.

## The tracker URL - bookmark it

The board lives at **http://127.0.0.1:8611** and one server carries
every project (header dropdown switches). If that port is taken by
another process the server moves to the next free one (8611-8620) and
records where it landed - so the URL to trust is whatever this prints:

```sh
kbuba get-url
```

**Instructions for AI agents:** after `setup-folder` (and after
installing autostart), run `kbuba get-url` and TELL YOUR USER the exact
URL in your reply, telling them to BOOKMARK it in their browser and
that `kbuba get-url` recovers it if they forget. Never assume 8611 -
always report what `get-url` returns.

## What setup-folder creates

```
CLAUDE.md / AGENTS.md      agent entry points: role selection + hard rules
orchestration/
  CONDUCTOR.md             spec ownership, dispatch, adversarial review,
                           context handoffs, ledger hygiene
  IMPLEMENTER.md           one-task discipline + mandatory report format
  TASK_TEMPLATE.md         the task packet (an implementer's entire brief)
  VISUAL_CHECKS.md         how agents verify visual claims
  STATE / DECISIONS / DEFECTS / HANDOFFS .md    seed ledgers
tracker/                   board + agent inbox, wired to the guard
tools/ledger-guard/        corruption + size-cap checks on the ledgers
.githooks/pre-commit       runs the guard on every orchestration/ commit
.gitignore
```

## Bundled discipline: ponytail

`setup-folder` also installs
[ponytail](https://github.com/dietrichgebert/ponytail) (MIT) - a plugin
that makes AI agents write the minimum code that actually works - and
sets its default intensity to **ultra** on first-time setup (an existing
mode config is never overwritten). The scaffold prints exactly what it
installed and where the default lives. Opt out with
`kbuba setup-folder --no-ponytail`; change modes anytime with
`/ponytail lite|full|ultra|off`. The scaffolded `CLAUDE.md` makes the
guidelines explicit, so agents on platforms without the plugin read and
apply them anyway.

## The method in five lines

1. The Conductor owns every specification and never lets an implementer
   design; implementers get self-contained packets and report in a fixed
   format.
2. Every implementer claim is verified adversarially - diffs read,
   acceptance commands re-run verbatim.
3. The disk is the memory: live state, decisions, defects, and handoffs
   are files, so conversations are disposable.
4. Ledgers are guarded: corruption is recovered from git (never
   compacted), growth is rotated, global substitutions are forbidden.
5. The owner steers through the tracker: questions pause work, answers
   carry read-receipts, and Done requires the owner's own review gate.

## Tracker notes

- A bare clone runs as-is: on first start the tracker bootstraps its
  own gitignored `tracker/config.json` + empty board, so `serve.py` and
  `kbuba autostart` work before any project exists (the clone shows up
  in the switcher as a home board).
- Multi-project: any repo under a registry root
  (`~/.local/state/kbuba-tracker/registry.json`, default `~/projects`)
  with a `tracker/config.json` appears in the switcher automatically;
  the last project opened is served first. Same-named copies (git
  worktrees) collapse to the newest.
- Agent channel: `python3 tracker/serve.py --inbox` prints unread owner
  interactions and stamps read-receipts - agents never load the board
  JSON wholesale.
- `TRACKER.md` is regenerated on every save as the human-readable view;
  the JSON stays canonical.

## Update

```sh
kbuba update
```

Pulls the latest kbuba into the clone and restarts the tracker so it
serves the new code (via the login service when installed; a manually
run tracker is stopped and the restart command printed). Projects are
never touched - their boards live in their own repos.

## Uninstall

```sh
kbuba uninstall                 # stops the running tracker, removes autostart
                                # + PATH shim + tracker state
kbuba uninstall --with-ponytail # also uninstalls the ponytail plugin
```

It prints exactly what it removed. Your scaffolded projects and the
clone itself are never deleted - remove the clone folder yourself.

See `tracker/README.md` for the full feature list and data shape.
