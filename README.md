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

**Windows:** clone the repo, then create `kbuba.cmd` in a directory on
`PATH` (e.g. `%LOCALAPPDATA%\Microsoft\WindowsApps`) containing:

```bat
@python "C:\path\to\kbuba\kbuba.py" %*
```

Everything the CLI does is plain Python (`kbuba.py`) - if a shim is not
possible, `python3 /path/to/kbuba.py setup-folder` is equivalent.

**Tracker at login (optional):** macOS `bash tracker/install-autostart.sh`
(LaunchAgent); Linux: `autostart/kbuba-tracker.service` (systemd user
unit, instructions inside); Windows: a Task Scheduler logon task running
`python C:\path\to\kbuba\tracker\serve.py`.

## Use

```sh
mkdir my-project && cd my-project
kbuba setup-folder "My Project"     # name defaults to the folder name
python3 tracker/serve.py            # board at http://127.0.0.1:8611
```

Then start a Conductor: open an AI conversation in the folder whose
first message contains `ROLE=CONDUCTOR` plus your product intent. Every
other conversation is an Implementer and waits for a task packet.

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

See `tracker/README.md` for the full feature list and data shape.
