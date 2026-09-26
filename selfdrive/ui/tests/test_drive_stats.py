import pytest
from openpilot.selfdrive.ui.sunnypilot.mici.drive_stats import DriveStats, format_duration


@pytest.mark.parametrize('seconds, expected', [(0, '00:00'), (9, '00:09'), (65, '01:05'), (3600, '60:00'), (6005, '100:05')])
def test_duration_format(seconds, expected):
  assert format_duration(seconds) == expected


def test_full_trip_stops_engagement_and_ignition_reset():
  stats = DriveStats()
  stats.update(0, True, 0, False, False)
  assert stats.started_at is None
  stats.update(10, True, 10, True, True)
  for t in range(11, 16):
    stats.update(t, True, 10, True, t < 15)
  for t in range(16, 20):
    stats.update(t, True, 0, False, False)
  summary = stats.update(20, False, None, False, None)
  assert summary.duration == 10
  assert summary.engaged == 5
  assert summary.engaged_percent == 50
  assert summary.top_speed == 10
  assert summary.distance == 55
  assert not summary.incomplete
  assert stats.update(21, False, None, False, None) is None
  stats.update(30, True, 1, True, False)
  summary = stats.update(31, False, None, False, None)
  assert summary.duration == 1
  assert summary.top_speed == 1
  assert summary.engaged == 0


def test_data_gaps_are_not_invented_distance_or_engagement():
  stats = DriveStats()
  stats.update(0, True, 20, True, True)
  stats.update(10, True, 20, True, True)
  stats.update(11, True, float('nan'), True, None)
  stats.update(12, True, 0, False, False)
  result = stats.update(13, False, None, False, None)
  assert result.duration == 13
  assert result.distance == 0
  assert result.engaged == 0
  assert result.incomplete


def test_reverse_distance_and_no_summary_without_movement():
  stats = DriveStats()
  stats.update(0, True, 0, False, False)
  assert stats.update(1, False, None, False, None) is None
  stats.update(2, True, -2, True, False)
  stats.update(3, True, -2, True, False)
  result = stats.update(4, False, None, False, None)
  assert result.distance == 2
  assert result.top_speed == 2
