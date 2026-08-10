# STATE - {{PROJECT}} live orchestration state

> Only the Conductor edits this file. Keep it live and compact: current
> phase, task statuses, in-flight work, active blockers, pending owner
> actions, and next handoffs only. Durable history lives in the other
> `orchestration/` ledgers.
>
> **BEFORE COMMITTING THIS FILE, RUN `python3 tools/ledger-guard/check.py`
> (exit 0 required). Never edit it with a global substitution / replace_all
> / `sed -i`. See CONDUCTOR.md §9.**

## Current seat

**Last updated:** (no seat has run yet - scaffolded by kbuba setup-folder)

## Standing info

**Phase:** project start. No normative spec exists yet; task packets
carry full requirements inline (CLAUDE.md rule 1).

**Dispatch default:** owner-chosen per dispatch via the tracker
Orchestration tab; direct spawn is the default route.

## Live task ledger

| ID | Title | Status |
|---|---|---|

## Pending owner actions (open only)

(none)

## Lessons that bind future work

(none yet)

## Next handoffs

1. First Conductor seat: read CONDUCTOR.md fully, run
   `python3 tracker/serve.py --inbox`, seed the tracker board with the
   project's first steps, and record the owner's product intent in
   CLAUDE.md's project paragraph + DECISIONS.md.
