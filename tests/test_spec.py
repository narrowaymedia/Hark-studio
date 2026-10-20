"""Planner: timeline layout, anchors and derived scores."""
from pathlib import Path

import yaml

from va.spec import plan

SPEC = {
    "video": {"name": "t", "pipeline": "quiz_game", "profile": "instagram_reels", "style": "bold_pop"},
    "inputs": {"footage": []},
    "teams": {"A": {"name": "A", "side": "left", "color": "#E63946"},
              "B": {"name": "B", "side": "right", "color": "#2D8CFF"}},
    "timeline": [
        {"Hook": {"text": "q", "seconds": 2.0}},
        {"Round": {"id": "r1", "in": 10, "out": 18, "answer_at": 15, "clue": "c", "answer": "a", "winner": "B"}},
        {"SFX": {"sound": "ding", "at": "r1.answer"}},
        {"Round": {"id": "r2", "in": 30, "out": 36, "answer_at": 33, "clue": "c", "answer": "a", "winner": "AB"}},
        {"CTA": {"countdown": 3}},
    ],
    "overlays": [{"Scoreboard": {}}],
}


def test_layout_and_scores(tmp_path: Path):
    (tmp_path / "video.yaml").write_text(yaml.safe_dump(SPEC))
    pl = plan(tmp_path)
    assert [c.name for c in pl.sequence] == ["Hook", "Round", "Round", "CTA"]
    assert pl.sequence[1].t0 == 2.0
    assert pl.ctx.derived["events"]["r1.answer"] == 7.0
    assert pl.anchored[0].p.at == 7.0
    assert pl.total == 2 + 8 + 6 + 5
    final = pl.ctx.derived["score_events"][-1]["score"]
    assert final == {"A": 1, "B": 2}
