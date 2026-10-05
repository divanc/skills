---
name: manage
description: Use when implementing work that is already understood and agreed.
---

# Managing a piece of work

No plan yet? Settle it with the user in a few lines first: the phases, what each lands, their order.

**You do not implement.** Editing files puts you inside the work instead of above it, and spends the
context you need later to argue with a report or recall an early decision. Exception: a change
smaller than its brief.

## The loop

For each phase:

1. **Brief and launch** one subagent.
2. **Read the report** as a claim, not a result.
3. **Verify it yourself.** Re-run the check that matters. Read the diff.
4. **Decide**: accept, send back, or change the plan.
5. **Commit** by explicit path, and reprint the board.

Never report to the user before you have the agent's result.

**The board** — reprinted whenever a phase lands or the user asks:

```
[x] 1  schema + migration      done, committed 4a1f2c
[x] 2  server contract         done, committed 90bb7e
[>] 3  client rewrite          agent running (port 3021)
[ ] 4  audit: mutation pass
[ ] 5  adversarial QA          two agents, parallel
```

After a context summary, the board plus the commits is enough to resume. Each brief's `State` line
is copied from it; writing that line from memory means you skipped step 5.

## Sizing a phase

A phase ends at a commit that leaves the tree green. If it cannot, build the new thing beside the
old one and delete the old one in its own later phase. While both run, every check still runs
against something that works, so a regression is attributable the day it appears.

## Writing a brief

A skeleton, not a form:

```
Phase N of <the work>: <one line>.

State: <what landed, what is committed, what is green>.
Decided already, do not revisit: <list>.
Build: <the work>.
Yours: <files>. Not yours: <files, and whose>.
Out of scope: <list> — that is phase <M>.
Traps: <the ones you know>.
Rules: stage explicit paths; never `git add -A`, `git add .`, `git commit -a`. Never `git stash`,
`git checkout .` or a pathless `git restore` — the checkout is shared; compare with `git worktree`
or `git show HEAD:path`. Do not commit. Kill every process you start and report the count. Use a
free port and name it. Work on a copy of any real database (`cp -c`), never the live one.
If something outside your files must change, stop and report — do not change it.
The user approved this direction — decide and act, do not defer.
Verify: <commands>. Paste the real output.
Report: what you built, the verification output, what you found and deliberately did not fix,
and any decision you need from me.
```

Hand judgement calls down with their reasoning and require the decisions back. Centralising them is
how you start implementing again.

## Adapting the plan

Announce every plan change in one line — a phase split, a gap-closing phase, a phase pulled
forward. The user holds the old plan until you do.

**Sending a phase back.** One detail wrong, or a rule changed: message the running agent; it keeps
its context. Frame misunderstood, or the phase is really two: kill it and write a fresh brief.
A user decision made mid-flight goes to the running agent now.

## Verification

Gate every phase on the repo's real checks. A phase may gate on a subset only if the full run gates
at the end, and the board says so.

- **Watch every test and guard fail before trusting it**: break the thing, see it caught, revert.
- **Verify in the environment the claim is about.** CI green on machines with a cached model went red
  on its first cold runner.
- **Verify the outcome, not the exit code.**

**When the report and your check disagree, your check wins**, and the gap is the finding. Don't ask
the agent to explain; re-run against a clean tree, then check which tree, database and exit code the
agent relied on.

**The "deliberately did not fix" list is the most reliable part of a report**; the summary is the
least. Each item becomes a phase or an explicit decline to the user — left in the transcript, it is
lost at the next summary.

### Audit agents

Before a release, and on any phase whose only tests were written by the agent that wrote the code.

- **Mutation testing**: mutate production code, report which mutations no test notices. Green
  phases still hide survivors.
- **Adversarial QA**: one agent against the API, one in a real browser, told to find what is broken,
  not confirm it works.

## Parallelism

Independent work goes out at once. Split by file before splitting by phase: changes sharing a file
land in one commit and cannot be verified or reverted alone. Two phases needing one file run in
sequence.

## Reporting

Lead with the verdict, then the two or three things that matter, then the decision you need — not a
retelling of the agent's report.
