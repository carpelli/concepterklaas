import random
from collections.abc import Callable, Iterable
from functools import wraps
from typing import Any

from flask import flash, redirect, render_template, request, session, url_for
from flask.typing import ResponseReturnValue

from . import ADMIN_SECRET, app, db
from .models import SystemState, User

# --- DECORATORS ---


def login_required(f: Callable) -> Callable:
    @wraps(f)
    def decorated_function(*args: Iterable[Any]) -> ResponseReturnValue:
        if "user_id" not in session:
            return redirect(url_for("index"))
        return f(db.get_or_404(User, session["user_id"]), *args)

    return decorated_function


# --- ROUTES ---


@app.route("/", methods=["GET", "POST"])
def index() -> ResponseReturnValue:
    if "user_id" in session:
        return redirect(url_for("concept"))
    users = db.session.query(User).filter(User.password_hash.is_not(None)).all()
    return render_template(
        "index.html",
        users=users,
    )


@app.route("/login", methods=["POST"])
def login() -> ResponseReturnValue:
    name = request.form["name"]
    password = request.form["password"]
    user = db.session.query(User).filter_by(name=name).one_or_none()

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
        user = db.session.query(User).filter_by(name=name).one_or_none()

        if user:
            if user.password_hash:
                flash("You have already created an account. Please log in.")
            else:
                user.set_password(password)
                db.session.commit()
                # Log the user in directly after creating the account
                session["user_id"] = user.id
                return redirect(url_for("concept"))
        else:
            flash("Participant not found.")

    new_users = db.session.query(User).filter_by(password_hash=None).all()
    available_names = [p.name for p in new_users]
    return render_template("new.html", available_names=available_names)


@app.route("/concept")
@login_required
def dashboard(user: User) -> ResponseReturnValue:
    if not user.concept:
        return redirect(url_for("concept"))
    return render_template("dashboard.html", user=user)


@app.route("/concept/change", methods=["GET", "POST"])
@login_required
def concept(user: User) -> ResponseReturnValue:
    if request.method == "POST":
        user.concept = request.form["concept"]
        db.session.commit()
        return redirect(url_for("dashboard"))
    return render_template("change_concept.html", user=user)


@app.route("/logout")
def logout() -> ResponseReturnValue:
    session.pop("user_id", None)
    flash("You have been logged out.")
    return redirect(url_for("index"))


@app.route("/admin", methods=["GET"])
@login_required
def admin(_user: User) -> ResponseReturnValue:
    users = db.session.query(User).all()
    assignment_run = db.get_or_404(SystemState, "assignment_run") == "True"
    return render_template("admin.html", users=users, assignment_run=assignment_run)


@app.route("/admin/participants/add", methods=["POST"])
@login_required
def add_user(_user: User) -> ResponseReturnValue:
    assignment_run = db.get_or_404(SystemState, "assignment_run") == "True"
    if assignment_run:
        flash("Cannot add participants after the assignment has been run.")
        return redirect(url_for("admin"))

    name = request.form["name"]
    if name:
        user = User(name=name)
        db.session.add(user)
        db.session.commit()
    else:
        flash("Name cannot be empty.")
    return redirect(url_for("admin"))


@app.route("/admin/participants/delete", methods=["POST"])
@login_required
def remove_user(_user: User) -> ResponseReturnValue:
    assignment_run = db.get_or_404(SystemState, "assignment_run") == "True"
    if assignment_run:
        return redirect(url_for("admin"))

    user = db.get_or_404(User, request.form["user_id"])
    db.session.delete(user)
    db.session.commit()
    return redirect(url_for("admin"))


@app.route("/run-assignment/<secret>")
def run_assignment(secret) -> ResponseReturnValue:
    if secret != ADMIN_SECRET:
        return "Unauthorized", 403

    assignment_run = db.get_or_404(SystemState, "assignment_run") == "True"
    if assignment_run:
        return "Assignment has already been run.", 400

    users = db.session.query(User).all()
    if len([p for p in users if p.concept]) != len(users):
        return (
            f"Cannot run assignment. Only {len([p for p in users if p.concept])} out of {len(users)} have submitted.",
            400,
        )

    # The assignment logic
    shuffled = [*users]
    random.shuffle(shuffled)
    for giver, receiver in zip(shuffled, shuffled[1:] + shuffled[:1], strict=True):
        giver.receiver = receiver

    assignment_state = db.session.get(SystemState, "assignment_run")
    assignment_state.value = "True"
    db.session.commit()
    return "Assignment complete!", 200
