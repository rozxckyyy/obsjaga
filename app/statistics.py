from dataclasses import dataclass
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session

from app.models import Role, Specialty, Status, Ticket, User
from app.services import ServiceError, TicketFilters, require_role

MAX_TIMELINE_POINTS = 31


@dataclass(frozen=True)
class TimelinePoint:
    start: date
    end: date
    count: int


@dataclass(frozen=True)
class TicketStatistics:
    by_specialty: dict[Specialty, int]
    by_status: dict[Status, int]
    timeline: tuple[TimelinePoint, ...]
    bucket_size: int

    @property
    def total(self) -> int:
        return sum(self.by_status.values())


class StatisticsService:
    def __init__(self, db: Session, user: User):
        self.db = db
        self.user = user

    def report(self, date_from: str, date_to: str, zone: ZoneInfo) -> TicketStatistics:
        require_role(self.user, Role.ADMIN)
        if not date_from or not date_to:
            raise ServiceError("Укажите обе даты периода.")

        local_day = cast(func.timezone(zone.key, Ticket.created_at), Date)
        query = select(local_day, Ticket.specialty, Ticket.status, func.count()).group_by(
            local_day, Ticket.specialty, Ticket.status,
        )
        query = TicketFilters(date_from=date_from, date_to=date_to).apply(query, "all", zone)
        start, end = date.fromisoformat(date_from), date.fromisoformat(date_to)
        days = (end - start).days + 1
        bucket_size = (days + MAX_TIMELINE_POINTS - 1) // MAX_TIMELINE_POINTS
        by_specialty = dict.fromkeys(Specialty, 0)
        by_status = dict.fromkeys(Status, 0)
        offsets = range(0, days, bucket_size)
        buckets = [0] * len(offsets)

        for day, specialty, status, count in self.db.execute(query):
            by_specialty[specialty] += count
            by_status[status] += count
            buckets[(day - start).days // bucket_size] += count

        timeline = tuple(
            TimelinePoint(
                start + timedelta(days=offset),
                start + timedelta(days=min(offset + bucket_size, days) - 1),
                count,
            )
            for offset, count in zip(offsets, buckets, strict=True)
        )
        return TicketStatistics(by_specialty, by_status, timeline, bucket_size)
