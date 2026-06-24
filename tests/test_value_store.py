import pytest
from hypothesis import given
from hypothesis import strategies as st

from logilink.value_store import ManagedTypedValue, ValueStore


def _store():
    return ValueStore(ManagedTypedValue("_proto", int))


def test_register_and_retrieve():
    store = _store()
    mv = ManagedTypedValue("x", int)
    store.register(mv)
    assert store["x"] is mv


def test_register_sets_store_reference():
    store = _store()
    mv = ManagedTypedValue("x", int)
    store.register(mv)
    assert mv.store is store


def test_set_store_twice_raises():
    mv = ManagedTypedValue("x", int)
    store = _store()
    mv.set_store(store)
    with pytest.raises(RuntimeError):
        mv.set_store(store)


def test_duplicate_register_raises():
    store = _store()
    store.register(ManagedTypedValue("x", int))
    with pytest.raises(KeyError):
        store.register(ManagedTypedValue("x", int))


def test_missing_key_raises():
    with pytest.raises(KeyError):
        _ = _store()["missing"]


def test_contains_and_len():
    store = _store()
    assert "x" not in store
    store.register(ManagedTypedValue("x", int))
    assert "x" in store
    assert len(store) == 1


@given(st.integers())
def test_value_behaviour(n):
    store = _store()
    mv = ManagedTypedValue("x", int)
    store.register(mv)
    mv.value = n
    assert store["x"].value == n


def test_lock_blocks_registration_and_mutation():
    store = _store()
    mv = ManagedTypedValue("x", int)
    store.register(mv)
    with store.with_lock():
        assert store.locked
        with pytest.raises(RuntimeError):
            store.register(ManagedTypedValue("y", int))
        with pytest.raises(RuntimeError):
            mv.value = 1
    assert not store.locked
    mv.value = 1
    assert mv.value == 1


def test_setting_value_sets_updated_flag():
    store = _store()
    mv = ManagedTypedValue("x", int)
    store.register(mv)
    assert not mv.value_updated
    mv.value = 1
    assert mv.value_updated


def test_check_and_assert_all_updated_values_equal():
    store = _store()
    mv1 = store.register(ManagedTypedValue("x", int))
    mv2 = store.register(ManagedTypedValue("y", int))

    assert store.check_all_updated_values_equal(state=False)
    mv1.value = 1
    assert not store.check_all_updated_values_equal(state=True)
    with pytest.raises(RuntimeError, match="y"):
        store.assert_all_updated_values_equal(state=True)
    mv2.value = 2
    assert store.check_all_updated_values_equal(state=True)
    store.assert_all_updated_values_equal(state=True)


def test_clear_updated_resets_all_flags():
    store = _store()
    mv1 = store.register(ManagedTypedValue("x", int))
    mv2 = store.register(ManagedTypedValue("y", int))
    mv1.value = 1
    mv2.value = 2
    store.clear_updated()
    assert store.check_all_updated_values_equal(state=False)


def test_store_works_with_managed_subclass():
    class TaggedManagedValue(ManagedTypedValue[int]):
        def __init__(self, name: str, tag: str):
            super().__init__(name, int)
            self.tag = tag

    store = ValueStore(TaggedManagedValue("_proto", tag=""))
    mv = TaggedManagedValue("x", tag="important")
    store.register(mv)
    store["x"].value = 42
    assert store["x"].value == 42
    assert store["x"].tag == "important"
    assert store["x"].store is store
