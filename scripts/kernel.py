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
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter

NL = chr(10)

# ⭐ Bumped whenever the INSTALLED SURFACE changes - the scripts, the adapter or
# the wiring. It lets an installed repo answer "am I behind?" without diffing
# eleven files, and it is what `fleet` reports per repo.
VERSION = "1.1.0"

FENCE = chr(96) * 3 + NL
FENCE_END = NL + chr(96) * 3
DESC_RE = r"^description:[^\S\r\n]*\S"

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

    # ⭐ A generated table that lives inside a handwritten file. AGENTS.md is
    # capped and mostly human, but its domain index is derived - so it is the
    # exact case markers exist for.
    try:
        import subprocess as _sp
        _r = _sp.run([sys.executable, os.path.join(os.path.dirname(
            os.path.abspath(__file__)), "traps.py"), "--domains"],
            cwd=root, capture_output=True, text=True, encoding="utf-8",
            errors="replace")
        if _r.stdout.strip():
            _st = write_section(os.path.join(root, "AGENTS.md"), "domains",
                                FENCE + _r.stdout.strip() + FENCE_END)
            if _st == "updated":
                print("  AGENTS.md domain index: refreshed in place")
            elif _st == "unmarked":
                print("  AGENTS.md has no domain markers - add these two lines "
                      "where you want a live index:")
                print("    " + SECTION_BEGIN % "domains")
                print("    " + SECTION_END % "domains")
    except Exception:
        pass

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

<!-- agent-root:begin protocol -->
# Agent Root

> **Root reviews with receipts. It never repairs, and it never guesses.**

This file is an adapter. The contract is `AGENT-ROOT.md` - portable markdown that
any assistant can follow. Read it first, then `AGENTS.md` for this repo's facts.

`.claude/skills/` is a project-skill location for GitHub Copilot too, so this one
file answers `/agent-root` in Claude Code and in Copilot, and both load it
automatically when the description matches the task.

## Run this. It is the whole opening move.

```bash
python scripts/root.py                 # orient + review the working tree
python scripts/root.py --commit HEAD   # a commit
python scripts/root.py --pr 42         # a pull request (needs gh)
python scripts/root.py --brief         # orientation only
```

ONE command, not six. It calibrates the kernel, loads the trap weight table,
scopes the traps to what changed, checks whether the edited files are the running
ones, and re-tests the documented facts - each with a timeout, each reporting its
own failure.

⚠️ **Read what it says it could NOT do.** A step that times out or is missing
prints a line saying so, and the footer counts how many steps produced output.
A verdict must never claim what a step that did not run would have shown.

Your job is the verdict, not the gathering - and a verdict without a receipt is
not a verdict.
<!-- agent-root:end protocol -->

## This repo's own notes

⭐ Everything ABOVE the marker is generated and refreshes on
`python scripts/kernel.py upgrade`. Everything BELOW is yours and is never
touched. Put this repo's domains, its never-OK list, and anything an upgrade
must not overwrite down here.
'''

COPILOT = """Read `AGENTS.md` in the repository root before answering or editing,
and `AGENT-ROOT.md` for the review contract.

Before substantive work, run `python scripts/traps.py --for <changed files>` and
read the output. This repo records hard-won traps in situ; that command is how
they reach you, scoped to what you are touching.
"""

# WARNING: README.md IS NOT ON THIS LIST AND MUST NEVER BE. This list is shared
# IMPLEMENTATION - files that must be byte-identical in every repo. README.md is
# the opposite: it is repo IDENTITY, and the same filename means a different
# document in each one. An ad-hoc `for f in ...; do cp` sync that included it
# overwrote a repo's own 5-line README with this project's 312-line one. When
# syncing by hand, sync THIS list, not a filename you happen to have edited.
#
# WARNING: DO NOT HAND-SYNC AT ALL - run `kernel.py install --target <repo>`.
# This warning was written here after the first clobbering, and the clobbering
# happened again within the hour, because a marker inside a source file cannot
# intercept a shell loop someone is typing somewhere else. Tripwires are prompts,
# not interlocks. The only fix that worked was removing the loop: install already
# copies the right list and cannot touch README.md.
INSTALL_FILES = [
    "AGENT-ROOT.md", "USING-AGENT-ROOT.md",
    "scripts/traps.py", "scripts/tripwires.py", "scripts/kernel.py",
    "scripts/drift.py", "scripts/verify.py", "scripts/review.py",
    # ⚠️ guard.py IS A SAFETY REQUIREMENT ON THIS LIST, not a convenience. The
    # PreToolUse hook blocks on exit code 2 - and a Python interpreter that
    # cannot find its script ALSO exits 2. So a missing guard.py does not fail
    # open, it blocks every matching tool call in the repo. It cannot fail open
    # if it never runs. Measured: with guard.py absent, all eight test cases
    # "blocked", including the two designed to prove fail-open.
    "scripts/guard.py",
    "scripts/root.py",
    "profiles/devops.py",
]


SECTION_BEGIN = "<!-- agent-root:begin %s -->"
SECTION_END = "<!-- agent-root:end %s -->"


def write_section(path, name, body):
    """Refresh ONE marked region of a mostly-handwritten file. Three modes.

    ⭐ Borrowed deliberately: a file is either absent, marked, or unmarked, and
    each deserves a different answer.

        absent    -> nothing. This never creates a document out of nowhere.
        marked    -> replace ONLY between the markers. Prose outside is untouched.
        unmarked  -> write <path>.generated.md beside it and say so.

    ⚠️ THE UNMARKED CASE IS WHY THIS EXISTS. The previous behaviour was
    all-or-nothing: install refused to touch an existing file at all, so a repo
    that had customised AGENTS.md could never receive an improved generated
    table again - it was frozen at whatever it had on day one. Refusing wholesale
    is safe and useless; clobbering is useful and unsafe. Markers are the seam.
    """
    if not os.path.exists(path):
        return "absent"
    text = io.open(path, encoding="utf-8", errors="replace").read()
    b, e = SECTION_BEGIN % name, SECTION_END % name
    if b in text and e in text:
        head, rest = text.split(b, 1)
        _, tail = rest.split(e, 1)
        new = head + b + NL + body.rstrip(NL) + NL + e + tail
        if new == text:
            return "nochange"
        io.open(path, "w", encoding="utf-8", newline="").write(new)
        return "updated"
    # ⚠️ NO FILE IS WRITTEN HERE. An earlier version dropped a `.generated.md`
    # beside every unmarked file, and running `map` in a real repo produced an
    # unrequested document in the working tree - a tool asked to regenerate ONE
    # index inventing a second one. The offer is made in the output instead;
    # markers are opt-in, so the absence of markers is an answer, not a gap.
    return "unmarked"


# ⚠️ ABSOLUTE, VIA THE PROJECT-DIR VARIABLE - never a relative path. Hooks do
# not run with a guaranteed working directory, and `python scripts/guard.py`
# resolves to nothing from anywhere else. Because a Python interpreter that
# cannot find its script exits 2, and 2 is the BLOCK code, an unresolvable path
# does not fail open - it blocks every matching tool call in the repo.
#
# ⚠️ Windows caveat, upstream: hook commands run through cmd.exe, which expands
# %VAR% and not $VAR, so the variable may arrive literal. That is survivable ONLY
# because the guard is now wired exclusively in repos that have opted into at
# least one rule - a much smaller blast radius than every install.
GUARD_CMD = 'python "$CLAUDE_PROJECT_DIR/scripts/guard.py"'

CI_WORKFLOW = """# Agent Root: fail the build when the knowledge layer goes stale.
# ⭐ kernel.py check has always existed; nothing enforced it, so a stale contract
# was only ever caught by someone choosing to run it. A check with no CI behind
# it is advice.
name: agent-root
on: [push, pull_request]
jobs:
  kernel:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
        with:
          fetch-depth: 0          # review.py reads history for co-change priors
      - uses: actions/setup-python@v7
        with:
          python-version: '3.13'
      - name: kernel intact (caps, skill frontmatter, required files)
        run: python scripts/kernel.py check
      - name: tripwires and interlocks match the manifest
        run: python scripts/tripwires.py --check
      - name: documented facts still hold
        run: python scripts/verify.py --quick
"""


def cmd_fleet(paths):
    """One row per repo: is Root installed, and is its knowledge alive?

    ⚠️ Reports ABSENCE as loudly as trouble. A repo with no Root shows "-", never
    a blank that reads like a pass; and a repo whose traps are zero is called out
    rather than being scored well for having nothing to be wrong about.
    """
    rows = []
    for p in paths:
        p = os.path.abspath(p)
        if not os.path.isdir(os.path.join(p, ".git")):
            continue
        name = os.path.basename(p)
        has = os.path.exists(os.path.join(p, "scripts", "traps.py"))
        if not has:
            rows.append((name, "-", "-", "-", "no"))
            continue
        traps = whys = "?"
        try:
            r = subprocess.run([sys.executable, os.path.join(p, "scripts", "traps.py"),
                                "--json"], cwd=p, capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            d = json.loads(r.stdout or "{}")
            traps = str(d.get("counts", {}).get("trap", "?"))
            whys = str(len(d.get("blocks", [])))
        except Exception:
            pass
        chk = subprocess.run([sys.executable, os.path.join(p, "scripts", "kernel.py"),
                              "check"], cwd=p, capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
        state = "ok" if "kernel intact" in (chk.stdout or "") else "STALE"
        wired = "yes" if os.path.exists(
            os.path.join(p, ".claude", "skills", "agent-root", "SKILL.md")) else "no"
        rows.append((name, traps, whys, state, wired))

    if not rows:
        print("  no git repositories found in those paths.")
        return 1
    print("  %-22s %7s %7s %7s %6s" % ("repo", "traps", "blocks", "kernel", "wired"))
    print("  " + "-" * 54)
    for r in rows:
        print("  %-22s %7s %7s %7s %6s" % r)
    missing = [r[0] for r in rows if r[4] == "no"]
    print()
    if missing:
        print("  %d of %d repo(s) have no Agent Root: %s"
              % (len(missing), len(rows), ", ".join(missing[:6])))
        print("  install with: python scripts/kernel.py install --target <repo>")
    return 0


def wire_guard(target):
    """Register the PreToolUse interlock, MERGING into any existing settings.

    ⚠️ This file belongs to the user, not to us. It may already carry hooks,
    permissions and model settings that matter more than ours, so the whole
    document is read, one entry is added if absent, and everything else is
    written back untouched. Clobbering a settings file to install a guard would
    be a fine way to have the guard removed permanently within the hour.

    ⭐ Committed, not local. `.claude/settings.json` is shared with the team;
    `settings.local.json` is personal and gitignored. A rule protecting the repo
    belongs in the shared file, where it cannot be silently switched off.
    """
    # ⚠️ NO RULES, NO HOOK. Wiring an interlock into a repo that has declared
    # nothing to enforce is all risk and no benefit, and it went wrong exactly
    # that way: chester0 had ZERO rules, and the hook still blocked every Write,
    # Edit and Bash - because the command was the RELATIVE path
    # `python scripts/guard.py`, and from any other working directory the
    # interpreter cannot find it and exits 2, which is the block code.
    #
    # ⭐ The comment warning about this collision was written in this same file,
    # by the author, before the relative path was shipped anyway. A guard is now
    # only installed once a repo owns at least one `<!-- block: ... -->` trap.
    blocks = os.path.join(target, ".claude", "agent-root-blocks.json")
    has_rules = False
    if os.path.exists(blocks):
        try:
            has_rules = bool(json.loads(
                io.open(blocks, encoding="utf-8").read() or "{}").get("blocks"))
        except Exception:
            has_rules = False
    if not has_rules:
        return None                       # nothing to enforce; nothing wired

    p = os.path.join(target, ".claude", "settings.json")
    data = {}
    if os.path.exists(p):
        try:
            data = json.loads(io.open(p, encoding="utf-8").read() or "{}")
        except Exception:
            # ⚠️ Unreadable settings are left ALONE. Overwriting a file we could
            # not parse would destroy configuration we never saw.
            print("  .claude/settings.json is not valid JSON - guard not wired")
            print("  fix the file, then run: python scripts/kernel.py install")
            return False

    hooks = data.setdefault("hooks", {})
    pre = hooks.setdefault("PreToolUse", [])
    if any(GUARD_CMD in json.dumps(entry) for entry in pre):
        return True                                  # already wired, idempotent

    pre.append({
        "matcher": "Write|Edit|MultiEdit|NotebookEdit|Bash|PowerShell|Shell",
        "hooks": [{"type": "command", "command": GUARD_CMD}],
    })
    os.makedirs(os.path.dirname(p), exist_ok=True)
    io.open(p, "w", encoding="utf-8", newline=NL).write(
        json.dumps(data, indent=2, ensure_ascii=False) + NL)
    return True


STAMP_REL = os.path.join(".claude", "agent-root.json")


def read_stamp(repo):
    try:
        return json.loads(io.open(os.path.join(repo, STAMP_REL),
                                  encoding="utf-8").read() or "{}")
    except Exception:
        return {}


def write_stamp(repo, source):
    """Record the version and WHERE IT CAME FROM, so upgrade needs no arguments.

    ⭐ The source path is the whole point. Without it, upgrading means
    remembering where you cloned the kernel months ago - and a maintenance step
    that depends on recall is a maintenance step that does not happen.
    """
    d = {"version": VERSION, "source": os.path.abspath(source)}
    p = os.path.join(repo, STAMP_REL)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    io.open(p, "w", encoding="utf-8", newline=NL).write(
        json.dumps(d, indent=2) + NL)


DECISION_MARK = "<!-- agent-root:from %s -->"


def cmd_decisions(root):
    """Draft evidenced STUBS into DECISIONS.md. Never writes a reason.

    ⚠️ THE REPORTED PROBLEM: DECISIONS.md is empty after init. That is by design
    - inventing rationale is the failure this project exists to prevent - but
    "by design" was doing a lot of work. `archaeology` already finds the reverts
    and the commits whose messages say *because*, calls them "DECISIONS.md
    entries written in the wrong place", and then leaves the human to retype
    them. The queue existed and nothing carried it across.

    ⭐ The seam is what git states VERBATIM versus what only a person knows. The
    date, the subject and the files are facts and get filled in. Context, why
    not the alternative, and consequence stay BLANK and visibly so - a stub that
    guessed at those would be exactly the confident wrong summary that displaces
    the real answer forever.

    Idempotent: each stub carries its commit sha, and a sha already present is
    skipped, so this can be re-run after every archaeology pass.
    """
    if not is_git(root):
        print("  not a git repository - decisions are mined from history.")
        return 1

    path = os.path.join(root, "DECISIONS.md")
    if not os.path.exists(path):
        print("  no DECISIONS.md - run `kernel.py init` first.")
        return 1
    existing = io.open(path, encoding="utf-8", errors="replace").read()

    # ⚠️ Same two seams archaeology reports, and deliberately no others. A
    # broader net would drag in ordinary commits and bury the real entries.
    pat = re.compile(r"(?i)\b(because|instead of|workaround|turns out|revert)\b")
    log = git(root, "log", "--format=@@C@@%H%x1f%ad%x1f%s", "--date=short",
              "--name-only", "-n", "500")

    found, cur = [], None
    for line in log.splitlines():
        if line.startswith("@@C@@"):
            if cur:
                found.append(cur)
            sha, date, subj = (line[5:].split("\x1f") + ["", ""])[:3]
            cur = {"sha": sha, "date": date, "subj": subj, "files": []}
        elif line.strip() and cur:
            cur["files"].append(line.strip())
    if cur:
        found.append(cur)

    hits = [c for c in found if pat.search(c["subj"])]
    fresh = [c for c in hits if (DECISION_MARK % c["sha"][:7]) not in existing]

    print("  %d commit(s) state a reason; %d already drafted; %d new"
          % (len(hits), len(hits) - len(fresh), len(fresh)))
    if not fresh:
        print("  nothing to add.")
        return 0

    out = [""]
    for c in fresh:
        files = ", ".join(c["files"][:4]) or "(no files recorded)"
        if len(c["files"]) > 4:
            files += " and %d more" % (len(c["files"]) - 4)
        out += [
            "## %s — %s   %s" % (c["date"], c["subj"][:88],
                                 DECISION_MARK % c["sha"][:7]),
            "",
            "**Context.** _UNWRITTEN — only you know what was true at the time._",
            "",
            "**Decision.** %s" % c["subj"],
            "",
            "**Why not the alternative.** _UNWRITTEN — this is the field that is "
            "never recorded and always the one someone needs._",
            "",
            "**Consequence.** _UNWRITTEN._",
            "",
            "*Evidence: commit `%s`, touched %s*" % (c["sha"][:7], files),
            "",
        ]

    with io.open(path, "a", encoding="utf-8", newline=NL) as fh:
        fh.write(NL.join(out))

    print("  appended %d stub(s) to DECISIONS.md" % len(fresh))
    print("")
    print("  ⚠️ These are STUBS, not decisions. Every _UNWRITTEN_ field is a")
    print("  question only you can answer, and a stub left unfilled is worth")
    print("  less than no entry - it looks documented and is not.")
    return 0


def cmd_upgrade(repo):
    """Refresh an installed kernel in place. No arguments, no paths to remember.

    ⚠️ Reports what CHANGED, file by file. An upgrade that only prints "done"
    hides a no-op: you cannot tell an upgrade that worked from one that silently
    found nothing to do, and the second is what a broken source path looks like.
    """
    st = read_stamp(repo)
    src = st.get("source")
    if not src:
        print("  no install stamp at " + STAMP_REL)
        print("  this repo predates upgrade tracking - run the installer once:")
        print("    python <agent-root>/scripts/kernel.py install --target .")
        return 1
    if not os.path.exists(os.path.join(src, "scripts", "kernel.py")):
        print("  the kernel source is no longer at:")
        print("    " + src)
        print("  move it back, or re-run install from wherever it lives now.")
        return 1

    print("  installed %s   source %s" % (st.get("version", "?"), VERSION))

    changed, same = [], 0
    for rel in INSTALL_FILES:
        a, b = os.path.join(src, rel), os.path.join(repo, rel)
        if not os.path.exists(a):
            continue
        old = io.open(b, "rb").read() if os.path.exists(b) else None
        new = io.open(a, "rb").read()
        if old == new:
            same += 1
            continue
        os.makedirs(os.path.dirname(b), exist_ok=True)
        io.open(b, "wb").write(new)
        changed.append(("updated" if old is not None else "added", rel))

    for how, rel in changed:
        print("  %-8s %s" % (how, rel))
    print("  %d file(s) changed, %d already current" % (len(changed), same))

    # ⭐ The adapter is refreshed THROUGH ITS MARKER, never overwritten. That is
    # what makes upgrading safe on a repo whose skill was customised: the
    # generated protocol moves, the repo's own notes below it do not. Without
    # this, "never overwrite" meant improvements could never arrive at all -
    # safe and useless, the same trade already fixed for AGENTS.md.
    ad = os.path.join(repo, ".claude", "skills", "agent-root", "SKILL.md")
    if not os.path.exists(ad):
        os.makedirs(os.path.dirname(ad), exist_ok=True)
        io.open(ad, "w", encoding="utf-8", newline=NL).write(ADAPTER)
        print("  wrote .claude/skills/agent-root/SKILL.md")
    else:
        # ⚠️ THE ADAPTER IS READ FROM THE SOURCE FILE, NOT FROM THIS MODULE'S
        # ADAPTER CONSTANT. `upgrade` runs the repo's EXISTING kernel.py - the
        # old code - to install the new one, so every in-memory constant here is
        # one version behind by definition. Using ADAPTER meant the protocol
        # section could never actually change: the copy succeeded, the skill
        # stayed stale, and the output said "upgraded".
        try:
            src_text = io.open(os.path.join(src, "scripts", "kernel.py"),
                               encoding="utf-8").read()
            body = src_text.split(SECTION_BEGIN % "protocol", 1)[-1]
            body = body.split(SECTION_END % "protocol", 1)[0].strip(NL)
        except Exception:
            body = ADAPTER.split(SECTION_BEGIN % "protocol", 1)[-1]
            body = body.split(SECTION_END % "protocol", 1)[0].strip(NL)
        state = write_section(ad, "protocol", body)
        if state == "updated":
            print("  updated SKILL.md (protocol section; your notes untouched)")
        elif state == "unmarked":
            print("  SKILL.md has no protocol markers, so it was left alone.")
            print("  To receive future upgrades, wrap the generated part in:")
            print("    " + SECTION_BEGIN % "protocol")
            print("    " + SECTION_END % "protocol")

    write_stamp(repo, src)
    print("")
    print("  already up to date." if not changed
          else "  upgraded. Re-run: python scripts/tripwires.py")
    return 0


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

    # WARNING: NEVER overwrite an adapter that already exists. Re-running install
    # on a live repo replaced a hand-tuned SKILL.md - whose description listed
    # that repo's real domains, which is exactly what makes the skill auto-fire -
    # with the generic stub. An installer that silently discards local
    # customisation punishes the people who used it best.
    ad = os.path.join(target, ".claude", "skills", "agent-root", "SKILL.md")
    os.makedirs(os.path.dirname(ad), exist_ok=True)
    if os.path.exists(ad):
        print("  kept existing .claude/skills/agent-root/SKILL.md (not overwritten)")
    else:
        io.open(ad, "w", encoding="utf-8", newline=NL).write(ADAPTER)

    ci = os.path.join(target, ".github", "copilot-instructions.md")
    os.makedirs(os.path.dirname(ci), exist_ok=True)
    if not os.path.exists(ci):
        io.open(ci, "w", encoding="utf-8", newline=NL).write(COPILOT)
    # ONE skill directory, read by BOTH assistants - do not add a second copy.
    # `.claude/skills/` is a project-skill location for Copilot as well (alongside
    # `.github/skills` and `.agents/skills`), in the CLI, in VS Code and for the
    # cloud agent, where it both auto-loads on its description and answers
    # `/agent-root`. It is therefore the INTERSECTION with Claude Code, not a
    # Claude-only path.
    #
    # WARNING: a `.github/prompts/agent-root.prompt.md` was added here on the
    # belief that Copilot had no skills. It was never checked, and it was wrong -
    # a second copy of the same instructions, free to drift from the first, which
    # is the duplication this project exists to prevent. Assert nothing about
    # another tool's features without reading its documentation.
    write_stamp(target, root)
    wire_guard(target)
    wf = os.path.join(target, ".github", "workflows", "agent-root.yml")
    os.makedirs(os.path.dirname(wf), exist_ok=True)
    if not os.path.exists(wf):          # never clobber an existing workflow
        io.open(wf, "w", encoding="utf-8", newline=NL).write(CI_WORKFLOW)
    print("  wired: .claude/skills/agent-root/SKILL.md")
    print("         -> /agent-root in Claude Code AND GitHub Copilot")
    print("         .github/copilot-instructions.md  (Copilot, always on)")

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
    # ⚠️ Skill frontmatter is validated because BOTH assistants read this
    # directory and Copilot requires `name` to be lowercase-with-hyphens. An
    # invalid name is not an error anyone sees - the skill is simply never
    # offered, which looks identical to a skill that was never written. Checked
    # here so a rename cannot silently un-publish a tripwire.
    sk = os.path.join(root, ".claude", "skills")
    if os.path.isdir(sk):
        for d in sorted(os.listdir(sk)):
            f = os.path.join(sk, d, "SKILL.md")
            if not os.path.exists(f):
                continue
            head = io.open(f, encoding="utf-8", errors="replace").read(800)
            m = re.search(r"^name:\s*(.+)$", head, re.M)
            nm = m.group(1).strip() if m else ""
            if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", nm or ""):
                problems.append(
                    "skill %s: name %r must be lowercase-with-hyphens or Copilot "
                    "ignores it" % (d, nm))
            elif nm != d:
                problems.append(
                    "skill %s: name %r does not match its directory" % (d, nm))
            # WARNING: the class here excludes the newline on purpose. Written
            # with plain backslash-s it also matched a line break, so the check
            # walked past an EMPTY description onto the next line and could
            # never fail. Found only by deleting a description and watching the
            # check still pass - a test that cannot fail proves nothing.
            if not re.search(DESC_RE, head, re.M):
                problems.append("skill %s: no description - nothing can trigger it" % d)

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
                    choices=["install", "upgrade", "init", "map",
                             "archaeology", "decisions", "check", "fleet"])
    ap.add_argument("paths", nargs="*",
                    help="for `fleet`: the repos to survey")
    ap.add_argument("--target",
                    help="install Agent Root into this repo")
    ap.add_argument("--all", action="store_true",
                    help="map every text file, not just docs and entry points")
    args = ap.parse_args()
    root = repo_root()
    # ⚠️ `fleet` is about OTHER repos. Printing this repo's path above a table of
    # several was actively misleading - it read as a heading for the rows below.
    if args.command != "fleet":
        print(f"repo: {root}")
    if args.command == "decisions":
        return cmd_decisions(root)
    if args.command == "upgrade":
        return cmd_upgrade(os.path.abspath(args.target or root))
    if args.command == "fleet":
        return cmd_fleet(args.paths or [os.getcwd()])
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
