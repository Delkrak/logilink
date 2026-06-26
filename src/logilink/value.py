from pydantic import TypeAdapter


class TypedValue[T]:
    def __init__(self, type: type[T]):
        self._type = type
        self._type_adapter = TypeAdapter(type)
        self._value: T | None = None
        self._value_set = False

    def __repr__(self) -> str:
        type_name = getattr(self._type, "__name__", repr(self._type))
        if self._value_set:
            return f"TypedValue[{type_name}]({self._value!r})"
        return f"TypedValue[{type_name}](<unset>)"

    @property
    def value(self) -> T:
        if not self._value_set:
            raise AttributeError("value has not been set")
        return self._value

    @value.setter
    def value(self, value: T):
        self._set_value(value)

    def _set_value(self, value: T):
        self._value_set = True
        self._value = self._type_adapter.validate_python(value)

    def reset(self):
        self._value = None
        self._value_set = False

    @property
    def value_set(self) -> bool:
        return self._value_set

    def value_equal(self, obj: object) -> bool:
        if not self.value_set:
            return False
        if isinstance(obj, TypedValue):
            return obj.value_set and self._type == obj._type and self.value == obj.value
        return self.value == obj

    def __eq__(self, obj: object) -> bool:
        return self.value_equal(obj)

    def exactly_equal(self, obj: object) -> bool:
        if not isinstance(obj, TypedValue):
            return False
        return (
            self._type == obj._type
            and self._value_set == obj._value_set
            and self._value == obj._value
        )
