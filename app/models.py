from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from werkzeug.security import check_password_hash, generate_password_hash

from . import db


class Person(db.Model):
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(128))
    concept: Mapped[str | None] = mapped_column(String(1000))

    receiver_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("person.id"))
    receiver: Mapped["Person | None"] = relationship(remote_side=[id], post_update=True)

    def __init__(self, name: str) -> None:
        self.name = name

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        if self.password_hash is None:
            return False
        return check_password_hash(self.password_hash, password)


class SystemState(db.Model):
    key = db.Column(db.String(50), primary_key=True)
    value = db.Column(db.String(100))

    def __init__(self, key: str, value: str) -> None:
        self.key = key
        self.value = value
