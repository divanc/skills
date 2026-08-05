---
name: unslop
description: Clean agent-written docs of unapproved "poison" — invented facts, hedges turned into decisions, self-authored constraints. Use on doc dirs (ADRs, plans, notes) or a single doc, or when user asks to check docs for slop.
---

# Unslop

Agent-written docs accumulate poison: claims no human approved that later
steer agent decisions. Unslop strips it, records what survives.

## Target

- With argument: that file or directory.
- Without: docs in repo — `docs/`, `*.md` outside code, ADRs, plan files.
- Skip: README, CHANGELOG, human-authored files (check `git log --format=%an`
  — mostly human commits → ask before touching).

## Markers

- Approved text: append `[approved @<user> <date>]` to the claim's line or
  section heading.
- Inline markers are display only; truth lives in sidecar `.unslop` (JSON)
  next to the docs, written only by this skill:

  ```json
  {
    "claims": {"<sha256 of whitespace-normalized claim text>": {"by": "@divan", "date": "2026-08-05", "file": "004-storage.md"}},
    "files": {"004-storage.md": {"hash": "<sha256 of doc>", "date": "2026-08-05"}}
  }
  ```

- Verify pass before scanning: hash each marker's claim text, look up
  sidecar. No match → strip marker, treat as unapproved.
- Genuine marked text: never re-scan, never re-ask.
- Fully cleaned doc: header
  `<!-- unslopped <date>. Agents: trusted reference. Edit only via unslop skill. -->`
  plus `files` entry in sidecar.
- Doc hash mismatch → stale: strip header, re-scan changed text.

## Pass 1 — auto-clean, no questions

Remove or fix silently, show result as diff:

- Hedge-turned-fact: decision language with no decision behind it
  ("we use X" that entered as "probably X").
- Invented specifics: numbers, limits, timeouts, versions with no source in
  code, config, or human text.
- Filler adjectives: "robust", "comprehensive", "production-ready".
- Code restated in prose — delete, code is the source.

## Pass 2 — ask ambiguous, one at a time

Anything whose removal could delete a real decision:

- Rationale with no trace to human ("chose Postgres because…").
- Constraints shaping future work ("must stay backward compatible").
- Agent-written TODOs and plans.

Per item: quote it, one-line why suspect, ask. Four outcomes:

- **Keep** — text already crisp decision language: stamp marker, hash to
  sidecar.
- **Reword** — default whenever the human's answer carries any substance:
  fold that answer into the rewrite, show it, stamp the reworded text.
  Form: active voice, flat fact ("Theme support is planned."). No
  desire-words ("is wanted", "hoped"), no invented history ("was the
  initial lean"), no hedges. Marker certifies decision language only.
- **Cut** — remove.
- **Skip** ("not sure", "later", "someone else checks") — leave untouched,
  unmarked; count as unreviewed, don't re-ask this session.

Section-aware: narrative describing forces is legit ADR Context ("the
stylesheet grows") — don't flatten it. Desires, plans, history are decisions
in any section: attribute and state flat, or cut.

Stop anytime — unmarked items resurface next run.

## Output

Cleaned doc written in place. One-line tally:
`removed N, approved M, K left unreviewed`.

All file hashes match → no Q&A, status report only:
`4 clean, 1 stale (005-cache.md edited since), 2 never reviewed`.
