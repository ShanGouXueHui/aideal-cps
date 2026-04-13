from pathlib import Path

from app.services.jd_union_cache_service import JDUnionCacheService


def test_cache_set_and_get(tmp_path: Path):
    cache = JDUnionCacheService(base_dir=str(tmp_path), default_ttl_seconds=60)
    key = "abc"
    payload = {"x": 1}
    cache.set(key, payload)
    assert cache.get(key) == payload
