# Component notes

One note per component: when to use it, when not to, and its defaults. `va components` lists the registered set.

- **Round**: game footage with a clue and an answer. Not for talking heads. Punch zoom at the answer, timer during the clue.
- **Hook**: always first. One question, under 8 words. Teaser flashes come from the rounds' answer moments.
- **CTA**: always last. Bonus clue is optional; countdown 3 by default.
- **Scoreboard**: only when there are teams. Never type scores; they derive from `winner`.
- **BRoll**: on a clue or a claim, 1-2 s. `cutaway` replaces the frame, `overlay` sits in a card.
- **Sticker**: a cut-out PNG pop-in. Needs an image in the library (`va lib add --kind stickers`) or a path.
- **Tag**: stamp at the reveal. One per round.
- **WordPop**: karaoke captions from the transcript. Use for talking footage, not for silent games.
- **PunchZoom**: on a beat or reveal, 0.4-0.5 s. Never more than 3 per 10 s.
