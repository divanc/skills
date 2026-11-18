---
name: handoff
description: Use when a manager's context passes 60%, or when a manager is told to take over from another one.
---

# Handing off a manager

A manager runs on IDs, rules and gates it holds in context. A context summary drops those first, so hand
off before one: past 60% context, at a break where no report is half-read. After a summary is too late; the
file can only hold what you still have.

## 1. Write the state

To `<evidence folder>/briefs/handoff.md`. The reader has none of your context: every ID exact, every path
absolute, nothing "as discussed".

```
# Handoff: manager of <work>, <date, time UTC>

Owner: <session name> (SendMessage). Merges: <who>. Old manager: <session name>, terminal <id>,
workspace <id>. Read first: <charter path>, <issue or spec>.

## Shipped
- <PR or commit>: <one line>.

## Open tasks
| task | state | branch | workspace | terminal (session name) |

## Rules in force
- <rule>: <its number and reason>.

## Left, in order
1. <step>: <its gate>.

## Where things live
<evidence, tools and what each does, threads, memory files>

## Terminals
Kept alive: <ids, why>. Closed: <ids>. Not mine, leave alone: <ids, whose>.
```

- **State says what happens next and who gives the go**: "mid-task; live runs wait for your go", not "in
  progress".
- **Each rule carries its number and reason**: "at most 4 runs an hour; stop at the first 429". The reason
  lets the new manager apply it to a case you never met.
- **"Not mine, leave alone"** stops the new manager closing a terminal it doesn't recognise.

Link the charter and briefs; don't copy them. The file is the state, not the history.

## 2. Launch the fresh manager

You launch it, in your workspace:

```
superset terminals create --local --workspace $SUPERSET_WORKSPACE_ID --json \
  --command "claude --dangerously-skip-permissions --agent divan:manager 'Load the handoff skill and take over from <handoff path>.'"
```

Same workspace, so it has your worktree and evidence folder. No quotes in the prompt; the file names you for
`TOOK OVER`. The output's `terminalId` is what step 4's `agents wait` takes.

Not `--from-terminal`: it seeds the session with the last 36k characters of your screen, mostly tool
output, which is the context you are handing off to escape. The file is the state.

From launch, act on nothing. Two managers on one board give conflicting orders.

## 3. Take over (the new manager)

Read the handoff file in full, then the charter. The file is a claim written from a full context. Before
acting, check each row against the world:

- `superset terminals list --workspace <id>` per task: the terminal is alive, the agent is where the file
  says.
- `gh pr list`, `git log` per branch: what is open, what is committed.
- Anything the file says is running (a review, a deploy): look at it.

Where they disagree, the world wins: fix the file and name the mismatch in your messages.

Then, in order:

1. SendMessage the old manager: `TOOK OVER`, plus any mismatch.
2. SendMessage the owner: "I manage <work> now, taking over from `<old name>`; state in <handoff path>."
   The owner replies to the name on that message.
3. SendMessage every live worker: "Your manager is now `<your name>`; send DONE or BLOCKED here." Their
   briefs name the old manager.
4. Re-subscribe `notify_when_idle` on each worker. Subscriptions die with the session that made them.

## 4. Close (the old manager)

On `TOOK OVER`, close your own terminal:

```
superset terminals close --local --workspace $SUPERSET_WORKSPACE_ID --terminal $SUPERSET_TERMINAL_ID
```

No `TOOK OVER` by the time `superset agents wait --terminal <new> --until settled` returns: read its
screen (`superset terminals read`), fix what stopped it, relaunch.
