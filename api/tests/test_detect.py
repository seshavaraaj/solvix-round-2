"""Each detection flag fires on a hand-made case (plan B2 done-when)."""
from app.core.detect import bunching, delay_emerging, overcrowded, underused

BANDS = [17.25 * 3600 + i * 900 for i in range(4)]
STOPS = ["A", "B", "Nehru Place", "D"]


def test_overcrowded_fires_and_names_stop():
    lf50 = [[0.5, 0.8, 0.95]] * 4
    lf90 = [[0.6, 0.9, 1.25]] * 4
    f = overcrowded(lf50, lf90, STOPS[:3], BANDS)
    assert f.on and f.confidence == "high"
    assert f.evidence == "P90 load 1.25 at Nehru Place, 17:15–18:15"


def test_overcrowded_off_below_capacity():
    f = overcrowded([[0.5, 0.6]] * 4, [[0.7, 0.99]] * 4, STOPS[:2], BANDS)
    assert not f.on and f.as_dict()["evidence"] is None


def test_overcrowded_dark_bus_lowers_confidence():
    f = overcrowded([[0.95]] * 4, [[1.3]] * 4, STOPS[:1], BANDS, dark=True)
    assert f.on and f.confidence == "medium"


def test_underused_needs_60_minutes():
    low = [[0.1, 0.2]] * 4
    assert underused(low, [[0.2, 0.3]] * 4, BANDS).on
    assert not underused(low[:3], [[0.2, 0.3]] * 3, BANDS[:3]).on        # only 45 minutes
    assert not underused([[0.1, 0.35]] * 4, [[0.2, 0.4]] * 4, BANDS).on


def test_delay_emerging_segment_sigma():
    seg = [{"name": "Ashram → Lajpat Nagar", "observed_s": 480, "expected_s": 300, "n": 3}]
    f = delay_emerging(seg, delay_now_min=1.0, delay_prev_min=1.0, cv=0.12)
    assert f.on and "Ashram → Lajpat Nagar" in f.evidence


def test_delay_emerging_growing_delay():
    f = delay_emerging([], delay_now_min=6.5, delay_prev_min=3.1, cv=0.12)
    assert f.on and f.evidence.startswith("Delay 6.5 min, up from 3.1 min")
    assert not delay_emerging([], delay_now_min=6.5, delay_prev_min=6.5, cv=0.12).on
    assert not delay_emerging([], delay_now_min=4.0, delay_prev_min=1.0, cv=0.12).on


def test_bunching_fires_and_dark_bus_lowers_confidence():
    hw = [{"headway_min": 4, "stop": "X", "dark": False}, {"headway_min": 12, "stop": "Y", "dark": False}]
    f = bunching(hw, planned_headway_min=10)
    assert f.on and f.confidence == "high" and f.evidence == "Headway 4 min vs planned 10 min"
    f = bunching([{"headway_min": 4, "stop": "X", "dark": True}], planned_headway_min=10, dark_on_route=1)
    assert f.on and f.confidence == "low" and f.evidence.endswith("; 1 dark bus")
    assert not bunching([{"headway_min": 6, "stop": "X", "dark": False}], planned_headway_min=10).on
