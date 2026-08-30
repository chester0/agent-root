# Using Agent Root

> **Root reviews with receipts. It never repairs, and it never guesses.**

---

# DOING

## Install it into a repo

```bash
git clone <the agent-root repo>          # once, anywhere on the machine
python /path/to/agent-root/scripts/kernel.py install --target /path/to/your/repo
```

That copies the tools, writes the Claude skill and the Copilot instructions, and
runs `init` — which reads your git history and lays down `AGENTS.md`, `MAP.md`,
`CANDIDATES.md` and `JOURNAL.md`. One command, and the repo is wired.

⚠️ **`init` gets you the skeleton, not the knowledge.** It can see which files
change together and which commits smell like reverts; it cannot see why. The hour
of triage it asks for at the end is the entire value — `CANDIDATES.md` is a list
of questions, and answers only come from someone who was there.

⭐ Install refuses to run from an incomplete checkout rather than skipping the
missing pieces. A half-installed reviewer that still says "installed" is worse
than one that fails, because you would go on to trust it.

## Call it

```
/agent-root
```

That is the whole invocation. In Claude Code it loads the review protocol and
your repo's facts. Everything below is about reading what comes back.

## When it earns its keep

| Say | And it will |
|---|---|
| *"review my changes"* | Check the diff against traps this repo already paid for |
| *"what am I about to break?"* | Load only the domains you are touching |
| *"why is this like this?"* | Find the `⭐` that explains it, or say it is undocumented |
| *"what's drifted?"* | Compare the repo against what is actually running |
| *"is this still true?"* | Re-check the facts the docs assert |

⚠️ **Ask it BEFORE the work, not only after.** The whole point is arriving with
the traps loaded. Asking afterwards is a code review; asking first is the thing
this exists for.

## Read the answer like this

Every review comes back in a fixed shape. **The fields are the review** — the
prose around them is not:

```
root@yourrepo — 214 traps on file across 7 domains

DOMAINS TOUCHED   api, deploy
TRAPS LOADED      31 (traps.py --for -)
REPEAT INCIDENT   docs/RUNBOOK.md:88 - you are re-walking this one
DRIFT             deploy/app.conf: repo 548e59 / host 3ac9ad — DRIFTED
LEDGER            no ⚠️ marker added for the stall you just fixed
VERDICT           …
```

⭐ **Empty receipt fields mean the review is fake.** If `TRAPS LOADED` says
nothing, no traps were loaded and the clean bill of health is worthless. **Bounce
it and ask again.** That is not distrust, it is the designed check — the fields
exist precisely because a plausible review is easy to write and a receipted one
is not.

## The three answers worth acting on immediately

- **`REPEAT INCIDENT` with a citation** — you are about to redo something that
  already cost you. Go and read that line before continuing.
- **`DRIFT ... DRIFTED`** — the file you are editing is **not** the file that is
  running. Decide which way the fix should travel before you write another line.
- **`LEDGER` naming something unwritten** — you learned something and did not
  record it. ⭐ An incident fix with no new `⚠️` marker fails review here: the
  code fix stops it once, the marker stops it forever.

## When it says GUESS

A verdict labelled `GUESS` is Root telling you it could not check. **That label
outranks a confident answer.** Either accept it as a hypothesis and go verify, or
ask *"what command would settle this?"* — Root is required to know.

## Run it yourself

Root has no private tools. Everything it does, you can do:

```bash
python scripts/kernel.py check                          # are the tools sane
python scripts/traps.py --domains                       # the weight table
git diff --name-only | python scripts/traps.py --for -  # traps for what you touched
python scripts/drift.py                                 # repo vs what is running
python scripts/verify.py --quick                        # do the docs still hold
```

## At work, without Claude

The protocol lives in `AGENT-ROOT.md` as plain markdown. Copilot reads
`AGENTS.md` and `.github/instructions/` natively, and the same commands run
anywhere. Point any assistant at `AGENT-ROOT.md` and ask it to follow the output
contract.

---

# KNOWING

## Why the receipts, and not just a good reviewer

An LLM cannot tell recall from confabulation. There is no internal wobble — a
remembered fact and an invented one arrive with identical confidence. In one
session an agent said *"verified: zero personal references"* three times,
honestly, and was wrong all three.

So Root is **not** built to be more careful. Care is not available. It is built
so that the absence of checking is **visible in the output**: fields that can
only be filled from command output, and a label for the times it could not.

⭐ You are not reading Root's opinion. You are reading what Root ran.

## Why it never repairs

`verify.py`, `drift.py` and Root all share one contract: report, never fix. A
reviewer that repairs is one you stop believing the first time it repairs
something wrongly — and its whole value is being believed. On some systems that mistake is expensive.

## Why "Root"

Two meanings, both meant. The Matrix agent — resident in the system, appears
wherever you are. And the unix superuser — total **access**.

⚠️ Note which half is the claim. Root does not know everything and cannot do
anything. **Root has access to everything.** Unix root does not *know* what a
process is doing; root reads `/proc` while everyone else speculates. If the
failure is retrieval rather than memory, the agent's power has to be retrieval.

> *Guessing is what agents without access do. You are root: every "I don't know"
> is immediately followed by the command that will.*

## Why one agent and not three

Code, devops and docs are three different questions, and it is tempting to make
them three reviewers. They are not split, because **the incidents live at the
seams**: a code change to a deployed file is code+devops; a config change that
falsifies a documented fact is devops+docs. A dispatcher cuts exactly where the
bodies are buried.

## What it cannot do

- **It has no sense of time passing.** It will not notice that something has hung
  for an hour the way you would by getting bored. If duration matters, print it.
- **It anchors on the most recent change.** The co-change data pushes back with
  base rates, but the pull toward *"it must be the thing I just did"* is real.
- **Its tripwires are prompts, not interlocks.** They raise the odds the right
  warning is in front of you. They cannot force it to be read.
- **It only sees text.** `drift.py` is the one place it looks past a label at the
  actual bytes — everywhere else, a filename or a status field is all it gets.

⭐ These are not bugs to file. They are why the receipts exist.
