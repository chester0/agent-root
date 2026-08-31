#!/usr/bin/env python3
"""Smoke test: init -> map -> archaeology -> tripwires --check, on a fixture repo.

⭐ It proves the two claims most likely to be false on someone else's machine:
   "standard library only, portable" and "the encoding is handled".
Both were broken here at least once. A green run on Windows and Linux is worth
more to a DevOps reader than any paragraph.
"""
import os, subprocess, sys, tempfile, shutil, io, json

NL = chr(10)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPTS = os.path.join(ROOT, "scripts")
FAIL = []


def run(*a, cwd=None, expect=0):
    p = subprocess.run(a, cwd=cwd, capture_output=True, text=True, errors="replace")
    if expect is not None and p.returncode != expect:
        FAIL.append(f"{' '.join(a[-2:])} -> rc={p.returncode}\n{p.stdout}\n{p.stderr}")
    return p


def main():
    tmp = tempfile.mkdtemp(prefix="kernel-smoke-")
    try:
        run("git", "init", "-q", tmp)
        run("git", "-C", tmp, "config", "user.email", "t@t.t")
        run("git", "-C", tmp, "config", "user.name", "t")
        shutil.copytree(SCRIPTS, os.path.join(tmp, "scripts"))
        # a COMPLETE source - install refuses a partial kernel, by design
        for extra in ("AGENT-ROOT.md", "USING-AGENT-ROOT.md"):
            src_extra = os.path.join(ROOT, extra)
            if os.path.exists(src_extra):
                shutil.copy2(src_extra, os.path.join(tmp, extra))
        shutil.copytree(os.path.join(ROOT, "profiles"),
                        os.path.join(tmp, "profiles"))

        # A fixture carrying BOTH marker forms, and non-ASCII prose, because the
        # encoding path is what broke twice.
        # WARNING: the fixture carries the file types the shipped PROFILES
        # target, not just the ones the author's own repo happened to use. An
        # audit found traps.py blind to .tf/.php/.vue/.ts while
        # profiles/devops.py told users to scan exactly those - four of six
        # shipped domains pointing at file types the scanner could not open.
        for _name, _body in (
            ("main.tf", 'resource "x" "y" {}\n# WARN: terraform trap must be seen\n'),
            ("Kernel.php", "<?php\n// WARN: php trap must be seen\n"),
            ("App.vue", "<template></template>\n<!-- WARN: vue trap must be seen -->\n"),
            ("app.ts", "// WARN: typescript trap must be seen\n"),
            ("Dockerfile", "FROM scratch\n# WARN: dockerfile trap must be seen\n"),
        ):
            io.open(os.path.join(tmp, _name), "w", encoding="utf-8",
                    newline="\n").write(_body)
        io.open(os.path.join(tmp, "README.md"), "w", encoding="utf-8", newline="\n").write(
            "# Fixture\n\n"
            "⚠️ emoji trap - naive cp1252 output dies here\n"
            "⭐ emoji design note\n"
            "WARN: ascii trap alias\n"
            "WHY: ascii design note alias\n"
            "Prose with an em dash — and an accent: café.\n")
        run("git", "-C", tmp, "add", "-A")
        run("git", "-C", tmp, "commit", "-qm", "fixture: because the encoding broke twice")

        py = sys.executable
        run(py, "scripts/kernel.py", "init", cwd=tmp)
        for f in ("AGENTS.md", "DECISIONS.md", "JOURNAL.md", "MAP.md", "CANDIDATES.md"):
            if not os.path.exists(os.path.join(tmp, f)):
                FAIL.append(f"init did not create {f}")

        run(py, "scripts/kernel.py", "map", cwd=tmp)
        run(py, "scripts/kernel.py", "archaeology", cwd=tmp)
        run(py, "scripts/kernel.py", "check", cwd=tmp)

        # BOTH marker forms must be found - the ASCII alias is the whole point of
        # supporting shops that lint emoji out of source.
        out = run(py, "scripts/traps.py", "--domains", cwd=tmp).stdout
        if "traps" not in out:
            FAIL.append("traps.py --domains produced no summary")
        root = run(py, "scripts/traps.py", "root", cwd=tmp).stdout
        for needle, why in (("emoji trap", "emoji WARN"), ("ascii trap", "ASCII WARN:"),
                            ("emoji design note", "emoji STAR"), ("ascii design note", "ASCII WHY:")):
            if needle not in root:
                FAIL.append(f"{why} marker not detected")
        # Every file type the shipped profiles point at must actually be scanned.
        allout = run(py, "scripts/traps.py", "--all", cwd=tmp).stdout
        for ext in ("terraform", "php", "vue", "typescript", "dockerfile"):
            if f"{ext} trap must be seen" not in allout:
                FAIL.append(f"{ext} marker NOT found - traps.py is blind to that file type")

        run(py, "scripts/tripwires.py", cwd=tmp)
        run(py, "scripts/tripwires.py", "--check", cwd=tmp)     # must be idempotent
        for f in (".claude/skills", ".github/instructions"):
            if not os.path.isdir(os.path.join(tmp, f)):
                FAIL.append(f"tripwires did not create {f}")
        # No mojibake may reach the generated files.
        for dp, _dn, fn in os.walk(os.path.join(tmp, ".github", "instructions")):
            for n in fn:
                if "â" in io.open(os.path.join(dp, n), encoding="utf-8", errors="replace").read():
                    FAIL.append(f"mojibake in generated {n}")

        # ⚠️ expect=0, not None. With expect=None a traceback passed green while
        # the summary still printed "verify" as covered - invocation reported as
        # verification.
        run(py, "scripts/verify.py", "--quick", cwd=tmp, expect=0)
        run(py, "scripts/drift.py", "--list", cwd=tmp)
        run(py, "scripts/review.py", cwd=tmp)          # working tree
        run(py, "scripts/review.py", "--commit", "HEAD", cwd=tmp)

        # ⭐ The single opening move. It must ALWAYS exit 0 and always print a
        # step count - it is what /agent-root runs, and an entry point that can
        # fail hard leaves the agent with nothing and no reason.
        r = run(py, "scripts/root.py", "--brief", cwd=tmp)
        assert "AGENT ROOT" in r.stdout, "root.py printed no header"
        assert "steps produced output" in r.stdout, "root.py printed no step count"
        # ⭐ --offline is a promise about the TOOL, not about the config. Assert
        # that the one network-capable step is genuinely not run, and that its
        # absence is stated rather than shown as a clean section.
        ro = run(py, "scripts/root.py", "--brief", "--offline", cwd=tmp)
        assert "skipped: --offline" in ro.stdout, "--offline did not skip drift"
        assert "has checked" in ro.stdout, "--offline did not state the gap"

        # ⭐ The README states a script count in its first paragraph. It said
        # five while there were six for a whole release, because a number in
        # prose has nothing checking it. Now it does.
        n = len([f for f in os.listdir(os.path.join(ROOT, "scripts"))
                 if f.endswith(".py")])
        words = {5: "five", 6: "six", 7: "seven", 8: "eight"}
        readme = io.open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
        assert ("%s Python-stdlib scripts" % words.get(n, n)) in readme, (
            "README script count is stale: there are %d scripts" % n)

        # install into a SECOND repo. This is the headline path - one command
        # then /agent-root - and it shipped broken twice: once because the
        # source was derived from the cwd (so it refused every real
        # invocation), once on an undefined name that only the write path
        # touched. Both would have been caught here.
        with tempfile.TemporaryDirectory() as dst:
            run("git", "init", "-q", ".", cwd=dst)
            io.open(os.path.join(dst, "README.md"), "w",
                    encoding="utf-8").write("# t" + NL)
            run("git", "add", "-A", cwd=dst)
            run("git", "-c", "user.email=t@t", "-c", "user.name=t",
                "commit", "-qm", "init", cwd=dst)
            run(py, os.path.join(tmp, "scripts", "kernel.py"),
                "install", "--target", dst, cwd=dst)
            for need in (os.path.join(".claude", "skills", "agent-root", "SKILL.md"),
                         os.path.join(".github", "copilot-instructions.md"),
                         os.path.join("scripts", "review.py"),
                         "AGENT-ROOT.md", "AGENTS.md"):
                assert os.path.exists(os.path.join(dst, need)), "install missed " + need
            # and the installed copy must actually run where it landed
            run(py, os.path.join(dst, "scripts", "review.py"), cwd=dst)

            # ⭐ THE GUARD IS TESTED IN BOTH DIRECTIONS, ALWAYS. A guard proven
            # only to block is half-tested, and the dangerous half is the other
            # one: an early version "blocked" all eight cases because guard.py
            # was missing and a Python interpreter that cannot find its script
            # ALSO exits 2. Blocking everything looked like working.
            rules = os.path.join(dst, ".claude", "agent-root-blocks.json")
            io.open(rules, "w", encoding="utf-8").write(json.dumps({"blocks": [
                {"on": "write", "match": "**/SECRET.md", "file": "t.md",
                 "line": 1, "why": "test rule"},
                {"on": "bash", "match": "*rm -rf /*", "file": "t.md",
                 "line": 2, "why": "test rule"}]}))
            g = os.path.join(dst, "scripts", "guard.py")

            def verdict(payload):
                p = subprocess.run([py, g], cwd=dst, input=json.dumps(payload),
                                   capture_output=True, text=True,
                                   encoding="utf-8", errors="replace")
                assert "can't open file" not in (p.stderr or ""), "guard.py missing"
                return p.returncode

            assert verdict({"tool_name": "Write",
                            "tool_input": {"file_path": "SECRET.md"}}) == 2
            assert verdict({"tool_name": "Bash",
                            "tool_input": {"command": "rm -rf /tmp/x"}}) == 2
            # ⚠️ EVERY SHELL. Inspecting Bash alone left every rule bypassable
            # by running the same command in PowerShell - which is the PRIMARY
            # shell on Windows, where this was reported.
            assert verdict({"tool_name": "PowerShell",
                            "tool_input": {"command": "rm -rf /tmp/x"}}) == 2
            # a terminal tool nobody has heard of, recognised by input shape
            assert verdict({"tool_name": "SomeNewTerminal",
                            "tool_input": {"command": "rm -rf /tmp/x"}}) == 2
            assert verdict({"tool_name": "PowerShell",
                            "tool_input": {"command": "git status"}}) == 0
            assert verdict({"tool_name": "Write",
                            "tool_input": {"file_path": "src/ok.py"}}) == 0
            assert verdict({"tool_name": "Bash",
                            "tool_input": {"command": "ls -la"}}) == 0
            assert verdict({"tool_name": "Read",
                            "tool_input": {"file_path": "SECRET.md"}}) == 0
            # fail OPEN: a guard that cannot parse its input must not stop work
            bad = subprocess.run([py, g], cwd=dst, input="not json{{{",
                                 capture_output=True, text=True,
                                 encoding="utf-8", errors="replace")
            assert bad.returncode == 0, "guard must fail open on bad input"

            # ⚠️ NO RULES MEANS NO HOOK. An interlock in a repo with nothing
            # to enforce is pure risk, and it misfired exactly so: the hook was
            # wired with a RELATIVE path, and an interpreter that cannot find
            # its script exits 2 - the block code - so a repo with zero rules
            # blocked every Write, Edit and Bash it attempted.
            sp = os.path.join(dst, ".claude", "settings.json")
            if os.path.exists(sp):
                st = json.loads(io.open(sp, encoding="utf-8").read())
                n = sum(1 for e in st.get("hooks", {}).get("PreToolUse", [])
                        if "guard.py" in json.dumps(e))
                assert n == 0, "a repo with no rules must have no guard hook"

            # declare a rule, compile it, reinstall - NOW it should wire, and
            # never with a relative path.
            io.open(os.path.join(dst, "R.md"), "w", encoding="utf-8").write(
                "WARNING: no secrets" + NL + "<!-- block: write **/SECRET.md -->" + NL)
            run("git", "add", "-A", cwd=dst)
            run("git", "-c", "user.email=t@t", "-c", "user.name=t",
                "commit", "-qm", "rule", cwd=dst)
            run(py, os.path.join(dst, "scripts", "tripwires.py"), cwd=dst)
            run(py, os.path.join(tmp, "scripts", "kernel.py"),
                "install", "--target", dst, cwd=dst)
            st = json.loads(io.open(sp, encoding="utf-8").read())
            entries = [e for e in st.get("hooks", {}).get("PreToolUse", [])
                       if "guard.py" in json.dumps(e)]
            assert len(entries) == 1, "expected one guard hook, found %d" % len(entries)
            cmdline = json.dumps(entries[0])
            assert "scripts/guard.py" in cmdline
            assert "CLAUDE_PROJECT_DIR" in cmdline, (
                "hook must not use a relative path - an unresolvable one blocks "
                "every tool call")

            # ⭐ UPGRADE MUST DELIVER IMPROVEMENTS AND PRESERVE CUSTOMISATION.
            # "Never overwrite an existing SKILL.md" made install safe and made
            # upgrades useless - a customised skill was frozen at whatever it
            # had on day one. The generated protocol lives between markers; the
            # repo's own notes live below them.
            skill = os.path.join(dst, ".claude", "skills", "agent-root", "SKILL.md")
            io.open(skill, "a", encoding="utf-8").write(NL + "MY OWN RULE." + NL)
            assert os.path.exists(os.path.join(dst, ".claude", "agent-root.json")), \
                "install must stamp the source so upgrade needs no arguments"
            r = run(py, os.path.join(dst, "scripts", "kernel.py"),
                    "upgrade", cwd=dst)
            assert "already current" in r.stdout or "changed" in r.stdout, \
                "upgrade printed no file accounting"
            body = io.open(skill, encoding="utf-8").read()
            assert "MY OWN RULE." in body, "upgrade destroyed the repo's own notes"
            assert "agent-root:begin protocol" in body, "protocol markers lost"

            # CI guard shipped
            assert os.path.exists(os.path.join(dst, ".github", "workflows",
                                               "agent-root.yml"))
            # fleet reports the installed repo without blowing up
            run(py, os.path.join(tmp, "scripts", "kernel.py"), "fleet", dst, cwd=dst)

        # WARNING: EVERY SHIPPED hash_cmd MUST SURVIVE .format(). A pure string
        # check, no ssh needed. The Windows example once shipped with mismatched
        # braces and raised KeyError, which the broad except turned into
        # "unreachable" - a reachability word for a config typo. It survived
        # every other test because DEPLOYMENTS only targets the Linux host, so
        # the tested string and the shipped string were different strings.
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location("_drift", os.path.join(tmp, "scripts", "drift.py"))
        _d = _ilu.module_from_spec(_spec)
        try:
            _spec.loader.exec_module(_d)
            for _h, _cfg in getattr(_d, "HOSTS", {}).items():
                _cmd = _cfg.get("hash_cmd")
                if not _cmd:
                    continue
                try:
                    _cmd.format(path="/tmp/x")
                except Exception as _e:
                    FAIL.append(f"HOSTS[{_h}].hash_cmd fails .format(): {type(_e).__name__}")
        except Exception as _e:
            FAIL.append(f"could not import drift.py to check hash_cmds: {_e}")

        # The shipped profile must generate, since the README tells people to use it.
        prof = os.path.join(tmp, "profiles")
        os.makedirs(prof, exist_ok=True)
        shutil.copy2(os.path.join(os.path.dirname(SCRIPTS), "profiles", "devops.py"),
                     os.path.join(prof, "devops.py"))
        run(py, "scripts/tripwires.py", "--profile", "profiles/devops.py", cwd=tmp)
        run(py, "scripts/tripwires.py", "--profile", "profiles/devops.py", "--check", cwd=tmp)

        # ⚠️ SELF-INGESTION MUST STAY CLOSED. The guard once missed the tool's own
        # banner on a case difference, and --out took a count from 37 to 74.
        # ⚠️ Commit EVERYTHING first. traps.py scans `git ls-files`, so anything
        # untracked is invisible - and an earlier version of this check copied
        # profiles/devops.py in between the two counts, so the number rose for an
        # honest reason and the test blamed the tool. Baseline on a clean tree.
        run("git", "-C", tmp, "add", "-A")
        run("git", "-C", tmp, "commit", "-qm", "pre-baseline", expect=None)
        before = run(py, "scripts/traps.py", "--domains", cwd=tmp).stdout
        # ⚠️ NOT "TRAPS.md" - that name was already in SKIP_NAMES, so the test
        # passed with or without the banner fix: it guarded the invulnerable case
        # and would have slept through the exact regression it commemorates.
        run(py, "scripts/traps.py", "--all", "--out", "GENERATED-VIEW.md", cwd=tmp)
        run("git", "-C", tmp, "add", "-A")
        run("git", "-C", tmp, "commit", "-qm", "generated view")
        after = run(py, "scripts/traps.py", "--domains", cwd=tmp).stdout
        if before.strip() != after.strip():
            FAIL.append("self-ingestion: counts changed after generating TRAPS.md")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if FAIL:
        print("SMOKE FAILED:")
        for f in FAIL:
            print("  -", f)
        return 1
    print("smoke OK - init, map, archaeology, traps (both marker forms), "
          "tripwires (idempotent, no mojibake), verify, drift, review, root (one-command), install, upgrade (delivers + preserves), guard (blocks+allows+fails open), CI, fleet, sections")
    return 0


if __name__ == "__main__":
    sys.exit(main())
