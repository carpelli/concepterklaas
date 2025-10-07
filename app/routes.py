import random
from collections.abc import Callable, Iterable
from functools import wraps
from typing import Any

from flask import flash, redirect, render_template, request, session, url_for
from flask.typing import ResponseReturnValue

from . import ADMIN_SECRET, app, db
from .models import Person, SystemState

# --- DECORATORS ---


def login_required(f: Callable) -> Callable:
    @wraps(f)
    def decorated_function(*args: Iterable[Any]) -> ResponseReturnValue:
        if "user_id" not in session:
            return redirect(url_for("index"))
        return f(db.get_or_404(Person, session["user_id"]), *args)

    return decorated_function


# --- ROUTES ---


@app.route("/", methods=["GET", "POST"])
def index() -> ResponseReturnValue:
    if "user_id" in session:
        return redirect(url_for("concept"))
    users = db.session.query(Person).filter(Person.password_hash.is_not(None)).all()
    return render_template(
        "index.html",
        users=users,
    )


@app.route("/login", methods=["POST"])
def login() -> ResponseReturnValue:
    name = request.form["name"]
    password = request.form["password"]
    user = db.session.query(Person).filter_by(name=name).one_or_none()

    if user and user.check_password(password):
        session["user_id"] = user.id
        return redirect(url_for("dashboard"))
    flash("Invalid name or password.")
    return redirect(url_for("index"))


@app.route("/new", methods=["GET", "POST"])
def new() -> ResponseReturnValue:
    if request.method == "POST":
        name = request.form["name"]
        password = request.form["password"]
        person = db.session.query(Person).filter_by(name=name).one_or_none()

        if person:
            if person.password_hash:
                flash("You have already created an account. Please log in.")
            else:
                person.set_password(password)
                db.session.commit()
                # Log the user in directly after creating the account
                session["user_id"] = person.id
                return redirect(url_for("concept"))
        else:
            flash("Participant not found.")

    participants = db.session.query(Person).filter_by(password_hash=None).all()
    available_names = [p.name for p in participants]
    return render_template("new.html", available_names=available_names)


@app.route("/concept")
@login_required
def dashboard(user: Person) -> ResponseReturnValue:
    if not user.concept:
        return redirect(url_for("concept/change"))
    return render_template("dashboard.html", user=user)


@app.route("/concept/change", methods=["GET", "POST"])
@login_required
def concept(user: Person) -> ResponseReturnValue:
    if request.method == "POST":
        user.concept = request.form["concept"]
        db.session.commit()
        return redirect(url_for("dashboard"))
    if not user.concept:
        return redirect(url_for("concept/change"))
    return render_template("change_concept.html", user=user)


@app.route("/logout")
def logout() -> ResponseReturnValue:
    session.pop("user_id", None)
    flash("You have been logged out.")
    return redirect(url_for("index"))


@app.route("/admin", methods=["GET"])
@login_required
def admin(_user: Person) -> ResponseReturnValue:
    participants = db.session.query(Person).all()
    assignment_run = db.session.get(SystemState, "assignment_run").value == "True"
    return render_template("admin.html", participants=participants, assignment_run=assignment_run)


@app.route("/admin/participants/add", methods=["POST"])
@login_required
def add_participant(_user: Person) -> ResponseReturnValue:
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
def remove_participant(_user: Person, person_id: int) -> ResponseReturnValue:
    assignment_run = db.get_or_404(SystemState, "assignment_run") == "True"
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
def run_assignment(secret) -> ResponseReturnValue:
    if secret != ADMIN_SECRET:
        return "Unauthorized", 403

    assignment_run = db.get_or_404(SystemState, "assignment_run") == "True"
    if assignment_run:
        return "Assignment has already been run.", 400

    participants = db.session.query(Person).all()
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
