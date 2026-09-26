"""Speed readouts for the comma four driving screen."""
import math
import time
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
    self._cluster_seen = False
    self._drive_frame = -1
    self._trip_since: float | None = None
    self._trip_seconds: int | None = None
    self._stopped_since: float | None = None
    self._stopped_seconds: int | None = None
    self._speed: float | None = None
    self._lead_speed: float | None = None

  def _fresh(self, service: str) -> bool:
    sm = ui_state.sm
    return sm.all_checks([service]) and sm.recv_frame[service] >= ui_state.started_frame

  def _update_state(self) -> None:
    # Clear old values before checking messages, including across ignition cycles.
    self._speed = self._lead_speed = None
    self._stopped_seconds = None
    if self._drive_frame != ui_state.started_frame:
      self._drive_frame = ui_state.started_frame
      self._stopped_since = None
      self._trip_since = None

    if not ui_state.started:
      self._trip_since = None
    elif self._trip_since is None and self._fresh('carState'):
      car_state = ui_state.sm['carState']
      if not car_state.standstill and math.isfinite(car_state.vEgo) and abs(car_state.vEgo) > 0.0:
        self._trip_since = time.monotonic()
    # Continue through stops, disengagements, and temporary carState gaps until the drive ends.
    self._trip_seconds = None if self._trip_since is None else max(0, int(time.monotonic() - self._trip_since))

    if not self._fresh('carState'):
      self._stopped_since = None
      return

    car_state = ui_state.sm['carState']
    if ui_state.started and car_state.standstill and car_state.vEgo == 0.0:
      now = time.monotonic()
      if self._stopped_since is None:
        self._stopped_since = now
      self._stopped_seconds = max(0, int(now - self._stopped_since))
    else:
      self._stopped_since = None
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

  def _draw_readout(self, anchor_x: float, top: float, speed: float | None, align_right: bool = False) -> None:
    if speed is None:
      return
    value = str(round(speed))
    size = 90
    text_width = measure_text_cached(self._font, value, size).x
    x = anchor_x - text_width if align_right else anchor_x - text_width / 2
    rl.draw_text_ex(self._font, value, rl.Vector2(x, top), size, 0, rl.WHITE)

  def _render(self, rect: rl.Rectangle) -> None:
    self._draw_readout(rect.x + rect.width / 2, rect.y - 12, self._speed)
    self._draw_readout(rect.x + rect.width - 4, rect.y - 12, self._lead_speed, align_right=True)
    if self._stopped_seconds is not None:
      minutes, seconds = divmod(self._stopped_seconds, 60)
      value = f'stopped: {minutes}:{seconds:02d}'
      size = 40
      text_width = measure_text_cached(self._font, value, size).x
      # Clear the torque arc at its maximum 26px offset + 56px height, with an 8px gap.
      bottom_clearance = 26 + 56 + 8
      position = rl.Vector2(rect.x + rect.width - 4 - text_width, rect.y + rect.height - size - bottom_clearance)
      rl.draw_text_ex(self._font, value, position, size, 0, rl.WHITE)

    if self._trip_seconds is not None:
      hours, remainder = divmod(self._trip_seconds, 3600)
      minutes, seconds = divmod(remainder, 60)
      value = f'{hours}:{minutes:02d}:{seconds:02d}' if hours else f'{minutes}:{seconds:02d}'
      # Align with the wheel's left edge and clear its turn-intent arrows and the torque arc.
      position = rl.Vector2(rect.x + 21, rect.y + rect.height - 40 - 90)
      rl.draw_text_ex(self._font, value, position, 40, 0, rl.WHITE)
