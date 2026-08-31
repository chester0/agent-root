#!/usr/bin/env python3
"""Mine merged PRs and closed issues for the WHY that git alone does not hold.

    python scripts/forge.py                # what the forge knows, as a report
    python scripts/forge.py --json         # same, for other tools
    python scripts/forge.py --limit 200    # look further back

WHY. `archaeology` mines local git, which records what changed and rarely why. A
pull request body is where somebody explained the choice; an issue thread is
where the incident that caused it was described while it was still fresh. Both
are part of the record, so reading them is retrieval - the same job as reading a
commit, one API call further out.

⭐ It quotes and cites. Every line it emits carries a PR or issue number and a
URL, because the whole contract is that an answer you cannot point at is one you
do not have. Nothing here summarises; it selects.

WARNING: read-only, and it never writes to the forge. It calls `gh` for reads
only - no comment, no label, no close. Publishing anything to a shared tracker is
an outward-facing act and belongs to a human.

⚠️ DEGRADES OUT LOUD. No `gh`, no auth, no remote, no PRs - each says so in one
line. A silent empty section here would read as "this repo has no recorded
decisions", which is a very different claim from "I could not look".
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

NL = chr(10)

# ⚠️ The same vocabulary archaeology uses on commit subjects. A PR that says
# "because" or "instead of" is explaining a decision; one that says "update deps"
# is not. Widening this drags in every routine PR and buries the real ones.
REASON = re.compile(
    r"(?i)\b(because|instead of|rather than|turns out|workaround|we chose|"
    r"decided to|the reason|root cause|regression|revert(?:ed|ing)?|"
    r"does not work|doesn't work|broke|broken)\b")

# An issue that was closed after a real diagnosis is an incident, and incidents
# are what earn traps.
INCIDENT = re.compile(
    r"(?i)\b(outage|incident|regression|data loss|corrupt|broke prod|"
    r"root cause|postmortem|post-mortem|hotfix|rollback)\b")


REPO = None            # set by --repo; None means "whatever repo we are inside"


def gh(args, timeout=60):
    """Run gh, returning (ok, parsed, note). Never raises, never hangs."""
    if REPO:
        args = list(args[:1]) + ["--repo", REPO] + list(args[1:])
    try:
        p = subprocess.run(["gh", *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
    except FileNotFoundError:
        return False, None, "gh is not installed - install it or skip this step"
    except subprocess.TimeoutExpired:
        return False, None, "gh timed out after %ss" % timeout
    except Exception as e:                                       # noqa: BLE001
        return False, None, "%s: %s" % (type(e).__name__, str(e)[:120])
    if p.returncode != 0:
        err = (p.stderr or "").strip().splitlines()
        return False, None, (err[0][:160] if err else "gh exited %d" % p.returncode)
    try:
        return True, json.loads(p.stdout or "[]"), ""
    except Exception:
        return False, None, "gh returned output that is not JSON"


# ⚠️ A PR TEMPLATE IS NOT AN EXPLANATION. The first version skipped blocks that
# START with an HTML comment, and a template whose comment CLOSED mid-block sailed
# through - so "If you are proposing a fix for a security issue, STOP" was
# reported as a PR's stated reason. Comments are stripped wholesale now.
COMMENT = re.compile(r"<!--.*?-->", re.S)

# ⚠️ BOTS EXPLAIN THEMSELVES AT LENGTH AND DECIDE NOTHING. A dependabot body
# matches half the reason vocabulary while carrying no human judgement, and a
# candidate list padded with dependency bumps is one nobody reads - the same
# dilution the tripwire cap exists to prevent.
BOT = re.compile(r"(?i)^(chore\(deps\)|build\(deps\)|bump |\[bot\]|"
                 r"dependabot|renovate)")
BOT_LOGIN = re.compile(r"(?i)(dependabot|renovate|\[bot\]$|-bot$)")


def first_para(text, n=280):
    """The opening of a body, which is where the explanation lives if anywhere."""
    text = COMMENT.sub("", text or "").replace("\r", "")
    for block in text.split(NL + NL):
        b = " ".join(block.split())
        if not b or b.startswith(("#", "-", "*", "|", ">", "[!")):
            continue
        return b[:n]
    return ""


def mine(limit):
    out = {"prs": [], "issues": [], "notes": []}

    ok, prs, note = gh(["pr", "list", "--state", "merged", "--limit", str(limit),
                        "--json", "number,title,body,url,mergedAt,files,author"])
    if not ok:
        out["notes"].append("pull requests: " + note)
    else:
        for p in prs or []:
            title = p.get("title", "") or ""
            login = ((p.get("author") or {}).get("login") or "")
            if BOT.search(title) or BOT_LOGIN.search(login):
                continue
            body = COMMENT.sub("", p.get("body", "") or "")
            blob = title + NL + body
            if not REASON.search(blob):
                continue
            out["prs"].append({
                "number": p.get("number"), "title": (p.get("title") or "")[:120],
                "url": p.get("url", ""), "date": (p.get("mergedAt") or "")[:10],
                "why": first_para(p.get("body")),
                "files": [f.get("path", "") for f in (p.get("files") or [])][:6],
            })

    ok, iss, note = gh(["issue", "list", "--state", "closed", "--limit", str(limit),
                        "--json", "number,title,body,url,closedAt,labels"])
    if not ok:
        out["notes"].append("issues: " + note)
    else:
        for i in iss or []:
            blob = (i.get("title", "") or "") + NL + (i.get("body", "") or "")
            labels = " ".join(l.get("name", "") for l in (i.get("labels") or []))
            if not (INCIDENT.search(blob) or re.search(r"(?i)bug|defect", labels)):
                continue
            out["issues"].append({
                "number": i.get("number"), "title": (i.get("title") or "")[:120],
                "url": i.get("url", ""), "date": (i.get("closedAt") or "")[:10],
                "why": first_para(i.get("body")),
                "labels": labels[:60],
            })
    return out


def render(data):
    L = []
    L.append("## Merged PRs that state a reason")
    L.append("")
    L.append("A PR body is where somebody explained the choice. These are "
             "`DECISIONS.md` entries that were written in the tracker.")
    L.append("")
    if data["prs"]:
        for p in data["prs"]:
            L.append("- **#%s** %s  *(%s)*" % (p["number"], p["title"], p["date"]))
            if p["why"]:
                L.append("  > %s" % p["why"])
            L.append("  %s" % p["url"])
    else:
        L.append("- *(none matched, or none could be read - see notes below)*")

    L.append("")
    L.append("## Closed issues that describe an incident")
    L.append("")
    L.append("An incident is what earns a trap. If one of these bit you and no "
             "`⚠️` marker exists where it bit, that is the gap.")
    L.append("")
    if data["issues"]:
        for i in data["issues"]:
            L.append("- **#%s** %s  *(%s)*" % (i["number"], i["title"], i["date"]))
            if i["why"]:
                L.append("  > %s" % i["why"])
            L.append("  %s" % i["url"])
    else:
        L.append("- *(none matched, or none could be read - see notes below)*")

    if data["notes"]:
        L.append("")
        L.append("⚠️ **Not everything could be read**, and that is not the same "
                 "as finding nothing:")
        for n in data["notes"]:
            L.append("- %s" % n)
    return NL.join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split(NL)[0])
    ap.add_argument("--limit", type=int, default=100,
                    help="how many PRs and issues to examine (default 100)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--repo", help="owner/name; default is the repo you are in")
    args = ap.parse_args()

    global REPO
    REPO = args.repo
    data = mine(args.limit)
    if args.json:
        json.dump(data, sys.stdout, indent=2, ensure_ascii=False)
        print()
        return 0
    print(render(data))
    print()
    print("%d PR(s) and %d issue(s) worth reading, from the last %d of each."
          % (len(data["prs"]), len(data["issues"]), args.limit))
    return 0


if __name__ == "__main__":
    sys.exit(main())
