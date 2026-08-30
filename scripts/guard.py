#!/usr/bin/env python3
"""Turn chosen traps into interlocks. Reads a PreToolUse event, blocks or allows.

Wired by `kernel.py install` into `.claude/settings.json`:

    PreToolUse (Write|Edit|Bash) --> python scripts/guard.py

It reads the tool call as JSON on stdin, matches it against the rules in
`.claude/agent-root-blocks.json`, and exits 2 to BLOCK or 0 to allow.

WHY THIS EXISTS. Everything else here is advisory, and this project's own README
says so: "tripwires are prompts, not interlocks - they cannot force a warning to
be read." That limit was demonstrated rather than theorised. A trap saying never
hand-sync README.md was written, and the same mistake was made again an hour
later by the author of the trap. A marker in a source file cannot stop a shell
command. This can.

WARNING: A GUARD THAT BLOCKS WRONGLY IS WORSE THAN NO GUARD, because the first
thing anyone does with a guard that cries wolf is switch it off permanently, and
then the real rules go with it. Four properties follow from that, and none are
optional:

  1. OPT-IN ONLY. A trap is advisory unless it carries an explicit
     `<!-- block: write <glob> -->` directive. Nothing is inferred from the
     wording of a trap. Compiling 777 existing warnings into blocks would
     produce an agent that refuses work for reasons no human chose.
  2. FAIL OPEN. Any error - missing rules file, bad JSON, unreadable stdin,
     an exception anywhere - allows the action. A broken guard must not become
     an outage. It says so on stderr and gets out of the way.
  3. CITE, ALWAYS. A block names the file and line of the trap that caused it,
     so the human can read the reason and disagree with it.
  4. ESCAPABLE. Rules live in a committed JSON file a human can edit or delete,
     and the block message says how. A guard with no exit is a trap of its own.

stdlib only. No network. Runs on every matching tool call, so it must stay fast:
it reads one small JSON file and never scans the repo.
"""
from __future__ import annotations

import fnmatch
import json
import os
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

RULES_REL = os.path.join(".claude", "agent-root-blocks.json")

WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
BASH_TOOLS = ("Bash",)

ALLOW, BLOCK = 0, 2


def repo_root(start):
    d = os.path.abspath(start)
    while True:
        if os.path.isdir(os.path.join(d, ".git")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return os.path.abspath(start)
        d = parent


def load_rules(root):
    p = os.path.join(root, RULES_REL)
    if not os.path.exists(p):
        return []
    with open(p, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    rules = data.get("blocks", [])
    return [r for r in rules
            if r.get("on") in ("write", "bash") and r.get("match")]


def norm(p):
    return str(p or "").replace("\\", "/")


def match_write(rule, path):
    """Match a glob against the path and its basename.

    ⚠️ Both forms are tried on purpose. A rule written as `**/README.md` is the
    obvious way to say "any README", and fnmatch alone would not match a bare
    relative `README.md`. A rule that silently never fires is the failure this
    whole file exists to prevent, so matching is deliberately generous HERE -
    the narrowness comes from rules being opt-in, not from the matcher.
    """
    pat, path = rule["match"], norm(path)
    if fnmatch.fnmatch(path, pat) or fnmatch.fnmatch(os.path.basename(path), pat):
        return True
    if pat.startswith("**/") and fnmatch.fnmatch(path, pat[3:]):
        return True
    return False


def match_bash(rule, command):
    pat, cmd = rule["match"], str(command or "")
    if fnmatch.fnmatch(cmd, pat) or fnmatch.fnmatch(cmd, "*" + pat + "*"):
        return True
    return pat in cmd


def explain(rule, subject):
    out = []
    out.append("")
    out.append("  BLOCKED by Agent Root - a trap in this repo forbids this.")
    out.append("")
    out.append("    action : %s" % subject[:160])
    out.append("    rule   : %s %s" % (rule.get("on"), rule.get("match")))
    out.append("    trap   : %s:%s" % (rule.get("file"), rule.get("line")))
    why = (rule.get("why") or "").strip()
    if why:
        out.append("")
        for line in (why[:400]).splitlines():
            out.append("    " + line)
    out.append("")
    out.append("  This rule is opt-in and editable: %s" % RULES_REL)
    out.append("  Regenerate it with: python scripts/tripwires.py")
    out.append("")
    return "\n".join(out)


def main():
    # WARNING: the whole body is wrapped. See property 2 - a guard that throws
    # must allow, never block. There is no error path here that stops work.
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return ALLOW
        event = json.loads(raw)
        tool = event.get("tool_name") or ""
        ti = event.get("tool_input") or {}

        root = repo_root(event.get("cwd") or os.getcwd())
        rules = load_rules(root)
        if not rules:
            return ALLOW

        if tool in WRITE_TOOLS:
            path = ti.get("file_path") or ti.get("notebook_path") or ""
            if path:
                for r in rules:
                    if r["on"] == "write" and match_write(r, path):
                        sys.stderr.write(explain(r, path))
                        return BLOCK

        if tool in BASH_TOOLS:
            cmd = ti.get("command") or ""
            if cmd:
                for r in rules:
                    if r["on"] == "bash" and match_bash(r, cmd):
                        sys.stderr.write(explain(r, cmd))
                        return BLOCK

        return ALLOW
    except Exception as e:                                   # noqa: BLE001
        sys.stderr.write("  agent-root guard skipped (%s: %s)\n"
                         % (type(e).__name__, str(e)[:120]))
        return ALLOW


if __name__ == "__main__":
    sys.exit(main())
