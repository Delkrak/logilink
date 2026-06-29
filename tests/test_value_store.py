import pytest
from hypothesis import given
from hypothesis import strategies as st

from logilink.value_store import ManagedTypedValue, ValueStore


def test_add_value_and_retrieve():
    store = ValueStore(ManagedTypedValue)
    mv = ManagedTypedValue("x", int)
    store.add_value(mv)
    assert store["x"] is mv


def test_add_value_sets_store_reference():
    store = ValueStore(ManagedTypedValue)
    mv = ManagedTypedValue("x", int)
    store.add_value(mv)
    assert mv.store is store


def test_set_store_twice_raises():
    mv = ManagedTypedValue("x", int)
    store = ValueStore(ManagedTypedValue)
    mv.set_store(store)
    with pytest.raises(RuntimeError):
        mv.set_store(store)


def test_duplicate_add_value_raises():
    store = ValueStore(ManagedTypedValue)
    store.add_value(ManagedTypedValue("x", int))
    with pytest.raises(KeyError):
        store.add_value(ManagedTypedValue("x", int))


def test_add_value_wrong_type_raises():
    class StrictValue(ManagedTypedValue[int]):
        def __init__(self, name: str):
            super().__init__(name, int)

    store = ValueStore(StrictValue)
    with pytest.raises(TypeError):
        store.add_value(ManagedTypedValue("x", int))


def test_missing_key_raises():
    with pytest.raises(KeyError):
        _ = ValueStore(ManagedTypedValue)["missing"]


def test_contains_and_len():
    store = ValueStore(ManagedTypedValue)
    assert "x" not in store
    store.add_value(ManagedTypedValue("x", int))
    assert "x" in store
    assert len(store) == 1


@given(st.integers())
def test_value_behaviour(n):
    store = ValueStore(ManagedTypedValue)
    mv = ManagedTypedValue("x", int)
    store.add_value(mv)
    mv.value = n
    assert store["x"].value == n


def test_lock_blocks_add_value_and_mutation():
    store = ValueStore(ManagedTypedValue)
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
    store = ValueStore(ManagedTypedValue)
    mv = ManagedTypedValue("x", int)
    store.add_value(mv)
    assert not mv.value_updated_flag
    mv.value = 1
    assert mv.value_updated_flag


def test_check_and_assert_all_value_updated_flag():
    store = ValueStore(ManagedTypedValue)
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
    store = ValueStore(ManagedTypedValue)
    mv1 = store.add_value(ManagedTypedValue("x", int))
    mv2 = store.add_value(ManagedTypedValue("y", int))
    mv1.value = 1
    mv2.value = 2
    store.reset_all_value_updated_flag()
    assert store.check_all_value_updated_flag(state=False)


def test_on_change_callback_fires_on_set_and_reset():
    store = ValueStore(ManagedTypedValue)
    mv = store.add_value(ManagedTypedValue("x", int))
    calls = []
    store.add_on_change_callback(lambda: calls.append(1))
    mv.value = 42
    assert len(calls) == 1
    mv.reset()
    assert len(calls) == 2


def test_clear_on_change_stops_callbacks():
    store = ValueStore(ManagedTypedValue)
    mv = store.add_value(ManagedTypedValue("x", int))
    calls = []
    store.add_on_change_callback(lambda: calls.append(1))
    mv.value = 1
    store.clear_on_change_callbacks()
    mv.value = 2
    assert len(calls) == 1


def test_values_returns_all_added():
    store = ValueStore(ManagedTypedValue)
    mv1 = store.add_value(ManagedTypedValue("x", int))
    mv2 = store.add_value(ManagedTypedValue("y", int))
    assert list(store.values()) == [mv1, mv2]


def test_batch_changes_fires_callback_once():
    store = ValueStore(ManagedTypedValue)
    mv1 = store.add_value(ManagedTypedValue("x", int))
    mv2 = store.add_value(ManagedTypedValue("y", int))
    calls = []
    store.add_on_change_callback(lambda: calls.append(1))
    with store.with_batch_changes():
        mv1.value = 1
        mv2.value = 2
    assert len(calls) == 1


def test_remove_value():
    store = ValueStore(ManagedTypedValue)
    store.add_value(ManagedTypedValue("x", int))
    mv2 = store.add_value(ManagedTypedValue("y", int))
    store.remove_value("x")
    assert "x" not in store
    assert store["y"] is mv2


def test_clear_values():
    store = ValueStore(ManagedTypedValue)
    store.add_value(ManagedTypedValue("x", int))
    store.add_value(ManagedTypedValue("y", int))
    store.clear_values()
    assert len(store) == 0


def test_reset_values():
    store = ValueStore(ManagedTypedValue)
    mv1 = store.add_value(ManagedTypedValue("x", int))
    mv2 = store.add_value(ManagedTypedValue("y", int))
    mv1.value = 1
    mv2.value = 2
    store.reset_values()
    assert not mv1.value_set and not mv2.value_set


def test_reset_clears_value_updated_flag():
    store = ValueStore(ManagedTypedValue)
    mv = store.add_value(ManagedTypedValue("x", int))
    mv.value = 1
    assert mv.value_updated_flag
    mv.reset()
    assert not mv.value_updated_flag


def test_setting_different_value_sets_changed_flag():
    store = ValueStore(ManagedTypedValue)
    mv = store.add_value(ManagedTypedValue("x", int))
    mv.value = 1
    mv._reset_changed_flag()
    mv.value = 2
    assert mv.value_changed_flag


def test_setting_same_value_leaves_changed_flag_false():
    store = ValueStore(ManagedTypedValue)
    mv = store.add_value(ManagedTypedValue("x", int))
    mv.value = 1
    mv._reset_changed_flag()
    mv.value = 1
    assert not mv.value_changed_flag


def test_first_set_sets_changed_flag():
    store = ValueStore(ManagedTypedValue)
    mv = store.add_value(ManagedTypedValue("x", int))
    mv.value = 0
    assert mv.value_changed_flag


def test_reset_clears_changed_flag():
    store = ValueStore(ManagedTypedValue)
    mv = store.add_value(ManagedTypedValue("x", int))
    mv.value = 1
    assert mv.value_changed_flag
    mv.reset()
    assert not mv.value_changed_flag


def test_reset_all_value_changed_flag():
    store = ValueStore(ManagedTypedValue)
    mv1 = store.add_value(ManagedTypedValue("x", int))
    mv2 = store.add_value(ManagedTypedValue("y", int))
    mv1.value = 1
    mv2.value = 2
    assert store.check_all_value_changed_flag(state=True)
    store.reset_all_value_changed_flag()
    assert store.check_all_value_changed_flag(state=False)


def test_assert_all_value_changed_flag():
    store = ValueStore(ManagedTypedValue)
    mv1 = store.add_value(ManagedTypedValue("x", int))
    mv2 = store.add_value(ManagedTypedValue("y", int))
    mv1.value = 1
    with pytest.raises(RuntimeError, match="y"):
        store.assert_all_value_changed_flag(state=True)
    mv2.value = 2
    store.assert_all_value_changed_flag(state=True)


def test_managed_typed_value_repr_unset():
    mv = ManagedTypedValue("x", int)
    assert repr(mv) == "ManagedTypedValue[int](name='x', <unset>)"


def test_managed_typed_value_repr_set():
    mv = ManagedTypedValue("x", int)
    mv.value = 42
    assert repr(mv) == "ManagedTypedValue[int](name='x', value=42)"


def test_value_store_repr():
    store = ValueStore(ManagedTypedValue)
    store.add_value(ManagedTypedValue("x", int))
    store.add_value(ManagedTypedValue("y", int))
    assert repr(store) == "ValueStore(['x', 'y'])"


def test_remove_value_while_locked_raises():
    store = ValueStore(ManagedTypedValue)
    store.add_value(ManagedTypedValue("x", int))
    store.lock()
    with pytest.raises(RuntimeError):
        store.remove_value("x")
    store.unlock()


def test_remove_value_missing_key_raises():
    store = ValueStore(ManagedTypedValue)
    with pytest.raises(KeyError):
        store.remove_value("missing")


def test_clear_values_while_locked_raises():
    store = ValueStore(ManagedTypedValue)
    store.add_value(ManagedTypedValue("x", int))
    store.lock()
    with pytest.raises(RuntimeError):
        store.clear_values()
    store.unlock()


def test_lock_and_unlock():
    store = ValueStore(ManagedTypedValue)
    mv = store.add_value(ManagedTypedValue("x", int))
    store.lock()
    assert store.locked
    with pytest.raises(RuntimeError):
        mv.value = 1
    store.unlock()
    assert not store.locked
    mv.value = 1
    assert mv.value == 1


def test_store_works_with_managed_subclass():
    class TaggedManagedValue(ManagedTypedValue[int]):
        def __init__(self, name: str, tag: str):
            super().__init__(name, int)
            self.tag = tag

    store = ValueStore(TaggedManagedValue)
    mv = TaggedManagedValue("x", tag="important")
    store.add_value(mv)
    store["x"].value = 42
    assert store["x"].value == 42
    assert store["x"].tag == "important"
    assert store["x"].store is store
