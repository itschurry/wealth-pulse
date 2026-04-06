from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import scheduler


class SchedulerTests(unittest.TestCase):
    def test_off_session_job_skips_when_kr_market_slot_is_open(self):
        now_utc = datetime(2026, 3, 23, 0, 0, tzinfo=timezone.utc)  # 09:00 KST

        with patch("scheduler.datetime") as mock_datetime, \
             patch("scheduler.is_market_half_hour_slot", return_value=True), \
             patch("scheduler._run") as mock_run:
            mock_datetime.now.return_value = now_utc
            scheduler._off_session_job()

        mock_run.assert_not_called()

    def test_off_session_job_runs_for_non_market_off_session_slot(self):
        now_utc = datetime(2026, 3, 22, 22, 0, tzinfo=timezone.utc)  # 07:00 KST

        with patch("scheduler.datetime") as mock_datetime, \
             patch("scheduler.is_market_half_hour_slot", return_value=False), \
             patch("scheduler._run") as mock_run:
            mock_datetime.now.return_value = now_utc
            scheduler._off_session_job()

        mock_run.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
