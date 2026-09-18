"""Speed readouts for the comma four driving screen."""
import math
import pyray as rl

from openpilot.common.constants import CV
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import FontWeight, gui_app
from openpilot.system.ui.lib.text_measure import measure_text_cached
from openpilot.system.ui.widgets import Widget


class SpeedReadouts(Widget):
  def __init__(self):
    super().__init__()
    self._font = gui_app.font(FontWeight.BOLD)
    self._label_font = gui_app.font(FontWeight.MEDIUM)
    self._cluster_seen = False
    self._speed: float | None = None
    self._lead_speed: float | None = None

  def _fresh(self, service: str) -> bool:
    sm = ui_state.sm
    return sm.all_checks([service]) and sm.recv_frame[service] >= ui_state.started_frame

  def _update_state(self) -> None:
    # Clear old values before checking messages, including across ignition cycles.
    self._speed = self._lead_speed = None
    if not self._fresh('carState'):
      return

    car_state = ui_state.sm['carState']
    conversion = CV.MS_TO_KPH if ui_state.is_metric else CV.MS_TO_MPH
    cluster_speed = car_state.vEgoCluster
    self._cluster_seen |= math.isfinite(cluster_speed) and cluster_speed > 0.0
    speed = cluster_speed if self._cluster_seen else car_state.vEgo
    if math.isfinite(speed):
      self._speed = max(0.0, speed * conversion)

    if self._fresh('radarState'):
      radar_state = ui_state.sm['radarState']
      lead = radar_state.leadOne
      errors = radar_state.radarErrors
      radar_ok = not (errors.canError or errors.radarFault or errors.wrongConfig or errors.radarUnavailableTemporary)
      # Relative speed uses measured ego speed, not the cluster's display offset.
      if lead.status and radar_ok and math.isfinite(car_state.vEgo) and math.isfinite(lead.vRel):
        self._lead_speed = max(0.0, (car_state.vEgo + lead.vRel) * conversion)

  def _draw_readout(self, center_x: float, top: float, label: str, speed: float | None) -> None:
    width, height = 106, 82
    card = rl.Rectangle(center_x - width / 2, top, width, height)
    rl.draw_rectangle_rounded(card, 0.2, 8, rl.Color(0, 0, 0, 160))
    unit = 'km/h' if ui_state.is_metric else 'mph'
    value = str(round(speed)) if speed is not None else '—'
    for text, font, size, y, color in (
      (label, self._label_font, 12, top + 5, rl.Color(255, 255, 255, 200)),
      (value, self._font, 42, top + 18, rl.WHITE),
      (unit, self._label_font, 14, top + 62, rl.Color(255, 255, 255, 200)),
    ):
      text_width = measure_text_cached(font, text, size).x
      rl.draw_text_ex(font, text, rl.Vector2(center_x - text_width / 2, y), size, 0, color)

  def _render(self, rect: rl.Rectangle) -> None:
    self._draw_readout(rect.x + rect.width / 2, rect.y + 12, 'SPEED', self._speed)
    self._draw_readout(rect.x + rect.width - 16 - 53, rect.y + 12, 'LEAD', self._lead_speed)
