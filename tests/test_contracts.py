"""Every component's props validate and it exposes a JSON schema."""
import pytest

from va.core import discover, ease_mid

REQUIRED = {"Segment": {"out": 2.0}, "PunchZoom": {"at": 1.0}, "Caption": {"text": "hi"},
            "Round": {"id": "r", "in": 0, "out": 4, "answer_at": 2, "clue": "c", "answer": "a"},
            "Hook": {"text": "q"}, "Timer": {"at": 0}, "InfoCard": {"at": 0, "title": "t"},
            "KineticTitle": {"text": "a b c"}, "SFX": {"sound": "pop"}}


@pytest.mark.parametrize("name", sorted(discover()))
def test_component_contract(name):
    cls = discover()[name]
    comp = cls(REQUIRED.get(name, {}))
    assert isinstance(cls.schema(), dict)
    assert comp.duration() >= 0
    assert cls.name == name


def test_unknown_prop_rejected():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        discover()["Caption"]({"text": "x", "nope": 1})


def test_ease_mid_back_out_overshoots_early():
    assert 0 < ease_mid("back_out", 1.0) < 0.5
