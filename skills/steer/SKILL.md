---
name: steer
description: Use on every report from an agent below you, on any plan change, and after a context summary, before you accept, forward or act on it.
---

# Steering against the charter

Re-read `charter.md` in the work's evidence folder first, whole. Your memory of it drifts; the file does not.
After a context summary, the summary is a claim too: re-read the charter and the last report's evidence.
On a plan change, run checks 1, 4 and 5 on the new plan before announcing it.

## Guard

Run each on the diff and the actions taken (commits, PRs, pushes, posts), not on the summary.

1. **Goal.** Which Done-when box does this move? None: it is off the path.
2. **Great, by evidence.** "Done", "passes", "verified" from below are claims. Evidence is a command's real output
   you re-ran, a screenshot of what the user sees, a test watched failing before it passed, a diff you read.
   A pass against a narrower bar (a rubric, a reviewer's score) is not Great: judge against the charter's words.
   A ready PR claims done; each box it closes needs its evidence first.
3. **Rules.** Each line of the charter's Rules and of the repo's own rules (`CLAUDE.md`, `AGENTS.md`) against
   the diff. A breach is a breach however good the work around it.
4. **Drift.** What was built against what was briefed. Scope that grew, shrank or swapped without a line saying
   so is drift, even when it is better.
5. **Ask list.** Is someone below making a decision the charter's "Ask the user only for" keeps for the user?
   An irreversible setting, money, a merge: it stops and goes up.

## Improve

6. Look at the result as its user will: what they will wait on without seeing it move, want to stop, have to read
   twice, or pay for without knowing. The fix they would ask for next is the idea; propose it before they ask.
   Small and inside the Goal: do it now. Bigger, or it changes a Done-when box: propose a Changes entry; the user
   decides. At most one idea per report.

## Output

The first failing check decides: 5 escalates, 1-4 correct, 6 improves, none continues. A correction lists every
failed check. Each line quotes the charter line (or, for check 3, the repo rule) it rests on; nothing to quote,
no correction.

```
continue
correct: <check>: <what is wrong, what to do>. "<charter line>"
improve: <the idea>; <now | proposed Changes entry>. "<charter line>"
escalate: <the decision, its options, your recommendation>. "<charter line>"
```

A correction goes to the agent that reported, which keeps its context. An escalation goes to whoever owns the
decision: the owner, or through the owner to the user.
