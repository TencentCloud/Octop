from octop_browser.dom.refs import RefCache


def test_store_and_lookup():
    cache = RefCache()
    cache.store("btn_1", node_id=42)
    assert cache.lookup("btn_1") == 42


def test_lookup_missing_returns_none():
    cache = RefCache()
    assert cache.lookup("nonexistent") is None


def test_invalidate_clears_all():
    cache = RefCache()
    cache.store("btn_1", node_id=42)
    cache.store("inp_2", node_id=99)
    cache.invalidate()
    assert cache.lookup("btn_1") is None
    assert cache.lookup("inp_2") is None


def test_store_overwrites():
    cache = RefCache()
    cache.store("btn_1", node_id=42)
    cache.store("btn_1", node_id=100)
    assert cache.lookup("btn_1") == 100


def test_all_refs():
    cache = RefCache()
    cache.store("btn_1", node_id=1)
    cache.store("inp_2", node_id=2)
    refs = cache.all_refs()
    assert refs == {"btn_1": 1, "inp_2": 2}
