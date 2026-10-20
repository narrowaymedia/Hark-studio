# quiz_game / analyze

Goal: find every round (question -> answer -> reaction) in the footage.

1. `va analyze <name> --footage <files> --ref <reference>`.
2. Read `analysis/transcript.json` for question and answer lines; read `analysis/moments.json` for reaction peaks (laughs, cheers).
3. A round is: the clue line (in), the moment the answer is said (answer_at), and the end of the reaction (out). Keep 0.5-1.5 s of reaction after the answer.
4. If the footage is HDR (`probe.json` hdr: true), tone mapping runs automatically. Mention it in the proposal.
5. Write candidate rounds into proposal notes with timestamps and who won. Gate: every candidate has in, answer_at, out and text.
