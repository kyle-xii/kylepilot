from types import SimpleNamespace

import pytest
from cereal import messaging
from openpilot.common.constants import CV
from openpilot.selfdrive.ui.sunnypilot.mici.onroad import speed_readouts


@pytest.fixture
def readouts(monkeypatch):
  sm = messaging.SubMaster(['carState', 'radarState'])
  for service in sm.services:
    sm.data[service] = getattr(messaging.new_message(service), service)
    sm.alive[service] = sm.valid[service] = sm.freq_ok[service] = True
    sm.recv_frame[service] = 100
  sm['carState'].vEgo = 20.0
  sm['carState'].vEgoCluster = 22.0
  sm['radarState'].leadOne.status = True
  sm['radarState'].leadOne.vRel = -5.0
  state = SimpleNamespace(sm=sm, is_metric=False, started_frame=50)
  widget = speed_readouts.SpeedReadouts.__new__(speed_readouts.SpeedReadouts)
  widget._cluster_seen = False
  monkeypatch.setattr(speed_readouts, 'ui_state', state)
  return widget, state


@pytest.mark.parametrize('metric, conversion', [(False, CV.MS_TO_MPH), (True, CV.MS_TO_KPH)])
def test_units_and_lead_speed_ignores_cluster_offset(readouts, metric, conversion):
  widget, state = readouts
  state.is_metric = metric
  widget._update_state()
  assert widget._speed == pytest.approx(22.0 * conversion)
  assert widget._lead_speed == pytest.approx(15.0 * conversion)


@pytest.mark.parametrize('service', ['carState', 'radarState'])
@pytest.mark.parametrize('failure', ['alive', 'valid', 'freq_ok', 'previous_drive'])
def test_stale_or_invalid_data_clears_previous_reading(readouts, service, failure):
  widget, state = readouts
  widget._update_state()
  assert widget._lead_speed is not None
  if failure == 'previous_drive':
    state.sm.recv_frame[service] = state.started_frame - 1
  else:
    getattr(state.sm, failure)[service] = False
  widget._update_state()
  assert widget._lead_speed is None
  if service == 'carState':
    assert widget._speed is None
  else:
    assert widget._speed is not None


@pytest.mark.parametrize('failure', ['no_lead', 'radar_error', 'nan_ego', 'nan_relative'])
def test_unavailable_lead_clears_previous_reading(readouts, failure):
  widget, state = readouts
  widget._update_state()
  if failure == 'no_lead':
    state.sm['radarState'].leadOne.status = False
  elif failure == 'radar_error':
    state.sm['radarState'].radarErrors.radarFault = True
  elif failure == 'nan_ego':
    state.sm['carState'].vEgo = float('nan')
  else:
    state.sm['radarState'].leadOne.vRel = float('nan')
  widget._update_state()
  assert widget._lead_speed is None


def test_cluster_fallback_and_standstill(readouts):
  widget, state = readouts
  state.sm['carState'].vEgoCluster = 0.0
  widget._update_state()
  assert widget._speed == pytest.approx(20.0 * CV.MS_TO_MPH)
  state.sm['carState'].vEgoCluster = 22.0
  widget._update_state()
  state.sm['carState'].vEgoCluster = 0.0
  state.sm['carState'].vEgo = 0.0
  state.sm['radarState'].leadOne.vRel = -0.1
  widget._update_state()
  assert widget._speed == 0.0
  assert widget._lead_speed == 0.0
