#!/usr/bin/env python3
"""Orchestration ledger guard: corruption detection and size caps.

Every file in `orchestration/` is project memory. Two failure classes have
actually happened in this repository, and this tool exists to make both
impossible to commit:

  1. CORRUPTION. On 2026-07-30 commit 07af703 grew STATE.md from 161,638
     bytes to 380,010,938 bytes: one 2,350-byte table row inserted after
     every single character of the file (161,638 x 2,350 = the exact blob
     size). That is a global substitution whose match was empty. The
     committed file then held 163,421 lines of which 95 were unique, and
     nobody noticed until the next seat opened it.
  2. UNBOUNDED GROWTH. Ledgers are append-only by habit, so DECISIONS.md
     and DEFECTS.md both passed 4,000 lines and HANDOFFS.md passed 900.
     A file no one can read is not memory.

Findings (each is one line: FILE CODE detail):
  LDG001_EMPTY            file is blank but its committed version is not
  LDG002_OVERSIZE_BYTES   file exceeds the hard byte ceiling
  LDG003_REPEATED_BLOCK   a long line occurs several times (the 07af703 bug)
  LDG004_LOW_UNIQUENESS   unique/total non-blank line ratio below the floor
  LDG005_CONSECUTIVE_RUN  identical lines repeat back to back
  LDG006_EXPLOSIVE_GROWTH file multiplied in size against its committed version
  LDG007_NO_HEADING       file does not open with a level-1 markdown heading
  LDG008_OVER_CAP         file is over its TOKEN cap; --compact (ledgers with
                          entry structure) or shorten by hand (docs/state)
  LDG009_PINNED_OVER_CAP  entries that may never be archived exceed the cap

Caps are TOKEN budgets, estimated
as ceil(chars / 4) - the standard English-prose approximation. Governed
files now include the guideline docs (CONDUCTOR, IMPLEMENTER,
TASK_TEMPLATE, VISUAL_CHECKS, repo-root CLAUDE.md): they have no entry
rotation, so exceeding their cap means a deliberate hand-compression.

LDG001-LDG007 are corruption: never commit, never "fix" by compacting.
LDG008 is routine and is what --compact resolves. LDG009 needs a human.

Compaction is archival rotation, not deletion: the oldest non-pinned
entries move verbatim into `orchestration/archive/<NAME>-archive.md` and
the live file gains a pointer block. Content is verified present in the
archive before the live file is shortened. Pinned entries never move:
open defects, unconsumed handoffs, and anything marked `<!-- pinned -->`.

Exit 0 only when zero findings. Usage:
  python3 tools/ledger-guard/check.py [--root DIR] [--compact] [--dry-run]
"""

import argparse
import collections
import re
import subprocess
import sys
from pathlib import Path

# --- corruption thresholds -------------------------------------------------
# Calibrated 2026-07-30 against the healthy ledgers, which score:
# uniqueness ratio >= 0.960, max consecutive run 1, and zero repeats of any
# line >= 80 chars. The corrupt STATE.md scored 0.0006. The margin is wide
# on purpose: a false positive costs one command, a false negative cost the
# project a 380 MB commit that is still in the object store.
HARD_BYTE_CEILING = 2 * 1024 * 1024
MIN_UNIQUENESS_RATIO = 0.90
UNIQUENESS_MIN_LINES = 50
LONG_LINE_CHARS = 80
MAX_LONG_LINE_REPEATS = 2
MAX_CONSECUTIVE_RUN = 3
GROWTH_FACTOR = 3.0
GROWTH_MIN_DELTA = 100 * 1024

PIN_MARKER = re.compile(r"<!--\s*pinned\s*-->", re.IGNORECASE)
POINTER_COST = 250  # tokens the archive pointer block adds back to a live file


def est_tokens(text: str) -> int:
    """ceil(chars/4): the standard prose approximation; deterministic and
    dependency-free. Caps below are calibrated against it, not a real
    tokenizer - consistency matters more than absolute accuracy here."""
    return (len(text) + 3) // 4


def group_tokens(group) -> int:
    return est_tokens("\n".join("\n".join(e) for e in group))

# A defect is archivable only when it is confidently finished. Anything
# ambiguous stays in the live file: losing sight of an open defect is a far
# worse outcome than a slightly long file.
CLOSED_WORDS = re.compile(r"\b(RESOLVED|CLOSED|FIXED|WITHDRAWN)\b")
# Only genuine open-status tokens pin. Words like OWED, PROGRESS or REVIEW
# FINDINGS appear in follow-up sections of defects that ARE fixed (D-087 has
# all three), and treating them as "open" pinned 370 lines of finished work.
NOT_CLOSED_WORDS = re.compile(
    r"\b(OPEN|NOT FIXED|UNPROVEN|IN PART|PENDING|CONFIRMED)\b"
)


class Ledger:
    """One governed file: how to split it, what may never be archived."""

    def __init__(self, name, cap, entry_re, kind, rel=None):
        self.name = name
        self.cap = cap  # tokens (est_tokens)
        self.entry_re = re.compile(entry_re) if entry_re else None
        self.kind = kind
        self.rel = rel or f"orchestration/{name}"


LEDGERS = [
    # STATE.md is live state, rewritten rather than appended - no entry
    # rotation; over cap = rewrite it (it is not append-only).
    Ledger("STATE.md", 3500, None, "state"),
    # 'File contract' is deliberately excluded so it stays in the preamble and
    # is never a rotation candidate: it is the rule set, not a handoff.
    Ledger("HANDOFFS.md", 1000, r"^## (Handoff #\d+|#\d+\b)", "handoffs"),
    Ledger(
        "DECISIONS.md",
        5000,
        r"^## (\d{4}-\d{2}-\d{2}|Deferred and accepted|V1 product and architecture)",
        "decisions",
    ),
    Ledger("DEFECTS.md", 2000, r"^## .{0,40}?\bD-\d+", "defects"),
    # Guideline docs: no rotation structure; over cap = hand-compress,
    # preserving every rule (they are read every seat - that IS the budget).
    Ledger("CONDUCTOR.md", 5000, None, "doc"),
    Ledger("IMPLEMENTER.md", 1000, None, "doc"),
    Ledger("TASK_TEMPLATE.md", 1000, None, "doc"),
    Ledger("VISUAL_CHECKS.md", 1000, None, "doc"),
    Ledger("CLAUDE.md", 1000, None, "doc", rel="CLAUDE.md"),
]


def committed_size(path: Path, root: Path) -> int:
    """Bytes of this file at HEAD, or -1 when it is not committed/available."""
    rel = path.relative_to(root).as_posix()
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "cat-file", "-s", f"HEAD:{rel}"],
            capture_output=True, text=True, timeout=30,
        )
        return int(out.stdout.strip()) if out.returncode == 0 else -1
    except (ValueError, OSError, subprocess.SubprocessError):
        return -1


def check_corruption(name, text, size, head_size):
    """Return findings for the structural-damage classes. Order is severity."""
    findings = []
    lines = text.split("\n")
    nonblank = [l for l in lines if l.strip()]

    if not nonblank and head_size > 0:
        findings.append((name, "LDG001_EMPTY",
                         f"file is blank but HEAD holds {head_size} bytes"))
        return findings

    if size > HARD_BYTE_CEILING:
        findings.append((name, "LDG002_OVERSIZE_BYTES",
                         f"{size} bytes exceeds the {HARD_BYTE_CEILING} ceiling"))

    counts = collections.Counter(nonblank)
    for line, n in counts.most_common():
        if n <= MAX_LONG_LINE_REPEATS or len(line) < LONG_LINE_CHARS:
            break
        findings.append((name, "LDG003_REPEATED_BLOCK",
                         f"a {len(line)}-char line occurs {n} times: {line[:60]!r}"))
        break

    if len(nonblank) >= UNIQUENESS_MIN_LINES:
        ratio = len(counts) / len(nonblank)
        if ratio < MIN_UNIQUENESS_RATIO:
            findings.append((name, "LDG004_LOW_UNIQUENESS",
                             f"only {len(counts)} unique of {len(nonblank)} non-blank "
                             f"lines (ratio {ratio:.4f} < {MIN_UNIQUENESS_RATIO})"))

    run = best = 1
    for i in range(1, len(nonblank)):
        run = run + 1 if nonblank[i] == nonblank[i - 1] else 1
        best = max(best, run)
    if best > MAX_CONSECUTIVE_RUN:
        findings.append((name, "LDG005_CONSECUTIVE_RUN",
                         f"{best} identical lines back to back"))

    if head_size > 0 and size > head_size * GROWTH_FACTOR and \
            size - head_size > GROWTH_MIN_DELTA:
        findings.append((name, "LDG006_EXPLOSIVE_GROWTH",
                         f"{head_size} -> {size} bytes "
                         f"(x{size / head_size:.1f}); review before committing"))

    if not nonblank[0].startswith("# "):
        findings.append((name, "LDG007_NO_HEADING",
                         f"first content line is {nonblank[0][:60]!r}"))
    return findings


def split_entries(lines, ledger):
    """Split into (preamble, entries). Wrapped '## ' headings stay with their
    entry: both DECISIONS.md and DEFECTS.md carry titles that run over two or
    three lines, so 'starts with ##' is not the same as 'is a new entry'."""
    starts = [i for i, l in enumerate(lines) if ledger.entry_re.match(l)]
    if not starts:
        return lines, []
    preamble = lines[:starts[0]]
    entries = [lines[a:b] for a, b in zip(starts, starts[1:] + [len(lines)])]
    return preamble, entries


def defect_id(entry):
    m = re.search(r"\bD-(\d+)", entry[0])
    return f"D-{int(m.group(1)):03d}" if m else None


def group_entries(entries, ledger):
    """Group entries that must move together. A defect's follow-up sections
    (`D-090 PROGRESS`, `D-085 RESOLUTION`) belong with the defect itself."""
    if ledger.kind != "defects":
        return [[e] for e in entries]
    groups, index = [], {}
    for e in entries:
        did = defect_id(e)
        if did is not None and did in index:
            groups[index[did]].append(e)
        else:
            if did is not None:
                index[did] = len(groups)
            groups.append([e])
    return groups


def is_pinned(group, ledger):
    """Pinned groups are never archived, whatever the cap costs."""
    text = "\n".join("\n".join(e) for e in group)
    if PIN_MARKER.search(text):
        return True, "explicit marker"
    if ledger.kind == "defects":
        # Status lives in the heading for 208 of 228 sections and in a
        # **Status:** field for the rest; read both, and keep anything that
        # is not unambiguously finished.
        head = " ".join(e[0] for e in group)
        status = " ".join(
            l for e in group for l in e if l.lower().startswith("**status:")
        )
        blob = f"{head} {status}".upper()
        if NOT_CLOSED_WORDS.search(blob) or not CLOSED_WORDS.search(blob):
            return True, "not confidently closed"
    if ledger.kind == "handoffs":
        # Consumption is recorded three ways across this file's history:
        # a **Consumed:** field, a bare "Consumed: <date> by ..." in prose,
        # and "CONSUMED <date>" inside a wrapped heading. A handoff that is
        # explicitly NOT consumed is still live and must stay.
        consumed = re.search(r"(?<!not\syet\s)(?<!not\s)\bconsumed[:\s]", text, re.I)
        unconsumed = re.search(r"\bnot\s+(yet\s+)?consumed\b", text, re.I)
        if unconsumed or not consumed:
            return True, "not consumed"
    return False, ""


POINTER_HEADING = "## Archived history"


def strip_pointer_block(preamble):
    """Remove a pointer block written by an earlier run so it is not doubled."""
    try:
        i = preamble.index(POINTER_HEADING)
    except ValueError:
        return preamble
    j = i + 1
    while j < len(preamble) and not preamble[j].startswith("## "):
        j += 1
    return preamble[:i] + preamble[j:]


def pointer_block(ledger, archived_groups, archive_rel):
    body = [
        POINTER_HEADING,
        "",
        "<!-- pinned -->",
        "",
        f"{sum(len(g) for g in archived_groups)} earlier entries were rotated "
        f"into [`{archive_rel}`]({archive_rel}) to hold this file under its "
        f"{ledger.cap}-token cap.",
        "Nothing was deleted: the archive is committed, and git history holds "
        "every prior revision. Grep the archive before assuming a decision or "
        "defect is unrecorded.",
        "",
    ]
    if ledger.kind == "defects":
        ids = sorted({defect_id(e) for g in archived_groups for e in g} - {None})
        if ids:
            body.append(f"Archived (all closed): {compress_ids(ids)}")
            body.append("")
    body.append("Rotation is mechanical, oldest first: "
                "`python3 tools/ledger-guard/check.py --compact`.")
    body.append("")
    return body


def compress_ids(ids):
    """D-001 D-002 D-003 D-007 -> 'D-001..D-003, D-007'."""
    nums = sorted(int(i.split("-")[1]) for i in ids)
    out, start, prev = [], nums[0], nums[0]
    for n in nums[1:] + [None]:
        if n == prev + 1:
            prev = n
            continue
        out.append(f"D-{start:03d}" if start == prev else f"D-{start:03d}..D-{prev:03d}")
        start = prev = n
    return ", ".join(out)


def compact(path, ledger, root, dry_run):
    """Rotate oldest non-pinned entries out until the token cap is met."""
    text = path.read_text(encoding="utf-8")
    total = est_tokens(text)
    if total <= ledger.cap or ledger.entry_re is None:
        return None
    lines = text.split("\n")
    preamble, entries = split_entries(lines, ledger)
    if not entries:
        return f"{ledger.name}: no entry structure to compact; shorten by hand"

    groups = group_entries(entries, ledger)
    pins = [is_pinned(g, ledger)[0] for g in groups]
    # Drop any pointer block from a previous run; it is rebuilt below.
    keep_pre = strip_pointer_block(preamble)

    # The pointer block itself costs tokens, so aim under the cap by its size.
    target = ledger.cap - POINTER_COST
    archived, kept = [], []
    budget = est_tokens("\n".join(keep_pre)) + sum(group_tokens(g) for g in groups)
    for group, pinned in zip(groups, pins):
        size = group_tokens(group)
        if pinned or budget <= target:
            kept.append(group)
        else:
            archived.append(group)
            budget -= size
    if not archived:
        return (f"{ledger.name}: over cap at {total} tokens but every entry "
                f"is pinned (LDG009)")

    archive_dir = root / "orchestration" / "archive"
    archive_path = archive_dir / f"{path.stem}-archive.md"
    archive_rel = f"archive/{archive_path.name}"

    new_entries = [l for g in kept for e in g for l in e]
    live = keep_pre + pointer_block(ledger, archived, archive_rel) + new_entries
    moved_text = "\n".join(l for g in archived for e in g for l in e)

    live_tokens = est_tokens("\n".join(live))
    if dry_run:
        return (f"{ledger.name}: {total} -> {live_tokens} tokens, "
                f"{sum(len(g) for g in archived)} entries "
                f"({len(moved_text.splitlines())} lines) to {archive_rel}"
                + ("" if live_tokens <= ledger.cap else
                   f"  [STILL OVER CAP by {live_tokens - ledger.cap}]"))

    archive_dir.mkdir(parents=True, exist_ok=True)
    if archive_path.exists():
        prior = archive_path.read_text(encoding="utf-8").rstrip("\n") + "\n\n"
    else:
        prior = (f"# {path.stem} - archived entries\n\n"
                 f"Rotated out of `orchestration/{path.name}` by "
                 f"`tools/ledger-guard/check.py --compact` to keep the live file "
                 f"readable. This file is append-only history: entries are moved "
                 f"here verbatim, never edited and never deleted. The live file "
                 f"carries a pointer to it.\n\n")
    archive_path.write_text(prior + moved_text.rstrip("\n") + "\n", encoding="utf-8")

    # Verify before shortening: every archived line must be present in the
    # archive file. Compaction must never be the thing that loses memory.
    written = archive_path.read_text(encoding="utf-8")
    for line in moved_text.split("\n"):
        if line.strip() and line not in written:
            raise SystemExit(
                f"ABORT: {ledger.name} archive is missing a moved line; "
                f"live file left untouched: {line[:70]!r}")

    path.write_text("\n".join(live), encoding="utf-8")
    return (f"{ledger.name}: {total} -> {live_tokens} tokens; "
            f"{sum(len(g) for g in archived)} entries archived to {archive_rel}")


def pinned_floor(path, ledger):
    """(tokens that may never be archived, whether any rotatable entry remains)."""
    if ledger.entry_re is None:
        return 0, False
    lines = path.read_text(encoding="utf-8").split("\n")
    preamble, entries = split_entries(lines, ledger)
    groups = group_entries(entries, ledger)
    floor = est_tokens("\n".join(strip_pointer_block(preamble)))
    rotatable = False
    for g in groups:
        if is_pinned(g, ledger)[0]:
            floor += group_tokens(g)
        else:
            rotatable = True
    return floor, rotatable


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", type=Path)
    ap.add_argument("--compact", action="store_true",
                    help="rotate oldest non-pinned entries into archive/")
    ap.add_argument("--dry-run", action="store_true",
                    help="with --compact, report what would move and change nothing")
    args = ap.parse_args()
    root = args.root.resolve()

    findings, notes = [], []
    for ledger in LEDGERS:
        path = root / ledger.rel
        if not path.exists():
            findings.append((ledger.name, "LDG001_EMPTY", "file is missing"))
            continue
        raw = path.read_bytes()
        text = raw.decode("utf-8", errors="replace")
        corrupt = check_corruption(ledger.name, text, len(raw),
                                   committed_size(path, root))
        findings.extend(corrupt)
        if corrupt:
            continue  # never compact a damaged file

        if args.compact:
            note = compact(path, ledger, root, args.dry_run)
            if note:
                notes.append(note)
            text = path.read_text(encoding="utf-8")

        n = est_tokens(text)
        if n > ledger.cap:
            floor, rotatable = pinned_floor(path, ledger)
            if ledger.entry_re is None:
                findings.append((ledger.name, "LDG008_OVER_CAP",
                                 f"{n} tokens over the {ledger.cap}-token cap; "
                                 f"no rotation for this file - compress it by "
                                 f"hand (rules/live state must survive intact)"))
            elif rotatable:
                findings.append((ledger.name, "LDG008_OVER_CAP",
                                 f"{n} tokens over the {ledger.cap}-token cap "
                                 f"with rotatable entries left; run "
                                 f"tools/ledger-guard/check.py --compact"))
            else:
                # Everything rotatable is already gone. The remainder is
                # pinned - open defects, unconsumed handoffs - and archiving
                # it would hide live work to satisfy a number. Report, do not
                # block, and do not let the number quietly disappear.
                notes.append(
                    f"WARN {ledger.name} LDG009_PINNED_OVER_CAP: {n} tokens vs a "
                    f"{ledger.cap}-token cap; all {floor} remaining tokens are "
                    f"pinned (open/unconsumed). Fully rotated. Shrinks as entries "
                    f"close, or needs a deliberate evidence-compression pass.")

    for note in notes:
        print(note)
    for name, code, detail in findings:
        print(f"{name} {code} {detail}")
    if findings:
        print(f"\n{len(findings)} finding(s). Do not commit orchestration/ "
              f"until these are zero.")
        return 1
    print("ledger-guard: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
