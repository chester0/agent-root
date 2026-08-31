# Agent Root

**A resident engineer for your repo:** it makes any assistant your employer
allows read the traps you already wrote — *before* acting — and tells you when
the file you are editing is not the one that is running.

Five markdown files you own, eight Python-stdlib scripts that maintain them. No
dependencies, no service, no vector database, no API key.

---

## The problem, stated honestly

Most "give the AI memory" projects assume the knowledge is missing. In a repo of
any age, it usually is not. On the repo this was extracted from, `traps.py`
counts **over seven hundred `⚠️` traps and four hundred `⭐` design notes already
written down**, plus a machine map and six months of journal.

On one day, an assistant working in that repo re-derived traps written **in the
files it was editing**, and broke a rule stated in capitals three directories
away — twice.

> ⭐ **The failure is retrieval, not memory.** More storage cannot help a system
> that already holds more than it reads.

Everything here follows from that one sentence.

## The two halves

Most tooling addresses one and calls it done.

**Programmer half — why is this like this?**
Traps and decisions, recorded *in situ* under a marker convention, retrieved
scoped to what you are touching.

**DevOps half — is the file I am editing the file that is running?**
`drift.py` compares the repo against live hosts over SSH/adb/`kubectl`/whatever
you plug in.

> ⭐ Drift is the failure a code-only assistant **cannot see**. It reads the repo,
> answers confidently, and is describing a file that is not executing.

## Quickstart

One command installs the tools, wires them into your assistant, and runs `init`:

```bash
python /path/to/agent-root/scripts/kernel.py install --target /path/to/your-repo
```

Then in your editor: **`/agent-root`**.

`init` reads your git history and seeds `AGENTS.md`, `MAP.md`, `CANDIDATES.md`,
`DECISIONS.md` and `JOURNAL.md`. After that, spend **one hour**: write the "what
this repo is" paragraph yourself, triage `CANDIDATES.md`, and leave the operating
rules **empty** until an incident earns one.

⚠️ **`init` gets you the skeleton, not the knowledge.** It sees which files change
together and which commits smell like reverts; it cannot see why. That hour of
triage is the entire value — `CANDIDATES.md` is a list of questions, and the
answers only exist in someone who was there.

⭐ Install **refuses an incomplete source** rather than skipping the missing
pieces. A half-installed reviewer that still reports "installed" is worse than one
that fails, because you would go on to trust it.

## DECISIONS.md is empty after init — on purpose, but not the end of it

`init` writes the contract and no content. Inventing rationale is the failure
this project exists to prevent, so nothing fabricates a *why*.

But "by design" was doing too much work. `archaeology` already finds the reverts
and the commits whose messages say *because*, calls them **"DECISIONS.md entries
written in the wrong place"** — and then left you to retype them.

```bash
python scripts/kernel.py decisions
```

drafts an evidenced **stub** per such commit:

```markdown
## 2026-08-22 — kitchen: hold the sound ON, because the component keeps re-muting it

**Context.** _UNWRITTEN — only you know what was true at the time._
**Decision.** kitchen: hold the sound ON, because the component keeps re-muting it
**Why not the alternative.** _UNWRITTEN — the field that is never recorded and
always the one someone needs._
**Consequence.** _UNWRITTEN._

*Evidence: commit `a3f21c8`, touched kitchen/index.html, kitchen/server.ps1*
```

⭐ **The seam is what git states verbatim versus what only a person knows.** The
date, the subject and the files are facts and get filled in. The three fields
that require a human stay blank *and visibly labelled so*. Idempotent — each stub
carries its commit sha — so run it after every archaeology pass.

⚠️ **A stub left unfilled is worth less than no entry**, because it looks
documented and is not. The command says so every time it runs.

## Does it touch my network?

**Out of the box, no.** A fresh install declares zero deployments, so `drift.py`
has no host to reach and returns in ~100 ms saying so:

```console
$ python scripts/drift.py
—  no deployments declared, so nothing was checked.
   This is not a pass. Declare them in scripts/kernel_config.py
```

Nothing else in the kernel opens a socket. `traps.py`, `kernel.py`, `review.py`
and `tripwires.py` read files and run `git`; `verify.py --quick` skips its port
predicates by design.

| | |
|---|---|
| Hosts shipped in this repo | none — the examples are `*.example.internal`, a reserved documentation domain |
| Config file with real addresses | `scripts/kernel_config.py`, which **`install` never copies** and this repo does not contain |
| Steps that can reach another machine | exactly one: `drift.py`, and only for deployments you declare |
| Explicit off switch | `python scripts/root.py --offline` |

⭐ **`--offline` is a guarantee, not a consequence.** "Nothing is configured" is a
fact about your config; `--offline` is a promise about the tool — the only step
that can leave the machine is not run at all, and the report says so rather than
quietly showing a clean drift section.

⚠️ It says so *loudly*, because a skipped drift check is a real gap: nothing has
verified that a deployed copy matches the repo. Silence there would be the
empty-section-reads-as-a-pass failure this project exists to prevent.

## Upgrading

```bash
python scripts/kernel.py upgrade
```

No arguments, no paths to remember: `install` stamps `.claude/agent-root.json`
with the version and where the kernel came from, and `upgrade` reads it. It
prints what changed, file by file — an upgrade that only says "done" hides a
no-op, and you cannot tell one that worked from one whose source path has moved.

⭐ **Your customised skill survives it.** The adapter has a generated region
between `<!-- agent-root:begin protocol -->` markers and a region below them that
is yours. Upgrades refresh the first and never touch the second. The previous
rule — *never overwrite an existing SKILL.md* — was safe and useless: a
customised skill was frozen at whatever it had on day one.

⚠️ **Upgrade runs the OLD code to install the new**, so the adapter text is read
from the source file on disk rather than from this module's constant. Using the
in-memory constant meant the protocol section could never actually change: the
copy succeeded, the skill stayed stale, and the output said "upgraded".

## Reviewing a change

`/agent-root` runs **one** command. Not six:

```bash
python scripts/root.py                 # orient + review the working tree
python scripts/root.py --commit HEAD   # a commit
python scripts/root.py --pr 42         # a pull request
```

⭐ **The sequence lives in code, not in the skill's prose.** Listing six commands
and trusting the agent to run them in order is the same weakness as a tripwire
being a prompt: an agent that runs four of six and answers confidently produces
output indistinguishable from one that ran all six.

⚠️ **Every step has a timeout, and a step that fails says so.** `drift.py`
contacts real hosts; a sleeping laptop used to mean the opening move sat there
with nothing on screen. Now it reports `TIMED OUT after 45s` — a finding, not
silence — and the footer counts how many steps actually produced output.

Underneath, `review.py` is still the gatherer and can be run alone:

```bash
python scripts/review.py                 # uncommitted working tree
python scripts/review.py --commit HEAD   # one commit
python scripts/review.py --range a..b    # a span
python scripts/review.py --pr 42         # a pull request (needs `gh`)
```

```console
CHANGED  (3)
  src/stream.py
  deploy/app.conf
  scripts/healthcheck.sh

DOMAINS TOUCHED / TRAPS ON FILE
  # resolved 3 path(s) to 2 domain(s): deploy, src
  41 trap/design lines recorded in those domains
    - L104: ⚠️ Do not do this with a second producer. That was tried:

DRIFT
  deploy/app.conf   web   repo 3ac9ad / host 548e59   DRIFTED

PRIORS  (base rates, not findings)
  coupling: src/stream.py usually changes with tests/test_stream.py (7 of 9) - it did not

LEDGER
  markers added by this change: 0
  WARNING: this looks like a fix and records NO trap.
```

> ⚠️ **It gathers; it never judges, and it never posts.** An evidence-gatherer
> that also opines is one you cannot check, because you can no longer tell which
> line came from a command and which from a guess. The verdict is the agent's, and
> every field above it traces to something that was run.

## What it actually looks like

Ask for one domain's traps before touching it *(output below is real, with
filenames and hosts sanitised — this project's whole claim is "measured, not
claimed", so it says so)*:

```console
$ python scripts/traps.py --domains
domain                traps    why
docs                    333     88
database                 99     48
scripts                   7      1

$ python scripts/traps.py database
# Traps - database
99 traps, 48 design notes. Generated by `scripts/traps.py`.

**`src/stream.py`**
- L104: ⚠️ Do not do this with a second producer. That was tried:
- L218: ⚠️ An earlier run of that test was wrong - feeding the splice with `cat`
  delivers eight seconds instantly, which made every option look broken.
```

And a generated tripwire, which every assistant sees when it opens that path:

```markdown
---
applyTo: "**/database/migrations/**,**/config/**"
---
# laravel-migrations

⚠️ **Before acting, load this domain's traps:**
    python scripts/traps.py database

- **`env()` outside `config/` returns NULL once `config:cache` has run.**
- **Queue workers run OLD code until restarted.**
```

## Agent Root

The kernel ships an **agent**, not just tools — otherwise every adopting repo has
to invent its own reviewer, which is backwards: the tools exist to serve one.

> **Root reviews with receipts. It never repairs, and it never guesses.**

⭐ The name inverts the obvious boast. Root does not know everything and cannot
do anything — **Root has ACCESS to everything.** Unix root does not *know* what a
process is doing; root reads `/proc` while everyone else speculates. Which is
forced by the thesis: if the failure is retrieval rather than memory, the agent's
power has to be retrieval too.

> *Guessing is what agents without access do. You are root: every "I don't know"
> is immediately followed by the command that will.*

See `AGENT-ROOT.md`. It is portable markdown by design — a tool-specific agent
file is a thin adapter pointing at it, so Root still works where the approved
assistant is a different one.

## The files

⚠️ **None of these ship in this repo — `kernel.py init` creates them in yours.**
What is published is the CONTRACT each one must satisfy, plus the scripts that
generate and check them. A knowledge layer full of someone else's content would
be worse than none.

| File | Contract |
|---|---|
| `AGENTS.md` | Router + earned rules. **≤120 lines, eviction-capped.** The cross-tool filename |
| `MAP.md` | Generated inventory. Never handwritten |
| `TRAPS.md` | Generated view of in-situ `⚠️`/`⭐` markers |
| `DECISIONS.md` | Dated why-it-is-like-this. **Supersede, never delete** |
| `JOURNAL.md` | Append-only worklog |

## Works with your assistant, not just one

`AGENTS.md` is the cross-tool convention — Claude, Copilot, Codex and Cursor all
read that filename. `tripwires.py` generates **both** trigger formats from one
manifest:

| Assistant | Mechanism | Fires on |
|---|---|---|
| Claude Code | `.claude/skills/<name>/SKILL.md` | `/name`, or description match |
| GitHub Copilot | `.claude/skills/<name>/SKILL.md` | `/name`, or description match |
| GitHub Copilot | `.github/copilot-instructions.md` | every request, repo-wide |
| GitHub Copilot | `.github/instructions/<name>.instructions.md` | `applyTo:` glob |

### One skill directory, both assistants

Copilot reads **`.claude/skills/`** as a project-skill location — alongside
`.github/skills/` and `.agents/skills/` — in the CLI, in VS Code, and for the
cloud agent. Skills load automatically when the description matches the task, and
can be invoked by name with `/agent-root`.

So `install` writes **one** skill directory and both assistants read it. It is the
intersection, not a Claude-only path, and that is why there is no second copy.

```
.claude/skills/agent-root/SKILL.md   -> /agent-root in Claude Code AND Copilot
.claude/skills/<domain>/SKILL.md     -> the generated tripwires, same deal
.github/copilot-instructions.md      -> Copilot, always on
.github/instructions/*.md            -> Copilot, fires on an applyTo path glob
```

Personal (cross-repo) skills live in `~/.copilot/skills/` or `~/.agents/skills/`;
VS Code also reads `~/.claude/skills/`.

⚠️ **`name:` must be lowercase-with-hyphens or Copilot silently ignores the
skill** — it is simply never offered, which looks identical to a skill nobody
wrote. `kernel.py check` validates the frontmatter of every skill for exactly this
reason, because a rename can un-publish a tripwire without any error.

⭐ **This section was wrong when first written.** It claimed Copilot had no skills,
which was never checked — and on that false premise a duplicate
`.github/prompts/agent-root.prompt.md` was generated, a second copy of the same
instructions free to drift from the first. Both the claim and the duplicate are
gone. Asserting what *another* tool cannot do, without reading its documentation,
is the same failure as asserting what your own code does without running it.

## Traps that stop you, not just warn you

Everything above is advisory, and for most traps that is correct. But a few rules
are worth enforcing, and a warning cannot enforce anything — this project proved
that on itself: a trap saying *never hand-sync README.md* was written, and the
same mistake was made again an hour later, by the author of the trap.

Add a directive to a trap and it compiles into an interlock:

```markdown
⚠️ **README.md is repo identity, not shared implementation.** Never hand-sync it.
<!-- block: write **/README.md -->

⚠️ **Never force-push to main.** History others have pulled must not be rewritten.
<!-- block: bash *push*--force* -->
```

`tripwires.py` compiles those into `.claude/agent-root-blocks.json`, and a
PreToolUse hook runs `guard.py` before every Write, Edit and Bash:

```console
  BLOCKED by Agent Root - a trap in this repo forbids this.

    action : README.md
    rule   : write **/README.md
    trap   : HOUSE-RULES.md:3

    ⚠️ README.md is repo identity, not shared implementation. Never hand-sync it.

  This rule is opt-in and editable: .claude/agent-root-blocks.json
```

⚠️ **A guard that blocks wrongly is worse than no guard**, because the first thing
anyone does with one that cries wolf is switch it off — and the real rules go with
it. So: **opt-in only** (nothing is inferred from the wording of existing traps),
**fail open** (any error allows the action), **always cite** the trap that caused
the block, and **always escapable** — the rules are a committed JSON file a human
can edit or delete.

⭐ **The hook is wired only once a repo declares a rule.** A repo with
nothing to enforce gets no hook at all — because the failure mode is not
hypothetical: it shipped with a *relative* command path, and a Python
interpreter that cannot find its script exits 2, which is the block code. A
repo with **zero** rules blocked every Write, Edit and Bash. The command is
now absolute via `$CLAUDE_PROJECT_DIR`, and wired only where it has work to do.

⭐ **`guard.py` is on the install list as a safety requirement, not a
convenience.** The hook blocks on exit code 2 — and a Python interpreter that
cannot find its script *also* exits 2. A missing guard does not fail open, it
blocks everything. Measured: with it absent, all eight test cases "blocked",
including the two written to prove fail-open.

## Facts that prove themselves

Knowledge does not decay into *useless*. It decays into **confidently wrong**,
which is worse, because it is trusted and acted on. So a claim can carry its own
proof, written beside it:

```markdown
The API listens on **port 8080**, not 3000.   <!-- verify: port 192.0.2.10 8080 -->
The token is gitignored.                     <!-- verify: gitignored scripts/token.txt -->
```

`python scripts/verify.py` re-checks every one, plus paths, links and tools.

> ⚠️ **A restricted predicate language, never shell.** `port`, `noport`, `file`,
> `nofile`, `tracked`, `gitignored`, `contains`, `absent`. A document that can
> execute commands is a document anyone who edits it can weaponise.

Facts are split by **who can check them**: machine-checkable ones are verified in
seconds; human-only ones (*is this decision still right?*) are only ever
**flagged, never judged**. And it **never repairs** — a verifier that fixes things
is one you stop believing the day it fixes something wrongly.

⭐ On its first real run it caught an overclaim: the machine table asserted a
phone's adb port was listening, when that port only opens on demand. The doc was
wrong and the tool said so.

## Why generated, not handwritten

The markers in the source files are canonical; every index is a view.

A hand-curated trap file forks from its source: one copy gets the fix, the other
keeps the old rule, and **the stale one is trusted because it looks maintained.**
Generation makes divergence structurally impossible.

> ⭐ Discipline is what already failed. Do not design a system that needs more of
> it.

## What `init` deliberately will not do

- ⚠️ **No auto-summarised prose.** No "this module handles X" blanketing. A
  confident wrong summary is worse than a blank: it is trusted, never
  re-examined, and it displaces the real knowledge someone would have written.
- ⚠️ **No seeded operating rules.** `AGENTS.md` starts empty. **A repo earns its
  rules one incident at a time, and that earning is the point.** A rule copied in
  because it sounds wise is wallpaper by week two.
- ⚠️ **No journal backfill, no invented rationale.** What git does not state
  verbatim stays unstated.

The starter profiles (`profiles/devops.py`) follow the same rule: they ship
**questions and checks**, never claims about a system they have never seen.

## Scale

Measured on a 21,898-file / 4,487-commit repository:

| | |
|---|---|
| `traps.py --domains` | **0.47 s** |
| `kernel.py archaeology` | **1.6 s** |
| `kernel.py map` | **2.1 s** |

⚠️ `map` is listed because it was nearly omitted. Its first implementation ran
`git log` once per file — about **twelve minutes** at this scale. Publishing the
two sub-second figures while quietly leaving out the twelve-minute one is exactly
the kind of measurement this project claims not to do. One `git log` pass fixed
it; the row stays as a reminder.

Python 3.9+, standard library only. CI runs the smoke test on Ubuntu and Windows,
3.9 and 3.13 — the encoding bugs this project hit were Windows-only.

## What this will not do

Two limitations, stated rather than left to be discovered.

**It cannot create the habit it depends on.** Every number in this README is the
output of one person's years of writing markers as they worked. A team without
that habit gets an empty `TRAPS.md` that stays empty. `archaeology` and a cheap-model triage pass **seed** from what git
and the code already contain — they do not sustain it. The value is proportional to a writing culture this does not install.

**Tripwires are prompts, not interlocks.** An assistant can still ignore a loaded
instruction. The incident that motivated all of this happened with the knowledge
already in the repo; firing it at the right moment reduces that class of failure,
it does not eliminate it. Which means the honest success metric is not "incidents
avoided" — that is unmeasurable — but **repeat-incident rate**: the same trap
hit twice.

## How you know it is working

Not "indexes fresh, skills tidy". **Incidents avoided, traps not re-hit, drift
caught before it misled someone.**

> If maintenance time rises while repeat incidents do not fall, delete the newest
> mechanism first.
