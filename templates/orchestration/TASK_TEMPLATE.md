# TASK Packet Template

The Conductor fills this template whenever work does not qualify for DIRECT
execution, then dispatches it either by spawning an implementer agent with
the packet as its entire prompt (the default, CONDUCTOR.md §1.6) or by
giving the owner the completed prompt to paste verbatim into a fresh
conversation. The packet is the
implementer's entire briefing: self-contained, pointer-based (reference spec
sections, never paste them), and scoped to one task. For visual/UX work it
cites committed reference artifacts and the rubric the owner's eye will
apply; prose alone does not specify a look. Lines in <angle brackets>
are placeholders; everything else is kept verbatim.

The filled packet is chat-only. Never save a completed, replacement, rework,
or retired packet in HANDOFFS.md, STATE.md, another ledger, or any repository
file; this blank template is the only packet form kept on disk.

```text
=== IMPLEMENTER NOTICE ===
YOU ARE AN IMPLEMENTER, NOT THE CONDUCTOR - whether this conversation was
spawned by the Conductor or created by the owner.
You execute exactly this one task and report back in the mandatory format;
your final report returns to the Conductor (directly if spawned, relayed
by the owner otherwise). Before starting,
read CLAUDE.md (Claude) or AGENTS.md (GPT) at the repo root, then
orchestration/IMPLEMENTER.md, and obey both. If anything below conflicts
with the specification named by TARGET VERSION, STOP and report BLOCKED.

=== TASK ===
TASK-ID: T-<nnn>
TITLE: <imperative, one line>
TARGET VERSION: <the versioned spec this task builds against, or INLINE
if this packet carries its full requirements>
WORKING COPY: <absolute path prepared by the Conductor>
BRANCH: task/T-<nnn>
BASELINE: <commit hash>

OBJECTIVE:
<1-3 sentences. What implementation or evidence exists when this task is done.
Never ask the Implementer to author its governing specification or choose a
design.>

SPEC REFERENCES (read these in-repo before coding):
- <exact applicable specification path> §<x>, §<y>
- <other repo files to read, with paths>

REFERENCE ARTIFACTS (visual/UX tasks only; committed paths, never
gitignored ones - a spawned worktree cannot see them):
- <reference render/capture path> - <the rubric the owner's eye applies>

ALLOWED FILES (create/modify nothing outside this list):
- <path>
- <path>

FORBIDDEN (reminders beyond the standard boundaries, if any):
- <e.g. "do not touch src/ui/ui.c even though you will read it">

ACCEPTANCE (the Conductor re-runs these; all must pass):
1. <exact command>  -> <expected result>
2. <exact command>  -> <expected result>

NOTES:
<known pitfalls, fixtures to use, or "none">

Report back using the exact format in orchestration/IMPLEMENTER.md §4.
=== END TASK ===
```

## Conductor checklist before sending

- [ ] Implementer notice present and first
- [ ] Target version and exactly one applicable normative specification named
- [ ] Isolated working copy and task branch already prepared
- [ ] Absolute working-copy path, branch, and baseline present
- [ ] Objective achievable without any of the Conductor's conversation
- [ ] Spec references are pointers, not pasted text
- [ ] Every required product/architecture/interface/format choice is already
      frozen in the cited specification; zero Implementer design discretion
- [ ] Allowed-files list is minimal and sufficient
- [ ] Every acceptance criterion is a runnable command, not an opinion
- [ ] Visual/UX task: committed reference artifact + rubric cited, never
      prose alone
- [ ] Task recorded in STATE.md with its route status (IN_FLIGHT(AGENT, date)
      or AWAITING_OWNER_DISPATCH(model, date)) and state committed
- [ ] Dispatched by exactly one route: agent spawned with the packet as its
      entire prompt, or exact prompt given to the owner
