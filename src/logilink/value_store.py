from collections.abc import Callable, Generator, Iterable
from contextlib import contextmanager

from logilink.value import TypedValue


class ManagedTypedValue[T](TypedValue[T]):
    def __init__(self, name: str, type: type[T]):
        super().__init__(type)
        self.name = name
        self._store: ValueStore | None = None
        self._value_updated_flag: bool = False

    @property
    def store(self) -> "ValueStore | None":
        return self._store

    def set_store(self, store: "ValueStore") -> None:
        if self._store is not None:
            raise RuntimeError(f"{self.name!r} is already bound to a store")
        self._store = store

    @property
    def value_updated_flag(self) -> bool:
        return self._value_updated_flag

    def _reset_updated_flag(self) -> None:
        self._value_updated_flag = False

    def _assert_mutable(self) -> None:
        if self._store is not None and self._store.locked:
            raise RuntimeError("store is locked")

    def _set_value(self, value: T):
        self._assert_mutable()
        super()._set_value(value)
        self._value_updated_flag = True
        if self._store is not None:
            self._store._notify_change()

    def reset(self):
        self._assert_mutable()
        super().reset()
        if self._store is not None:
            self._store._notify_change()

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
        self._on_change_callbacks: list[Callable[[], None]] = []
        self._on_change_batching: bool = False
        self._on_change_pending: bool = False

    def __repr__(self) -> str:
        return f"ValueStore({list(self._values)!r})"

    def add_value(self, mv: TV) -> TV:
        if self._locked:
            raise RuntimeError("store is locked")
        if mv.name in self._values:
            raise KeyError(f"{mv.name!r} is already added")
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

    def values(self) -> Iterable[TV]:
        return self._values.values()

    def __len__(self) -> int:
        return len(self._values)

    def remove_value(self, name: str) -> TV:
        if self._locked:
            raise RuntimeError("store is locked")
        try:
            return self._values.pop(name)
        except KeyError:
            raise KeyError(f"{name!r} is not registered") from None

    def clear_values(self) -> None:
        if self._locked:
            raise RuntimeError("store is locked")
        self._values.clear()

    def reset_values(self) -> None:
        for mv in self._values.values():
            mv.reset()

    # lock

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

    # on_change

    def add_on_change_callback(self, callback: Callable[[], None]) -> None:
        self._on_change_callbacks.append(callback)

    def clear_on_change_callbacks(self) -> None:
        self._on_change_callbacks.clear()

    def _notify_change(self) -> None:
        if self._on_change_batching:
            self._on_change_pending = True
            return
        for cb in self._on_change_callbacks:
            cb()

    @contextmanager
    def with_batch_changes(self) -> Generator[None, None, None]:
        self._on_change_batching = True
        try:
            yield
        finally:
            self._on_change_batching = False
            if self._on_change_pending:
                self._on_change_pending = False
                self._notify_change()

    # value_updated_flag

    def check_all_value_updated_flag(self, state: bool) -> bool:
        return all(mv.value_updated_flag == state for mv in self._values.values())

    def assert_all_value_updated_flag(self, state: bool) -> None:
        failing = [name for name, mv in self._values.items() if mv.value_updated_flag != state]
        if failing:
            raise RuntimeError(f"values not matching updated state={state}: {failing}")

    def reset_all_value_updated_flag(self) -> None:
        for mv in self._values.values():
            mv._reset_updated_flag()
