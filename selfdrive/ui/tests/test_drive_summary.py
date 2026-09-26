from types import SimpleNamespace
import pytest

from openpilot.selfdrive.ui.sunnypilot.mici import drive_summary
from openpilot.selfdrive.ui.sunnypilot.mici.drive_stats import DriveSummary
from openpilot.selfdrive.ui.mici.layouts import main


@pytest.mark.parametrize('lat, longitudinal, expected', [(True, False, 100), (False, True, 100), (True, True, 100), (False, False, 0)])
def test_controller_counts_active_steering_only(monkeypatch, lat, longitudinal, expected):
  class Messages(dict):
    recv_frame = {'carState': 100, 'carControl': 100}
    def all_checks(self, services):
      return True
  sm = Messages(carState=SimpleNamespace(vEgo=10.0, standstill=False),
                carControl=SimpleNamespace(latActive=lat, longActive=longitudinal))
  state = SimpleNamespace(sm=sm, started=True, ignition=True, is_body=False, started_frame=10)
  monkeypatch.setattr(drive_summary, 'ui_state', state)
  now = [0.0]
  monkeypatch.setattr(drive_summary.time, 'monotonic', lambda: now[0])
  controller = drive_summary.DriveSummaryController()
  assert controller.update() is None
  now[0] = 1.0
  controller.update()
  state.ignition = state.started = False
  now[0] = 2.0
  result = controller.update()
  assert result.engaged_percent == expected


def test_shutdown_shows_summary_and_restart_closes_it(monkeypatch):
  screen = object()
  stack = []
  app = SimpleNamespace(widget_in_stack=lambda w: w in stack,
                        pop_widgets_to=lambda *args, **kwargs: stack.clear(),
                        push_widget=stack.append)
  monkeypatch.setattr(main, 'gui_app', app)
  monkeypatch.setattr(main, 'DriveSummaryScreen', lambda summary: screen)
  monkeypatch.setattr(main.rl, 'get_time', lambda: 10.0)
  state = SimpleNamespace(started=False, sm={'carState': SimpleNamespace(standstill=True)})
  monkeypatch.setattr(main, 'ui_state', state)
  layout = main.MiciMainLayout.__new__(main.MiciMainLayout)
  layout._onboarding_window = object()
  summaries = iter([DriveSummary(10, 5, 10, 100, False), None])
  layout._drive_summary = SimpleNamespace(update=lambda: next(summaries))
  layout._summary_screen = None
  layout._prev_onroad = True
  layout._prev_standstill = True
  layout._onroad_time_delay = 1.0
  layout._home_layout = object()
  layout._scroll_to = lambda widget: None
  layout._handle_transitions()
  assert layout._onroad_time_delay is None
  assert stack == [screen]
  state.started = True
  layout._handle_transitions()
  assert not stack
  assert layout._onroad_time_delay == 10.0
