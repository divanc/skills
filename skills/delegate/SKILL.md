---
name: delegate
description: Use when you own a piece of work and hand it to a manager agent instead of running the workers yourself.
---

# Delegating to a manager

You are the owner. The user talks to you, the manager runs the workers, and you hold the charter and accept the
result. You brief no worker and implement nothing: your context is for the user's intent and the verdict.

## 1. Write the charter

Before any agent starts. Copy `charter.md` from this skill's folder to `<evidence folder>/charter.md` and settle
each field with the user in a few lines.

- **Goal** in the user's words.
- **Done when**: each box names its evidence.
- **Ask the user only for**: the decisions that stay theirs. Everything else, you and the manager decide.

One screen. Link the long spec; don't paste it. Only you append to Changes, dated.

## 2. Brief the manager

Write the brief to `<evidence folder>/briefs/manager.md` and start the manager as its own session, so its
context is not yours:

```
superset ws create --local --project <id> --name <name> --branch <branch> --json \
  --command "claude --dangerously-skip-permissions -n <manager name> --agent divan:manager 'Read your brief at <path> and do it.'"
```

The brief:

```
You manage <the work>. Load `manage` and `steer`.
Charter: <evidence folder>/charter.md. Re-read it at every report.
Evidence folder: <path>. Briefs go in <path>/briefs/.
State: <what exists, what is decided>.
Report to me (<owner name>) by SendMessage: DONE or BLOCKED with evidence per Done-when box,
a decision from the Ask list, or a proposed Changes entry. Nothing else needs me.
```

Keep the workspace ID and `terminals[0].terminalId` from its JSON. On a handoff ("I manage <work> now..."), replace
the saved name and IDs with the new manager's and subscribe again. Subscribe with
`SendMessage(to: <manager name>, notify_when_idle: true)`; block with `superset agents wait --local
--workspace <id> --terminal <id> --until settled`; never a screen poller. By default Claude Code holds messages
from a session in another permission-mode class: run the owner in the manager's mode class, or set
`crossSessionInbound: accept`. Check each delivery notice.

## 3. While it runs

Run `steer` on every manager message. `correct` and a small `improve` go back to the manager. `escalate` and a
proposed Changes entry go to the user: the decision, its options, your recommendation, in a few lines. Their
answer goes into Changes, dated, and to the manager at once.

The user hears from you only at done and when their decision is needed. Asked for status, give the
manager's board, not a retelling.

## 4. Accept

Open each Done-when box's evidence yourself: re-run the command, look at the screenshot, read the PR's checks. A box
whose evidence you have not seen stays open and goes back to the manager.

Done is:

- **Tested PRs**: open, CI green, the repo's checks run with their real output in the PR body, reviewed to the
  charter's Great. The user merges; no divan agent can (a hook blocks it).
- **A demo artifact**: one page that shows the result as its user sees it, each Done-when box with its
  evidence, before and after. Publish it and link it.

## 5. Report and close

To the user: the verdict, the PRs, the demo link, what is left with its issue numbers, and the decisions you need
(the merge). Then close the manager: `superset terminals close --local --workspace <id> --terminal <id>`.
