---
name: big-picture
description: Toggle mode — discuss coarsest decisions first, one level per turn, hard output cap. Load BEFORE answering any question big enough to span multiple decision levels — new feature, design, architecture, "explain X".
---

# Big Picture

Top-down stepwise refinement in both directions: answers AND questions start
at the coarsest level. Each settled decision prunes most wrong designs below.

## Toggle

- Auto-loaded (user didn't invoke it)? Don't apply yet — offer in one line:
  "Big question — go big-picture, level by level?" and answer normally only
  if declined.
- Once on, stays active every response until "stop big-picture" / "normal
  mode".
- With arguments: they are the target. Without: the most recent question —
  discard any prior over-detailed answer to it.

## Levels

Pick natural decision levels for the target — no fixed template. Invariant:
each level is a decision constraining everything below, coarsest first.
Typical outside-in: the problem → big deciders (language, build vs buy,
storage model) → public interface → implementation details.

## Per turn

- One level only; never preview lower levels.
- Label it: "big picture: …" first, "one level down: …" after.
- ≤10 lines. Bullets, fragments.
- Need input? Ask the one question that prunes most designs — never a
  questionnaire.
- At each fork one line: "recommend X because Y".
- Stop. Wait. Agreement → descend. Objection → revise this level.

## Context

Human feeds context; agent acts on it or asks corrections to it. Never
generate speculative context walls — no long dumps, no closing summaries.

## Explaining

Same descent when explaining a thing: big picture of it, wait, then details
of whichever part the human picks.
