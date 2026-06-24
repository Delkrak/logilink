from collections.abc import Generator
from contextlib import contextmanager

from logilink.value import TypedValue


class ManagedTypedValue[T](TypedValue[T]):
    def __init__(self, name: str, type: type[T]):
        super().__init__(type)
        self.name = name
        self._store: ValueStore | None = None
        self._value_updated: bool = False

    @property
    def store(self) -> "ValueStore | None":
        return self._store

    def set_store(self, store: "ValueStore") -> None:
        if self._store is not None:
            raise RuntimeError(f"{self.name!r} is already bound to a store")
        self._store = store

    @property
    def value_updated(self) -> bool:
        return self._value_updated

    def _clear_updated(self) -> None:
        self._value_updated = False

    def _assert_mutable(self) -> None:
        if self._store is not None and self._store.locked:
            raise RuntimeError("store is locked")

    def _set_value(self, value: T):
        self._assert_mutable()
        super()._set_value(value)
        self._value_updated = True

    def _set_default_value(self, value: T):
        self._assert_mutable()
        super()._set_default_value(value)

    def clear_value(self):
        self._assert_mutable()
        super().clear_value()

    def clear_default_value(self):
        self._assert_mutable()
        super().clear_default_value()

    def clear(self):
        self._assert_mutable()
        super().clear()

    def __repr__(self) -> str:
        type_name = getattr(self._type, "__name__", repr(self._type))
        if self._value_set:
            return f"ManagedTypedValue[{type_name}](name={self.name!r}, value={self._value!r})"
        return f"ManagedTypedValue[{type_name}](name={self.name!r}, <unset>)"


class ValueStore[TV: ManagedTypedValue]:
    def __init__(self, prototype: TV):
        self._type = prototype._type
        self._locked = False
        self._values: dict[str, TV] = {}

    @property
    def locked(self) -> bool:
        return self._locked

    @contextmanager
    def with_lock(self) -> Generator[None, None, None]:
        self._locked = True
        try:
            yield
        finally:
            self._locked = False

    def register(self, mv: TV) -> TV:
        if self._locked:
            raise RuntimeError("store is locked")
        if mv.name in self._values:
            raise KeyError(f"{mv.name!r} is already registered")
        mv.set_store(self)
        self._values[mv.name] = mv
        return mv

    def __getitem__(self, name: str) -> TV:
        try:
            return self._values[name]
        except KeyError:
            raise KeyError(f"{name!r} is not registered") from None

    def __contains__(self, name: str) -> bool:
        return name in self._values

    def __len__(self) -> int:
        return len(self._values)

    def check_all_updated_values_equal(self, state: bool) -> bool:
        return all(mv.value_updated == state for mv in self._values.values())

    def assert_all_updated_values_equal(self, state: bool) -> None:
        failing = [name for name, mv in self._values.items() if mv.value_updated != state]
        if failing:
            raise RuntimeError(f"values not matching updated state={state}: {failing}")

    def clear_updated(self) -> None:
        for mv in self._values.values():
            mv._clear_updated()

    def __repr__(self) -> str:
        return f"ValueStore({list(self._values)!r})"
