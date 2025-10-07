from pathlib import Path

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase

# IMPORTANT: Change this secret key!
# You can generate one using: python -c 'import os; print(os.urandom(16))'
app = Flask(__name__)
app.config["SECRET_KEY"] = "a_really_strong_secret_key_goes_here"

# IMPORTANT: Change this admin secret to protect the assignment route!
ADMIN_SECRET = "make-this-a-long-random-string"

# Database setup
db_path = Path(app.root_path).parent / "instance" / "app.db"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + db_path.as_posix()
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)

db.init_app(app)

from . import routes  # noqa: E402, F401
from .models import SystemState, User  # noqa: E402


def create_database() -> None:
    with app.app_context():
        db.create_all()
        if not db.session.scalar(db.select(User)):
            db.session.add(User(name="First"))
        if not db.session.get(SystemState, "assignment_run"):
            db.session.add(SystemState(key="assignment_run", value="False"))
        db.session.commit()
