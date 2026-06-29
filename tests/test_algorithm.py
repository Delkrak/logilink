import pytest
from pydantic import BaseModel

from logilink.algorithm import Algorithm


class EmptyModel(BaseModel):
    pass


class DelayConfig(BaseModel):
    initial: float = 0.0


class StateSpaceConfig(BaseModel):
    initial: float = 0.0


class StateSpaceSettings(BaseModel):
    a: float = 0.0
    b: float = 1.0
    c: float = 1.0
    d: float = 0.0


class Delay(Algorithm[DelayConfig, EmptyModel]):
    def on_setup(self, config: DelayConfig, settings: EmptyModel):
        self.input_u = self.create_input("u", float)
        self.output_y = self.create_output("y", float, config.initial)
        self.state_x = self.create_state("x", float, config.initial)

    def on_settings_changed(self, settings: EmptyModel):
        pass

    def on_update(self):
        self.output_y.value = self.state_x.value
        self.state_x.next = self.input_u.value


class StateSpace(Algorithm[StateSpaceConfig, StateSpaceSettings]):
    """x[n+1] = a*x[n] + b*u[n],  y[n] = c*x[n] + d*u[n].
    State x is held in the inner DelayAlgorithm.
    """

    def on_setup(self, config: StateSpaceConfig, settings: StateSpaceSettings):
        self.input_u = self.create_input("u", float)
        self.output_y = self.create_output("y", float, 0.0)
        self.block_delay = self.add_algorithm(
            Delay("delay", DelayConfig(initial=config.initial), EmptyModel())
        )

    def on_settings_changed(self, settings: StateSpaceSettings):
        self.block_delay.on_settings_changed(EmptyModel())

    def on_update(self):
        x = self.block_delay.output_y.value
        u = self.input_u.value
        s = self.settings
        self.output_y.value = s.c * x + s.d * u
        self.block_delay.input_u.value = s.a * x + s.b * u


class CounterAlgorithm(Algorithm[EmptyModel, EmptyModel]):
    def on_setup(self, configuration, settings):
        self.input_increment = self.create_input("increment", float)
        self.output_total = self.create_output("total", float, 0.0)
        self.state_counter = self.create_state("counter", float, 0.0)

    def on_settings_changed(self, settings: EmptyModel):
        pass

    def on_update(self):
        self.state_counter.next = self.state_counter.value + self.input_increment.value
        self.output_total.value = self.state_counter.value + self.input_increment.value


class DemoAlgorithmConfiguration(BaseModel):
    create_subalgorithm: bool = True


class DemoAlgorithmSettings(DemoAlgorithmConfiguration):
    gain: int = 10


class DemoAlgorithm(Algorithm[DemoAlgorithmConfiguration, DemoAlgorithmSettings]):
    configuration_class = DemoAlgorithmConfiguration
    settings_class = DemoAlgorithmSettings

    def on_setup(self, configuration: DemoAlgorithmConfiguration, settings: DemoAlgorithmSettings):
        self.input_value = self.create_input("input", float)
        self.output_value = self.create_output("output", float, 0.0)

        self.block_sub = None
        if configuration.create_subalgorithm:
            self.block_sub = self.add_algorithm(
                DemoAlgorithm(
                    "subalgorithm",
                    DemoAlgorithmConfiguration(create_subalgorithm=False),
                    settings,
                )
            )

    def on_settings_changed(self, settings: DemoAlgorithmSettings):
        if self.block_sub:
            self.block_sub.on_settings_changed(self.settings)

    def on_update(self):
        value = self.input_value.value * self.settings.gain
        if self.block_sub:
            self.block_sub.input_value.value = value
            self.output_value.value = self.block_sub.output_value.value
        else:
            self.output_value.value = value


def _demo(*, create_subalgorithm: bool = True, gain: int = 3) -> DemoAlgorithm:
    config = DemoAlgorithmConfiguration(create_subalgorithm=create_subalgorithm)
    settings = DemoAlgorithmSettings(gain=gain)
    return DemoAlgorithm("root", config, settings)


def test_auto_initializes_on_construction():
    algo = DemoAlgorithm(
        "root",
        DemoAlgorithmConfiguration(create_subalgorithm=False),
        DemoAlgorithmSettings(gain=1),
    )
    assert algo.input_value is not None
    assert algo.output_value is not None


def test_step_without_subalgorithm():
    algo = _demo(create_subalgorithm=False, gain=3)
    algo.input_value.value = 2.0
    algo.step(1.0)
    assert algo.output_value.value == 6.0


def test_step_with_subalgorithm():
    algo = _demo(create_subalgorithm=True, gain=3)
    algo.input_value.value = 2.0
    algo.step(1.0)
    assert algo.output_value.value == 18.0
    algo.input_value.value = 2.0
    algo.step(1.0)
    assert algo.output_value.value == 18.0


def test_update_settings_propagates():
    algo = _demo(create_subalgorithm=True, gain=5)
    algo.input_value.value = 2.0
    algo.step(1.0)
    assert algo.output_value.value == 50.0


def test_reset_restores_initial_state():
    algo = _demo(create_subalgorithm=True, gain=3)
    algo.input_value.value = 2.0
    algo.step(1.0)
    algo.input_value.value = 2.0
    algo.step(1.0)
    assert algo.output_value.value == 18.0

    algo.reset()
    assert not algo.input_value.value_set
    assert algo.output_value.value == 0.0


def test_state_accumulates_across_steps():
    algo = CounterAlgorithm("counter", EmptyModel(), EmptyModel())
    algo.input_increment.value = 1.0
    algo.step(1.0)
    assert algo.output_total.value == 1.0
    algo.input_increment.value = 1.0
    algo.step(1.0)
    assert algo.output_total.value == 2.0


def test_state_reset_restores_initial():
    algo = CounterAlgorithm("counter", EmptyModel(), EmptyModel())
    algo.input_increment.value = 5.0
    algo.step(1.0)
    assert algo.state_counter.value == 5.0
    algo.reset()
    assert algo.state_counter.value == 0.0


def test_delay_is_one_step_behind():
    algo = Delay("d", DelayConfig(initial=0.0), EmptyModel())
    for inp, expected_out in [(3.0, 0.0), (5.0, 3.0), (7.0, 5.0)]:
        algo.input_u.value = inp
        algo.step(1.0)
        assert algo.output_y.value == expected_out


class ForgetfulAlgorithm(Algorithm[EmptyModel, EmptyModel]):
    """Has a sub-algorithm but never calls its on_settings_changed."""

    def on_setup(self, config: EmptyModel, settings: EmptyModel):
        self.input_x = self.create_input("x", float)
        self.output_y = self.create_output("y", float, 0.0)
        self.block_counter = self.add_algorithm(
            CounterAlgorithm("counter", EmptyModel(), EmptyModel())
        )

    def on_settings_changed(self, settings: EmptyModel):
        pass  # deliberately forgets block_counter

    def on_update(self):
        self.block_counter.input_increment.value = self.input_x.value
        self.output_y.value = self.block_counter.output_total.value


def test_settings_class_must_inherit_configuration_class():
    with pytest.raises(TypeError, match="subclass"):

        class BadAlgorithm(Algorithm[DemoAlgorithmConfiguration, DemoAlgorithmSettings]):
            configuration_class = DemoAlgorithmSettings  # reversed: wrong hierarchy
            settings_class = DemoAlgorithmConfiguration

            def on_setup(self, config, settings): ...

            def on_settings_changed(self, settings): ...

            def on_update(self): ...


def test_step_raises_on_non_root():
    algo = StateSpace("ss", StateSpaceConfig(), StateSpaceSettings())
    with pytest.raises(RuntimeError, match="root"):
        algo.block_delay.step(1.0)


def test_reset_raises_on_non_root():
    algo = StateSpace("ss", StateSpaceConfig(), StateSpaceSettings())
    with pytest.raises(RuntimeError, match="root"):
        algo.block_delay.reset()


def test_on_settings_changed_updates_settings():
    algo = _demo(create_subalgorithm=False, gain=3)
    algo.on_settings_changed(DemoAlgorithmSettings(gain=7))
    assert algo.settings.gain == 7


def test_on_settings_changed_raises_if_sub_not_notified():
    algo = ForgetfulAlgorithm("f", EmptyModel(), EmptyModel())
    with pytest.raises(RuntimeError, match="counter"):
        algo.on_settings_changed(EmptyModel())


def test_on_settings_changed_cascades_to_inner_block():
    algo = StateSpace("ss", StateSpaceConfig(), StateSpaceSettings())
    algo.on_settings_changed(StateSpaceSettings(a=0.9))
    assert algo.settings.a == 0.9
    assert algo.block_delay._on_settings_changed_called


def test_state_space_with_delay():
    # x[n+1] = a*x[n] + b*u,  y[n] = c*x[n] + d*u,  x[0]=0, u constant
    # Closed-form: x[n] = b*u*(1 - a**n) / (1 - a)
    # Delay block introduces 1-step lag, so y_out at step n reads x[n-1].
    a, b, c, d, u = 0.5, 0.6, 0.7, 0.8, 0.9
    algo = StateSpace(
        "ss",
        StateSpaceConfig(initial=0.0),
        StateSpaceSettings(a=a, b=b, c=c, d=d),
    )
    for n in range(1, 5):
        x_n = b * u * (1 - a**n) / (1 - a)
        x_n_prev = b * u * (1 - a ** (n - 1)) / (1 - a)
        algo.input_u.value = u
        algo.step(1.0)
        assert algo.block_delay.state_x.value == pytest.approx(x_n)
        assert algo.output_y.value == pytest.approx(c * x_n_prev + d * u)
