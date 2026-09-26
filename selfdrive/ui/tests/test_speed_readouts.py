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
  state = SimpleNamespace(sm=sm, is_metric=False, started_frame=50, started=True)
  widget = speed_readouts.SpeedReadouts.__new__(speed_readouts.SpeedReadouts)
  speed_readouts.Widget.__init__(widget)
  widget._cluster_seen = False
  widget._drive_frame = -1
  widget._trip_since = None
  widget._trip_seconds = None
  widget._stopped_since = None
  widget._stopped_seconds = None
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


def test_stopped_timer_counts_and_resets_on_movement(readouts, monkeypatch):
  widget, state = readouts
  now = [100.0]
  monkeypatch.setattr(speed_readouts.time, 'monotonic', lambda: now[0])
  state.sm['carState'].vEgo = 0.0
  state.sm['carState'].standstill = True
  widget._update_state()
  assert widget._stopped_seconds == 0
  now[0] = 161.9
  widget._update_state()
  assert widget._stopped_seconds == 61
  state.sm['carState'].standstill = False
  widget._update_state()
  assert widget._stopped_seconds is None
  state.sm['carState'].vEgo = 0.0
  state.sm['carState'].standstill = True
  widget._update_state()
  assert widget._stopped_seconds == 0


@pytest.mark.parametrize('reset', ['stale', 'offroad', 'new_drive'])
def test_stopped_timer_does_not_carry_across_data_gaps_or_drives(readouts, monkeypatch, reset):
  widget, state = readouts
  now = [100.0]
  monkeypatch.setattr(speed_readouts.time, 'monotonic', lambda: now[0])
  state.sm['carState'].vEgo = 0.0
  state.sm['carState'].standstill = True
  widget._update_state()
  now[0] = 110.0
  if reset == 'stale':
    state.sm.alive['carState'] = False
  elif reset == 'offroad':
    state.started = False
  else:
    state.started_frame = 90
  widget._update_state()
  assert widget._stopped_seconds == (0 if reset == 'new_drive' else None)
  state.sm.alive['carState'] = True
  state.started = True
  widget._update_state()
  assert widget._stopped_seconds == 0


def test_stopped_timer_resets_when_moving_while_hidden(readouts, monkeypatch):
  widget, state = readouts
  now = [100.0]
  monkeypatch.setattr(speed_readouts.time, 'monotonic', lambda: now[0])
  widget.set_visible(False)
  state.sm['carState'].vEgo = 0.0
  state.sm['carState'].standstill = True
  widget.render()
  now[0] = 120.0
  widget.render()
  assert widget._stopped_seconds == 20
  state.sm['carState'].standstill = False
  widget.render()
  assert widget._stopped_seconds is None
  state.sm['carState'].vEgo = 0.0
  state.sm['carState'].standstill = True
  widget.render()
  assert widget._stopped_seconds == 0


@pytest.mark.parametrize('speed', [0.01, -0.01, 0.2, float('nan'), float('inf')])
def test_stopped_timer_requires_zero_actual_speed(readouts, monkeypatch, speed):
  widget, state = readouts
  now = [100.0]
  monkeypatch.setattr(speed_readouts.time, 'monotonic', lambda: now[0])
  car_state = state.sm['carState']
  car_state.standstill = True
  car_state.vEgo = 0.0
  widget._update_state()
  now[0] += 10
  widget._update_state()
  assert widget._stopped_seconds == 10
  # Even creep that rounds to 0 mph must clear the timer, despite standstill being true.
  car_state.vEgo = speed
  widget._update_state()
  assert widget._stopped_seconds is None
  now[0] += 10
  widget._update_state()
  assert widget._stopped_seconds is None
  car_state.vEgo = 0.0
  widget._update_state()
  assert widget._stopped_seconds == 0


def test_trip_timer_starts_on_movement_and_continues_through_stops(readouts, monkeypatch):
  widget, state = readouts
  now = [100.0]
  monkeypatch.setattr(speed_readouts.time, 'monotonic', lambda: now[0])
  car = state.sm['carState']
  car.vEgo = 0.0
  car.standstill = True
  widget._update_state()
  assert widget._trip_seconds is None
  now[0] = 150.0
  car.vEgo = 1.0
  car.standstill = False
  widget._update_state()
  assert widget._trip_seconds == 0
  now[0] = 200.0
  car.vEgo = 0.0
  car.standstill = True
  widget._update_state()
  assert widget._trip_seconds == 50
  now[0] = 3811.0
  widget._update_state()
  assert widget._trip_seconds == 3661
  state.started = False
  widget._update_state()
  assert widget._trip_seconds is None
  state.started = True
  state.started_frame = 90
  widget._update_state()
  assert widget._trip_seconds is None


def test_trip_timer_survives_data_gaps_and_hidden_alerts_but_not_new_drive(readouts, monkeypatch):
  widget, state = readouts
  now = [100.0]
  monkeypatch.setattr(speed_readouts.time, 'monotonic', lambda: now[0])
  widget.set_visible(False)
  widget.render()
  assert widget._trip_seconds == 0
  state.sm.alive['carState'] = False
  now[0] = 130.0
  widget.render()
  assert widget._trip_seconds == 30
  state.sm.alive['carState'] = True
  now[0] = 160.0
  widget.render()
  assert widget._trip_seconds == 60
  # Offroad screens may not render this widget, so the next drive must also reset it.
  state.started_frame = 90
  state.sm['carState'].vEgo = 0.0
  widget.render()
  assert widget._trip_seconds is None


@pytest.mark.parametrize('failure', ['zero', 'nan', 'infinity', 'standstill', 'stale', 'offroad'])
def test_trip_timer_does_not_start_without_valid_movement(readouts, failure):
  widget, state = readouts
  if failure in ('zero', 'nan', 'infinity'):
    state.sm['carState'].vEgo = {'zero': 0.0, 'nan': float('nan'), 'infinity': float('inf')}[failure]
  elif failure == 'standstill':
    state.sm['carState'].standstill = True
  elif failure == 'stale':
    state.sm.alive['carState'] = False
  else:
    state.started = False
  widget._update_state()
  assert widget._trip_seconds is None
