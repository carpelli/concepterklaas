import random
from collections.abc import Callable
from functools import wraps

from flask import flash, redirect, render_template, request, session, url_for
from flask.typing import ResponseReturnValue

from . import ADMIN_SECRET, app, db
from .models import Person, SystemState

# --- DECORATORS ---


def login_required(f: Callable) -> Callable:
    @wraps(f)
    def decorated_function() -> Callable:
        if "user_id" not in session:
            return redirect(url_for("index"))
        return f()

    return decorated_function


# --- ROUTES ---


@app.route("/", methods=["GET", "POST"])
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        name = request.form["name"]
        password = request.form["password"]
        participant = db.session.query(Person).filter_by(name=name).one_or_none()

        if "concept" not in request.form:  # This is a login attempt
            if participant and participant.check_password(password):
                session["user_id"] = participant.id
                return redirect(url_for("dashboard"))
            else:
                flash("Invalid name or password.")
        else:  # This is a wish submission
            concept = request.form["concept"]
            if participant:
                if participant.concept:
                    flash("You have already submitted a wish. Please log in.")
                else:
                    participant.concept = concept
                    participant.set_password(password)
                    db.session.commit()
                    flash("Your wish has been saved! You can now log in.")
            else:
                flash("Participant not found.")

    participants = db.session.query(Person).all()
    submitted_names = {p.name for p in participants if p.concept}
    available_participants = [p.name for p in participants if p.name not in submitted_names]

    return render_template(
        "index.html",
        available_participants=available_participants,
        PARTICIPANTS=[p.name for p in participants],
    )


@app.route("/login", methods=["POST"])
def login() -> ResponseReturnValue:
    name = request.form["name"]
    password = request.form["password"]
    participant = db.session.query(Person).filter_by(name=name).one_or_none()

    if participant and participant.check_password(password):
        session["user_id"] = participant.id
        return redirect(url_for("dashboard"))
    else:
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
                return redirect(url_for("dashboard"))
        else:
            flash("Participant not found.")

    participants = db.session.query(Person).filter_by(password_hash=None).all()
    available_names = [p.name for p in participants]
    return render_template("new.html", available_names=available_names)


@app.route("/dashboard")
@login_required
def dashboard() -> ResponseReturnValue:
    user = db.session.get(Person, session["user_id"])
    return render_template("dashboard.html", user=user)


@app.route("/logout")
def logout() -> ResponseReturnValue:
    session.pop("user_id", None)
    flash("You have been logged out.")
    return redirect(url_for("index"))


@app.route("/admin", methods=["GET"])
@login_required
def admin() -> ResponseReturnValue:
    participants = db.session.query(Person).all()
    assignment_run = db.session.get(SystemState, "assignment_run").value == "True"
    return render_template("admin.html", participants=participants, assignment_run=assignment_run)


@app.route("/admin/participants/add", methods=["POST"])
@login_required
def add_participant() -> ResponseReturnValue:
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
def remove_participant(person_id) -> ResponseReturnValue:
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
def run_assignment(secret) -> ResponseReturnValue:
    if secret != ADMIN_SECRET:
        return "Unauthorized", 403

    assignment_run = db.session.get(SystemState, "assignment_run").value == "True"
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
