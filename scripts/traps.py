#!/usr/bin/env python3
"""Extract this repo's accumulated traps into something an agent can actually load.

⭐ WHY THIS EXISTS, AND WHY IT IS THE FIRST THING BUILT

The problem in this repo has never been missing knowledge. There are already
hundreds of hard-won lessons written down, under a consistent convention nobody
designed as one:

⚠️ Run `--domains` for the live count. It is deliberately not repeated in prose
anywhere: an audit caught this figure drifting across three files at once, in a
project whose whole claim is "measured, not claimed".

    (warning sign)  a trap - something that bit, and will bite again
    (star)          the load-bearing insight - why it is built this way

The failure is RETRIEVAL. In the repo this was extracted from, an assistant
re-derived traps already written in the very files it was editing, and broke a
rule stated in capitals in a handoff document three directories away - twice, on
a live system with physical consequences. The rule was correct, current, and
never read.

So this does not accumulate knowledge. It makes the existing knowledge cheap
enough to read BEFORE acting, which is the only moment it is worth anything.

## Cost, honestly

The full corpus is far too large to sit in a context window, which is exactly why
loading "everything" was never the answer. Scoped to one domain it is small:
one domain is a few dozen lines. That asymmetry is the whole design.

## Usage

    python scripts/traps.py database       # traps for one domain
    python scripts/traps.py --file src/queue.py
    python scripts/traps.py --domains      # what domains exist, and their weight
    python scripts/traps.py --all --out TRAPS.md

Domains are directories, plus a `root` bucket for top-level docs. A domain can
also be given as any path prefix, so `docs/runbooks` works.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

# ⚠️ THE MARKERS ARE CONFIGURABLE, AND THAT IS NOT DECORATION.
# The emoji form is what this convention grew up as, but plenty of shops lint
# emoji out of source entirely - one of this author's own repos carries the rule
# "No emoji in code (Windows cp1252)". The guidance is to adopt whatever
# convention a repo already uses; the tool must be able to practise that.
#
# So both forms are recognised, and the ASCII aliases are first-class:
#
#     ⚠️  or  WARN:      a trap - something that bit, and will bite again
#     ⭐  or  WHY:       the load-bearing insight
#
# Override with TRAPS_WARN / TRAPS_STAR in the environment to match a house style.
WARN_MARKS = tuple(filter(None, (os.environ.get("TRAPS_WARN"), "⚠", "WARN:")))
STAR_MARKS = tuple(filter(None, (os.environ.get("TRAPS_STAR"), "⭐", "WHY:")))

# Text files worth scanning. Binaries and generated output are pointless here and
# would drown the signal.
# ⚠️ THIS LIST IS THE TOOL'S EYESIGHT, AND IT WAS BLIND TO ITS OWN FLAGSHIP
# PROFILE. It used to be one repo's stack - md/py/ps1/sh/yaml/js/html/java -
# fossilised into kernel code, while profiles/devops.py sold the tool to a
# PHP/Laravel/Vue/Terraform shop and its terraform tripwire said "run
# traps.py terraform". Four of six shipped domains pointed at file types the
# scanner could not open. Nobody had run a .tf marker through it.
#
# Kept deliberately wide, and overridable from kernel_config.py like every other
# constant - editing shared kernel code to add a file type is exactly what this
# project tells you not to do.
EXTS = {
    ".md", ".txt", ".rst",
    ".py", ".sh", ".ps1", ".rb", ".pl",
    ".js", ".ts", ".tsx", ".jsx", ".vue", ".svelte",
    ".php", ".java", ".kt", ".go", ".rs", ".c", ".h", ".cpp", ".cs",
    ".tf", ".tfvars", ".hcl",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".json",
    ".sql", ".html", ".css", ".scss",
    ".gradle", ".dockerfile",
}

# Directories whose contents are not this repo's own hard-won knowledge.
# ⚠️ "renders" used to be in here - one repo's image-output folder, in kernel
# logic. Generic build/vendor dirs only; anything site-specific belongs in
# kernel_config.py.
SKIP_DIRS = {".git", ".hg", ".svn", "node_modules", "vendor", ".venv", "venv",
             "build", "dist", "target", "__pycache__", ".pytest_cache",
             ".terraform", "archive"}

# ⚠️ NEVER COUNT YOUR OWN OUTPUT. Generated files carry markers too - a tripwire
# telling you to heed traps, a MAP warning it is generated - and counting them
# inflates the number this tool exists to report honestly. An audit caught the
# figure drifting 459 -> 622 -> 729 across three files purely from self-ingestion,
# in a project whose whole claim is "measured, not claimed".
# ⚠️ EXTENSIONLESS FILES ARE INVISIBLE TO AN EXTENSION TEST, and the shipped
# docker-build domain targets `**/Dockerfile*`. A WARN: in a bare `Dockerfile`
# scored zero hits until this existed - the same blindness as the .tf/.php one,
# in the one shape an extension list structurally cannot see.
SCAN_BASENAMES = {"Dockerfile", "Containerfile", "Makefile", "Jenkinsfile",
                  "Procfile", "Vagrantfile", "Justfile"}

SKIP_NAMES = {"MAP.md", "TRAPS.md", "CANDIDATES.md"}

try:
    import kernel_config as _cfg
except Exception:
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import kernel_config as _cfg
    except Exception:
        _cfg = None
if _cfg is not None:
    for _k in ("EXTS", "SKIP_DIRS", "SKIP_NAMES", "SCAN_BASENAMES"):
        if hasattr(_cfg, _k):
            globals()[_k] = getattr(_cfg, _k)
# ⚠️ MATCH THIS STRING EXACTLY IN render(). The first version checked for
# "GENERATED by scripts/" while render() emitted "Generated by `scripts/...`" -
# different case - so the tool's own output slipped its own anti-self-ingestion
# filter. Measured: --out MYTRAPS.md then committing took the count 37 -> 74.
GENERATED_BANNER = "GENERATED by scripts/"


# WARNING: Windows consoles default to cp1252 and CANNOT encode the very markers
# this tool exists to print - the first run died with
#     UnicodeEncodeError: 'charmap' codec can't encode characters
# The workspace CLAUDE.md already carries "No emoji in code (Windows cp1252)"
# for a sibling project, so this was a documented trap walked into by a tool
# written to surface documented traps. Force UTF-8 on the streams rather than
# stripping the markers: the marker IS the grade, and a trap that prints as a
# plain note has lost the thing that made it worth reading.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass    # not a real console, or already UTF-8 - either is fine


def repo_root() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()
    except Exception:
        return os.getcwd()


def tracked_files(root: str) -> list[str]:
    """Prefer git's index: it already excludes junk, and it is fast.

    Falls back to a walk so this still works in a worktree that is not a
    checkout, or before `git add`.
    """
    try:
        out = subprocess.run(
            ["git", "-C", root, "ls-files"],
            capture_output=True, text=True, check=True,
        )
        files = [f for f in out.stdout.splitlines() if f]
        if files:
            return files
    except Exception:
        pass
    found = []
    for base, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for n in names:
            rel = os.path.relpath(os.path.join(base, n), root)
            found.append(rel.replace(os.sep, "/"))
    return found


def domain_of(path: str) -> str:
    """First path segment, or `root` for top-level files."""
    parts = path.split("/")
    return parts[0] if len(parts) > 1 else "root"


def scan(root: str, paths: list[str]) -> list[dict]:
    hits = []
    for rel in paths:
        base = os.path.basename(rel)
        if (os.path.splitext(rel)[1].lower() not in EXTS
                and base not in SCAN_BASENAMES
                and not base.startswith(tuple(SCAN_BASENAMES))):
            continue
        if any(seg in SKIP_DIRS for seg in rel.split("/")):
            continue
        if os.path.basename(rel) in SKIP_NAMES:
            continue
        full = os.path.join(root, rel)
        try:
            with open(full, "r", encoding="utf-8", errors="replace") as fh:
                lines = fh.readlines()
        except OSError:
            continue
        if any(GENERATED_BANNER in l for l in lines[:6]):
            continue                      # generated view, not a source of truth
        for i, line in enumerate(lines, 1):
            hit_w = any(m in line for m in WARN_MARKS)
            hit_s = any(m in line for m in STAR_MARKS)
            if not hit_w and not hit_s:
                continue
            kind = "trap" if hit_w else "why"
            text = line.strip()
            # Strip the comment/quote furniture so the lesson reads as a
            # sentence rather than as source. The marker itself stays: it is
            # the grade, and losing it flattens a trap into a note.
            text = re.sub(r"^([#>*\-]+|//+|/\*+|\s*\*)\s*", "", text)
            text = text.strip()
            if len(text) < 12:          # a bare marker on its own line
                continue
            # A trap usually continues onto the next line or two. Carry them
            # while they look like prose continuation, not a new bullet.
            tail = []
            for j in range(i, min(i + 3, len(lines))):
                nxt = lines[j].strip()
                nxt = re.sub(r"^([#>*\-]+|//+|\s*\*)\s*", "", nxt).strip()
                if not nxt or any(m in nxt for m in WARN_MARKS + STAR_MARKS):
                    break
                if re.match(r"^(def |class |\}|\{|import |from )", nxt):
                    break
                tail.append(nxt)
                if nxt.endswith("."):
                    break
            if tail:
                text = text + " " + " ".join(tail)
            hits.append({
                "file": rel, "line": i, "kind": kind,
                "domain": domain_of(rel),
                "text": " ".join(text.split())[:400],
            })
    return hits


def render(hits: list[dict], title: str) -> str:
    traps = [h for h in hits if h["kind"] == "trap"]
    whys = [h for h in hits if h["kind"] == "why"]
    out = [f"# {title}", ""]
    # Emit the guard string verbatim so this file is excluded from future scans.
    out.append(f"<!-- {GENERATED_BANNER}traps.py - do not edit; "
               f"fix the source file and regenerate. -->")
    out.append("")
    out.append(f"{len(traps)} traps, {len(whys)} design notes.")
    out.append("")
    for label, group in (("Traps", traps), ("Why it is built this way", whys)):
        if not group:
            continue
        out.append(f"## {label}")
        out.append("")
        by_file: dict[str, list[dict]] = {}
        for h in group:
            by_file.setdefault(h["file"], []).append(h)
        for f in sorted(by_file):
            out.append(f"**`{f}`**")
            for h in by_file[f]:
                out.append(f"- L{h['line']}: {h['text']}")
            out.append("")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="Extract this repo's traps.")
    ap.add_argument("domain", nargs="?", help="domain or path prefix, e.g. database")
    ap.add_argument("--file", help="a single file")
    ap.add_argument("--domains", action="store_true", help="list domains by weight")
    ap.add_argument("--all", action="store_true", help="everything (large)")
    ap.add_argument("--for", dest="for_files", nargs="*", metavar="FILE",
                    help="resolve the domains of these files and load only those. "
                         "Pass '-' to read paths from stdin, e.g. "
                         "git diff --name-only | traps.py --for -")
    ap.add_argument("--out", help="write to this file instead of stdout")
    args = ap.parse_args()

    root = repo_root()
    hits = scan(root, tracked_files(root))

    if args.domains:
        counts: dict[str, list[int]] = {}
        for h in hits:
            c = counts.setdefault(h["domain"], [0, 0])
            c[0 if h["kind"] == "trap" else 1] += 1
        print(f"{'domain':<20} {'traps':>6} {'why':>6}")
        for d in sorted(counts, key=lambda k: -counts[k][0]):
            t, w = counts[d]
            print(f"{d:<20} {t:>6} {w:>6}")
        print(f"\ntotal: {sum(c[0] for c in counts.values())} traps, "
              f"{sum(c[1] for c in counts.values())} design notes")
        return 0

    if args.for_files is not None:
        # ⚠️ THE MAPPING STEP IS WHERE A REVIEW GOES WRONG SILENTLY. Deciding
        # which domain a changed file belongs to was left to the caller, and the
        # first real use got it wrong: a diff touching .claude/skills/... was
        # scoped to "root", returned nothing, and would have produced a confident
        # clean bill of health from an empty scan. An empty result that looks
        # like a pass is this project's signature failure. So the tool resolves
        # it, not the reader.
        paths = list(args.for_files)
        if not paths or paths == ["-"]:
            paths = [ln.strip() for ln in sys.stdin.read().splitlines() if ln.strip()]
        paths = [p.replace("\\", "/") for p in paths]
        doms = sorted({domain_of(p) for p in paths})
        sel = [h for h in hits if h["domain"] in doms]
        title = "Traps - " + ", ".join(doms)
        print("# resolved %d path(s) to %d domain(s): %s"
              % (len(paths), len(doms), ", ".join(doms)))
        print("")
    elif args.file:
        sel = [h for h in hits if h["file"] == args.file.replace("\\", "/")]
        title = f"Traps - {args.file}"
    elif args.domain:
        pref = args.domain.rstrip("/")
        sel = [h for h in hits
               if h["domain"] == pref or h["file"].startswith(pref + "/")]
        title = f"Traps - {pref}"
    elif args.all:
        sel = hits
        title = "Traps - whole repo"
    else:
        ap.print_help()
        return 2

    if not sel:
        # An empty result is a real answer here, and saying so plainly beats
        # printing nothing and letting it read as a broken command.
        print(f"No traps recorded for that scope. "
              f"(Scanned {len(hits)} marks across the repo.)")
        return 0

    text = render(sel, title)
    if args.out:
        with open(os.path.join(root, args.out), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text + "\n")
        print(f"wrote {args.out}: {len(sel)} entries")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
