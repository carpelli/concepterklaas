import random
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from functools import wraps
from typing import Any

from flask import flash, redirect, render_template, request, session, url_for
from flask.typing import ResponseReturnValue
from sqlalchemy import select

from . import app, db
from .models import Event, Host, Participant


def login_required(f: Callable) -> Callable:
    @wraps(f)
    def decorated_function(*args: Iterable[Any], **kwargs) -> ResponseReturnValue:
        print("called login_required")
        if "host_id" not in session:
            return redirect(url_for("index")), 401
        return f(db.get_or_404(Host, session["host_id"]), *args, **kwargs)

    return decorated_function


def admin_required(f: Callable) -> Callable:
    @wraps(f)
    def decorated_function(host: Host, *args: Iterable[Any], **kwargs) -> ResponseReturnValue:
        print("called admin_required")
        event_id = request.view_args["event_public_id"]
        event = db.one_or_404(select(Event).where(Event.public_id == event_id))
        if event.admin != host:
            return "not admin", 403
        return f(host, *args, **kwargs)

    return login_required(decorated_function)


@app.route("/", methods=["GET", "POST"])
def index() -> ResponseReturnValue:
    if request.method == "POST":
        host = Host(email=request.form["email"])
        host.set_password(request.form["password"])
        db.session.add(host)
        db.session.commit()
        session["host_id"] = host.id
        return redirect(url_for("admin"))
    if "host_id" in session:
        return redirect(url_for("admin"))
    return render_template("index.html")


@app.route("/login", methods=["POST"])
def login() -> ResponseReturnValue:
    host = db.one_or_404(select(Host).where(Host.email == request.form["email"]))
    if host.check_password(request.form["password"]):
        session["host_id"] = host.id
        return redirect(url_for("admin"))
    flash("Invalid email or password.")
    return redirect(url_for("index"))


@app.route("/<event_public_id>/<magic_token>")
def participant_view(event_public_id: str, magic_token: str) -> ResponseReturnValue:
    participant = db.one_or_404(
        select(Participant).where(
            Participant.magic_token == magic_token,
            Participant.event.has(public_id=event_public_id),
        )
    )
    if not participant.concept:
        return render_template("change_concept.html", participant=participant)
    return render_template("dashboard.html", user=participant)


@app.route("/<magic_token>/concept", methods=["POST"])
def concept(magic_token: str) -> ResponseReturnValue:
    participant = db.one_or_404(select(Participant).where(Participant.magic_token == magic_token))
    if participant.event.assignment_run_at is not None:
        return "assignment already run", 409
    participant.concept = request.form["concept"]
    db.session.commit()
    return redirect(
        url_for(
            "participant_view",
            event_public_id=participant.event.public_id,
            magic_token=participant.magic_token,
        )
    )


@app.route("/logout")
def logout() -> ResponseReturnValue:
    session.pop("host_id", None)
    flash("You have been logged out.")
    return redirect(url_for("index"))


@app.route("/admin", methods=["GET", "POST"])
@login_required
def admin(host: Host) -> ResponseReturnValue:
    if request.method == "POST":
        event = Event(name=request.form["event_name"])
        event.admin = host
        db.session.add(event)
        db.session.commit()
        return redirect(url_for("admin"))
    return render_template("admin.html", host=host)


@app.route("/<event_public_id>", methods=["GET"])
@admin_required
def event_detail(host: Host, event_public_id: str) -> ResponseReturnValue:
    event = db.one_or_404(select(Event).where(Event.public_id == event_public_id))
    return render_template(
        "event.html",
        event=event,
        participants=event.participants,
        assignment_run=event.assignment_run_at is not None,
        can_run_assignment=all(p.concept for p in event.participants),
    )


@app.route("/<event_public_id>/participants/add", methods=["POST"])
@admin_required
def add_participant(host: Host, event_public_id: str) -> ResponseReturnValue:
    event = db.one_or_404(select(Event).where(Event.public_id == event_public_id))
    if event.assignment_run_at is not None:
        return "assignment already run", 409

    name = request.form["name"]
    if name:
        participant = Participant(name=name, event=event)
        db.session.add(participant)
        db.session.commit()
    else:
        flash("Name cannot be empty")
    return redirect(url_for("event_detail", event_public_id=event_public_id, _anchor="name"))


@app.route("/<event_public_id>/participants/delete", methods=["POST"])
@admin_required
def remove_participant(_host: Host, event_public_id: str) -> ResponseReturnValue:
    participant = db.get_or_404(Participant, request.form["participant_id"])
    if participant.event.public_id != event_public_id:
        return "participant not in event", 400
    if participant.event.assignment_run_at is not None:
        return "assignment already run", 409

    db.session.delete(participant)
    db.session.commit()
    return redirect(url_for("event_detail", event_public_id=event_public_id))


@app.route("/<event_public_id>/assign", methods=["POST"])
@admin_required
def run_assignment(host: Host, event_public_id: str) -> ResponseReturnValue:
    event = db.one_or_404(select(Event).where(Event.public_id == event_public_id))
    if event.assignment_run_at is not None:
        return "assignment already run", 409

    participants = event.participants
    if any(not p.concept for p in participants):
        return "not all participants have a concept", 409

    # The assignment logic
    shuffled = [*participants]
    random.shuffle(shuffled)
    for giver, receiver in zip(shuffled, shuffled[1:] + shuffled[:1], strict=True):
        giver.receiver = receiver

    event.assignment_run_at = datetime.now(UTC)
    db.session.commit()
    return redirect(url_for("event_detail", event_public_id=event_public_id))
