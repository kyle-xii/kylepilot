import time
import pyray as rl

from openpilot.common.constants import CV
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.selfdrive.ui.sunnypilot.mici.drive_stats import DriveStats, DriveSummary, format_duration
from openpilot.system.ui.lib.application import gui_app, FontWeight
from openpilot.system.ui.lib.text_measure import measure_text_cached
from openpilot.system.ui.widgets.nav_widget import NavWidget


class DriveSummaryController:
  def __init__(self):
    self.stats = DriveStats()

  def update(self) -> DriveSummary | None:
    sm = ui_state.sm
    def fresh(service):
      return sm.all_checks([service]) and sm.recv_frame[service] >= ui_state.started_frame

    car = sm['carState']
    speed = car.vEgo if fresh('carState') else None
    control = sm['carControl']
    # Actual lateral activity includes sunnypilot's steering-only assistance.
    engaged = bool(control.latActive or control.longActive) if fresh('carControl') else None
    return self.stats.update(time.monotonic(), ui_state.ignition, speed,
                             ui_state.started and not car.standstill and not ui_state.is_body, engaged)


class DriveSummaryScreen(NavWidget):
  def __init__(self, summary: DriveSummary):
    super().__init__()
    self.summary = summary
    self.set_rect(rl.Rectangle(0, 0, gui_app.width, gui_app.height))
    self.set_click_callback(lambda: self.dismiss())
    self._font = gui_app.font(FontWeight.BOLD)
    self._regular = gui_app.font(FontWeight.NORMAL)

  def _text(self, value, x, y, size, color, right=False, bold=False):
    font = self._font if bold else self._regular
    if right:
      x -= measure_text_cached(font, value, size).x
    rl.draw_text_ex(font, value, rl.Vector2(x, y), size, 0, color)

  def _render(self, rect):
    rl.draw_rectangle_rec(rect, rl.Color(15, 19, 23, 255))
    self._text('Drive summary', rect.x + 24, rect.y + 14, 30, rl.WHITE, bold=True)
    rows = [
      ('Drive time', format_duration(self.summary.duration)),
      ('Openpilot engaged', f'{format_duration(self.summary.engaged)} ({self.summary.engaged_percent}%)'),
      ('Top speed', f'{self.summary.top_speed * CV.MS_TO_MPH:.0f} mph'),
      ('Distance', f'{self.summary.distance / 1609.344:.1f} miles'),
    ]
    for i, (label, value) in enumerate(rows):
      y = rect.y + 58 + i * 34
      self._text(label, rect.x + 24, y, 23, rl.Color(180, 189, 199, 255))
      self._text(value, rect.x + rect.width - 24, y, 26, rl.WHITE, right=True, bold=True)
    footer = 'Some data unavailable · Tap to close' if self.summary.incomplete else 'Tap anywhere to close'
    self._text(footer, rect.x + 24, rect.y + 211, 16, rl.Color(140, 150, 160, 255))
    self._text('kylepilot', rect.x + rect.width - 16, rect.y + rect.height - 23,
               12, rl.Color(140, 150, 160, 255), right=True)
