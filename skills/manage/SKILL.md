---
name: manage
description: Use when implementing work that is already understood and agreed.
---

# Managing a piece of work

No plan yet? Settle it with the user in a few lines first: the phases, what each lands, their order.

**You do not implement.** Editing files puts you inside the work instead of above it, and spends the
context you need later to argue with a report or recall an early decision. Exception, where your tools
allow it (not as `divan:manager`): a change smaller than its brief.

## The loop

For each phase:

1. **Brief and launch** one worker.
2. **Read the report** as a claim, not a result. Run `steer` on it when the work has a charter.
3. **Verify it yourself.** Re-run the check that matters. Read the diff.
4. **Decide**: accept, send back, or change the plan.
5. **Land it** and reprint the board. Workers commit on their branches by explicit path; integrating onto
   the PR branch is a worker's brief like any other. You read the commit. Without workers (not as
   `divan:manager`), commit by explicit path yourself.
6. **Close the worker** once its work is integrated: `superset terminals close --local --workspace <id>
   --terminal <id>`. A finished worker left open is one more terminal the next reader must tell apart from
   live work.

Never report to the user before you have the agent's result.

Workers are Paradev sessions running `divan:worker`. The agent holds the limits; the brief holds the task:

```
superset ws create --local --project <id> --name <name> --branch <branch> --base-branch <PR branch> \
  --skip-branch-prefix --json \
  --command "claude --dangerously-skip-permissions -n <task> --agent divan:worker 'Read your brief at <path>, check your starting commit against its State, and do it.'"
```

`-n <task>` is the session name `ListAgents` shows and `SendMessage` takes. No quotes in the prompt; the
brief file carries the rest. The output's `terminals[0].terminalId` is the `<id>` the `superset` commands
below take as `--terminal`.

Reviewers and critics are your subagents: the `Agent` tool with `subagent_type` `divan:reviewer` or
`divan:critic`.

**The board** — reprinted whenever a phase lands or the user asks:

```
[x] 1  schema + migration      done, committed 4a1f2c
[x] 2  server contract         done, committed 90bb7e
[>] 3  client rewrite          agent running (port 3021)
[ ] 4  audit: mutation pass
[ ] 5  adversarial QA          two agents, parallel
```

After a context summary, resume from the board and the commits; under a charter, also the charter and
the last report's evidence, then run `steer`. Each brief's `State` line is copied from the board; writing that line from memory
means you skipped step 5. Under a charter, past 60% context, run `handoff` before the summary comes.

## Finish signals

Every brief ends with the report envelope below; the worker's DONE or BLOCKED message is the signal.

At launch, subscribe with `SendMessage(to: <task>, notify_when_idle: true)` and no message. To block on
one worker, `superset agents wait --local --workspace <id> --terminal <id> --until settled`. Both are
wake-ups, not proof of done: a worker settles when it ends a turn, including one that leaves a background
shell or nested `claude -p` session running. Woken without a DONE or BLOCKED, read its screen (`superset
terminals read --local --workspace <id> --terminal <id>`). The notice is one-shot and arrives only after
your turn ends; re-subscribe.

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
`git checkout .` or a pathless `git restore` — the stash stack is shared by every worktree, and the
checkout may be; compare with `git worktree` or `git show HEAD:path`. Commit only on your branch. Kill
every process you start and report the count. Use a free port and name it. Work on a copy of any real
database (`cp -c`), never the live one.
If something outside your files must change, stop and report — do not change it.
The user approved this direction — decide and act, do not defer.
Verify: <commands>. Paste the real output.
Report: your last action is a SendMessage to `<my session name>`, then print the same text:
  DONE <task>   (or BLOCKED <task>)
  summary: <one line>
  commit: <sha> on <branch>
  files: <paths>
  checks: <what you ran; the real output or a path to it>
  not fixed, on purpose: <list or none>
  needs: <a decision from me, or none>
```

Hand judgement calls down with their reasoning and require the decisions back. Centralising them is
how you start implementing again.

## Adapting the plan

Announce every plan change in one line — a phase split, a gap-closing phase, a phase pulled
forward. The user holds the old plan until you do. Under a charter, announce it on the board; one that
changes scope or a Done-when box goes to the owner as a proposed Changes entry.

**Sending a phase back.** One detail wrong, or a rule changed: message the running agent; it keeps
its context. Frame misunderstood, or the phase is really two: kill it and write a fresh brief.
A user decision made mid-flight goes to the running agent now.

## Verification

Gate every phase on the repo's real checks. A phase may gate on a subset only if the full run gates
at the end, and the board says so.

- **Watch every test and guard fail before trusting it**: break the thing, see it caught, revert.
  As `divan:manager`, a worker breaks it; you read the output.
- **Verify in the environment the claim is about.** CI green on machines with a cached model went red
  on its first cold runner.
- **Verify the outcome, not the exit code.**

**When the report and your check disagree, your check wins**, and the gap is the finding. Don't ask
the agent to explain; re-run against a clean tree, then check which tree, database and exit code the
agent relied on.

**The "deliberately did not fix" list is the most reliable part of a report**; the summary is the
least. Each item becomes a phase or an explicit decline to the user — left in the transcript, it is
lost at the next summary.

### The reviewer loop

Every PR, before it goes up. Each round is a fresh `Agent` call to `divan:reviewer` (it runs Codex),
given the changed files and the charter's Great (without a charter, the agreed acceptance criteria), not
the writer's report or reasoning. It returns `score: N/10` per file with findings. Below 10, the findings
go to the worker and a new reviewer scores the fix. Stop at 10/10 on every file; quote the final verdict
in the PR.

### The critic

What users see (Slack messages, UI) also goes to a `divan:critic` subagent, judged against the charter's
references (without a charter, the agreed acceptance criteria and the user-facing references), PASS or
FAIL per reference with quoted evidence. Tests prove it works, not that it reads right.

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
