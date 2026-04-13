from pathlib import Path

from app.services.free_model_pool import FreeModelPool, ProviderRecord


def test_pick_best_prefers_priority(tmp_path: Path):
    pool = FreeModelPool(state_path=tmp_path / "state.json")
    pool.providers = [
        ProviderRecord(provider_id="p1", model_name="m1", base_url="u1", api_key_env="K1", priority=10),
        ProviderRecord(provider_id="p2", model_name="m2", base_url="u2", api_key_env="K2", priority=100),
    ]
    assert pool.pick_best() is not None
    assert pool.pick_best().provider_id == "p2"


def test_failure_can_disable_provider(tmp_path: Path):
    pool = FreeModelPool(state_path=tmp_path / "state.json")
    provider = ProviderRecord(provider_id="p1", model_name="m1", base_url="u1", api_key_env="K1", priority=10)
    pool.providers = [provider]

    pool.mark_failure("p1", "err1")
    pool.mark_failure("p1", "err2")
    pool.mark_failure("p1", "err3")

    item = pool.providers[0]
    assert item.consecutive_failures >= 3
    assert item.disabled_until is not None
