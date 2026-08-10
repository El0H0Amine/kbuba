# tracker - standalone project tracker

Zero-dependency board for multi-step projects: lifecycle table, charts,
dependency graph, owner question/decision surface, orchestration file
editor. Stdlib Python + one HTML file; no build step.

## Run

```sh
python3 tracker/serve.py        # http://127.0.0.1:8611
```

## Autostart at login (macOS)

```sh
bash tracker/install-autostart.sh
```

Installs a LaunchAgent (`com.projectkbuba.tracker`): starts the server at
login, restarts it on crash, and exits cleanly if the port is already
taken (no respawn loop). Log: `~/Library/Logs/kbuba-tracker.log`.
Uninstall commands are in the script header. Re-run after moving the repo.

## Multiple projects

The server discovers every `<root>/*/tracker/config.json` under the
registry roots (`~/.local/state/kbuba-tracker/registry.json`, default
root `~/projects`; add roots by editing that file). A header dropdown
switches between discovered projects; the last one opened is remembered
and served first at startup. Same-named trackers (task worktrees of one
repo) collapse to the copy with the newest data file. Agent CLI commands
(`--inbox` etc.) always act on the repo the invoked `serve.py` lives in,
never on the UI's selection.

## Reuse in another project

One command (copies the folder, names it, creates an empty board):

```sh
bash tracker/new-project.sh ~/projects/<new-repo> "Project Name"
```

Or copy this folder by hand, then edit `config.json` (an unedited copy
keeps the old project name and silently dedupes into it):

- `project` - display name
- `data` - path to the tracker JSON (canonical source of truth)
- `orchestration_dir` - directory whose .md files the Orchestration tab
  lists and edits (omit or point at an empty dir to disable)
- `guard` + `guard_cwd` - command run after every orchestration save;
  non-zero exit restores the previous file content

`TRACKER.md` (the markdown table view) is regenerated on every save.

## Agent commands

```sh
python3 tracker/serve.py --inbox     # print unread owner interactions, stamp read-receipts
python3 tracker/serve.py --reopen <item-id> <question-id> "follow-up question"
python3 tracker/serve.py --log-session <item-id> <session-id> <model> "final one-liner"
python3 tracker/serve.py --sessions <item-id>   # deliberate audit read
```

`--reopen` sends an insufficiently-answered question back to the owner;
the old exchange collapses into the question's `history`. The session
audit (`sessions` file in config) records which implementer sessions
worked each step; it is context-cold - shown in the UI on Gantt-row
click, never in `--inbox`. Items with `agent: true` are the Conductor's
standing judgment of what the owner-set dispatch policy (Orchestration
tab: model/version/thinking) can carry in parallel.

## Rules encoded in the UI/server

- A step with an open Conductor question is "awaiting owner" - it cannot
  leave Discovery (Rule of Spec), and stays flagged if raised mid-flight.
- Done requires Story + Design + Tech + Owner-verified checks and zero
  open questions (Review Gate; enforced server-side).
- Owner gate: when S/D/T pass, the Conductor authors `ownerCheck` on the
  item ({commands, checklist:[{text,done}], comment}) - the Questions tab
  shows the exact commands to run and the checklist; the O check unlocks
  only when the checklist is complete.
- Every owner interaction becomes an inbox event with a read-receipt;
  agents consume the delta with `--inbox`, never the whole JSON.
- Archiving a Done step CLEANS it: full Q&A/history/notes + its inbox
  events move to the `cold` file (point it off-repo); the live archive
  keeps name + decisions + one half-sentence lesson.
- Concurrent edits: rev check, stale saves get 409 and the UI reloads.

## Data shape

```json
{"rev": 1, "project": "...", "items": [{
  "id": "slug", "name": "...", "domain": "User Story|Product Design|Technical|Cross-Functional",
  "stage": "Discovery|Speced|Implementation|Review|Done",
  "deps": ["other-id"], "notes": "...",
  "questions": [{"id": "q1", "text": "...", "answer": null, "answeredAt": null, "asked": "YYYY-MM-DD"}],
  "decisions": ["..."],
  "review": {"story": false, "design": false, "tech": false}}]}
```

Dependency edits (`deps`) are done in the JSON for now.
