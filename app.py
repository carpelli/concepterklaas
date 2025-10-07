import random
from functools import wraps
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.util import NoneType
from werkzeug.security import check_password_hash, generate_password_hash

# --- CONFIGURATION ---

# IMPORTANT: Change this secret key!
# You can generate one using: python -c 'import os; print(os.urandom(16))'
app = Flask(__name__)
app.config["SECRET_KEY"] = "a_really_strong_secret_key_goes_here"

# IMPORTANT: Change this admin secret to protect the assignment route!
ADMIN_SECRET = "make-this-a-long-random-string"

# Database setup
db_path = Path(__file__).parent / "instance" / "app.db"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + db_path.as_posix()
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)

db.init_app(app)


class Person(db.Model):
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(128))
    concept: Mapped[str | None] = mapped_column(String(200))

    receiver_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("person.id"))
    receiver: Mapped["Person | None"] = relationship(remote_side=[id], post_update=True)

    def __init__(self, name: str) -> None:
        self.name = name

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class SystemState(db.Model):
    key = db.Column(db.String(50), primary_key=True)
    value = db.Column(db.String(100))

    def __init__(self, key: str, value: str) -> None:
        self.key = key
        self.value = value


# --- DECORATORS ---


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("index"))
        return f(*args, **kwargs)

    return decorated_function


# --- ROUTES ---


@app.route("/", methods=["GET"])
def index():
    # If user is already logged in, redirect to dashboard
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        name = request.form["name"]
        password = request.form["password"]
        participant = db.session.execute(
            db.select(Person).filter_by(name=name),
        ).scalar_one_or_none()

        # Handle Login
        if "concept" not in request.form:
            if participant and participant.check_password(password):
                session["user_id"] = participant.id
                return redirect(url_for("dashboard"))
            flash("Invalid name or password.")
        # Handle Wish Submission
        else:
            concept = request.form["concept"]
            # Find the person by name
            person = db.session.execute(
                db.select(Person).filter_by(name=name),
            ).scalar_one_or_none()

            if person:
                if person.concept:
                    flash("You have already submitted a wish. Please log in.")
                else:
                    person.concept = concept
                    person.set_password(password)
                    db.session.commit()
                    flash("Your wish has been saved! You can now log in.")
            else:
                flash("Participant not found.")

    # Get list of all participants
    participants = db.session.execute(db.select(Person)).scalars().all()

    # Get list of participants who have not yet submitted a wish
    submitted_names = [p.name for p in participants if p.concept]
    available_participants = [p.name for p in participants if p.name not in submitted_names]

    return render_template(
        "index.html",
        available_participants=available_participants,
        PARTICIPANTS=[p.name for p in participants],
    )


@app.route("/login", methods=["POST"])
def login():
    name = request.form["name"]
    password = request.form["password"]
    participant = db.session.execute(
        db.select(Person).filter_by(name=name),
    ).scalar_one_or_none()
    if participant and participant.check_password(password):
        session["user_id"] = participant.id
        return redirect(url_for("dashboard"))
    flash("Invalid name or password.")
    return redirect(url_for("index"))


@app.route("/new", methods=["GET", "POST"])
def new():
    if request.method == "POST":
        name = request.form["name"]
        password = request.form["password"]
        person = db.session.execute(
            db.select(Person).filter_by(name=name),
        ).scalar_one_or_none()

        if person:
            if person.password_hash:
                flash("You have already created an account. Please log in.")
            else:
                person.set_password(password)
                db.session.commit()
                return login()
        else:
            flash("Participant not found.")

    participants = db.session.execute(db.select(Person)).scalars().all()
    available_names = [p.name for p in participants if p.password_hash is None]
    return render_template("new.html", available_names=available_names)


@app.route("/dashboard")
@login_required
def dashboard():
    user = db.session.get(Person, session["user_id"])
    return render_template("dashboard.html", user=user)


@app.route("/logout")
def logout():
    session.pop("user_id", None)
    flash("You have been logged out.")
    return redirect(url_for("index"))


@app.route("/admin", methods=["GET"])
@login_required
def admin():
    participants = db.session.execute(db.select(Person)).scalars().all()
    assignment_run = db.session.get(SystemState, "assignment_run").value == "True"
    return render_template("admin.html", participants=participants, assignment_run=assignment_run)


@app.route("/admin/participants/add", methods=["POST"])
@login_required
def add_participant():
    assignment_run = db.session.get(SystemState, "assignment_run").value == "True"
    if assignment_run:
        flash("Cannot add participants after the assignment has been run.")
        return redirect(url_for("admin"))

    name = request.form["name"]
    if name:
        participant = Person(name=name)
        db.session.add(participant)
        db.session.commit()
        flash(f"Participant {name} added.")
    else:
        flash("Name cannot be empty.")
    return redirect(url_for("admin"))


@app.route("/admin/participants/<int:person_id>/delete", methods=["POST"])
@login_required
def remove_participant(person_id):
    assignment_run = db.session.get(SystemState, "assignment_run").value == "True"
    if assignment_run:
        flash("Cannot remove participants after the assignment has been run.")
        return redirect(url_for("admin"))

    participant = db.session.get(Person, person_id)
    if participant:
        db.session.delete(participant)
        db.session.commit()
        flash(f"Participant {participant.name} removed.")
    else:
        flash("Participant not found.")
    return redirect(url_for("admin"))


@app.route("/run-assignment/<secret>")
def run_assignment(secret):
    if secret != ADMIN_SECRET:
        return "Unauthorized", 403

    assignment_run = db.session.get(SystemState, "assignment_run").value == "True"
    if assignment_run:
        return "Assignment has already been run.", 400

    participants = db.session.execute(db.select(Person)).scalars().all()
    total_participants = len(participants)
    if len([p for p in participants if p.concept]) != total_participants:
        return (
            f"Cannot run assignment. Only {len([p for p in participants if p.concept])} out of {total_participants} have submitted.",
            400,
        )

    # The assignment logic
    shuffled = [*participants]
    random.shuffle(shuffled)

    for giver, receiver in zip(shuffled, shuffled[1:] + shuffled[:1], strict=True):
        giver.receiver = receiver

    assignment_state = db.session.get(SystemState, "assignment_run")
    assignment_state.value = "True"
    db.session.commit()
    return "Assignment complete!", 200


def create_database() -> None:
    with app.app_context():
        db.create_all()
        if not db.session.execute(db.select(Person)).scalars().first():
            db.session.add(Person(name="First"))
        if not db.session.get(SystemState, "assignment_run"):
            db.session.add(SystemState(key="assignment_run", value="False"))
        db.session.commit()


# To initialize the database, open a terminal in your project folder and run:
# > flask shell
# >>> from app import app, db, SystemState
# >>> with app.app_context():
# ...     db.create_all()
# ...     if not db.session.get(SystemState, 'assignment_run'):
# ...         db.session.add(SystemState(key='assignment_run', value='False'))
# ...         db.session.commit()
# ...
# >>> exit()
