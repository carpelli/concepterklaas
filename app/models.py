import secrets
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from werkzeug.security import check_password_hash, generate_password_hash

from . import db
from .utils import sanitize, slugify


class Event(db.Model):
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[str] = mapped_column(String(70), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(50))
    message: Mapped[str | None] = mapped_column(String(1000))
    admin_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id"))

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
    assignment_run_at: Mapped[datetime | None] = mapped_column(DateTime)

    admin: Mapped["User"] = relationship(
        back_populates="event", foreign_keys=[admin_id], post_update=True
    )
    users: Mapped[list["User"]] = relationship(
        back_populates="event", foreign_keys="[User.event_id]", cascade="all, delete-orphan"
    )

    def __init__(self, name: str) -> None:
        self.name = sanitize(name)
        token = secrets.token_urlsafe(9)
        self.public_id = f"{slugify(name)}-{token}"


class User(db.Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"))
    name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str | None] = mapped_column(String(128))
    concept: Mapped[str | None] = mapped_column(String(1000))
    receiver_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"))

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    event: Mapped[Event] = relationship(back_populates="users", foreign_keys=[event_id])
    receiver: Mapped["User | None"] = relationship(remote_side=[id], post_update=True)

    def __init__(self, name: str, event: Event) -> None:
        self.name = sanitize(name)
        self.event = event

    def is_admin(self) -> bool:
        return self is self.event.admin

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        if self.password_hash is None:
            return False
        return check_password_hash(self.password_hash, password)
