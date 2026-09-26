"""Per-ignition trip statistics, independent of rendering and engagement toggles."""
import math
from dataclasses import dataclass


def format_duration(seconds: float) -> str:
  minutes, seconds = divmod(max(0, int(seconds)), 60)
  return f'{minutes:02d}:{seconds:02d}'


@dataclass(frozen=True)
class DriveSummary:
  duration: float
  engaged: float
  top_speed: float
  distance: float
  incomplete: bool

  @property
  def engaged_percent(self) -> int:
    return round(100 * min(self.engaged, self.duration) / self.duration) if self.duration > 0 else 0


class DriveStats:
  def __init__(self):
    self.started_at: float | None = None
    self.last_time: float | None = None
    self.last_speed: float | None = None
    self.last_engaged: bool | None = None
    self.engaged = 0.0
    self.distance = 0.0
    self.top_speed = 0.0
    self.incomplete = False

  def update(self, now: float, ignition: bool, speed: float | None, moving: bool,
             engaged: bool | None) -> DriveSummary | None:
    speed = abs(speed) if speed is not None and math.isfinite(speed) else None
    if not ignition:
      summary = None
      if self.started_at is not None:
        duration = max(0.0, now - self.started_at)
        # Credit the final short interval using the last known engagement state.
        dt = max(0.0, now - self.last_time) if self.last_time is not None else 0.0
        if dt <= 1.0 and self.last_engaged:
          self.engaged += dt
        summary = DriveSummary(duration, min(duration, self.engaged), self.top_speed, self.distance, self.incomplete)
      self.__init__()
      return summary

    if self.started_at is None:
      if not moving or speed is None or speed == 0:
        return None
      self.started_at = now

    if self.last_time is not None:
      dt = max(0.0, now - self.last_time)
      if dt <= 1.0:
        if speed is not None and self.last_speed is not None:
          self.distance += (speed + self.last_speed) * 0.5 * dt
        else:
          self.incomplete = True
        if engaged is not None and self.last_engaged is not None:
          if self.last_engaged:
            self.engaged += dt
        else:
          self.incomplete = True
      else:
        self.incomplete = True
    if speed is not None:
      self.top_speed = max(self.top_speed, speed)
    self.last_time, self.last_speed, self.last_engaged = now, speed, engaged
    return None
