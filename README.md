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

One branch = one directory. Wrapper folder holds `main/` plus one worktree per branch, named after it.
No stash juggling, no branch switching mid-session, and parallel agent sessions get separate checkouts instead of fighting over one.

The skill teaches the agent the convention and its lifecycle:

- **Create** — worktree per branch; knows `.env` and deps need copying/installing.
- **Prune** — removes dead worktrees and merged branches; asks before touching unmerged work.
- **Migrate** — plain clone → this layout, three renames, no re-clone.

## License

MIT
