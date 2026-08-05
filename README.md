# divan/skills

My agent skills, packaged as a Claude Code plugin. Small, composable, hackable.

## Install

Add the marketplace, then install the plugin:

```
/plugin marketplace add divanc/skills
/plugin install divan@skills
```

## Skills

### worktrees

Makes your repo look like this:

```
myrepo/
  main/          # the real clone (.git lives here)
  fix-auth/      # git worktree, branch fix-auth
  perf-web/      # git worktree, branch perf-web
```

One branch = one directory; the outer folder is just a container. The agent understands the layout and works within it: never switches branches inside a worktree, creates a new sibling per task instead, keeps dir names matching branch names.

- **Create** — worktree per branch; knows `.env` and deps need copying/installing.
- **Prune** — removes dead worktrees and merged branches; asks before touching unmerged work.
- **Migrate** — plain clone → this layout, three renames, no re-clone.

Why this beats a single checkout: no stash juggling or branch switching mid-work, every branch keeps its own build state, and parallel agent sessions get separate directories instead of clobbering one checkout.

## License

MIT
