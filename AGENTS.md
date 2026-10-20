# AGENTS.md: the VideoAgent contract

You are the orchestrator. Python gives you tools and persistence; pipelines (YAML) and
director skills (Markdown) tell you what to do at each stage. There is no hidden orchestrator.

## Rules

1. Pick a pipeline first (`va/pipeline_defs/*.yaml`), then read its manifest and the stage skill in `va/skills/<pipeline>/` before calling tools.
2. Never improvise outside the pipeline; propose a new component instead.
3. Stop at every approval gate (`gate: user_approval*`) and wait for the user.
4. Lock the render runtime at proposal; never swap silently.
5. Never spend above `BUDGET_APPROVE_ABOVE_USD` without approval.
6. Never publish without explicit approval. `va deliver` only writes files.
7. Log every decision with alternatives and reasons in `projects/<name>/decisions.jsonl`.
8. Never present a render that failed QA (`va qa` exits non-zero).
9. Renders go to local temp storage first, then copy (the compositor already does this).

## Flow

```bash
va new <name> --pipeline quiz_game
va analyze <name> --footage inputs/game.mov --ref <url|file>
va plan <name> --idea "..."        # writes proposal.md -> STOP for approval
# edit projects/<name>/video.yaml from analysis/*.json (rounds, anchors, text)
va assets <name>
va build <name> --preview           # fast check, then without --preview
va qa <name>                        # look at out/qa/contact.jpg yourself
va deliver <name>                   # STOP: ask before publishing anywhere
```

## Editing the spec

- One file, `video.yaml`. A fix is a one-line edit and a re-render.
- `timeline` items play back to back (Hook, Round, Segment, CTA). Others anchor with `at: <id>.<event>` (events: start, clue, answer, end) or seconds.
- Never type derived values (scores, start times, sync points). They are computed.
- `va components` lists every component and its props; `va schema` writes JSON schemas.
