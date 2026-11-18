---
name: steer
description: Use on every report from an agent below you, on any plan change, and after a context summary, before you accept, forward or act on it.
---

# Steering against the charter

Re-read `charter.md` in the work's evidence folder first, whole.
After a context summary, also read the last report's evidence.
On a plan change, run checks 1, 3, 4 and 5 on the new plan before announcing it.

## Guard

Run each on the diff and the actions taken (commits, PRs, pushes, posts), not on the summary.

1. **Goal.** Which Done-when box does this move? None: it is off the path.
2. **Great, by evidence.** "Done", "passes", "verified" from below are claims. Evidence is a command's real output
   you re-ran, a screenshot of what the user sees, a test watched failing before it passed, a diff you read.
   A pass against a narrower bar (a rubric, a reviewer's score) is not Great: judge against the charter's words.
   A ready PR claims done; each box it closes needs its evidence first.
3. **Rules.** Each line of the charter's Rules and of the repo's own rules (`CLAUDE.md`, `AGENTS.md`) against
   the diff.
4. **Drift.** What was built against what was briefed. Scope that grew, shrank or swapped without a line saying
   so is drift, even when it is better.
5. **Ask list.** Is someone below making a decision on the charter's "Ask the user only for" list? It stops and
   goes up.

## Improve

6. Look at the result as its user will: what they will wait on without seeing it move, want to stop, have to read
   twice, or pay for without knowing. Propose the next fix they would ask for, before they ask.
   Small and inside the Goal: do it now. Bigger, or it changes a Done-when box: propose a Changes entry; the user
   decides. At most one idea per report.

## Output

The guard sets the verdict: check 5 failed escalates, never corrects; else 1-4 failed corrects; else continue.
A correction lists every failed check. An improve line, when check 6 finds one, rides with any verdict. Each line
quotes the charter line it rests on (check 3 may quote the repo rule, check 4 the brief); nothing to quote, no
correction.

```
continue
correct: <check 1-4>: <what is wrong, what to do>. "<charter line>"
improve: <the idea>; <now | proposed Changes entry>. "<charter line>"
escalate: <the decision, its options, your recommendation>. "<charter line>"
```

A correction goes to the agent that reported, which keeps its context. An escalation goes to whoever owns the
decision: the owner, or through the owner to the user.
