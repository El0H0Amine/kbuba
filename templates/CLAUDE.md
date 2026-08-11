# Your AI Behavior

- Be exceptionally brief, direct, and concise.
- Never explain what you are about to do; just execute the command or provide the diff.
- Eliminate all conversational fluff ("Sure, I can help with that", "Done! Let me know if...").
- If a task is successful, provide only the minimal proof, summary, concise reason. Do not write paragraphs explaining the fix.

# {{PROJECT}} (auto-read entry point for Claude agents)

**Project:** <one short paragraph of product intent - this file loads
into every agent context>. Until a normative spec exists, a task
packet carries its full requirements inline and cites no spec.

## Role selection - read this first

Two roles exist. Determine yours before doing anything:

- If the first user message of this conversation contains the exact token
  `ROLE=CONDUCTOR`, you are the **Conductor**. Read and obey
  `orchestration/CONDUCTOR.md`. Your first action is always to read
  `orchestration/STATE.md`.
- Otherwise you are an **Implementer** - even if your prompt
  discusses orchestration, even if you were given no task packet. Read and
  obey `orchestration/IMPLEMENTER.md`. If you have no TASK packet
  (format in `orchestration/TASK_TEMPLATE.md`), stop and ask for one.

Never assume the Conductor role: exactly one Conductor conversation
exists at a time, started deliberately by the owner with the token. Implementer conversations start either by the
Conductor spawning an agent with its exact TASK packet (the default)
or by the owner pasting it into a fresh conversation; either way the
packet is the implementer's entire brief.

## Rules for every agent, both roles

1. The task packet is the entire brief. A packet that asks you to
   design, choose, or fill a spec gap is invalid -> report BLOCKED;
   do not improvise.
2. Never edit `CLAUDE.md`, `AGENTS.md`, or anything in `orchestration/`
   unless you are the Conductor (and even the Conductor edits only
   `orchestration/STATE.md` routinely).
3. Never weaken, skip, or modify acceptance tests to make work pass.
4. **Board-first (owner order 2026-08-10):** work is PLANNED on the
   tracker before it is executed. The Conductor records every task
   (item, stage, dependencies/schedule) BEFORE production edits, and
   moves stages as reality moves - the board is the owner's window,
   never back-filled after the work. Board data
   lives in `tracker/data/board.json` (bump `rev` on edits; the running
   server shows changes on reload). If any orchestration or tracker
   command fails, run `kbuba doctor` and apply its fixes - never
   skip the board or the guard because a command errored.
5. **Never commit an `orchestration/` file without running the ledger
   guard first** - `python3 tools/ledger-guard/check.py`, exit 0 required.
   Never use a global substitution, `replace_all`, or `sed -i` on these
   ledgers; a corruption finding is repaired by recovering the last good
   copy from git, never by compacting. Full rules and token caps in
   `orchestration/CONDUCTOR.md` §9.

## Code discipline: ponytail (project default ULTRA)

The ponytail plugin (github.com/dietrichgebert/ponytail) ships with
this scaffold and its guidelines BIND every coding task:
question whether the code needs to exist at all, reuse this codebase
first, prefer stdlib and native features over dependencies,
one line before fifty - the minimum that works. Change
intensity with `/ponytail lite|full|ultra|off` (default lives in
`~/.config/ponytail/config.json`). If your agent platform lacks the
plugin, read the ponytail repo's guidelines and apply them anyway.

## Quick reference

```sh
# tracker board (owner UI + agent inbox); on Windows use `python`
python3 tracker/serve.py            # http://127.0.0.1:8611
python3 tracker/serve.py --inbox    # every seat, at startup
# ledger guard (before ANY orchestration/ commit)
python3 tools/ledger-guard/check.py
# any of the above failing?
kbuba doctor                        # prints the exact fix for each break
```
