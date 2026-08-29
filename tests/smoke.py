#!/usr/bin/env python3
"""Smoke test: init -> map -> archaeology -> tripwires --check, on a fixture repo.

⭐ It proves the two claims most likely to be false on someone else's machine:
   "standard library only, portable" and "the encoding is handled".
Both were broken here at least once. A green run on Windows and Linux is worth
more to a DevOps reader than any paragraph.
"""
import os, subprocess, sys, tempfile, shutil, io

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
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
          "tripwires (idempotent, no mojibake), verify, drift")
    return 0


if __name__ == "__main__":
    sys.exit(main())
