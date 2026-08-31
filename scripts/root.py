#!/usr/bin/env python3
"""The whole opening move, as ONE command. `/agent-root` runs this and reads it.

    python scripts/root.py                 # orient + review the working tree
    python scripts/root.py --commit HEAD   # a commit
    python scripts/root.py --pr 42         # a pull request
    python scripts/root.py --brief         # orientation only, no diff

WHY ONE COMMAND. The skill used to list six commands and trust the agent to run
them in order. That is the same weakness as a tripwire being a prompt: it depends
on the agent's discipline, and a skipped step produces a review that LOOKS
complete. An agent that runs four of six steps and answers confidently is
indistinguishable, in its output, from one that ran all six.

So the sequence lives here, in code, where it cannot be partially executed and
then summarised as if it had been.

Three properties this buys, none of which the six-command version had:

  1. NOTHING HANGS. Every step has a timeout. `drift.py` reaches real hosts over
     SSH and adb, and a sleeping laptop used to mean the whole opening move sat
     there with nothing on screen. A step that times out is REPORTED as timed
     out, which is a finding - not silence.
  2. ABSENCE IS STATED. A tool that is missing, fails, or times out prints a line
     saying so. An empty section that reads as a pass is this project's signature
     failure and it is not available here.
  3. ONE RECEIPT. Every section names the command that produced it, so a human
     can re-run any single line and get the same answer.

WARNING: read-only, like everything else Root runs. It calls other scripts, none
of which write to the repo, and it posts nothing anywhere.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
NL = chr(10)
RULE = "=" * 72

# ⚠️ PER-STEP TIMEOUTS, AND drift's IS THE GENEROUS ONE ON PURPOSE. It contacts
# real machines; the others are local and should be near-instant. A step that
# needs longer than this is telling you something either way.
TIMEOUTS = {"check": 30, "domains": 60, "scoped": 60, "drift": 45, "verify": 60}


def run(args, timeout, cwd):
    """Return (ok, text, note). Never raises, never hangs, never lies about why."""
    try:
        p = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        out = (p.stdout or "").rstrip()
        if p.returncode != 0 and not out:
            return False, "", "exited %d: %s" % (
                p.returncode, (p.stderr or "").strip()[:160])
        return True, out, ""
    except subprocess.TimeoutExpired:
        return False, "", ("TIMED OUT after %ss - that is a finding, not a "
                           "detail: something it contacts is not answering"
                           % timeout)
    except FileNotFoundError:
        return False, "", "not installed"
    except Exception as e:                                       # noqa: BLE001
        return False, "", "%s: %s" % (type(e).__name__, str(e)[:120])


def tool(name, *args, timeout=60, cwd=None):
    p = os.path.join(HERE, name)
    if not os.path.exists(p):
        return False, "", name + " not installed"
    return run([sys.executable, p, *args], timeout, cwd)


def git(cwd, *args):
    ok, out, _ = run(["git", *args], 30, cwd)
    return out if ok else ""


def section(title, cmd, ok, body, note, limit=14):
    print(NL + title)
    print("  $ " + cmd)
    if not ok:
        # ⭐ The failure IS the content. Printing a blank section here is how a
        # review comes back clean because nothing ran.
        print("  -- " + (note or "no output"))
        return
    lines = [l for l in body.splitlines() if l.strip()]
    if not lines:
        print("  -- produced no output (that is an answer, not a pass)")
        return
    for l in lines[:limit]:
        print("  " + l[:160])
    if len(lines) > limit:
        print("  ... %d more line(s)" % (len(lines) - limit))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split(NL)[0])
    ap.add_argument("--commit")
    ap.add_argument("--range")
    ap.add_argument("--pr")
    ap.add_argument("--brief", action="store_true",
                    help="orientation only - skip the diff review")
    args = ap.parse_args()

    root = git(os.getcwd(), "rev-parse", "--show-toplevel").strip() or os.getcwd()
    name = os.path.basename(root)

    print(RULE)
    print("AGENT ROOT  --  %s" % name)
    print("Root reviews with receipts. It never repairs, and it never guesses.")
    print(RULE)

    steps = []

    ok, out, note = tool("kernel.py", "check",
                         timeout=TIMEOUTS["check"], cwd=root)
    steps.append(ok)
    section("CALIBRATE  (is the kernel itself sound?)",
            "python scripts/kernel.py check", ok, out, note, limit=8)

    ok, out, note = tool("traps.py", "--domains",
                         timeout=TIMEOUTS["domains"], cwd=root)
    steps.append(ok)
    section("WHERE THE SURPRISES LIVE  (base rates, not findings)",
            "python scripts/traps.py --domains", ok, out, note, limit=16)

    if not args.brief:
        rargs = ["review.py"]
        for flag, val in (("--commit", args.commit), ("--range", args.range),
                          ("--pr", args.pr)):
            if val:
                rargs += [flag, val]
        ok, out, note = tool(*rargs, timeout=TIMEOUTS["scoped"], cwd=root)
        steps.append(ok)
        section("UNDER REVIEW  (changed files, their traps, drift, priors, ledger)",
                "python " + " ".join(["scripts/" + rargs[0]] + rargs[1:]),
                ok, out, note, limit=60)

    ok, out, note = tool("drift.py", timeout=TIMEOUTS["drift"], cwd=root)
    steps.append(ok)
    section("IS THE EDITED COPY THE RUNNING COPY?",
            "python scripts/drift.py", ok, out, note, limit=14)

    ok, out, note = tool("verify.py", "--quick",
                         timeout=TIMEOUTS["verify"], cwd=root)
    steps.append(ok)
    section("DO THE DOCUMENTED FACTS STILL HOLD?",
            "python scripts/verify.py --quick", ok, out, note, limit=12)

    done = sum(1 for s in steps if s)
    print(NL + RULE)
    print("%d of %d steps produced output." % (done, len(steps)))
    if done < len(steps):
        # ⚠️ Say it at the END too. A failure noted only beside its own section
        # is easy to scroll past, and the verdict that follows would be built on
        # a gap nobody registered.
        print("⚠️  A step above did not run. Any verdict must say so, and must "
              "not claim what that step would have shown.")
    print("Receipts only - the verdict is the agent's, per AGENT-ROOT.md §6.")
    print("Nothing was modified, approved or posted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
