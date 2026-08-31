# Agent Root

**A resident reviewer for your repo.** It makes your assistant read the traps you
already wrote *before* it acts, and tells you when the file you are editing is not
the file that is running.

Five markdown files you own, eight Python-stdlib scripts that maintain them. No
dependencies, no service, no vector database, no API key.

---

## Install

```bash
git clone <this repo>            # once, anywhere on the machine
python /path/to/agent-root/scripts/kernel.py install --target /path/to/your-repo
```

Then in Claude Code or GitHub Copilot: **`/agent-root`**.

Install copies the tools, writes the skill, and runs `init` — which reads your git
history and seeds `AGENTS.md`, `MAP.md`, `CANDIDATES.md`, `DECISIONS.md` and
`JOURNAL.md`.

⚠️ **`init` gives you the skeleton, not the knowledge.** It mines git for what
changed together and which commits smell like reverts, and writes those as
questions in `CANDIDATES.md`. It never writes an answer.

Install also generates the per-domain tripwires **from your repo's own trap
distribution** — real triggers, derived, with no rules invented.

⭐ **Then just run `/agent-root`.** It triages the queue on its own: It opens the
commits and the code, answers what the record can settle **with a citation each**,
and hands back only the questions that need someone who was there. That is not
auto-summary — it is the retrieval this tool exists for. What it cannot cite, it
marks `_UNWRITTEN_` and leaves for you.

## Upgrade

```bash
python scripts/kernel.py upgrade
```

No arguments. Install stamps `.claude/agent-root.json` with the version and where
the kernel came from; upgrade reads it and prints what changed, file by file.

⭐ **Your customised skill survives.** The adapter has a generated region between
`<!-- agent-root:begin protocol -->` markers, and a region below them that is
yours. Upgrades refresh the first and never touch the second.

## Use

```bash
python scripts/root.py                 # orient + review the working tree
python scripts/root.py --commit HEAD   # one commit
python scripts/root.py --pr 42         # a pull request (needs gh)
python scripts/root.py --brief         # orientation only
python scripts/root.py --offline       # make no outbound connections
```

**One command, not six.** It calibrates the kernel, loads the trap weight table,
scopes traps to what changed, checks whether the edited copy is the running copy,
and re-tests documented facts — each step with a timeout.

```console
UNDER REVIEW  (changed files, their traps, drift, priors, ledger)
  $ python scripts/review.py

  DOMAINS TOUCHED / TRAPS ON FILE
    41 trap/design lines recorded in those domains
      - L104: ⚠️ Do not do this with a second producer. That was tried:

  DRIFT
    deploy/app.conf   web   repo 3ac9ad / host 548e59   DRIFTED

  LEDGER
    markers added by this change: 0
    WARNING: this looks like a fix and records NO trap.

4 of 4 steps produced output.
```

⚠️ **Read the step count.** A step that times out or fails says so, and no verdict
may claim what a step that did not run would have shown.

### The other commands

| | |
|---|---|
| `traps.py <domain>` | the traps for one domain, before you touch it |
| `traps.py --domains` | the weight table — where surprises actually live |
| `traps.py --json` | the store, for other tools |
| `kernel.py decisions` | draft evidenced decision stubs from git history |
| `kernel.py check` | is anything stale or malformed |
| `kernel.py fleet <repos>` | one row per repo: traps, kernel state, wired |
| `drift.py` | repo versus what is actually running |
| `verify.py --quick` | do the documented facts still hold |
| `tripwires.py` | regenerate the per-domain triggers |

---

## What it actually does

**Programmer half — why is this like this?** Traps and decisions recorded *in
situ* under a `⚠️`/`⭐` marker convention, retrieved scoped to what you touch.

**DevOps half — is the file I am editing the file that is running?** `drift.py`
compares the repo against live hosts over SSH, adb, `kubectl`, whatever you plug
in.

> ⭐ **The failure is retrieval, not memory.** The repo this came from already had
> 850+ traps written down. An assistant re-derived traps written *in the files it
> was editing*, and broke a rule stated in capitals three directories away. More
> storage cannot help a system that already holds more than it reads.

## Works with Claude Code and Copilot

Copilot reads `.claude/skills/` as a project-skill location, so **one file serves
both** — `/agent-root` works in each, and both load it automatically on a
description match.

| File | Fires on |
|---|---|
| `.claude/skills/<name>/SKILL.md` | `/name`, or description match — **both assistants** |
| `.github/copilot-instructions.md` | every request, repo-wide (Copilot) |
| `.github/instructions/<name>.instructions.md` | `applyTo:` glob (Copilot) |

⚠️ `name:` must be lowercase-with-hyphens or Copilot ignores the skill
**silently**. `kernel.py check` validates it.

## Traps that stop you, not just warn you

Most traps are advisory, and should be. Add a directive and one becomes an
interlock:

```markdown
⚠️ **Never force-push to main.**
<!-- block: bash *push*--force* -->
```

`tripwires.py` compiles it; a PreToolUse hook checks every Write, Edit and shell
command. **Opt-in only, fails open, always cites the trap, always deletable.**

⭐ No rules, no hook — a repo with nothing to enforce gets no hook at all.

## Does it touch my network?

**Out of the box, no.** A fresh install declares zero deployments, so `drift.py`
has nothing to reach and returns in ~100 ms saying so. Nothing else opens a
socket.

The only file naming real machines is `scripts/kernel_config.py`, which install
never copies and this repo does not contain. `root.py --offline` is the explicit
guarantee.

## Why it is built this way

- ⭐ **Generated, never handwritten.** A hand-curated index forks from its source;
  the stale copy is trusted because it looks maintained.
- ⚠️ **Cite it or leave it blank — there is no third option.** `init` writes no
  prose at all, and the agent writes only what it can point at: a commit, a file,
  a line. Plausible prose with no citation is worse than a blank, because it is
  trusted, never re-examined, and permanently displaces the real answer.
- ⚠️ **`AGENTS.md` starts with no rules.** A repo earns them one incident at a
  time; rules copied in because they sound wise are wallpaper by week two.
- ⚠️ **Nothing repairs.** A reviewer that fixes things is one you stop believing
  the day it fixes something wrongly.
- ⭐ **Nothing checked never wears a green tick.** An unconfigured check reports
  "nothing was checked", because an empty result that reads as a pass is the
  failure this project exists to prevent.

Facts can carry their own proof, re-checked by `verify.py`:

```markdown
The API listens on **port 8080**.   <!-- verify: port 192.0.2.10 8080 -->
```

⚠️ A restricted predicate language, never shell — a document that can execute
commands is one anyone who edits it can weaponise.

## Limits, stated

**It cannot create the habit it depends on.** Every number here is the output of
one person writing markers as they worked. A team without that habit gets an
empty `TRAPS.md` that stays empty.

**Tripwires are prompts.** Interlocks exist for the few rules worth enforcing, but
an assistant can still ignore a loaded instruction. The honest metric is not
"incidents avoided" — unmeasurable — but **repeat-incident rate**: the same trap
hit twice.

> If maintenance time rises while repeat incidents do not fall, delete the newest
> mechanism first.

Python 3.9+, stdlib only. CI runs the smoke test on Ubuntu and Windows, 3.9 and
3.13 — the encoding bugs this project hit were Windows-only.

MIT.
