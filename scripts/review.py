#!/usr/bin/env python3
"""Assemble the evidence for a review. Agent Root judges; this gathers.

    python scripts/review.py                  # uncommitted working tree
    python scripts/review.py --commit HEAD    # one commit
    python scripts/review.py --range a..b     # a span
    python scripts/review.py --pr 42          # a pull request (needs `gh`)

WARNING: THIS SCRIPT HAS NO OPINIONS AND MUST NOT ACQUIRE ANY. It prints
receipts - what changed, which domains that touches, the traps already recorded
there, whether any touched file is running somewhere else, what history says
usually changes alongside, and whether the change wrote down what it learned.
The verdict is the agent's job.

The split matters. An evidence-gatherer that also judges is a tool you cannot
check, because you can no longer tell which part of its output came from a
command and which from a guess. Every line below traces to a command.

WARNING: read-only. Never posts, never comments, never approves. Publishing a
review is an outward-facing act and belongs to a human who has read it.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

# WARNING: EVERY subprocess call here passes encoding="utf-8". Reconfiguring this
# script's own stdout is not enough - captured output from a CHILD is decoded with
# the locale default, which on Windows is cp1252, and the markers came back as
# mojibake in the very report that prints them. Fixing your own stream does not
# fix the one you read from someone else.
HERE = os.path.dirname(os.path.abspath(__file__))
NL = chr(10)


def git(root, *args):
    try:
        return subprocess.run(["git", "-C", root, *args], capture_output=True,
                              text=True, encoding="utf-8", errors="replace").stdout
    except Exception:
        return ""


def root_dir():
    out = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True).stdout.strip()
    return out or os.getcwd()


def run_tool(root, name, *args):
    """Call a sibling tool. Missing tools degrade to a stated absence, never
    to a silent empty section - an empty result that reads as a pass is this
    project's signature failure."""
    p = os.path.join(HERE, name)
    if not os.path.exists(p):
        return None, name + " not installed"
    r = subprocess.run([sys.executable, p, *args], cwd=root,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout, None


def changed_files(root, args):
    """What is under review, and where the diff text comes from."""
    if args.pr:
        gh = subprocess.run(["gh", "pr", "view", args.pr, "--json",
                             "files,title,author,baseRefName,headRefName"],
                            cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if gh.returncode != 0:
            return [], "", "gh failed: " + (gh.stderr or "").strip()[:120]
        import json
        d = json.loads(gh.stdout or "{}")
        files = [f["path"] for f in d.get("files", [])]
        diff = subprocess.run(["gh", "pr", "diff", args.pr], cwd=root,
                              capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
        label = "PR #%s  %s  (%s -> %s)  by %s" % (
            args.pr, d.get("title", ""), d.get("headRefName", "?"),
            d.get("baseRefName", "?"), (d.get("author") or {}).get("login", "?"))
        return files, diff, label
    if args.commit:
        files = git(root, "show", "--name-only", "--format=", args.commit).split()
        diff = git(root, "show", args.commit)
        subj = git(root, "log", "-1", "--format=%s", args.commit).strip()
        return files, diff, "commit %s  %s" % (args.commit, subj)
    if args.range:
        files = git(root, "diff", "--name-only", args.range).split()
        return files, git(root, "diff", args.range), "range " + args.range
    files = git(root, "diff", "--name-only", "HEAD").split()
    # WARNING: -uall is load-bearing. Plain --porcelain collapses an untracked
    # directory to ".claude/", which broke two sections at once: those entries
    # resolved to no domain, and the bare prefix "scripts/" matched any line
    # mentioning any path under it - pulling an unrelated advice line into the
    # DRIFT report as though it were a finding.
    files += [l[3:] for l in git(root, "status", "--porcelain", "-uall").splitlines()
              if l.startswith("?? ")]
    return sorted(set(files)), git(root, "diff", "HEAD"), "working tree"


def coupling(root, files):
    """What history says usually changes alongside these files, and did not.

    WARNING: this is a BASE RATE, offered against the pull toward blaming the
    most recent edit. It is a prompt to check, never a finding on its own.
    """
    log = git(root, "log", "--format=@@C@@", "--name-only", "-n", "400")
    commits, cur = [], []
    for line in log.splitlines():
        if line.startswith("@@C@@"):
            if cur:
                commits.append(cur)
            cur = []
        elif line.strip():
            cur.append(line.strip())
    if cur:
        commits.append(cur)

    out = []
    for f in files:
        with_f = [c for c in commits if f in c]
        if len(with_f) < 4:
            continue
        partners = {}
        for c in with_f:
            for other in c:
                if other != f and len(c) <= 8:
                    partners[other] = partners.get(other, 0) + 1
        for other, n in sorted(partners.items(), key=lambda kv: -kv[1])[:2]:
            if n >= 3 and other not in files:
                out.append("%s usually changes with %s (%d of %d) - it did not"
                           % (f, other, n, len(with_f)))
    return out


def reverts(root, files):
    """Commits that were rolled back. A fix here has been wrong before."""
    out = []
    for f in files:
        log = git(root, "log", "--format=%h %s", "-n", "60", "--", f)
        for line in log.splitlines():
            if re.search(r"(?i)\brevert\b", line):
                out.append("%s : %s" % (f, line.strip()[:96]))
    return out[:6]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split(NL)[0])
    ap.add_argument("--commit")
    ap.add_argument("--range")
    ap.add_argument("--pr")
    args = ap.parse_args()
    root = root_dir()

    files, diff, label = changed_files(root, args)
    print("root@%s  --  %s" % (os.path.basename(root), label))
    print("=" * 68)

    if not files:
        print(NL + "  nothing to review (no changed files)")
        return 0

    print(NL + "CHANGED  (%d)" % len(files))
    for f in files[:40]:
        print("  " + f)
    if len(files) > 40:
        print("  ... and %d more" % (len(files) - 40))

    # --- domains + the traps already recorded there --------------------------
    print(NL + "DOMAINS TOUCHED / TRAPS ON FILE")
    out, err = run_tool(root, "traps.py", "--for", *files)
    if err:
        print("  " + err)
    else:
        head = [l for l in (out or "").splitlines() if l.startswith("# resolved")]
        print("  " + (head[0] if head else "no domains resolved"))
        traps = [l for l in (out or "").splitlines() if l.startswith("- L")]
        print("  %d trap/design lines recorded in those domains" % len(traps))
        for l in traps[:12]:
            print("    " + l[:150])
        if len(traps) > 12:
            print("    ... %d more - run: traps.py --for <files>" % (len(traps) - 12))

    # --- is the edited copy the running copy? --------------------------------
    print(NL + "DRIFT")
    out, err = run_tool(root, "drift.py")
    if err:
        print("  " + err)
    else:
        # match on the whole path, never a prefix - see the -uall note above
        fset = set(files)
        rows = [l for l in (out or "").splitlines()
                if (fset & set(l.split())) or "DRIFT" in l or "MISSING" in l]
        print("  " + (NL + "  ").join(rows[:8]) if rows else "  no touched file is a declared deployment")

    # --- priors, against the pull of recency ---------------------------------
    cp = coupling(root, files)
    rv = reverts(root, files)
    print(NL + "PRIORS  (base rates, not findings)")
    if cp:
        for c in cp[:6]:
            print("  coupling: " + c)
    if rv:
        for r in rv:
            print("  revert:   " + r)
    if not cp and not rv:
        print("  none on file")

    # --- did the change write down what it learned? --------------------------
    # keep in step with traps.WARN_MARKS - "WARN:" alone silently missed every
    # "WARNING:" in the tree, so the ledger under-counted its own change by 5.
    added_markers = len(re.findall(r"^\+.*(?:⚠|WARN(?:ING)?:)", diff or "", re.M))
    fixish = bool(re.search(r"(?i)\b(fix|bug|broke|regress|revert|incident)\b",
                            label + " " + (diff or "")[:4000]))
    print(NL + "LEDGER")
    print("  markers added by this change: %d" % added_markers)
    if fixish and added_markers == 0:
        print("  WARNING: this looks like a fix and records NO trap. In this")
        print("  house that fails review: the code fix stops it once, the marker")
        print("  stops it every time after.")

    print(NL + "=" * 68)
    print("Receipts only. The verdict is Agent Root's - see AGENT-ROOT.md section 6.")
    print("Nothing was posted, approved or changed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
