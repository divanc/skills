# divan/skills

Skills for humans.

## Install

Add the marketplace, then install the plugin:

```
/plugin marketplace add divanc/skills
/plugin install divan@skills
```

## Skills

- [big-picture](#big-picture) — design discussions one decision level at a time, ≤10 lines per turn
- [manage](#manage) — run an agreed plan as an orchestrator: workers build, you verify
- [delegate](#delegate) — hand work to a manager agent under a one-screen charter; you accept the result
- [steer](#steer) — check every report against the charter: guard, then one idea
- [handoff](#handoff) — replace a manager whose context is filling, without losing the state
- [worktrees](#worktrees) — one branch = one directory; create, prune, migrate

Plus four [agents](#agents) for the owner → manager → workers setup.

### big-picture

Toggle mode for design discussions and explanations.

Agents approach design with complicated language and a lot of detail at
once. That's exhausting to process and error-prone: it's easy to miss a
detail in a 300-line reply, and the missed detail stays in context and
poisons everything downstream. Volume also flips the roles — the agent
drives, generating context, while the human is reduced to reviewing it.

This skill inverts both. The agent starts at the coarsest decision level —
why build this at all, what it covers — and descends one level per turn,
only after you agree. Each settled decision prunes most of the wrong designs
below it, so detail arrives only where it still matters. And the agent rides
passenger: you feed context, it acts on it or asks corrections — it doesn't
generate walls of it.

- One decision or one question per turn, ≤10 lines.
- Proposes itself on big layered questions; answers normally if you decline.
- `/big-picture <thing>` also works as an explainer: big picture first, then
  details of the part you pick.
- Stays on until "stop big-picture" / "normal mode".

### manage

Runs work that is already understood and agreed, as an orchestrator.

Left alone, an agent implements a plan itself: it sinks into the code, burns
the context it needs later, and grades its own work. This skill keeps it above
the work. Each phase goes to one worker with a brief; the orchestrator reads
the report as a claim, re-runs the checks itself, and accepts only what it
verified.

- **Board** — phase list reprinted as phases land; survives context summaries.
- **Briefs** — state, settled decisions, file ownership, scope, and git rules
  that stop parallel agents clobbering a shared checkout.
- **Verification** — every test watched failing, outcomes over exit codes,
  your check wins over the agent's report.
- **Audits** — mutation testing and adversarial QA before a release.
- **Finish signals** — a worker's last act is a message to the manager; idle
  notices only wake it to go read.
- **Review** — a fresh Codex reviewer per round until every file scores 10/10;
  a critic for anything users see.
- Phases end green: new code lands beside old, old is deleted in its own phase.

### delegate

Hands a piece of work to a manager agent, so your context holds the user's
intent, not the workers' reports.

You write a one-screen charter with the user — the goal in their words, what great
looks like, done-when boxes each with its evidence, hard rules, the decisions
that stay theirs — start a manager in its own session, and accept its result
box by box against the evidence.

- **Charter template** — `skills/delegate/charter.md`; only the owner logs Changes.
- **Quiet** — the user hears at done, or when a decision is theirs.
- **Done** — tested PRs, unmerged, and a demo page.

### steer

Keeps work on its charter. Runs on every report from below, every plan change,
and after a context summary.

Steer re-reads the charter and runs five guard
checks — goal, evidence over claims, rules, drift, decisions that belong to the
user — then one improve check: what the user will ask for next.

- Output: continue, correct, or escalate, plus an optional improve line.
- Every correction quotes the charter line it rests on, or the repo rule
  (check 3) or the brief (check 4); nothing to quote, no correction.
- At most one idea per report; small ones done now, bigger ones go to the user.

### handoff

Past 60% context the manager writes the state to a file, starts a fresh manager
from it, and closes once the new one confirms.

- **State file** — task table with IDs, rules in force, what's left, where things live.
- **Verify first** — the new manager checks the file against live terminals and
  PRs; the world wins.
- Workers and the owner are told the new session name.

### worktrees

Makes your repo look like this:

```
myrepo/
  main/          # the real clone (.git lives here)
  fix-auth/      # git worktree, branch fix-auth
  perf-web/      # git worktree, branch perf-web
```

One branch = one directory; the outer folder is just a container. The agent
understands the layout and works within it: never switches branches inside a
worktree, creates a new sibling per task instead, keeps dir names matching
branch names.

- **Create** — worktree per branch; knows `.env` and deps need copying/installing.
- **Prune** — removes dead worktrees and merged branches; asks before touching unmerged work.
- **Migrate** — plain clone → this layout, three renames, no re-clone.

Why this beats a single checkout: no stash juggling or branch switching
mid-work, every branch keeps its own build state, and parallel agent sessions
get separate directories instead of clobbering one checkout.

## Agents

For the 3-layer setup: you (the owner, with `delegate` and `steer`) → a manager
→ workers. Tools and `hooks/limits.py` enforce what the table lists, and
[Gaps](#gaps) names what they don't. Workers and the manager run as Paradev sessions (`claude --agent
divan:<name>`); the reviewer and critic are the manager's subagents.

Requirements:

- Paradev, for the `superset` CLI that launches and watches sessions.
- Claude Code 2.1.295 or later, and `python3` 3.9 or later, for the hook. The
  hook fails closed: without `python3`, Bash, Write, Agent and Workflow calls
  are blocked in every session that loads the plugin.
- Codex CLI 0.169 or later (`codex exec`, `codex review`), for the reviewer.
- Owner and manager in the same permission-mode class with inbound messages
  allowed, or `crossSessionInbound: accept`; otherwise Claude Code holds or
  refuses their messages. Check the delivery notice.

| agent | does | can't | enforced by |
|---|---|---|---|
| manager | briefs workers, verifies, runs checks, steers | edit, commit, merge, fetch, write outside its `briefs/` | tools (no Edit); hook: Write only in the `briefs/` beside `charter.md`; git/gh writes and writing Bash commands blocked |
| worker | one briefed task in its worktree | merge; push to `main` or `deploy`, without a remote and branch, or with options beyond the common ones; `add -A`, `commit -a`, `stash` (but `list`, `show`), `checkout .`, `reset --hard`, `clean -f` | hook |
| reviewer | scores files with Codex, returns findings | change files; run Codex outside its read-only sandbox | tools; hook |
| critic | judges what users see against the charter | edit, post, click, `curl` | tools (WebFetch, Slack read-only); hook: the browser only looks; screenshots only to the evidence folder or `$TMPDIR` |

The hook also checks commands inside wrappers (`env`, `xargs`, `bash -c`, ...),
and blocks unknown git global options and unknown options on wrappers, shells
and `curl`. The exact rules are in `hooks/limits.py`.

No divan agent merges: `gh pr merge` is blocked for all four. Your own session
isn't limited, even when it spawns divan subagents. Any other subagent a divan
agent spawns (general-purpose, Explore, ...) runs under that agent's limits; a
reviewer or critic keeps its own.

### Gaps

- The hook matches Bash as command text, so a command that writes through its
  own syntax still gets past it: `sed`'s `w`, a test, a script, or a command
  fed in as data (`echo cmd | xargs sh -c '{}'`).
- Git config can still redirect: repo or environment config
  (`remote.<name>.push`, `GIT_CONFIG_PARAMETERS` exported earlier) a worker's
  push; a repo's `diff.external` or `textconv` a reader's `git diff` or
  `log -p`.
- Nothing confines a worker to its brief's files.
- Agents started by the Workflow tool are untested against these limits.
- Agents run on the owner's GitHub credentials, so GitHub can't tell an agent
  merge from yours: the hook is what stops it. Require a PR and a review on
  `main` and `deploy` so a push the hook misses still can't land.

## License

MIT
