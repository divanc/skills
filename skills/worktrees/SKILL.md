---
name: worktrees
description: Use when the repo is a worktree wrapper (main/ holds the real .git), or for any git worktree request — create, remove, prune, migrate a plain clone to this layout.
---

# Worktrees

Wrapper layout: outer dir is NOT a repo — plain folder with one subdir per branch. `main/` holds the real `.git` (a directory); siblings are linked worktrees (their `.git` is a file). Worktree dir name == branch name, always.

Detect: outer dir has `main/` whose `.git` is a directory; `git -C main worktree list` shows the siblings.

## Rules

- Work happens on the branch matching the subdir name. Never `git switch` inside a worktree — create a new worktree instead.
- Same branch can't be checked out in two worktrees at once.
- Never `rm -rf` a worktree — leaves stale metadata in `main/.git/worktrees/`. Use `git worktree remove`. If already deleted by hand: `git -C main worktree prune`.
- Before starting new feature work, ASK whether to create a new branch + worktree rather than working in the current one.

## Create

```sh
cd <wrapper>/main
git worktree add ../<name> -b <name>    # new branch
git worktree add ../<name> <name>       # existing branch
```

Gitignored files don't come along: copy `.env*` from main, install deps (`pnpm i` / `npm ci`).

## Prune

1. `git -C main worktree list` — registered worktrees.
2. Compare with actual subdirs. Dirs not in the list (and not `main/`) with no `.git` = leftovers from a hand-deleted worktree — safe to `rm -rf` those. A dir with its own `.git` *directory* is a standalone repo parked in the wrapper — leave it, mention it to the user.
3. `git -C main worktree prune` — clears metadata for missing dirs.
4. For each registered worktree: merged into main and clean (`git status --porcelain` empty)? → `git -C main worktree remove ../<name>`, then `git branch -d <name>` if branch no longer needed. Dirty or unmerged → ask before touching.

## Migrate (plain clone → wrapper)

From the clone's parent dir:

```sh
git -C <repo> status --porcelain          # preflight; dirty is OK, but know what's there
git -C <repo> worktree list               # existing worktrees? they need `git worktree repair` after the move
mv <repo> <repo>.tmp && mkdir <repo> && mv <repo>.tmp <repo>/main
```

If linked worktrees existed pre-move: `git -C <repo>/main worktree repair`.

If the clone was on a feature branch: `git -C <repo>/main switch main` (untracked files survive checkout), then create the feature branch as a proper worktree per Create.

Finish: verify `git -C <repo>/main worktree list` and `git -C <repo>/main status`.