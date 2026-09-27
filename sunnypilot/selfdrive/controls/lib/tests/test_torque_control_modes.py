from pathlib import Path
from types import SimpleNamespace
import pytest
from unittest.mock import patch  # noqa: TID251

from cereal import car, custom, log
from opendbc.car.vehicle_model import VehicleModel
from openpilot.common.basedir import BASEDIR
from openpilot.selfdrive.controls.lib.latcontrol_torque import LatControlTorque as TorqueV1
from openpilot.selfdrive.modeld.constants import ModelConstants
from openpilot.sunnypilot.selfdrive.controls.lib.latcontrol_torque_v0 import LatControlTorque as TorqueV0


class TestTorqueControlModes:
  def make_controller(self, cls, enabled=True):
    cp = car.CarParams.new_message(mass=1718., wheelbase=2.7, centerToFront=1.188,
                                  steerRatio=16.9, tireStiffnessFront=100000., tireStiffnessRear=100000.,
                                  steerActuatorDelay=0.12, steerLimitTimer=0.4)
    cp.lateralTuning.init("torque")
    cp.lateralTuning.torque.latAccelFactor = 1.5
    cp.lateralTuning.torque.friction = 0.175
    sp = custom.CarParamsSP.new_message()
    sp.neuralNetworkLateralControl.model.path = str(Path(BASEDIR) / "sunnypilot/neural_network_data/neural_network_lateral_control/TOYOTA_PRIUS.json")
    ci = SimpleNamespace(torque_from_lateral_accel=lambda: lambda a, p: a / p.latAccelFactor,
                         lateral_accel_from_torque=lambda: lambda a, p: a * p.latAccelFactor,
                         torque_from_lateral_accel_in_torque_space=lambda: lambda a, p, gravity_adjusted: a.lateral_acceleration / p.latAccelFactor)
    params = SimpleNamespace(get_bool=lambda key: key == "NeuralNetworkLateralControl" and enabled)
    with patch("openpilot.sunnypilot.selfdrive.controls.lib.nnlc.nnlc.Params", return_value=params), \
         patch("openpilot.sunnypilot.selfdrive.controls.lib.latcontrol_torque_ext_override.Params", return_value=params):
      controller = cls(cp.as_reader(), sp.as_reader(), ci, 0.01)
    model = log.ModelDataV2.new_message()
    n = len(ModelConstants.T_IDXS)
    model.orientation.x = [0.] * n
    model.orientation.y = [0.] * n
    model.acceleration.y = [0.1] * n
    controller.extension.update_model_v2(model)
    controller.extension.update_lateral_lag(0.33)
    return controller, VehicleModel(cp)

  def step(self, controller, vm, active=True, speed=25., pressed=False, limited=False, curvature=0.00016):
    cs = car.CarState.new_message(vEgo=speed, steeringPressed=pressed)
    params = log.LiveParametersData.new_message()
    return controller.update(active, cs, vm, params, limited, curvature, None, False, 0.33)[0]

  @pytest.mark.parametrize("cls", [TorqueV0, TorqueV1])
  @pytest.mark.parametrize("enabled", [False, True])
  @pytest.mark.parametrize("curvature", [-0.01, -0.00016, 0., 0.00016, 0.01])
  def test_one_pid_update_and_bounded_output(self, cls, enabled, curvature):
    c, vm = self.make_controller(cls, enabled)
    with patch.object(c.pid, "update", wraps=c.pid.update) as update:
      output = self.step(c, vm, curvature=curvature)
    assert update.call_count == 1
    assert abs(output) <= 1.
    if enabled:
      assert c.pid.pos_limit == 1.
      assert c.pid.neg_limit == -1.

  @pytest.mark.parametrize("cls", [TorqueV0, TorqueV1])
  @pytest.mark.parametrize("enabled", [False, True])
  @pytest.mark.parametrize("kwargs", [{"pressed": True}, {"limited": True}, {"speed": 4.}])
  def test_integrator_freeze_and_inactive(self, cls, enabled, kwargs):
    c, vm = self.make_controller(cls, enabled)
    self.step(c, vm)
    before = c.pid.i
    self.step(c, vm, **kwargs)
    assert c.pid.i == before
    with patch.object(c.pid, "update", wraps=c.pid.update) as update:
      assert self.step(c, vm, active=False) == 0.
    update.assert_not_called()

  @pytest.mark.parametrize("cls", [TorqueV0, TorqueV1])
  def test_mode_transitions_reset_integrator_and_limits(self, cls):
    c, vm = self.make_controller(cls)
    for valid in (True, False, True, False):
      c.pid.i = 0.6
      c.extension.model_valid = valid
      self.step(c, vm, limited=True)
      assert c.pid.i == 0.
      assert c.pid.pos_limit == (1. if valid else 1.5)
      assert c.pid.neg_limit == (-1. if valid else -1.5)

  @pytest.mark.parametrize("cls", [TorqueV0, TorqueV1])
  def test_live_params_cannot_replace_neural_torque_limits(self, cls):
    c, vm = self.make_controller(cls)
    self.step(c, vm)
    c.update_live_torque_params(2., -0.2, 0.18)
    self.step(c, vm)
    assert c.pid.pos_limit == 1.
    c.extension.model_valid = False
    self.step(c, vm)
    assert c.pid.pos_limit == 2.
