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
- [manage](#manage) — run an agreed plan as an orchestrator: subagents build, you verify
- [worktrees](#worktrees) — one branch = one directory; create, prune, migrate

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
the work. Each phase goes to one subagent with a brief; the orchestrator reads
the report as a claim, re-runs the checks itself, and commits only what it
verified.

- **Board** — phase list reprinted as phases land; survives context summaries.
- **Briefs** — state, settled decisions, file ownership, scope, and git rules
  that stop parallel agents clobbering a shared checkout.
- **Verification** — every test watched failing, outcomes over exit codes,
  your check wins over the agent's report.
- **Audits** — mutation testing and adversarial QA before a release.
- Phases end green: new code lands beside old, old is deleted in its own phase.

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

## License

MIT
