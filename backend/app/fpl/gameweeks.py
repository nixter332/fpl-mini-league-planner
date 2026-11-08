"""Gameweek timing: which GW we can still act on, and when shared data goes stale."""

from collections.abc import Iterable
from datetime import datetime

from app.fpl.models import Event


def next_actionable_gameweek(events: Iterable[Event], now: datetime) -> Event | None:
    """The first gameweek whose deadline is still in the future.

    Once a deadline passes, transfers count for the following gameweek, so a GW that
    is in progress or finished is never actionable. Returns None after the last
    deadline of the season.
    """
    upcoming = [e for e in events if e.deadline_time > now]
    return min(upcoming, key=lambda e: e.deadline_time, default=None)


def latest_started_gameweek(events: Iterable[Event], now: datetime) -> Event | None:
    """The most recent gameweek whose deadline has passed (squads are visible for it)."""
    started = [e for e in events if e.deadline_time <= now]
    return max(started, key=lambda e: e.deadline_time, default=None)


def latest_finished_gameweek(events: Iterable[Event]) -> Event | None:
    """The most recent gameweek FPL has marked finished and data-checked (final points)."""
    done = [e for e in events if e.finished and e.data_checked]
    return max(done, key=lambda e: e.id, default=None)


def next_deadline(events: Iterable[Event], now: datetime) -> datetime | None:
    event = next_actionable_gameweek(events, now)
    return event.deadline_time if event else None
