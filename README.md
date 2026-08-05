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
- [unslop](#unslop) — strip agent-written docs of claims no human approved
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

### unslop

Cleans agent-written docs of "poison" — context no human approved.

Agents write reference docs (ADRs, plans, notes) and later read them back as
truth. Along the way they smuggle in claims nobody decided: a "probably X"
that hardened into "we use X", a timeout that was never chosen, a constraint
the agent invented for itself. Those claims then steer future agent decisions
in ways you didn't intend.

Unslop scans docs in two passes:

- **Auto-clean** — removes what's harmless to remove: hedges-turned-facts,
  invented numbers, filler adjectives, prose restating code. Shown as a diff.
- **Ask** — anything whose removal could delete a real decision gets one
  question: keep, reword, cut, or skip. Your answer is the source: "we need
  to support themes" turns "a light theme is wanted" into "Theme support is
  planned." Kept claims are stamped `[approved @you <date>]` and never asked
  again; skipped ones stay unmarked and resurface next run.

Markers alone would be forgeable — agents mimic patterns they see — so the
truth lives in a sidecar `.unslop` file: a hash of each approved claim,
written only by the skill. A marker whose text doesn't hash-match the sidecar
is treated as unapproved and re-reviewed; editing an approved claim
invalidates it the same way.

Stop anytime — unmarked text just resurfaces next run, so every session is
resumable for free. A fully cleaned doc gets a header telling agents to treat
it as trusted, backed by a whole-doc hash in the sidecar — edit the doc and
it's flagged stale on the next run. Running on an already-clean target prints
a status report instead: `4 clean, 1 stale, 2 never reviewed`.

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
