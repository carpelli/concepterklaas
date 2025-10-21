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

# IMPORTANT: Change this secret key!
# You can generate one using: python -c 'import os; print(os.urandom(16))'
app = Flask(__name__)
app.jinja_env.globals.update(
    {
        "heroicon_micro": heroicon_micro,
        "heroicon_mini": heroicon_mini,
        "heroicon_outline": heroicon_outline,
        "heroicon_solid": heroicon_solid,
    }
)
app.config["SECRET_KEY"] = "a_really_strong_secret_key_goes_here"

# IMPORTANT: Change this admin secret to protect the assignment route!
ADMIN_SECRET = "make-this-a-long-random-string"

# Database setup
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)
db.init_app(app)


# The following ensures that foreign key constraints are enforced for SQLite.
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


from . import routes  # noqa: E402, F401
