"""Tests for the deterministic Vorerkrankung trigger (itsg.vorerkrankung).

The official test constellation (Hinweise_DTA-EEL-Bespiel_Vorerkrankung_
Testkonstellation.docx) is the ground truth for the numbers: prior AUs
14.07.–15.07.2025, 01.10.–17.10.2025, 01.12.–03.12.2025, 01.03.–03.03.2026
(25 days) plus the current AU from 11.03.2026 (10 known days) = 35 ≥ 30.
"""
from __future__ import annotations

import unittest
from datetime import date

from itsg.vorerkrankung import (
    STATUS_NO_TRIGGER,
    STATUS_NOT_EVALUATED,
    STATUS_TRIGGER,
    Episode,
    add_months,
    day_count,
    evaluate,
)

CONSTELLATION = [
    Episode("2025-07-14", "2025-07-15", True),
    Episode("2025-10-01", "2025-10-17", True),
    Episode("2025-12-01", "2025-12-03", True),
    Episode("2026-03-01", "2026-03-03", True),
]
CURRENT = Episode("2026-03-11", "2026-03-20", True)
REPORTING = date(2026, 3, 11)


class TestCalendarMath(unittest.TestCase):
    def test_inclusive_day_count_matches_official_numbers(self):
        self.assertEqual(day_count(date(2025, 7, 14), date(2025, 7, 15)), 2)
        self.assertEqual(day_count(date(2025, 10, 1), date(2025, 10, 17)), 17)
        self.assertEqual(day_count(date(2026, 3, 1), date(2026, 3, 3)), 3)

    def test_add_months_clamps_to_month_end(self):
        self.assertEqual(add_months(date(2026, 3, 31), -6), date(2025, 9, 30))
        self.assertEqual(add_months(date(2026, 3, 11), -6), date(2025, 9, 11))
        self.assertEqual(add_months(date(2026, 3, 11), -12), date(2025, 3, 11))


class TestOfficialConstellation(unittest.TestCase):
    def test_trigger_with_official_numbers(self):
        result = evaluate(CURRENT, CONSTELLATION, REPORTING)
        self.assertEqual(result.status, STATUS_TRIGGER)
        self.assertEqual(result.days_prior, 25)
        self.assertEqual(result.days_current, 10)
        self.assertEqual(result.days_total, 35)
        self.assertTrue(result.criteria["cumulative_30_days_12_months"]["satisfied"])
        self.assertTrue(result.criteria["prior_within_6_months"]["satisfied"])

    def test_module_version_and_citation_recorded(self):
        result = evaluate(CURRENT, CONSTELLATION, REPORTING)
        self.assertTrue(result.module_version.startswith("itsg.vorerkrankung/"))
        self.assertIn("3.12", result.citation)
        self.assertTrue(result.interpretation_notes)


class TestBoundaries(unittest.TestCase):
    def test_29_days_does_not_trigger(self):
        prior = [Episode("2025-06-01", "2025-06-28", True)]  # 28 days
        result = evaluate(Episode("2026-03-01", "2026-03-01", True), prior, date(2026, 3, 1))
        self.assertEqual(result.status, STATUS_NO_TRIGGER)
        self.assertEqual(result.days_total, 29)

    def test_exactly_30_days_triggers(self):
        prior = [Episode("2025-12-01", "2025-12-28", True)]  # 28 days, within 6 months
        result = evaluate(Episode("2026-03-01", "2026-03-02", True), prior, date(2026, 3, 1))
        self.assertEqual(result.status, STATUS_TRIGGER)
        self.assertEqual(result.days_total, 30)

    def test_prior_au_older_than_6_months_does_not_satisfy_proximity(self):
        prior = [Episode("2025-01-01", "2025-01-30", True)]  # 30 days but too old
        result = evaluate(CURRENT, prior, REPORTING)
        self.assertEqual(result.status, STATUS_NO_TRIGGER)
        self.assertFalse(result.criteria["prior_within_6_months"]["satisfied"])
        self.assertFalse(result.criteria["cumulative_30_days_12_months"]["satisfied"])

    def test_unattested_current_absence_never_triggers(self):
        result = evaluate(Episode("2026-03-11", "2026-03-20", False), CONSTELLATION, REPORTING)
        self.assertEqual(result.status, STATUS_NO_TRIGGER)
        self.assertFalse(result.criteria["certificate_current"]["satisfied"])

    def test_unattested_episodes_are_excluded_from_counting(self):
        mixed = CONSTELLATION + [Episode("2026-02-01", "2026-02-20", False)]  # 20 unattested days
        result = evaluate(CURRENT, mixed, REPORTING)
        self.assertEqual(result.days_prior, 25)  # unchanged
        self.assertIn("bescheinigte", " ".join(result.trace))


class TestOpenEndAndFailClosed(unittest.TestCase):
    def test_open_ended_current_absence_counts_one_week_from_reporting_date(self):
        result = evaluate(Episode("2026-03-11", None, True), CONSTELLATION, REPORTING)
        self.assertEqual(result.days_current, 7)  # 11.03.–17.03. inclusive
        self.assertEqual(result.days_total, 32)
        self.assertEqual(result.status, STATUS_TRIGGER)

    def test_open_ended_prior_episode_is_not_evaluated(self):
        result = evaluate(CURRENT, [Episode("2025-07-14", None, True)], REPORTING)
        self.assertEqual(result.status, STATUS_NOT_EVALUATED)
        self.assertTrue(any("open-ended" in line for line in result.trace))

    def test_missing_current_start_is_not_evaluated(self):
        result = evaluate(Episode(None, "2026-03-20", True), CONSTELLATION, REPORTING)
        self.assertEqual(result.status, STATUS_NOT_EVALUATED)

    def test_unparseable_date_is_not_evaluated(self):
        result = evaluate(Episode("not-a-date", "2026-03-20", True), CONSTELLATION, REPORTING)
        self.assertEqual(result.status, STATUS_NOT_EVALUATED)


if __name__ == "__main__":
    unittest.main()
