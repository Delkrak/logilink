import pytest
from hypothesis import given
from hypothesis import strategies as st

from logilink.value_store import ManagedTypedValue, ValueStore


def _store():
    return ValueStore(ManagedTypedValue("_proto", int))


def test_add_value_and_retrieve():
    store = _store()
    mv = ManagedTypedValue("x", int)
    store.add_value(mv)
    assert store["x"] is mv


def test_add_value_sets_store_reference():
    store = _store()
    mv = ManagedTypedValue("x", int)
    store.add_value(mv)
    assert mv.store is store


def test_set_store_twice_raises():
    mv = ManagedTypedValue("x", int)
    store = _store()
    mv.set_store(store)
    with pytest.raises(RuntimeError):
        mv.set_store(store)


def test_duplicate_add_value_raises():
    store = _store()
    store.add_value(ManagedTypedValue("x", int))
    with pytest.raises(KeyError):
        store.add_value(ManagedTypedValue("x", int))


def test_missing_key_raises():
    with pytest.raises(KeyError):
        _ = _store()["missing"]


def test_contains_and_len():
    store = _store()
    assert "x" not in store
    store.add_value(ManagedTypedValue("x", int))
    assert "x" in store
    assert len(store) == 1


@given(st.integers())
def test_value_behaviour(n):
    store = _store()
    mv = ManagedTypedValue("x", int)
    store.add_value(mv)
    mv.value = n
    assert store["x"].value == n


def test_lock_blocks_add_value_and_mutation():
    store = _store()
    mv = ManagedTypedValue("x", int)
    store.add_value(mv)
    with store.with_lock():
        assert store.locked
        with pytest.raises(RuntimeError):
            store.add_value(ManagedTypedValue("y", int))
        with pytest.raises(RuntimeError):
            mv.value = 1
    assert not store.locked
    mv.value = 1
    assert mv.value == 1


def test_setting_value_sets_updated_flag():
    store = _store()
    mv = ManagedTypedValue("x", int)
    store.add_value(mv)
    assert not mv.value_updated_flag
    mv.value = 1
    assert mv.value_updated_flag


def test_check_and_assert_all_value_updated_flag():
    store = _store()
    mv1 = store.add_value(ManagedTypedValue("x", int))
    mv2 = store.add_value(ManagedTypedValue("y", int))

    assert store.check_all_value_updated_flag(state=False)
    mv1.value = 1
    assert not store.check_all_value_updated_flag(state=True)
    with pytest.raises(RuntimeError, match="y"):
        store.assert_all_value_updated_flag(state=True)
    mv2.value = 2
    assert store.check_all_value_updated_flag(state=True)
    store.assert_all_value_updated_flag(state=True)


def test_reset_all_value_updated_flag():
    store = _store()
    mv1 = store.add_value(ManagedTypedValue("x", int))
    mv2 = store.add_value(ManagedTypedValue("y", int))
    mv1.value = 1
    mv2.value = 2
    store.reset_all_value_updated_flag()
    assert store.check_all_value_updated_flag(state=False)


def test_on_change_callback_fires_on_set_and_reset():
    store = _store()
    mv = store.add_value(ManagedTypedValue("x", int))
    calls = []
    store.add_on_change_callback(lambda: calls.append(1))
    mv.value = 42
    assert len(calls) == 1
    mv.reset()
    assert len(calls) == 2


def test_clear_on_change_stops_callbacks():
    store = _store()
    mv = store.add_value(ManagedTypedValue("x", int))
    calls = []
    store.add_on_change_callback(lambda: calls.append(1))
    mv.value = 1
    store.clear_on_change_callbacks()
    mv.value = 2
    assert len(calls) == 1


def test_values_returns_all_added():
    store = _store()
    mv1 = store.add_value(ManagedTypedValue("x", int))
    mv2 = store.add_value(ManagedTypedValue("y", int))
    assert list(store.values()) == [mv1, mv2]


def test_batch_changes_fires_callback_once():
    store = _store()
    mv1 = store.add_value(ManagedTypedValue("x", int))
    mv2 = store.add_value(ManagedTypedValue("y", int))
    calls = []
    store.add_on_change_callback(lambda: calls.append(1))
    with store.with_batch_changes():
        mv1.value = 1
        mv2.value = 2
    assert len(calls) == 1


def test_remove_value():
    store = _store()
    store.add_value(ManagedTypedValue("x", int))
    mv2 = store.add_value(ManagedTypedValue("y", int))
    store.remove_value("x")
    assert "x" not in store
    assert store["y"] is mv2


def test_clear_values():
    store = _store()
    store.add_value(ManagedTypedValue("x", int))
    store.add_value(ManagedTypedValue("y", int))
    store.clear_values()
    assert len(store) == 0


def test_reset_values():
    store = _store()
    mv1 = store.add_value(ManagedTypedValue("x", int))
    mv2 = store.add_value(ManagedTypedValue("y", int))
    mv1.value = 1
    mv2.value = 2
    store.reset_values()
    assert not mv1.value_set and not mv2.value_set


def test_store_works_with_managed_subclass():
    class TaggedManagedValue(ManagedTypedValue[int]):
        def __init__(self, name: str, tag: str):
            super().__init__(name, int)
            self.tag = tag

    store = ValueStore(TaggedManagedValue("_proto", tag=""))
    mv = TaggedManagedValue("x", tag="important")
    store.add_value(mv)
    store["x"].value = 42
    assert store["x"].value == 42
    assert store["x"].tag == "important"
    assert store["x"].store is store
