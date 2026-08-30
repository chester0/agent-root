#!/usr/bin/env python3
"""Compare what is IN the repo against what is actually RUNNING. Read-only.

    python scripts/drift.py            # check every declared deployment
    python scripts/drift.py --host web
    python scripts/drift.py --list     # what is declared to run where

## Why this exists

`AGENTS.md` states the rule - **the machine is the truth, the repo is the
intent** - but a rule nothing enforces is a rule that gets broken. This repo
contains code that RUNS ELSEWHERE - on an app server, a device, a cluster. Every
one of those has a deployed copy that can drift from the file you are editing.

⭐ Drift is the failure a code-only assistant cannot see. It reads the repo, gives
you a confident answer about behaviour, and is describing a file that is not the
one executing. In the repo this came from, that question - "is the deployed copy
the same as this one?" - was answered by hand with a SHA comparison, and the
answer mattered: it eliminated a whole hypothesis in one command.

⚠️ **READ-ONLY, DELIBERATELY.** This never deploys, restarts or repairs anything.
A sentinel that acts is a sentinel you stop trusting the first time it acts
wrongly on a live system - and these hosts can have physical consequences.
It reports; a human decides.

## The manifest is the payload

`DEPLOYMENTS` below is an EXAMPLE. In your repo it is different content
behind the same contract - and in a Terraform repo you would not write one at
all, because `terraform plan` IS this tool. The kernel ships the SLOT for drift
detection, not one implementation of it.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

# ---------------------------------------------------------------------------
# EXAMPLE MANIFEST - REPLACE ALL OF THIS.
#
# ⚠️ This is payload, not kernel. It describes YOUR hosts and YOUR deployments,
# so it is the one part of this file you must rewrite before it does anything
# useful - and the one part you must not commit to a public repo without
# thinking about what it reveals. A deployment manifest is a map of your
# infrastructure: usernames, addresses, ports, and where privileged code runs.
#
# The kernel is the CONTRACT (declare what runs where, hash both ends, report
# only). The contents are yours.
# ---------------------------------------------------------------------------
SSH_KEY = os.path.expanduser("~/.ssh/id_ed25519")
ADB = "adb"

HOSTS = {
    # name        transport   address                    what it is
    # ⚠️ hash_cmd BELONGS TO THE HOST, NOT THE TOOL. The first version hard-coded
    # a PowerShell Get-FileHash into the ssh branch - one repo's Windows box
    # baked into kernel logic - so the shipped Linux example could never have
    # worked against the host it described, and would have reported
    # "unreachable" rather than "no powershell", which is the exact mislabel the
    # comment further down warns about.
    "web":   {"kind": "ssh",   "addr": "deploy@web-01.example.internal",
              "hash_cmd": "sha256sum {path} 2>/dev/null || echo MISSING",
              "note": "application server (Linux)"},
    "winbox": {"kind": "ssh",  "addr": "deploy@win-01.example.internal",
               # WARNING: every literal brace in a hash_cmd must be DOUBLED - the
               # string goes through .format(path=...). This example shipped with
               # the if-branch doubled and the else-branch not, so it raised
               # KeyError and the broad except turned a config typo into
               # "unreachable", a reachability word for a programming error.
               # It was never caught because DEPLOYMENTS only targets the Linux
               # host, so this string had never once been through format().
               "hash_cmd": ("powershell -NoProfile -Command \"if (Test-Path '{path}') "
                            "{{ (Get-FileHash '{path}' -Algorithm SHA256).Hash }} "
                            "else {{ 'MISSING' }}\""),
               "note": "a Windows host needs its own hash command"},
    "local": {"kind": "local", "addr": "",
              "note": "this machine"},
}

# WARNING: EMPTY ON PURPOSE, and it must stay empty here.
# This list once shipped with two example rows. On a fresh install they ran as
# if they were real: a repo that had never declared a deployment got back
# "scripts/healthcheck.sh  web  no local file" - a phantom finding, generated
# entirely by sample data, in the section a reviewer trusts most.
# An unconfigured tool must report an ABSENCE, never a row that reads as a
# finding. Declare real deployments in scripts/kernel_config.py; the shape is:
#     DEPLOYMENTS = [("repo/path", "host", "/where/it/actually/runs")]
DEPLOYMENTS = []

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



def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:12]


def local_bytes(path: str) -> bytes | None:
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError:
        return None


def remote_bytes(host: str, path: str) -> tuple[bytes | None, str]:
    h = HOSTS[host]
    try:
        if h["kind"] == "ssh":
            cmd = h.get("hash_cmd", "sha256sum {path}").format(path=path)
            out = subprocess.run(
                ["ssh", "-i", SSH_KEY, "-o", "ConnectTimeout=8",
                 "-o", "StrictHostKeyChecking=accept-new", h["addr"], cmd],
                capture_output=True, text=True, timeout=45)
            v = (out.stdout or "").strip().split()[0] if out.stdout.strip() else ""
            if v and len(v) >= 12:
                return (None, v[:12].lower())
            # ⚠️ Distinguish these. An ssh that failed to connect, and a hash
            # command that is not installed on the remote, both return empty
            # stdout - and calling either "missing" asserts the file is absent
            # when the truth is we never looked. The stderr is the tell.
            err = (out.stderr or "").strip()
            low = err.lower()
            # ⚠️ ORDER MATTERS. "no such file" is a real finding - the deployed
            # copy is GONE, which is drift worth shouting about - while a missing
            # hash binary says nothing about the file at all. Collapsing them was
            # the second half of the same bug: both shipped hash commands error
            # on an absent file, so a deleted deployment read as "not evidence of
            # anything".
            if v == "MISSING" or "no such file" in low or "cannot find" in low:
                return (None, "missing")
            if "not found" in low or "not recognized" in low:
                return (None, "no hash cmd on host")
            return (None, "unreachable (ssh)")
        if h["kind"] == "adb":
            out = subprocess.run(
                [ADB, "-s", h["addr"], "shell",
                 f"su -c 'sha256sum {path} 2>/dev/null || echo MISSING'"],
                capture_output=True, text=True, timeout=45)
            v = out.stdout.strip().split()[0] if out.stdout.strip() else ""
            return (None, v[:12] if v and v != "MISSING" else "missing")
        return (local_bytes(path), "")
    except Exception as e:
        return (None, f"unreachable ({type(e).__name__})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", help="only this host")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    root = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                          capture_output=True, text=True).stdout.strip() or os.getcwd()

    if args.list:
        for hname, h in HOSTS.items():
            print(f"{hname:<9} {h['kind']:<6} {h['addr'] or '-':<24} {h['note']}")
        print()
        for repo_p, host, remote_p in DEPLOYMENTS:
            print(f"  {repo_p:<34} -> {host}:{remote_p}")
        return 0

    rows, drifted, unreachable = [], 0, 0
    for repo_p, host, remote_p in DEPLOYMENTS:
        if args.host and host != args.host:
            continue
        local = local_bytes(os.path.join(root, repo_p))
        if local is None:
            rows.append((repo_p, host, "no local file", "?", "?"))
            continue
        # SHA-256 of the local bytes, truncated the same way the remote is.
        lh_full = sha(local)
        _, rh = remote_bytes(host, remote_p)
        # ⚠️ EVERY STATE remote_bytes CAN RETURN MUST BE LISTED HERE. An audit
        # caught "no hash cmd on host" being returned and never read: it fell
        # through to the DRIFT branch, so a host merely lacking sha256sum tripped
        # the loudest alarm this tool has. A false DRIFT is worse than the
        # mislabel it replaced, because DRIFT is the thing people act on.
        UNKNOWN_STATES = ("unreachable", "missing", "no hash cmd")
        if any(rh.startswith(u) for u in UNKNOWN_STATES):
            state, note = "?", rh
            unreachable += 1
        elif rh == lh_full:
            state, note = "match", ""
        else:
            state, note = "DRIFT", f"remote {rh}"
            drifted += 1
        rows.append((repo_p, host, state, lh_full, note))

    w = max((len(r[0]) for r in rows), default=20)
    print(f"{'repo file':<{w}}  {'host':<8} {'state':<6} {'repo sha':<12} note")
    print("-" * (w + 44))
    for repo_p, host, state, lh, note in rows:
        print(f"{repo_p:<{w}}  {host:<8} {state:<6} {lh:<12} {note}")

    print()
    if drifted:
        print(f"⚠️  {drifted} file(s) DRIFTED - the running copy is not this one.")
        print("    Diff before editing, and decide which way the fix should travel.")
    gone = [r for r in rows if r[4] == "missing"]
    if gone:
        print(f"⚠️  {len(gone)} deployed file(s) MISSING on the host - that is drift,")
        print("    not an unknown: something that should be running is not there.")
    other = unreachable - len(gone)
    if other > 0:
        print(f"    {other} unreachable or unhashable - not evidence of anything;")
        print("    a host that is off looks identical to one that is broken.")
    if not DEPLOYMENTS:
        # WARNING: an empty set satisfies a universal claim, so "everything
        # matches" was printed by a repo that had declared NOTHING - a green
        # check produced by having done no work. Nothing checked is a distinct
        # answer from nothing wrong, and it must never wear the tick.
        print("—  no deployments declared, so nothing was checked.")
        print("    This is not a pass. Declare them in scripts/kernel_config.py:")
        print('        DEPLOYMENTS = [("repo/path", "host", "/where/it/runs")]')
        return 0
    if not drifted and not unreachable:
        print("✓  all %d declared deployment(s) match the repo." % len(DEPLOYMENTS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
