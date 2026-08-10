# Visual checks - how to see, and what to look for

Generic protocol for any project. It tells an agent how to actually SEE
its output and what a defect looks like, and it splits judgment between
agent and owner. App-specific checklists never live here; a task packet
carries them.

Status legend for owner queues: [ ] awaiting owner, [x] approved, [!] veto.

## How to see

1. **Render at true size on the real target geometry.** A desktop window
   at a different resolution hides layout errors; verify at the shipped
   pixel size and aspect, then zoom IN for detail - never judge from a
   thumbnail.
2. **Capture, then look at the capture.** A claim without an opened
   image is hearsay - including your own. Open every artifact you cite;
   decode it (correct dimensions, not truncated), don't just regenerate it.
3. **See it in motion when it moves.** A stills-only review misses loop
   seams, stutter, tearing, and desync; watch at authored speed, and
   step frame-by-frame across the loop boundary.
4. **See every state, not the happy one:** empty, loading, error,
   offline, overflowing (longest realistic string, most items), aged
   (past every TTL), first-run, and both themes/viewports if they exist.
5. **Compare against the approved reference.** Put the render and the
   reference side by side; judge deviation from the reference, not from
   memory or from the prompt that generated it.
6. **Injected-mistake control:** when a checker or gate is part of the
   claim, feed it a known-bad input and confirm it fails. A gate that
   has never failed has never been tested.

## What to look for

- **Geometry:** clipping at every edge, overflow past its container,
  misalignment against siblings, off-grid spacing, wrong aspect
  (stretched art), elements the layout silently pushed off-screen.
- **Text:** truncation, overlap, unreadable contrast against its actual
  background, wrong glyphs after transcode (accents!), baseline jitter,
  text that should scroll/wrap but clips.
- **Color:** deviation from the approved palette/reference, banding,
  halos or fringes around composited elements, states that are
  indistinguishable (selected vs not, healthy vs failed).
- **Motion:** loop seams, phase lock between elements meant to be
  independent, cadence different from the authored rate, animation that
  never rests (idle discipline), transitions that pop.
- **Composition (flag, don't rule):** anything that reads as pasted-on,
  floating, or detached from the scene light/perspective.
- **Honesty:** a surface that looks healthy while its data source is
  down; placeholder or stale data presented as live.

## Who judges what

- The **agent** judges everything above that a rule can decide, and
  fixes or reports it before claiming PASS.
- **Taste** - charm, weight, whether it feels like the product - is the
  owner's; queue it with a one-line question and the exact file/command
  to look at. Never mark a taste item approved on the owner's behalf.
- The Conductor's eye outranks any implementer report; an implementer's
  "verified visually" is a claim, not evidence.
