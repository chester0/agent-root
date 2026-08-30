#!/usr/bin/env python3
"""Bootstrap and maintain the repo knowledge kernel. Portable: any repo, any assistant.

    python scripts/kernel.py init          # seed the kernel files in a fresh repo
    python scripts/kernel.py map           # regenerate MAP.md
    python scripts/kernel.py archaeology   # mine git history for what to document
    python scripts/kernel.py check         # is anything stale?

## What the kernel is

Five files and three rituals. That is the whole portable pattern:

    AGENTS.md      the router and the earned operating rules   (cross-tool: Claude,
                   Copilot, Codex and Cursor all read this name)
    MAP.md         generated inventory - never handwritten
    TRAPS.md       generated view of the in-situ markers       (see traps.py)
    DECISIONS.md   dated why-it-is-like-this; supersede, never delete
    JOURNAL.md     append-only worklog

    rituals: journal-on-finish - write-on-contact - a weekly gardening pass

⭐ The kernel is the FILE NAMES, THEIR CONTRACTS AND THE RITUALS. Everything they
contain is payload, and payload is necessarily bespoke. That seam is what lets
the same pattern serve a life-repo and a Terraform monorepo without pretending
they are the same thing.

## What init deliberately does NOT do

⚠️ **No auto-summarised prose.** No "here is what this module does" blanketing.
Low-quality auto-summary is worse than an honest blank, because it is trusted,
wrong, and it displaces the write-on-contact ritual that produces real knowledge.
This tool generates INDEXES and CANDIDATE QUEUES - never prose that sounds like
understanding.

⚠️ **No seeded constitution.** AGENTS.md's operating rules start EMPTY. Rules
copied in because they sound wise are wallpaper by the second week. A repo earns
its rules one incident at a time, and that earning IS the co-evolution.

⚠️ **No journal backfill, no invented rationale.** History that git does not state
verbatim stays unstated.
"""
from __future__ import annotations

import argparse
import io
import os
import re
import shutil
import subprocess
import sys
from collections import Counter

NL = chr(10)

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

# ⚠️ ONE ANSWER TO "WHAT IS A TEXT FILE", NOT TWO. This file used to keep its own
# list, which had drifted from traps.py's - so `map` was blind to file types
# `traps` could see. Two definitions of the same idea, inside a repo whose entire
# subject is preventing exactly that. traps.py owns them; this imports.
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from traps import EXTS as TEXT_EXT, SKIP_DIRS as SKIP
except Exception:      # traps.py not alongside - keep working, narrower
    TEXT_EXT = {".md", ".py", ".sh", ".yaml", ".yml", ".tf", ".js", ".ts", ".php"}
    NL = chr(10)

SKIP = {".git", "node_modules", ".venv", "build", "__pycache__", "dist", "archive"}


def git(root: str, *args: str) -> str:
    try:
        return subprocess.run(["git", "-C", root, *args],
                              capture_output=True, text=True,
                              check=True, errors="replace").stdout
    except Exception:
        return ""


def repo_root() -> str:
    out = git(os.getcwd(), "rev-parse", "--show-toplevel").strip()
    return out or os.getcwd()


def tracked(root: str) -> list[str]:
    return [f for f in git(root, "ls-files").splitlines() if f]


# --------------------------------------------------------------------------- map
def first_heading(path: str) -> str:
    """The document's own one-line self-description. Never invented."""
    try:
        with io.open(path, encoding="utf-8", errors="replace") as fh:
            for _ in range(40):
                line = fh.readline()
                if not line:
                    break
                line = line.strip()
                if line.startswith("# "):
                    return line[2:].strip()[:90]
                if line.startswith('"""') and len(line) > 5:
                    return line.strip('"').strip()[:90]
    except OSError:
        pass
    return ""


# ⚠️ A MAP OF EVERYTHING IS A MAP OF NOTHING. On a 21,898-file code repo the
# unscoped version produced 21,094 rows - a table nobody reads, that costs real
# context if loaded, and whose only honest use is grep, which the shell already
# does better. Code is largely self-indexing (grep, LSP, module layout); prose
# and entry points are not. So the default is documentation plus entry points,
# and `--all` is available when you genuinely want the lot.
ENTRY_HINTS = ("main.", "cli.", "app.", "manage.py", "setup.py", "index.",
               "Dockerfile", "Makefile", "docker-compose")


def is_git(root: str) -> bool:
    return bool(git(root, "rev-parse", "--git-dir").strip())


def cmd_map(root: str, scope_all: bool = False) -> int:
    # ⚠️ SAY SO RATHER THAN WRITING AN EMPTY MAP. Outside a git repo - an
    # extracted tarball, a directory not yet `git init`-ed - tracked() returns
    # nothing and this silently produced a 0-row MAP.md. An empty index that
    # looks generated is the trusted-but-wrong failure this whole project is
    # about, and it would be someone's first contact with the tool.
    if not is_git(root):
        print("  not a git repository - MAP and archaeology both need history.")
        print("  run `git init` and make one commit first.")
        return 1
    files = [f for f in tracked(root)
             if os.path.splitext(f)[1].lower() in TEXT_EXT
             and not any(s in f.split("/") for s in SKIP)]
    if not scope_all:
        # ⚠️ "docs + top-level only" produced a ONE-ROW map of the kernel's own
        # repo, because everything real lived in scripts/. Depth is the better
        # cut: shallow files are the ones a newcomer needs named, and deep trees
        # are where the unreadable 20,000-row table came from.
        files = [f for f in files
                 if f.lower().endswith(".md")
                 or f.count("/") <= 1
                 or any(h in os.path.basename(f) for h in ENTRY_HINTS)]
    # ⚠️ ONE git pass, not one per file. The first version ran `git log -1` per
    # path: measured at ~33 ms/call, that is roughly TWELVE MINUTES on a
    # 21,898-file repo - the same repo whose sub-second figures headline the
    # README. A tool that is fast in the numbers you publish and slow in the
    # command you omit is worse than a slow tool.
    dates = {}
    cur = ""
    # A literal ASCII sentinel. Using a NUL byte here made the source itself
    # unparseable - "source code cannot contain null bytes" - twice, because the
    # escape survived the heredoc that was writing the fix.
    for line in git(root, "log", "--format=@@D@@%ad", "--date=short",
                    "--name-only").splitlines():
        if line.startswith("@@D@@"):
            cur = line[5:].strip()
        elif line.strip():
            dates.setdefault(line.strip(), cur)   # first sighting = most recent

    rows = []
    for f in sorted(files):
        rows.append((f, first_heading(os.path.join(root, f)), dates.get(f, "")))

    stamp = git(root, "log", "-1", "--format=%ad", "--date=short").strip()
    out = [
        "# MAP",
        "",
        f"Generated by `scripts/kernel.py map` at repo state **{stamp}**. "
        f"{len(rows)} files.",
        "",
        "⚠️ **Generated - do not edit.** A handwritten map rots and is believed "
        "anyway, which is worse than having none. If this is more than a couple "
        "of weeks older than the repo, treat it as a hint, not a fact.",
        "",
        "Descriptions are each file's own first heading, never a summary written "
        "for it.",
        "",
        "| file | what it says it is | last touched |",
        "|---|---|---|",
    ]
    for f, desc, date in rows:
        out.append(f"| `{f}` | {desc or '—'} | {date or '—'} |")
    io.open(os.path.join(root, "MAP.md"), "w", encoding="utf-8",
            newline="\n").write("\n".join(out) + "\n")
    print(f"  MAP.md: {len(rows)} files")
    return 0


# ------------------------------------------------------------------- archaeology
def cmd_archaeology(root: str) -> int:
    """Mine git for what a human should document. Queues, never conclusions."""
    if not is_git(root):
        print("  not a git repository - there is no history to mine.")
        return 1
    log = git(root, "log", "--format=%H%x00%s", "--name-only")
    commits, cur, files_in = [], None, []
    for line in log.splitlines():
        if "\x00" in line:
            if cur:
                commits.append((cur, files_in))
            h, subj = line.split("\x00", 1)
            cur, files_in = subj, []
        elif line.strip():
            files_in.append(line.strip())
    if cur:
        commits.append((cur, files_in))

    churn = Counter()
    pairs = Counter()
    for _subj, fs in commits:
        live = [f for f in fs if not any(s in f.split("/") for s in SKIP)]
        churn.update(live)
        if 1 < len(live) <= 8:      # huge commits couple everything; ignore them
            for i in range(len(live)):
                for j in range(i + 1, len(live)):
                    pairs[tuple(sorted((live[i], live[j])))] += 1

    reverts = [s for s, _ in commits if re.match(r"(?i)^revert\b", s)]
    rationale = [s for s, _ in commits
                 if re.search(r"(?i)\b(because|instead of|workaround|turns out|"
                              r"it was never|does not work|no longer)\b", s)]

    out = [
        "# Documentation candidates — mined from git history",
        "",
        f"Generated by `scripts/kernel.py archaeology`. {len(commits)} commits scanned.",
        "",
        "⚠️ **These are QUESTIONS, not answers.** Nothing here is documentation. "
        "It is a queue for about an hour of human triage, and the deliberate "
        "alternative to auto-summarised prose that sounds like understanding and "
        "is not.",
        "",
        "## Churn hotspots — where traps live",
        "",
        "Most-modified files. Something changed here repeatedly, which usually "
        "means it was hard, surprising, or wrong more than once.",
        "",
    ]
    for f, n in churn.most_common(15):
        out.append(f"- **{n}×** `{f}`")

    out += ["", "## Co-change coupling — undocumented dependencies", "",
            "Files that keep changing together. If the link is not obvious from "
            "reading them, it is exactly the blast-radius note nobody wrote.", ""]
    for (a, b), n in pairs.most_common(12):
        if n >= 3:
            out.append(f"- **{n}×** `{a}` ↔ `{b}`")

    out += ["", "## Reverts — decision goldmines", "",
            "Something was tried and rolled back. The reason is usually in the "
            "message, and almost never anywhere else.", ""]
    for s in reverts[:15] or ["- *(none)*"]:
        out.append(f"- {s}" if not s.startswith("- ") else s)

    out += ["", "## Commits that state a reason", "",
            "Messages containing *because / instead of / workaround / turns out*. "
            "These are `DECISIONS.md` entries that were written in the wrong place.", ""]
    for s in rationale[:25] or ["- *(none)*"]:
        out.append(f"- {s}" if not s.startswith("- ") else s)

    out += ["", "---", "",
            "⭐ **Triage rule:** an entry earns a place in `DECISIONS.md` or a "
            "`⚠️` marker in the file it concerns. If nobody can say why it "
            "mattered, delete the line — an honest blank beats a confident guess."]

    io.open(os.path.join(root, "CANDIDATES.md"), "w", encoding="utf-8",
            newline="\n").write("\n".join(out) + "\n")
    print(f"  CANDIDATES.md: {len(churn)} files, {len(reverts)} reverts, "
          f"{len(rationale)} rationale commits")
    return 0


# -------------------------------------------------------------------------- init
AGENTS_SEED = """# {name} — operating instructions for any AI assistant

<!-- The cross-tool convention: Claude, Copilot, Codex and Cursor all read this
     filename. Knowledge that lives only in a tool-specific file cannot travel to
     the repos where that tool is not approved. -->

## What this repo is

*(One honest paragraph. What it does, who depends on it, what breaks if it is
wrong. Write this yourself — a generated version would be plausible and hollow.)*

## Before acting

```bash
python scripts/traps.py --domains
python scripts/traps.py <domain>
```

Traps are recorded in situ with a `⚠️` marker, and design rationale with `⭐`.
When something bites, the fix is not only the code — it is the marker, because
that is what makes the lesson retrievable next time.

## Operating rules

*(EMPTY ON PURPOSE. Rules are earned, never seeded. Each one added here should
cite the incident that bought it. A rule copied in because it sounds wise is
wallpaper by the second week.)*

## Where things are

| Domain | Start here |
|---|---|
| | |

## Never, here

*(The things that have actually gone wrong. Also empty until they have.)*

---

⚠️ **Hard cap: 120 lines.** This file is loaded on every session, so every line
is paid for forever. Adding a rule means evicting one.
"""

DECISIONS_SEED = """# Decisions

Why things are the way they are. The questions a new person asks in week one and
nobody can answer in year two.

⚠️ **Supersede, never delete.** A reversed decision is more informative than a
tidy file: it records that the obvious thing was tried.

Format — dated, one heading each:

## YYYY-MM-DD — <the decision>

**Context.** What was true at the time.
**Decision.** What was chosen.
**Why not the alternative.** The part that is never written down and is always
the thing someone needs.
**Consequence.** What this now constrains.

---

*(Seed `CANDIDATES.md` with `kernel.py archaeology`; the reverts and the commits
saying "because" are decisions written in the wrong place.)*
"""


def cmd_init(root: str) -> int:
    name = os.path.basename(root)
    created, existing = [], []
    seeds = {
        "AGENTS.md": AGENTS_SEED.format(name=name),
        "DECISIONS.md": DECISIONS_SEED,
        "JOURNAL.md": f"# {name} — journal\n\nDated entries, written as things "
                      f"FINISH rather than at session end: what was believed, "
                      f"what it turned out to be, what it taught.\n",
    }
    for fn, text in seeds.items():
        p = os.path.join(root, fn)
        if os.path.exists(p):
            existing.append(fn)
            continue
        io.open(p, "w", encoding="utf-8", newline="\n").write(text)
        created.append(fn)

    print(f"  created : {', '.join(created) or 'nothing'}")
    print(f"  kept    : {', '.join(existing) or 'nothing'}  (never overwritten)")
    cmd_map(root)
    cmd_archaeology(root)
    print()
    print("  Next, and it is about an hour of human work:")
    print("   1. Write the 'What this repo is' paragraph in AGENTS.md. Yourself.")
    print("   2. Triage CANDIDATES.md — reverts and 'because' commits first.")
    print("   3. Leave the operating rules EMPTY until an incident earns one.")
    print("   4. Run: python scripts/tripwires.py   (emits Claude + Copilot tripwires)")
    print("      then: python scripts/traps.py --domains")
    return 0


# --------------------------------------------------------------------------- install
ADAPTER = '''---
name: agent-root
description: AGENT ROOT - the resident reviewer for this repository. Use when reviewing changes, reviewing a commit or a pull request, orienting in the repo, asking why something is built the way it is, or checking what has drifted or gone stale.
---

# Agent Root

> **Root reviews with receipts. It never repairs, and it never guesses.**

This file is an adapter. The contract is `AGENT-ROOT.md` - portable markdown that
any assistant can follow. Read it first, then `AGENTS.md` for this repo's facts.

## Gather the evidence, then judge it

```bash
python scripts/review.py                 # the working tree
python scripts/review.py --commit HEAD   # a commit
python scripts/review.py --pr 42         # a pull request (needs gh)
```

That command fills the receipt fields. Your job is the verdict, not the
gathering - and a verdict without a receipt is not a verdict.
'''

COPILOT = """Read `AGENTS.md` in the repository root before answering or editing,
and `AGENT-ROOT.md` for the review contract.

Before substantive work, run `python scripts/traps.py --for <changed files>` and
read the output. This repo records hard-won traps in situ; that command is how
they reach you, scoped to what you are touching.
"""

INSTALL_FILES = [
    "AGENT-ROOT.md", "USING-AGENT-ROOT.md",
    "scripts/traps.py", "scripts/tripwires.py", "scripts/kernel.py",
    "scripts/drift.py", "scripts/verify.py", "scripts/review.py",
    "profiles/devops.py",
]


def cmd_install(root, target):
    """Drop Agent Root into a repository and bring it up. One command.

    WARNING: copies NAMED files, never a directory walk. A folder copy is how
    session-state junk - including an agent replay log - nearly shipped in this
    project's own release.
    """
    # WARNING: a partial install must not report success. This loop used to
    # print "missing from source, skipped" and then finish with "Agent Root is
    # installed" and exit 0 - so a copy with no contract file, the one document
    # the whole agent reads, looked exactly like a good one. Absent input is an
    # error here, never a shrug.
    copied, missing = 0, []
    for rel in INSTALL_FILES:
        s = os.path.join(root, rel)
        if not os.path.exists(s):
            missing.append(rel)
            continue
        d = os.path.join(target, rel)
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.copy2(s, d)
        copied += 1
    if missing:
        print("  INSTALL FAILED - not present in the source kernel:")
        for m in missing:
            print("    " + m)
        print("  Nothing was wired up. Install from a complete checkout.")
        return 1
    print("  copied %d file(s)" % copied)

    ad = os.path.join(target, ".claude", "skills", "agent-root", "SKILL.md")
    os.makedirs(os.path.dirname(ad), exist_ok=True)
    io.open(ad, "w", encoding="utf-8", newline=NL).write(ADAPTER)

    ci = os.path.join(target, ".github", "copilot-instructions.md")
    os.makedirs(os.path.dirname(ci), exist_ok=True)
    if not os.path.exists(ci):
        io.open(ci, "w", encoding="utf-8", newline=NL).write(COPILOT)
    print("  wired: .claude/skills/agent-root/ + .github/copilot-instructions.md")

    cwd = os.getcwd()
    try:
        os.chdir(target)
        cmd_init(target)
    finally:
        os.chdir(cwd)
    print("")
    print("  Agent Root is installed. Now:  /agent-root")
    return 0


def cmd_check(root: str) -> int:
    problems = []
    for fn in ("AGENTS.md", "MAP.md", "JOURNAL.md"):
        if not os.path.exists(os.path.join(root, fn)):
            problems.append(f"missing {fn}")
    # ⚠️ Caps are enforced, not remembered. AGENT-ROOT.md's cap once read "one
    # screen" - unmeasurable, and duly broken by the author while adding a rule
    # about measurement. A cap that is not an exit code is a wish.
    for fn, cap in (("AGENTS.md", 120), ("AGENT-ROOT.md", 160)):
        f = os.path.join(root, fn)
        if not os.path.exists(f):
            continue
        n = sum(1 for _ in io.open(f, encoding="utf-8", errors="replace"))
        if n > cap:
            problems.append(f"{fn} is {n} lines, over its {cap}-line cap — evict something")
    for p in problems:
        print(f"  ⚠️ {p}")
    if not problems:
        print("  kernel intact")
    return 1 if problems else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("command",
                    choices=["install", "init", "map", "archaeology", "check"])
    ap.add_argument("--target",
                    help="install Agent Root into this repo")
    ap.add_argument("--all", action="store_true",
                    help="map every text file, not just docs and entry points")
    args = ap.parse_args()
    root = repo_root()
    print(f"repo: {root}")
    if args.command == "install":
        # WARNING: the SOURCE is where this script lives, not the cwd. Deriving
        # it from `git rev-parse` made source and target identical whenever the
        # command was run from inside the repo being installed into - which is
        # the only way anyone would ever run it - so install refused every real
        # invocation and worked only in the one case nobody wants.
        src = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        tgt = os.path.abspath(args.target or os.getcwd())
        if src == tgt:
            print("  target is the kernel itself - pass --target <other repo>")
            return 1
        return cmd_install(src, tgt)
    if args.command == "map":
        return cmd_map(root, args.all)
    return {"init": cmd_init, "archaeology": cmd_archaeology,
            "check": cmd_check}[args.command](root)


if __name__ == "__main__":
    sys.exit(main())
