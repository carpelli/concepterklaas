import os

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from heroicons.jinja import (
    heroicon_micro,
    heroicon_mini,
    heroicon_outline,
    heroicon_solid,
)
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase

app = Flask(__name__)

app.jinja_env.globals.update(
    {
        "heroicon_micro": heroicon_micro,
        "heroicon_mini": heroicon_mini,
        "heroicon_outline": heroicon_outline,
        "heroicon_solid": heroicon_solid,
    }
)

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)
db.init_app(app)


# Ensure foreign key constraints are enforced for SQLite
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, _connection_record):  # noqa: ANN001, ANN201
    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        with dbapi_connection.cursor() as cursor:
            cursor.execute("PRAGMA foreign_keys=ON")


from . import routes  # noqa: E402, F401
