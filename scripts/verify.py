#!/usr/bin/env python3
"""Re-check the facts this repo asserts. Read-only. Reports; never repairs.

    python scripts/verify.py             # everything
    python scripts/verify.py --quick     # skip anything that touches the network
    python scripts/verify.py --stale 90  # also flag docs older than N days

## Why

Every fact here was true WHEN WRITTEN. Hosts move, ports change, files get
renamed, services are retired. A knowledge layer that is never re-checked does
not decay into useless - it decays into **confidently wrong**, which is worse
than empty, because it is trusted and acted on.

⭐ The organising idea is that facts differ by WHO CAN CHECK THEM:

    machine-checkable   a host answering, a file existing, a link resolving,
                        a deployed hash matching  -> verified here, in seconds
    human-only          whether a decision is still right, whether a plan is
                        still wanted            -> only ever FLAGGED, never judged

Conflating the two produces either noise or false confidence. This tool does the
first kind exhaustively and hands you a short list of the second.

⚠️ **It never edits anything.** A verifier that repairs is one you stop reading
the day it repairs something wrongly - and its whole value is being believed.

⚠️ **An unreachable host is not a failed fact.** A machine that is off looks
exactly like one that has moved. Those are reported separately, and neither is
called a failure.
"""
from __future__ import annotations

import argparse
import os
import re
import socket
import subprocess
import sys
import time

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

OK, BAD, UNKNOWN = "ok", "STALE", "?"

# ---------------------------------------------------------------------------
# EXAMPLE CONFIGURATION - REPLACE THESE FOUR.
#
# ⚠️ This is payload, not kernel. An audit caught this file shipping another
# repo's directory names and port map baked into its logic, after its siblings
# had already had exactly that surgery - the same mistake, in the file that was
# written after the review. Hoisting them here is what stops it happening a
# third time: payload that lives in named constants at the top is payload
# somebody notices.
# ---------------------------------------------------------------------------

# Ports worth probing when a doc asserts a host. Yours will differ.
PORTS = (22, 80, 443, 3000, 5432, 8080)

# Some notes legitimately write paths from a level ABOVE the repo root
# ("myrepo/scripts/x.py"). Set this to your repo's directory name to strip it,
# or None to disable.
REPO_PREFIX = None

# Sibling repositories referenced from these docs. A path into one of them is a
# fact this tool cannot check, so it is skipped rather than reported as broken.
SIBLING_REPOS = ()

# Subdirectories whose docs are worth staleness-checking. Empty = root only.
STALE_SCOPE = ()

# Directories of notes the agent itself writes, scanned for stale references.
# Another layout assumption that was hardcoded until an audit found the pattern.
NOTE_DIRS = ("memory", "notes", "docs/decisions")


# ---------------------------------------------------------------------------
# ⭐ ONE IMPLEMENTATION, MANY REPOS. If `scripts/kernel_config.py` exists beside
# this file, any constant it defines overrides the EXAMPLE values above.
#
# This exists because the alternative was caught happening: two copies of these
# scripts, one with a fix and one without, drifting 50-plus lines apart - the
# exact duplication-divergence failure this project tells you to design out.
# Code is identical everywhere; only configuration differs, and configuration
# lives in a file that is obviously configuration.
# ---------------------------------------------------------------------------
try:
    import kernel_config as _cfg                      # noqa: E402
except Exception:
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import kernel_config as _cfg                  # noqa: E402
    except Exception:
        _cfg = None
if _cfg is not None:
    for _k in dir(_cfg):
        if _k.isupper():
            globals()[_k] = getattr(_cfg, _k)



def root() -> str:
    out = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True).stdout.strip()
    return out or os.getcwd()


def read(p: str) -> str:
    try:
        with open(p, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


# ---------------------------------------------------------------- hosts
def check_hosts(r: str) -> list[tuple]:
    """Every IP asserted in AGENTS.md should still answer on a port we claim."""
    text = read(os.path.join(r, "AGENTS.md"))
    rows = []
    # `**Name** `1.2.3.4`` in the machine table, plus any bare tailnet address
    for m in re.finditer(r"\*\*([A-Za-z0-9 ]+)\*\*\s*`((?:\d{1,3}\.){3}\d{1,3})`", text):
        name, ip = m.group(1).strip(), m.group(2)
        alive = []
        for p in PORTS:
            s = socket.socket()
            s.settimeout(0.6)
            try:
                if s.connect_ex((ip, p)) == 0:
                    alive.append(p)
            except OSError:
                pass
            finally:
                s.close()
        if alive:
            rows.append((OK, f"{name} {ip}", f"answers on {', '.join(map(str, alive))}"))
        else:
            rows.append((UNKNOWN, f"{name} {ip}",
                         "no answer - off, or moved. Not a failed fact on its own"))
    return rows


# ---------------------------------------------------------------- paths
def check_paths(r: str) -> list[tuple]:
    """Repo paths named in always-loaded files should still exist.

    ⚠️ PRECISION OVER RECALL, DELIBERATELY. The first version flagged 46 things
    of which roughly eight were real, and a verifier that cries wolf is worse
    than none - the noise buries the findings that matter and the tool stops
    being read. So a candidate is only reported when it is unambiguously a path
    into THIS repo:

      - it must contain a "/" - a bare `server.ps1` in prose is a name, not a
        reference, and there are dozens of those
      - a leading REPO_PREFIX is stripped: notes legitimately write paths from
        the workspace root, and that is correct, not broken
      - it is resolved relative to the referring file first, then the repo root
      - references to a repo listed in SIBLING_REPOS are skipped - pointing at
        a neighbouring repository is a fact this tool cannot check
    """
    sources = ["AGENTS.md", "CLAUDE.md", ".github/copilot-instructions.md"]
    for base in (".claude/skills", ".github/instructions"):
        d = os.path.join(r, base)
        for dirpath, _dn, fn in os.walk(d):
            sources += [os.path.relpath(os.path.join(dirpath, f), r)
                        for f in fn if f.endswith(".md")]
    for nd in NOTE_DIRS:
        mem = os.path.join(r, nd)
        if os.path.isdir(mem):
            sources += [os.path.relpath(os.path.join(mem, f), r)
                        for f in os.listdir(mem) if f.endswith(".md")]

    seen, rows = set(), []
    for src in sources:
        text = read(os.path.join(r, src))
        if not text:
            continue
        for m in re.finditer(r"`([A-Za-z0-9_./-]+\.(?:md|py|ps1|sh|yaml|yml|html|json))`", text):
            cand = m.group(1)
            if "/" not in cand:
                continue                      # a name in prose, not a path
            if cand.startswith(("http", "/")):
                continue
            low = cand.lower()
            if SIBLING_REPOS and any(s in low for s in SIBLING_REPOS):
                continue                      # another repo - not ours to verify
            probe = cand
            if REPO_PREFIX and low.startswith(REPO_PREFIX.lower() + "/"):
                probe = cand[len(REPO_PREFIX) + 1:]
            key = (src, probe)
            if key in seen:
                continue
            seen.add(key)
            here = os.path.normpath(os.path.join(
                os.path.dirname(os.path.join(r, src)), probe))
            if os.path.exists(here) or os.path.exists(os.path.join(r, probe)):
                continue
            hits = subprocess.run(
                ["git", "-C", r, "ls-files", "*" + os.path.basename(probe)],
                capture_output=True, text=True).stdout.split()
            if hits:
                rows.append((BAD, probe, f"moved to {hits[0]} (said by {src})"))
            else:
                rows.append((BAD, probe, f"does not exist (said by {src})"))
    return rows


# ---------------------------------------------------------------- claims
# A claim carries its own proof, written beside it:
#
#     The API listens on **port 8080**, not 3000.  <!-- verify: port 192.0.2.10 8080 -->
#
# (192.0.2.0/24 is TEST-NET-1, reserved for documentation - never a real host.)
#
# ⚠️ A RESTRICTED PREDICATE LANGUAGE, NEVER SHELL. Running arbitrary commands
# embedded in markdown would make every document an execution vector - anyone who
# can edit a doc could then run anything. These eight predicates cover almost
# every factual assertion in this repo and none of them can do harm.
#
# ⭐ The proof lives NEXT TO the claim for the same reason traps live in the file
# they concern: separated, they drift, and the stale half is the one that gets
# believed.
PREDICATES = """
  port <host> <port>        something answers there
  noport <host> <port>      nothing answers there  (proves "not 8123")
  file <path>               exists
  nofile <path>             does not exist
  tracked <path>            is committed to git
  gitignored <path>         git refuses to track it  (proves a secret is safe)
  contains <path> <text>    file contains that text
  absent <path> <text>      file does NOT contain it
"""


def _tcp(host: str, port: int, timeout: float = 1.2) -> bool:
    s = socket.socket()
    s.settimeout(timeout)
    try:
        return s.connect_ex((host, int(port))) == 0
    except OSError:
        return False
    finally:
        s.close()


def check_claims(r: str, quick: bool) -> list[tuple]:
    files = subprocess.run(["git", "-C", r, "ls-files", "*.md"],
                           capture_output=True, text=True).stdout.split()
    rows = []
    for f in files:
        if f.startswith("archive/"):
            continue
        for ln, line in enumerate(read(os.path.join(r, f)).splitlines(), 1):
            m = re.search(r"<!--\s*verify:\s*(.+?)\s*-->", line)
            if not m:
                continue
            parts = m.group(1).split()
            if not parts:
                continue
            op, args = parts[0], parts[1:]
            where = f"{f}:{ln}"
            try:
                if op in ("port", "noport"):
                    if quick:
                        rows.append((UNKNOWN, where, f"{op} skipped (--quick)"))
                        continue
                    up = _tcp(args[0], args[1])
                    good = up if op == "port" else not up
                    rows.append((OK if good else BAD, where,
                                 f"{args[0]}:{args[1]} " +
                                 ("answers" if up else "silent") +
                                 ("" if good else f" - the doc claims {op}")))
                elif op in ("file", "nofile"):
                    ex = os.path.exists(os.path.join(r, args[0]))
                    good = ex if op == "file" else not ex
                    rows.append((OK if good else BAD, where,
                                 f"{args[0]} " + ("exists" if ex else "missing")))
                elif op == "tracked":
                    out = subprocess.run(["git", "-C", r, "ls-files", "--error-unmatch", args[0]],
                                         capture_output=True, text=True)
                    rows.append((OK if out.returncode == 0 else BAD, where,
                                 f"{args[0]} " + ("is tracked" if out.returncode == 0
                                                  else "is NOT tracked")))
                elif op == "gitignored":
                    out = subprocess.run(["git", "-C", r, "check-ignore", args[0]],
                                         capture_output=True, text=True)
                    rows.append((OK if out.returncode == 0 else BAD, where,
                                 f"{args[0]} " + ("is ignored" if out.returncode == 0
                                                  else "is NOT ignored - a secret may be committable")))
                elif op in ("contains", "absent"):
                    body_text = read(os.path.join(r, args[0]))
                    needle = " ".join(args[1:])
                    has = needle in body_text
                    good = has if op == "contains" else not has
                    rows.append((OK if good else BAD, where,
                                 f"{args[0]} "
                                 + ("contains" if has else "lacks")
                                 + f" '{needle[:40]}'"))
                else:
                    rows.append((BAD, where, f"unknown predicate '{op}'"))
            except Exception as e:
                rows.append((UNKNOWN, where, f"{op} could not run: {type(e).__name__}"))
    return rows


# ---------------------------------------------------------------- links
def check_links(r: str) -> list[tuple]:
    """Markdown links between live docs. Archive and history are exempt."""
    files = subprocess.run(["git", "-C", r, "ls-files", "*.md"],
                           capture_output=True, text=True).stdout.split()
    rows = []
    for f in files:
        if f.startswith("archive/") or f == "JOURNAL.md":
            continue          # history is allowed to point at retired things
        text = read(os.path.join(r, f))
        for m in re.finditer(r"\[[^\]]*\]\(([^)#]+\.md)\)", text):
            tgt = m.group(1)
            if tgt.startswith(("http", "mailto")):
                continue
            resolved = os.path.normpath(os.path.join(os.path.dirname(os.path.join(r, f)), tgt))
            if not os.path.exists(resolved):
                rows.append((BAD, tgt, f"broken link in {f}"))
    return rows


# ---------------------------------------------------------------- tools
def check_tools(r: str) -> list[tuple]:
    """The commands the docs tell you to run should actually run."""
    rows = []
    for script in ("scripts/traps.py", "scripts/kernel.py",
                   "scripts/tripwires.py", "scripts/drift.py"):
        p = os.path.join(r, script)
        if not os.path.exists(p):
            rows.append((BAD, script, "referenced by the kernel but missing"))
            continue
        try:
            out = subprocess.run([sys.executable, p, "--help"],
                                 capture_output=True, text=True, timeout=30)
            rows.append((OK if out.returncode == 0 else BAD, script,
                         "runs" if out.returncode == 0 else "--help failed"))
        except Exception as e:
            rows.append((BAD, script, f"will not run: {type(e).__name__}"))
    return rows


# ---------------------------------------------------------------- staleness
def check_stale(r: str, days: int) -> list[tuple]:
    """⚠️ FLAGGED, never judged. Age is a prompt for a human, not a verdict.

    A doc untouched for a year may be finished and correct. Only a person knows.
    """
    files = subprocess.run(["git", "-C", r, "ls-files", "PLAN-*.md", "*.md"],
                           capture_output=True, text=True).stdout.split()
    cutoff = time.time() - days * 86400
    rows = []
    for f in sorted(set(files)):
        if f.startswith("archive/"):
            continue
        if "/" in f and not (STALE_SCOPE and f.startswith(STALE_SCOPE)):
            continue
        text = read(os.path.join(r, f))[:1500]
        # only docs that CLAIM to be current are worth flagging
        if not re.search(r"(?i)\b(status|current|live|in progress|ongoing|WIP)\b", text):
            continue
        d = subprocess.run(["git", "-C", r, "log", "-1", "--format=%ct", "--", f],
                           capture_output=True, text=True).stdout.strip()
        if d and float(d) < cutoff:
            age = int((time.time() - float(d)) / 86400)
            rows.append((UNKNOWN, f, f"claims current, untouched {age} days"))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="skip network checks")
    ap.add_argument("--stale", type=int, default=0,
                    help="also flag docs claiming 'current' older than N days")
    args = ap.parse_args()
    r = root()
    print(f"repo: {r}\n")

    groups = [("claims that carry their own proof", check_claims(r, args.quick)),
              ("paths named in always-loaded files", check_paths(r)),
              ("links between live docs", check_links(r)),
              ("tools the docs tell you to run", check_tools(r))]
    if not args.quick:
        groups.insert(0, ("hosts asserted in AGENTS.md", check_hosts(r)))
    if args.stale:
        groups.append((f"docs claiming 'current' but untouched >{args.stale}d",
                       check_stale(r, args.stale)))

    bad = unknown = 0
    for title, rows in groups:
        print(f"== {title}")
        if not rows:
            print("   nothing to check\n")
            continue
        for state, what, note in rows:
            if state == OK:
                continue                      # silence is the healthy signal
            mark = "⚠️ " if state == BAD else "?  "
            print(f"   {mark}{what}\n       {note}")
            bad += state == BAD
            unknown += state == UNKNOWN
        oks = sum(1 for s, _, _ in rows if s == OK)
        print(f"   ({oks} verified)\n")

    print("-" * 60)
    if bad:
        print(f"⚠️  {bad} asserted fact(s) NO LONGER HOLD. Fix the file that says it.")
    if unknown:
        print(f"?   {unknown} could not be settled here - a human decides.")
    if not bad and not unknown:
        print("✓  every machine-checkable fact still holds.")
    print("\nNothing was modified. Repairing is a human's call.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
