import random
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from werkzeug.security import check_password_hash, generate_password_hash

# --- CONFIGURATION ---

# IMPORTANT: Change this secret key!
# You can generate one using: python -c 'import os; print(os.urandom(16))'
app = Flask(__name__)
app.config["SECRET_KEY"] = "a_really_strong_secret_key_goes_here"

# IMPORTANT: Change this admin secret to protect the assignment route!
ADMIN_SECRET = "make-this-a-long-random-string"

# Define the list of participants
PARTICIPANTS = ["Alice", "Bob", "Charlie", "Diana", "Eve"]

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
    receiver: Mapped["Person | None"] = relationship()

    def __init__(self, name: str) -> None:
        self.name = name

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


# --- ROUTES ---


@app.route("/", methods=["GET", "POST"])
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
            if not participant:
                participant = Person(name=name)
                participant.concept = concept
                participant.set_password(password)
                db.session.add(participant)
                db.session.commit()
                flash("Your wish has been saved! You can now log in.")
            else:
                flash("You have already submitted a wish. Please log in.")

    # Get list of participants who have not yet submitted a wish
    submitted_names = db.session.execute(db.select(Person.name)).scalars().all()
    available_participants = [p for p in PARTICIPANTS if p not in submitted_names]

    return render_template(
        "index.html",
        available_participants=available_participants,
        PARTICIPANTS=PARTICIPANTS,
    )


@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("index"))

    user = db.session.get(Person, session["user_id"])
    return render_template("dashboard.html", user=user)


@app.route("/logout")
def logout():
    session.pop("user_id", None)
    flash("You have been logged out.")
    return redirect(url_for("index"))


@app.route("/run-assignment/<secret>")
def run_assignment(secret):
    if secret != ADMIN_SECRET:
        return "Unauthorized", 403

    participants = db.session.execute(db.select(Person)).scalars().all()
    if len(participants) != len(PARTICIPANTS):
        return (
            f"Cannot run assignment. Only {len(participants)} out of {len(PARTICIPANTS)} have submitted.",
            400,
        )

    # The assignment logic
    shuffled = [*participants]
    random.shuffle(shuffled)

    for giver, receiver in zip(shuffled, shuffled[1:] + shuffled[:1], strict=True):
        giver.receiver = receiver

    db.session.commit()
    return "Assignment complete!", 200


# To initialize the database, open a terminal in your project folder and run:
# > flask shell
# >>> from app import app, db
# >>> with app.app_context():
# ...     db.create_all()
# ...
# >>> exit()
