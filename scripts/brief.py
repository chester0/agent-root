#!/usr/bin/env python3
"""What a senior engineer knows about a repo before reviewing anything in it.

    python scripts/brief.py                 # the dossier
    python scripts/brief.py --offline       # local evidence only, no gh
    python scripts/brief.py --limit 300     # look further back
    python scripts/brief.py --out BRIEF.md

WHY. `archaeology` produces a QUEUE - questions for a human. That is right for a
small repo and useless on a work repo with ten thousand commits, where the queue
is longer than anyone will ever read. What a reviewer actually needs first is
different in kind: how the thing builds and ships, what gates a merge, who knows
which corner, where it has broken before, and what reviewers keep having to say.

⭐ Six sections, and every one is DERIVED. Nothing here is a summary of what the
code "does" - that is the auto-summary this project refuses to write, because a
confident wrong one displaces the real answer permanently. These are facts with
a command or a citation behind each.

⚠️ THE MOST VALUABLE SECTION IS THE REVIEW COMMENTS. A PR review comment is the
one place a senior engineer writes down "don't do that, because" while it is
still specific. Git never records it, and it is invisible to every tool that
reads only code.

WARNING: read-only, and bounded. Work repos are large; every query is capped and
every section says what it sampled, because a dossier that silently truncates is
one that reads as complete.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import subprocess
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

NL = chr(10)
HERE = os.path.dirname(os.path.abspath(__file__))

# ⚠️ Build/test/ship is detected from FILES THAT EXIST, never guessed from the
# language. A repo with a Makefile and a package.json ships by whichever one CI
# calls, and only CI knows which.
STACK_FILES = [
    ("package.json", "node"), ("pnpm-lock.yaml", "node"), ("yarn.lock", "node"),
    ("composer.json", "php"), ("artisan", "laravel"),
    ("requirements.txt", "python"), ("pyproject.toml", "python"),
    ("go.mod", "go"), ("Cargo.toml", "rust"), ("pom.xml", "java"),
    ("build.gradle", "java"), ("Gemfile", "ruby"),
    ("Makefile", "make"), ("Justfile", "just"), ("Taskfile.yml", "task"),
    ("Dockerfile", "docker"), ("docker-compose.yml", "compose"),
    ("Chart.yaml", "helm"), ("main.tf", "terraform"), ("Pulumi.yaml", "pulumi"),
    ("serverless.yml", "serverless"), ("skaffold.yaml", "skaffold"),
]

DEPLOY_WORDS = re.compile(
    r"(?i)(deploy|release|publish|promote|rollout|ship|cd\b|production|prod\b)")


def sh(args, cwd, timeout=60):
    try:
        p = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        return p.returncode == 0, p.stdout, (p.stderr or "").strip()[:160]
    except FileNotFoundError:
        return False, "", args[0] + " is not installed"
    except subprocess.TimeoutExpired:
        return False, "", "timed out after %ss" % timeout
    except Exception as e:                                        # noqa: BLE001
        return False, "", "%s: %s" % (type(e).__name__, str(e)[:120])


def gh_json(args, cwd, timeout=90):
    ok, out, err = sh(["gh", *args], cwd, timeout)
    if not ok:
        return None, err
    try:
        return json.loads(out or "[]"), ""
    except Exception:
        return None, "gh returned output that is not JSON"


# --------------------------------------------------------------- how it ships
def how_it_ships(root):
    L, found = [], []
    for fn, kind in STACK_FILES:
        hits = sh(["git", "ls-files", "*" + fn], root)[1].split()
        if hits:
            found.append((kind, hits[0] if len(hits) == 1
                          else "%s (+%d more)" % (hits[0], len(hits) - 1)))
    if found:
        L.append("**Stack, by the files that exist:**")
        for kind, where in found[:14]:
            L.append("- `%s` — %s" % (kind, where))
    else:
        L.append("- *(no recognised build or packaging file found)*")

    # ⭐ The commands people actually run, read out of the manifests themselves
    pkg = os.path.join(root, "package.json")
    if os.path.exists(pkg):
        try:
            scripts = json.loads(io_read(pkg)).get("scripts", {})
            keep = {k: v for k, v in scripts.items()
                    if k in ("build", "test", "lint", "start", "dev", "deploy",
                             "typecheck", "e2e", "migrate")}
            if keep:
                L.append("")
                L.append("**npm scripts that matter:**")
                for k, v in keep.items():
                    L.append("- `npm run %s` → `%s`" % (k, v[:90]))
        except Exception:
            pass

    wf = os.path.join(root, ".github", "workflows")
    if os.path.isdir(wf):
        L.append("")
        L.append("**CI workflows** *(the ones matching deploy words are marked)*:")
        for fn in sorted(os.listdir(wf))[:14]:
            if not fn.endswith((".yml", ".yaml")):
                continue
            body = io_read(os.path.join(wf, fn))[:4000]
            on = re.search(r"(?m)^on:\s*(.+)$", body)
            trig = (on.group(1).strip()[:48] if on else "")
            mark = "  ⚠️ **deploys**" if DEPLOY_WORDS.search(fn + " " + body[:600]) else ""
            L.append("- `%s` %s%s" % (fn, ("— on: " + trig) if trig else "", mark))
    return L


def io_read(p):
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


# ------------------------------------------------------------ what gates merge
def merge_gates(root, offline):
    L = []
    for cand in ("CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS"):
        p = os.path.join(root, cand.replace("/", os.sep))
        if os.path.exists(p):
            rules = [l.strip() for l in io_read(p).splitlines()
                     if l.strip() and not l.startswith("#")]
            L.append("**CODEOWNERS** (`%s`) — %d rule(s). Touching these paths "
                     "pulls in a required reviewer:" % (cand, len(rules)))
            for r in rules[:10]:
                L.append("- `%s`" % r[:110])
            break
    if not L:
        L.append("- no CODEOWNERS file — review assignment is by convention, "
                 "not by rule")

    if offline:
        L.append("")
        L.append("⚠️ **Branch protection not read** (--offline). What actually "
                 "blocks a merge is therefore unknown, not absent.")
        return L

    data, err = gh_json(["api", "repos/{owner}/{repo}/rules/branches/main"], root)
    if data is None:
        data, err2 = gh_json(
            ["api", "repos/{owner}/{repo}/branches/main/protection"], root)
        err = err if data is None else ""
    if data:
        L.append("")
        L.append("**Required before merge to main:**")
        blob = json.dumps(data)
        for label, needle in (("required status checks", "required_status_checks"),
                              ("pull request reviews", "required_pull_request"),
                              ("linear history", "required_linear_history"),
                              ("signed commits", "required_signatures"),
                              ("conversation resolution", "required_conversation")):
            if needle in blob:
                L.append("- %s" % label)
        checks = re.findall(r'"context":\s*"([^"]{1,60})"', blob) or \
            re.findall(r'"required_status_checks".{0,400}?"contexts":\s*\[([^\]]*)\]',
                       blob)
        if checks:
            L.append("- contexts: " + ", ".join(str(c)[:40] for c in checks[:8]))
    else:
        L.append("")
        L.append("- branch protection could not be read: %s" % (err or "no data"))
        L.append("  *(that is 'unknown', not 'unprotected')*")
    return L


# ------------------------------------------------------------------- ownership
def ownership(root, limit):
    L = []
    ok, out, _ = sh(["git", "log", "--format=@@A@@%an", "--name-only",
                     "-n", str(limit)], root, timeout=120)
    if not ok:
        return ["- git log unavailable"]
    who, cur = collections.defaultdict(collections.Counter), None
    for line in out.splitlines():
        if line.startswith("@@A@@"):
            cur = line[5:].strip()
        elif line.strip() and cur:
            path = line.strip()
            # ⚠️ A top-level FILE is not an area. Splitting on "/" turned
            # go.mod into "go.mod/" and rendered it as a directory people own.
            if "/" not in path:
                continue
            who[path.split("/")[0]][cur] += 1
    rows = sorted(who.items(), key=lambda kv: -sum(kv[1].values()))[:12]
    if not rows:
        return ["- no authorship signal in the sampled history"]
    L.append("**Who has touched what** *(top-level path, last %d commits)*:" % limit)
    for area, counter in rows:
        names = ", ".join("%s (%d)" % (n, c) for n, c in counter.most_common(3))
        L.append("- `%s/` — %s" % (area, names))
    L.append("")
    L.append("⚠️ Frequency is not authority. This says who has *touched* it, "
             "which is where to ask, not who decides.")
    return L


# --------------------------------------------------------- what reviewers say
def review_themes(root, limit, offline):
    if offline:
        return ["⚠️ **Not read** (--offline). PR review comments are the one "
                "place 'don't do that, because' is written down; skipping them "
                "leaves the most reviewer-specific knowledge unread."]
    prs, err = gh_json(["pr", "list", "--state", "merged", "--limit", str(limit),
                        "--json", "number"], root)
    if prs is None:
        return ["- could not list pull requests: %s" % err]
    if not prs:
        return ["- no merged pull requests found"]

    # ⚠️ Sampled, and it says so. Fetching every comment on a busy repo is
    # thousands of calls; a dossier that quietly stops at 20 is worse than one
    # that names its own sample size.
    sample = [p["number"] for p in prs[:25]]
    bodies = []
    for n in sample:
        data, _ = gh_json(
            ["api", "repos/{owner}/{repo}/pulls/%d/comments?per_page=40" % n],
            root, timeout=45)
        for c in (data or []):
            b = " ".join((c.get("body") or "").split())
            if 40 < len(b) < 400:
                bodies.append((n, b, c.get("path", "")))

    if not bodies:
        return ["- no review comments in the %d most recent merged PRs "
                "(sampled)" % len(sample)]

    themes = re.compile(
        r"(?i)\b(should|instead|prefer|avoid|don't|do not|never|careful|"
        r"race|leak|N\+1|deadlock|timeout|retry|idempoten|migration|index|"
        r"secret|token|permission)\b")
    # ⚠️ Dedup on the TEXT. A bot posting the same requirement on four files
    # filled four slots with one sentence, and repetition is the signal here -
    # so it is counted and shown once, not shown four times.
    seen, picked = {}, []
    for n, b, p in bodies:
        if not themes.search(b):
            continue
        key = b[:120].lower()
        if key in seen:
            seen[key][0] += 1
            continue
        row = [1, n, b, p]
        seen[key] = row
        picked.append(row)
    L = ["**What reviewers actually keep saying** *(sampled %d PRs, %d comments, "
         "%d instructive)*:" % (len(sample), len(bodies), len(picked))]
    picked.sort(key=lambda r: -r[0])
    for cnt, n, b, p in picked[:12]:
        times = ("  **×%d** — said on %d files/PRs" % (cnt, cnt)) if cnt > 1 else ""
        L.append("- **#%s** %s%s" % (n, ("`%s` — " % p) if p else "", times))
        L.append("  > %s" % b[:260])
    if not picked:
        L.append("- none matched the instructive vocabulary")
    return L


def main():
    ap = argparse.ArgumentParser(description=__doc__.split(NL)[0])
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--out")
    args = ap.parse_args()

    ok, top, _ = sh(["git", "rev-parse", "--show-toplevel"], os.getcwd())
    root = top.strip() if ok and top.strip() else os.getcwd()

    L = ["# Reviewer's brief — %s" % os.path.basename(root), "",
         "Generated by `scripts/brief.py`. Every line is derived from the repo, "
         "its history or its forge — nothing here is a summary of what the code "
         "does, because a confident wrong one displaces the real answer.", ""]

    for title, rows in (
        ("## How it builds, tests and ships", how_it_ships(root)),
        ("## What gates a merge", merge_gates(root, args.offline)),
        ("## Who knows which corner", ownership(root, args.limit)),
        ("## What reviewers keep saying", review_themes(root, 60, args.offline)),
    ):
        L.append(title)
        L.append("")
        L += rows
        L.append("")

    text = NL.join(L)
    if args.out:
        with open(os.path.join(root, args.out), "w", encoding="utf-8",
                  newline=NL) as fh:
            fh.write(text + NL)
        print("  wrote " + args.out)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
