# quiz_game / plan

Turn the approved proposal into `video.yaml`.

- Start from `va/pipeline_defs/templates/quiz_game.video.yaml` (`va new` copies it).
- Timeline: `Hook` first (hook text visible within the first 2 s), one `Round` per approved round, `CTA` last.
- `Round` props: `id`, `src`, `in`, `out`, `answer_at`, `clue`, `answer`, `winner` (A | B | AB | none), optional `clue_sticker: {image|search}`.
- Anchor b-roll to clues: `- BRoll: {query: "...", at: r1.clue, dur: 1.2, mode: cutaway}`.
- Overlays: `Scoreboard` (scores are derived from winners) and `ProgressBar`.
- Checks: total inside `target_seconds`, hook in first 2 s, CTA last. Run `va build --preview` first.
