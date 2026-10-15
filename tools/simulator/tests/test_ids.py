import pytest

from sim.ids import SeqCounter, event_id


def test_format():
    assert event_id("r1", "EQ1", 3) == "sim:r1:EQ1:3"


def test_seq_per_equipment_and_replayable():
    def run():
        c = SeqCounter()
        return [event_id("r", e, c.next(e)) for e in ["A", "B", "A", "A"]]

    assert run() == ["sim:r:A:1", "sim:r:B:1", "sim:r:A:2", "sim:r:A:3"]
    assert run() == run()


def test_too_long():
    with pytest.raises(ValueError):
        event_id("x" * 130, "EQ", 1)
