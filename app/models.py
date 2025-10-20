import secrets
from datetime import datetime
from typing import TypedDict

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, deferred, mapped_column, relationship
from werkzeug.security import check_password_hash, generate_password_hash

from . import db
from .utils import sanitize, slugify


class Event(db.Model):
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(50))
    message: Mapped[str | None] = mapped_column(String(1000))
    host_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("host.id"))

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
    assignment_run_at: Mapped[datetime | None] = mapped_column(DateTime)

    host: Mapped["Host"] = relationship(back_populates="events")
    participants: Mapped[list["Participant"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("host_id", "slug", name="uix_name"),)

    def __init__(self, name: str) -> None:
        self.name = sanitize(name)
        self.slug = slugify(name)


class Host(db.Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(80), unique=True)
    password_hash: Mapped[str | None] = deferred(mapped_column(String(128)))
    participant_id: Mapped[int | None] = mapped_column(ForeignKey("participant.id"))

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    events: Mapped[list["Event"]] = relationship(back_populates="host")
    participant: Mapped["Participant | None"] = relationship()

    def __init__(self, email: str) -> None:
        self.email = email

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        if self.password_hash is None:
            return False
        return check_password_hash(self.password_hash, password)


class ParticipantUrlInfo(TypedDict):
    event_slug: str
    participant_slug: str
    token: str


class Participant(db.Model):
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"))
    name: Mapped[str] = mapped_column(String(80))
    token: Mapped[str] = mapped_column(String(22), unique=True, index=True)
    concept: Mapped[str | None] = mapped_column(String(1000))
    receiver_id: Mapped[int | None] = mapped_column(ForeignKey("participant.id"))

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    event: Mapped["Event"] = relationship(back_populates="participants")
    receiver: Mapped["Participant | None"] = relationship(remote_side=[id], post_update=True)

    @property
    def slug(self) -> str:
        return slugify(self.name)

    def __init__(self, name: str, event: "Event") -> None:
        self.name = sanitize(name)
        self.event = event
        self.token = secrets.token_urlsafe(16)

    def public_url_info(self) -> ParticipantUrlInfo:
        return {
            "event_slug": self.event.slug,
            "participant_slug": self.slug,
            "token": self.token,
        }
