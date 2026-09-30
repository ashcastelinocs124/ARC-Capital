import pytest

from castelino.agents.update.registry import ModelRegistry
from tests.update_fixtures import make_forecast


def test_empty_registry_has_no_current(tmp_path):
    assert ModelRegistry(tmp_path).current() is None


def test_save_and_point_both_models(tmp_path):
    reg = ModelRegistry(tmp_path)
    v = reg.save_version(make_forecast(g_prob=0.7, i_prob=0.9))
    assert v == "v0001"
    reg.set_pointer("growth", v)
    assert reg.current() is None  # inflation pointer still missing
    reg.set_pointer("inflation", v)
    cur = reg.current()
    assert cur.growth.prob_up == 0.7 and cur.inflation.prob_up == 0.9


def test_pointers_are_per_model(tmp_path):
    reg = ModelRegistry(tmp_path)
    v1 = reg.save_version(make_forecast(g_prob=0.76, i_prob=0.87))
    v2 = reg.save_version(make_forecast(g_prob=0.71, i_prob=0.91))
    assert (v1, v2) == ("v0001", "v0002")
    reg.set_pointer("growth", v2)
    reg.set_pointer("inflation", v1)
    cur = reg.current()
    assert cur.growth.prob_up == 0.71 and cur.inflation.prob_up == 0.87
    assert reg.pointers() == {"growth": "v0002", "inflation": "v0001"}


def test_rollback_moves_pointer_back(tmp_path):
    reg = ModelRegistry(tmp_path)
    v1 = reg.save_version(make_forecast(g_prob=0.76))
    v2 = reg.save_version(make_forecast(g_prob=0.71))
    for m in ("growth", "inflation"):
        reg.set_pointer(m, v2)
    reg.rollback("growth", v1)
    assert reg.current().growth.prob_up == 0.76


def test_unknown_version_or_model_raises(tmp_path):
    reg = ModelRegistry(tmp_path)
    with pytest.raises(KeyError):
        reg.set_pointer("growth", "v0099")
    v = reg.save_version(make_forecast())
    with pytest.raises(KeyError):
        reg.set_pointer("bogus", v)


def test_unreadable_version_makes_current_none_instead_of_raising(tmp_path):
    reg = ModelRegistry(tmp_path)
    v = reg.save_version(make_forecast())
    reg.set_pointer("growth", v)
    reg.set_pointer("inflation", v)
    (tmp_path / f"{v}.json").write_text('{"growth": {"train_metrics": {"brier": null}}}')
    assert reg.current() is None
