# agent-root — operating instructions for any AI assistant

<!-- The cross-tool convention: Claude, Copilot, Codex and Cursor all read this
     filename. Knowledge that lives only in a tool-specific file cannot travel to
     the repos where that tool is not approved. -->

## What this repo is

Agent Root is a resident reviewer you install into a repository. It reads the
repo's own recorded traps, checks whether the files you edited are the files
actually running, and reports what history says usually changes alongside them —
then hands a verdict backed by fields that can only be filled from command
output. It exists because an LLM cannot tell recall from confabulation: there is
no internal signal separating a remembered fact from an invented one, so this
tool is built to make the *absence of checking* visible rather than to be more
careful.

⚠️ **This repo is installed into other people's repositories.** A bug here is not
a bug in one codebase; it is a wrong review delivered confidently in every repo
that installed it. That is why `install` refuses a partial source, why an
unconfigured `drift.py` reports "nothing was checked" instead of a tick, and why
nothing in `scripts/` ever writes to the repo it is reviewing.

## Before acting

```bash
python scripts/traps.py --domains
python scripts/traps.py <domain>
```

Traps are recorded in situ with a `⚠️` marker, and design rationale with `⭐`.
When something bites, the fix is not only the code — it is the marker, because
that is what makes the lesson retrievable next time.

## Operating rules

*(EMPTY ON PURPOSE. Rules are earned, never seeded. Each one added here should
cite the incident that bought it. A rule copied in because it sounds wise is
wallpaper by the second week.)*

## Where things are

| Domain | Start here |
|---|---|
| | |

## Never, here

*(The things that have actually gone wrong. Also empty until they have.)*

---

⚠️ **Hard cap: 120 lines.** This file is loaded on every session, so every line
is paid for forever. Adding a rule means evicting one.
