import random
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from functools import wraps
from typing import Any

from flask import flash, redirect, render_template, request, session, url_for
from flask.typing import ResponseReturnValue
from sqlalchemy import select

from . import app, db
from .models import Event, User


def login_required(f: Callable) -> Callable:
    @wraps(f)
    def decorated_function(*args: Iterable[Any]) -> ResponseReturnValue:
        if "user_id" not in session:
            return redirect(url_for("index")), 401
        return f(db.get_or_404(User, session["user_id"]), *args)

    return decorated_function


def admin_required(f: Callable) -> Callable:
    @wraps(f)
    def decorated_function(user: User, *args: Iterable[Any]) -> ResponseReturnValue:
        if user.event.admin != user:
            return "not admin", 403
        return f(user, *args)

    return login_required(decorated_function)


def before_assignment(f: Callable) -> Callable:
    @wraps(f)
    def decorated_function(user: User, *args: Iterable[Any]) -> ResponseReturnValue:
        if user.event.assignment_run_at is not None:
            return "assignment already run", 409
        return f(user, *args)

    return decorated_function


@app.route("/", methods=["GET", "POST"])
def index() -> ResponseReturnValue:
    if request.method == "POST":
        event = Event(request.form["event_name"])
        admin = User(request.form["admin_name"], event)
        event.admin = admin
        admin.set_password(request.form["password"])
        db.session.add_all([event, admin])
        db.session.commit()
        session["user_id"] = admin.id
        return redirect(url_for("admin"))
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return render_template("index.html")


@app.route("/<event_public_id>")
def event_index(event_public_id: str) -> ResponseReturnValue:
    event = db.one_or_404(select(Event).where(Event.public_id == event_public_id))
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    users = (
        db.session.query(User).filter(User.event == event, User.password_hash.is_not(None)).all()
    )
    return render_template("event.html", users=users, event_public_id=event_public_id)


@app.route("/<event_public_id>/new", methods=["GET", "POST"])
def new(event_public_id: str) -> ResponseReturnValue:
    # event = db.one_or_404(select(Event).where(Event.public_id == event_public_id))
    event = db.session.query(Event).filter_by(public_id=event_public_id).one()

    if request.method == "POST":
        user = db.get_or_404(User, request.form["user_id"])
        password = request.form["password"]

        if user:
            if user.password_hash:
                flash("You have already created an account. Please log in.")
            else:
                user.set_password(password)
                db.session.commit()
                # Log the user in directly after creating the account
                session["user_id"] = user.id
                return redirect(url_for("dashboard"))
        else:
            flash("Participant not found.")

    new_users = [user for user in event.users if user.password_hash is None]
    return render_template("new.html", new_users=new_users, event_public_id=event_public_id)


@app.route("/login", methods=["POST"])
def login() -> ResponseReturnValue:
    password = request.form["password"]
    user = db.session.get(User, request.form["user_id"])

    if user and user.check_password(password):
        session["user_id"] = user.id
        return redirect(url_for("dashboard"))
    flash("Invalid name or password.")
    return redirect(url_for("event_index", event_public_id=request.form["event_public_id"]))


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
@login_required
def logout(user: User) -> ResponseReturnValue:
    session.pop("user_id", None)
    flash("You have been logged out.")
    return redirect(url_for("event_index", event_public_id=user.event.public_id))


@app.route("/admin", methods=["GET"])
@admin_required
def admin(admin: User) -> ResponseReturnValue:
    return render_template(
        "admin.html",
        users=admin.event.users,
        admin=admin,
        assignment_run=admin.event.assignment_run_at is not None,
        can_run_assignment=all(user.concept for user in admin.event.users),
    )


@app.route("/admin/participants/add", methods=["POST"])
@admin_required
@before_assignment
def add_user(admin: User) -> ResponseReturnValue:
    name = request.form["name"]
    if name:
        user = User(name=name, event=admin.event)
        db.session.add(user)
        db.session.commit()
    else:
        flash("Name cannot be empty")
    return redirect(url_for("admin"))


@app.route("/admin/participants/delete", methods=["POST"])
@admin_required
@before_assignment
def remove_user(_admin: User) -> ResponseReturnValue:
    user = db.get_or_404(User, request.form["user_id"])
    db.session.delete(user)
    db.session.commit()
    return redirect(url_for("admin"))


@app.route("/admin/assign", methods=["POST"])
@admin_required
@before_assignment
def run_assignment(admin: User) -> ResponseReturnValue:
    users = admin.event.users
    if any(not user.concept for user in users):
        return "not all users have a concept", 409

    # The assignment logic
    shuffled = [*users]
    random.shuffle(shuffled)
    for giver, receiver in zip(shuffled, shuffled[1:] + shuffled[:1], strict=True):
        giver.receiver = receiver

    admin.event.assignment_run_at = datetime.now(UTC)
    db.session.commit()
    return redirect(url_for("admin"))
