from castelino.adoption.models import BUCKETS, GICS_SECTORS, PILLARS
from castelino.config import get_settings


def test_adoption_defaults():
    a = get_settings().adoption
    assert a.top_n == 100
    assert a.thin_cell_below == 5
    assert a.hire_smoothing_periods == 7
    assert a.data_dir == "data/adoption"


def test_constants():
    assert BUCKETS == ("large", "small")
    assert PILLARS == ("talk", "hire", "spend")
    assert len(GICS_SECTORS) == 11
