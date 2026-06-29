from abc import ABC, abstractmethod
from contextvars import ContextVar
from typing import ClassVar

from pydantic import BaseModel

from logilink.value_store import ManagedTypedValue, ValueStore


class Input[T](ManagedTypedValue[T]): ...


class Output[T](ManagedTypedValue[T]):
    def __init__(self, name: str, type: type[T], default: T):
        super().__init__(name, type)
        self._default_value: T = self._type_adapter.validate_python(default)
        self._set_value(self._default_value)

    def reset(self):
        super().reset()
        self._set_value(self._default_value)
        self._reset_updated_flag()


class State[T](ManagedTypedValue[T]):
    def __init__(self, name: str, type: type[T], initial: T):
        super().__init__(name, type)
        self._initial_value: T = self._type_adapter.validate_python(initial)
        self._committed_value: T = self._initial_value

    @property
    def value(self) -> T:
        return self._committed_value

    @value.setter
    def value(self, _: T):
        raise AttributeError("state value is read-only; use .next")

    @property
    def next(self) -> T:
        raise AttributeError("next is write-only")

    @next.setter
    def next(self, value: T):
        self._set_value(value)

    def _commit(self):
        self._committed_value = self._value

    def reset(self):
        self._committed_value = self._initial_value
        super().reset()


class StateStore(ValueStore[State]):
    def __init__(self):
        super().__init__(State)

    def commit_all(self):
        for s in self._values.values():
            s._commit()


class Algorithm[T_CONFIGURATION: BaseModel, T_SETTINGS: BaseModel](ABC):
    configuration_class: type[T_CONFIGURATION] = None
    settings_class: type[T_SETTINGS] = None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        config_cls = cls.configuration_class
        settings_cls = cls.settings_class
        if (
            config_cls is not None
            and settings_cls is not None
            and not issubclass(settings_cls, config_cls)
        ):
            raise TypeError(
                f"{cls.__name__}: settings_class must be a subclass of configuration_class"
            )

    __in_setup: ClassVar[ContextVar[bool]] = ContextVar("in_setup", default=False)

    def __init__(
        self,
        name: str,
        configuration: T_CONFIGURATION,
        settings: T_SETTINGS,
        *,
        _parent: "Algorithm | None" = None,
    ):
        assert "/" not in name
        self.name = name

        self._default_configuration = configuration.model_copy()
        self._default_settings = settings.model_copy()

        self._parent = _parent
        self._settings = settings.model_copy()
        self._configuration = configuration.model_copy()

        self._sub_algorithms: list[Algorithm] = []
        self._inputs = ValueStore(Input)
        self._outputs = ValueStore(Output)
        self._states = StateStore()
        self._on_settings_changed_called = False

        # swap methods
        self.on_settings_changed_original, self.on_settings_changed = (
            self.on_settings_changed,
            self._on_settings_changed,
        )

        if not Algorithm.__in_setup.get():
            self._setup(configuration, settings)

    @property
    def is_root(self):
        return self._parent is None

    @property
    def configuration(self) -> T_CONFIGURATION:
        return self._configuration

    @property
    def settings(self) -> T_SETTINGS:
        return self._settings

    def create_input[T](self, name: str, type: type[T]) -> Input[T]:
        return self._inputs.add_value(Input(name, type))

    def create_output[T](self, name: str, type: type[T], default: T) -> Output[T]:
        return self._outputs.add_value(Output(name, type, default))

    def create_state[T](self, name: str, type: type[T], initial: T) -> State[T]:
        return self._states.add_value(State(name, type, initial))

    def add_algorithm[T: "Algorithm"](self, algorithm: T) -> T:
        assert isinstance(algorithm, Algorithm)
        new_algorithm = algorithm.__class__(
            name=algorithm.name,
            configuration=algorithm._default_configuration,
            settings=algorithm._default_settings,
            _parent=self,
        )
        new_algorithm._setup(algorithm._default_configuration, algorithm._default_settings)
        self._sub_algorithms.append(new_algorithm)
        return new_algorithm

    def _clear_algorithms(self):
        for algorithm in self._sub_algorithms:
            algorithm._clear_algorithms()
        self._sub_algorithms.clear()

    @abstractmethod
    def on_setup(self, configuration: T_CONFIGURATION, settings: T_SETTINGS): ...

    def _setup(self, configuration: T_CONFIGURATION, settings: T_SETTINGS):
        token = Algorithm.__in_setup.set(True)
        try:
            self._clear_algorithms()
            self._inputs.clear_values()
            self._outputs.clear_values()
            self._states.clear_values()
            self.on_setup(configuration, settings)
        finally:
            Algorithm.__in_setup.reset(token)

    @abstractmethod
    def on_settings_changed(self, settings: T_SETTINGS): ...

    def _on_settings_changed(self, settings: T_SETTINGS):
        self._settings = settings.model_copy()
        self._on_settings_changed_called = True
        for sub in self._sub_algorithms:
            sub._on_settings_changed_called = False
        self.on_settings_changed_original(self._settings)
        missed = [s.name for s in self._sub_algorithms if not s._on_settings_changed_called]
        if missed:
            raise RuntimeError(
                f"{self.name!r}: on_settings_changed not called for sub-algorithms: {missed}"
            )

    def _reset(self):
        self._inputs.reset_values()
        self._outputs.reset_values()
        self._states.reset_values()
        for sub in self._sub_algorithms:
            sub._reset()

    def reset(self):
        if not self.is_root:
            raise RuntimeError(f"{self.name!r}: reset() can only be called on a root algorithm")
        self._reset()

    @abstractmethod
    def on_update(self): ...

    def _step(self, step_size: float):
        self._inputs.assert_all_value_updated_flag(state=True)
        for _ in range(2):
            self._inputs.reset_all_value_updated_flag()
            self._outputs.reset_all_value_updated_flag()
            self._states.reset_all_value_updated_flag()
            with self._inputs.with_lock():
                self.on_update()
            self._outputs.assert_all_value_updated_flag(state=True)
            self._states.assert_all_value_updated_flag(state=True)
            for sub in self._sub_algorithms:
                sub._outputs.reset_all_value_changed_flag()
                sub._step(step_size)
            no_sub_output_changed = all(
                sub._outputs.check_all_value_changed_flag(state=False)
                for sub in self._sub_algorithms
            )
            if no_sub_output_changed:
                return
        raise RuntimeError(f"Algorithm {self.name!r} did not converge after 2 iterations")

    def _commit_states(self):
        self._states.commit_all()
        for sub in self._sub_algorithms:
            sub._commit_states()

    def step(self, step_size: float):
        if not self.is_root:
            raise RuntimeError(f"{self.name!r}: step() can only be called on a root algorithm")
        self._step(step_size)
        self._commit_states()
