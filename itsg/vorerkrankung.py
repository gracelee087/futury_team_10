"""Vorerkrankungsanfrage trigger rule — deterministic, versioned (plan.md step 2).

Rule source (normative wording, official corpus):

  Verfahrensbeschreibung DTA EEL, Punkt 3.12 „Datenbaustein DBVO –
  Vorerkrankungszeiten", Version 13.4, ab 01.01.2027, S. 135–136
  (ITSG Files/Rules details/2026_03_10_Endfassung_Verfahrensbeschreibung_
  DTA_EEL_Version_13.4_ab_01.01.2027.pdf, SHA-256 94ecfd87…e1397).

Trigger (all must hold, evaluation at the reporting date):

  1. a sickness certificate exists for the current absence
     („dem Arbeitgeber für die aktuelle Arbeitsunfähigkeit eine
     Arbeitsunfähigkeitsbescheinigung vorliegt");
  2. at least one certified potential prior sickness within the last
     6 months before the current absence begins (machine criterion,
     same document: between the start of the current AU and the end of
     the last certified AU no more than 6 months may lie);
  3. the accumulated times of all potential prior sicknesses within the
     last 12 months together with the current absence comprise at least
     30 days at the time of the report
     („... mindestens 30 Tage umfassen").

Open-ended absences (no end date): judged with a duration of one week
into the future from the reporting date („mit einer Dauer von einer Woche
in die Zukunft ab dem Tagesdatum zu beurteilen").

Fail closed: incomplete or invalid input returns NOT_EVALUATED, never a
trigger. Only certified („bescheinigte") episodes count; unattested
episodes are excluded and reported. This module implements the transmit-
side employer check only — it creates no benefit claim (plan.md boundary).

Interpretation decisions that a qualified human reviewer must confirm at
the criterion gate (G3) are listed in INTERPRETATION_NOTES and echoed in
every result.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

MODULE_VERSION = "itsg.vorerkrankung/0.1.0"

CITATION = (
    "Verfahrensbeschreibung DTA EEL, Punkt 3.12 „Datenbaustein DBVO – "
    "Vorerkrankungszeiten“, Version 13.4, ab 01.01.2027, S. 135–136"
)

STATUS_TRIGGER = "TRIGGER"
STATUS_NO_TRIGGER = "NO_TRIGGER"
STATUS_NOT_EVALUATED = "NOT_EVALUATED"

MIN_TOTAL_DAYS = 30
PROXIMITY_MONTHS = 6
WINDOW_MONTHS = 12
OPEN_END_DAYS = 7  # open-ended absence counts as one week from the reporting date

INTERPRETATION_NOTES = (
    "Kalendertage inklusive beider Endpunkte gezählt (offizielle Konstellation: "
    "14.07.–15.07.2025 = 2 Tage).",
    "6-Monatsnähe kalendermonatsgenau zwischen Beginn der aktuellen AU und Ende "
    "der letzten attestierten AU (Maschinenkriterium, VB §3.12).",
    "12-Monatsfenster verankert am Beginn der aktuellen Arbeitsunfähigkeit.",
    "Offenes Ende der aktuellen AU: Dauer einer Woche ab dem Tagesdatum, inklusive gezählt "
    "(VB §3.12; end = Tagesdatum + 6 Kalendertage).",
    "Open-ended prior episodes are not countable deterministically -> NOT_EVALUATED "
    "(fail closed); the normative open-end clause addresses the current absence.",
    "Nur bescheinigte Zeiten zählen; Papiernachweise beim AG gelten als bescheinigt "
    "(Konstellation: 'liegt dem AG als Papiernachweis vor').",
)


@dataclass(frozen=True)
class Episode:
    """One absence episode; end=None means open-ended. Dates: ISO strings or date."""

    start: date | str
    end: date | str | None
    attested: bool = False
    note: str = ""

    def parsed(self) -> tuple[date, date | None]:
        return _as_date(self.start), _as_date(self.end) if self.end is not None else None


@dataclass(frozen=True)
class VorerkrankungResult:
    """Typed, reproducible result (governance §4: calculation/check implementation)."""

    status: str
    criteria: dict[str, dict]
    days_prior: int
    days_current: int
    days_total: int
    module_version: str = MODULE_VERSION
    citation: str = CITATION
    interpretation_notes: tuple[str, ...] = INTERPRETATION_NOTES
    trace: list[str] = field(default_factory=list)


def _as_date(value: date | str) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def add_months(anchor: date, months: int) -> date:
    """Calendar-month arithmetic without external libraries (day clamped to month end)."""
    total = anchor.month - 1 + months
    year = anchor.year + total // 12
    month = total % 12 + 1
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    day = min(anchor.day, (next_month - timedelta(days=1)).day)
    return date(year, month, day)


def day_count(start: date, end: date) -> int:
    """Inclusive calendar-day count (14.07.–15.07. = 2, per the official constellation)."""
    return (end - start).days + 1


def evaluate(
    current: Episode,
    prior: list[Episode],
    reporting_date: date | str,
) -> VorerkrankungResult:
    """Evaluate the DBVO trigger deterministically. Missing input never triggers."""
    trace: list[str] = []
    if not isinstance(reporting_date, date):
        reporting_date = _as_date(reporting_date)

    # -- input completeness (fail closed) ------------------------------------
    problems: list[str] = []
    try:
        current_start, current_end = current.parsed()
    except (TypeError, ValueError) as exc:
        current_start = current_end = None
        problems.append(f"current episode dates unusable: {exc}")
    if current_start is None:
        problems.append("current absence has no start date")
    for idx, ep in enumerate(prior):
        try:
            ep_start, ep_end = ep.parsed()
            if ep_start is None or ep_end is None:
                problems.append(
                    f"prior episode #{idx + 1} is open-ended or undated — not countable "
                    "(fail closed; open-end clause covers the current absence)"
                )
        except (TypeError, ValueError) as exc:
            problems.append(f"prior episode #{idx + 1} dates unusable: {exc}")
    if problems:
        return VorerkrankungResult(
            status=STATUS_NOT_EVALUATED,
            criteria={},
            days_prior=0,
            days_current=0,
            days_total=0,
            trace=[f"input problem: {p}" for p in problems],
        )

    # -- current absence end: open-ended => one week inclusive from today ----
    if current_end is None:
        current_end = reporting_date + timedelta(days=OPEN_END_DAYS - 1)
        trace.append(
            f"open-ended current absence: judged with end {current_end.isoformat()} "
            f"(Dauer einer Woche ab Tagesdatum {reporting_date.isoformat()}, VB §3.12)"
        )

    certified_prior = [ep for ep in prior if ep.attested]
    excluded = [ep for ep in prior if not ep.attested]
    if excluded:
        trace.append(
            f"{len(excluded)} unauffällig nicht-bescheinigte Episode(n) ausgeschlossen "
            "(nur bescheinigte Zeiten zählen, VB §3.12)"
        )

    # -- criterion 1: certificate for the current absence --------------------
    c1 = current.attested
    trace.append(
        f"criterion 1 (Bescheinigung aktuelle AU): {'erfüllt' if c1 else 'nicht erfüllt'}"
    )

    # -- criterion 2: >=1 certified prior AU within 6 months before AU start --
    proximity_limit = add_months(current_start, -PROXIMITY_MONTHS)
    near = [ep for ep in certified_prior if ep.parsed()[1] >= proximity_limit]
    c2 = bool(near)
    if near:
        last_end = max(ep.parsed()[1] for ep in near)
        trace.append(
            f"criterion 2 (>=1 bescheinigte Vorerkrankung/6 Monate): erfüllt — "
            f"letzte attestierte AU endet {last_end.isoformat()}, Grenze "
            f"{proximity_limit.isoformat()}"
        )
    else:
        trace.append(
            f"criterion 2: nicht erfüllt — keine bescheinigte Vorerkrankung mit Ende "
            f"am oder nach {proximity_limit.isoformat()}"
        )

    # -- criterion 3: >=30 cumulative days within 12 months incl. current AU --
    window_start = add_months(current_start, -WINDOW_MONTHS)
    counted = [
        ep for ep in certified_prior
        if ep.parsed()[1] >= window_start and ep.parsed()[0] <= current_start
    ]
    days_prior = sum(day_count(*ep.parsed()) for ep in counted)
    days_current = day_count(current_start, current_end)
    days_total = days_prior + days_current
    c3 = days_total >= MIN_TOTAL_DAYS
    trace.append(
        f"criterion 3 (>= {MIN_TOTAL_DAYS} Tage/12 Monate): {days_prior} Tage Vorzeiten "
        f"+ {days_current} Tage aktuelle AU = {days_total} — "
        f"{'erfüllt' if c3 else 'nicht erfüllt'}"
    )

    status = STATUS_TRIGGER if (c1 and c2 and c3) else STATUS_NO_TRIGGER
    return VorerkrankungResult(
        status=status,
        criteria={
            "certificate_current": {"satisfied": c1},
            "prior_within_6_months": {"satisfied": c2, "limit": proximity_limit.isoformat()},
            "cumulative_30_days_12_months": {
                "satisfied": c3,
                "days_prior": days_prior,
                "days_current": days_current,
                "days_total": days_total,
                "window_start": window_start.isoformat(),
            },
        },
        days_prior=days_prior,
        days_current=days_current,
        days_total=days_total,
        trace=trace,
    )
