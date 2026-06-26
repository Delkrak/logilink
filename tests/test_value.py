import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from logilink.value import TypedValue

scalars = st.one_of(st.integers(), st.floats(allow_nan=False), st.text(), st.booleans())


def test_access_before_set_raises():
    with pytest.raises(AttributeError):
        _ = TypedValue(int).value


@given(scalars)
def test_set_marks_as_set_and_returns_value(v):
    type_ = type(v)
    tv = TypedValue(type_)
    tv.value = v
    assert tv._value_set
    assert tv.value == v


@given(scalars, scalars)
def test_reassignment_replaces_value(a, b):
    type_ = type(a)
    tv = TypedValue(type_)
    tv.value = a
    tv.value = b if isinstance(b, type_) else a
    assert tv._value_set


@given(st.lists(st.integers()))
def test_generic_list_roundtrip(lst):
    tv = TypedValue(list[int])
    tv.value = lst
    assert tv.value == lst


def test_invalid_value_raises_validation_error():
    tv = TypedValue(int)
    with pytest.raises(ValidationError):
        tv.value = "not a number"


def test_optional_accepts_none():
    tv = TypedValue(int | None)
    tv.value = None
    assert tv.value is None


def test_instances_are_isolated():
    tv1, tv2 = TypedValue(int), TypedValue(int)
    tv1.value = 1
    with pytest.raises(AttributeError):
        _ = tv2.value


@given(st.integers())
def test_reset_to_unset(n):
    tv = TypedValue(int)
    tv.value = n
    tv.reset()
    assert not tv._value_set
    with pytest.raises(AttributeError):
        _ = tv.value


def test_value_set():
    tv = TypedValue(int)
    assert not tv.value_set
    tv.value = 1
    assert tv.value_set


@given(st.integers())
def test_eq_compares_by_value(n):
    tv1, tv2 = TypedValue(int), TypedValue(int)
    tv1.value = n
    tv2.value = n
    assert tv1 == tv2
    assert tv1.value_equal(n)


def test_eq_on_unset_returns_false():
    tv = TypedValue(int)
    assert tv != 1
    assert not tv.value_equal(TypedValue(int))


def test_repr_shows_type_and_value():
    tv = TypedValue(int)
    assert repr(tv) == "TypedValue[int](<unset>)"
    tv.value = 42
    assert repr(tv) == "TypedValue[int](42)"


@given(st.integers())
def test_value_equal_different_types(n):
    tv_int = TypedValue(int)
    tv_float = TypedValue(float)
    tv_int.value = n
    tv_float.value = n
    assert not tv_int.value_equal(tv_float)


@given(st.integers())
def test_exactly_equal(n):
    tv1, tv2 = TypedValue(int), TypedValue(int)
    tv1.value = n
    tv2.value = n
    assert tv1.exactly_equal(tv2)
    tv2.reset()
    assert not tv1.exactly_equal(tv2)
