import random
from collections.abc import Callable
from datetime import UTC, datetime
from functools import wraps
from typing import Any

from flask import flash, redirect, render_template, request, session, url_for
from flask.typing import ResponseReturnValue
from sqlalchemy import select
from sqlalchemy.exc import NoResultFound

from . import app, db
from .models import Event, Host, Participant


def login_required(f: Callable) -> Callable:
    @wraps(f)
    def decorated(**kwargs: dict[str, Any]) -> ResponseReturnValue:
        if "host_id" not in session:
            return redirect(url_for("index")), 401
        host = db.get_or_404(Host, session["host_id"])
        if "event_id" in kwargs:
            event = db.get_or_404(Event, kwargs["event_id"])
            del kwargs["event_id"]
            return f(host, event, **kwargs)
        return f(host, **kwargs)

    return decorated


def before_assignment(f: Callable) -> Callable:
    @wraps(f)
    def decorated(host: Host, event: Event, **kwargs: dict[str, Any]) -> ResponseReturnValue:
        if event.assignment_run_at is not None:
            return "assignment already run", 409
        return f(host, event, **kwargs)

    return decorated


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
    if "participant_id" in session:
        return redirect(url_for("refer"))
    return render_template("index.html")


@app.route("/login", methods=["POST"])
def login() -> ResponseReturnValue:
    host = db.session.query(Host).filter_by(email=request.form["email"]).one_or_none()
    if host and host.check_password(request.form["password"]):
        session["host_id"] = host.id
        return redirect(url_for("admin"))
    flash("Invalid email or password.")
    return redirect(url_for("index"))


@app.route("/refer")
def refer() -> ResponseReturnValue:
    if "participant_id" not in session:
        return redirect(url_for("index"))
    participant = Participant.query.get(session["participant_id"])
    return render_template("refer.html", event=participant.event, participant=participant)


@app.route("/events/<event_slug>/<participant_slug>/<token>")
def participant_view(event_slug: str, participant_slug: str, token: str) -> ResponseReturnValue:
    participant = db.one_or_404(
        select(Participant).where(
            Participant.token == token,
            Participant.slug == participant_slug,
            Participant.event.has(slug=event_slug),
        )
    )
    session["participant_id"] = participant.id
    if not participant.concept:
        return render_template("change_concept.html", participant=participant)
    return render_template("dashboard.html", participant=participant)


@app.route("/<token>/concept", methods=["POST"])
def concept(token: str) -> ResponseReturnValue:
    participant = db.one_or_404(select(Participant).where(Participant.token == token))
    if participant.event.assignment_run_at is not None:
        return "assignment already run", 409
    participant.concept = request.form["concept"]
    db.session.commit()
    return redirect(
        url_for(
            "participant_view",
            event_slug=participant.event.slug,
            participant_slug=participant.slug,
            token=participant.token,
        )
    )


@app.route("/logout")
def logout() -> ResponseReturnValue:
    session.pop("host_id", None)
    session.pop("participant_id", None)
    flash("You have been logged out.")
    return redirect(url_for("index"))


@app.route("/admin", methods=["GET", "POST"])
@login_required
def admin(host: Host) -> ResponseReturnValue:
    if request.method == "POST":
        event = Event(name=request.form["event_name"], host=host)
        db.session.add(event)
        db.session.commit()
        return redirect(url_for("admin"))
    return render_template("admin.html", host=host)


@app.route("/admin/<event_id>", methods=["GET"])
@login_required
def event_detail(_host: Host, event: Event) -> ResponseReturnValue:
    try:
        me = db.session.get(Participant, session["participant_id"])
    except KeyError:
        me = None
    return render_template(
        "event.html",
        event=event,
        participants=event.participants,
        assignment_run=event.assignment_run_at is not None,
        can_run_assignment=all(p.concept for p in event.participants),
        me=me,
    )


@app.route("/admin/<event_id>/participants/add", methods=["POST"])
@login_required
@before_assignment
def add_participant(_host: Host, event: Event) -> ResponseReturnValue:
    name = request.form["name"]
    participant = Participant(name=name, event=event)
    if participant.slug:
        db.session.add(participant)
        db.session.commit()
    else:
        flash("name cannot be empty")
    return redirect(url_for("event_detail", event_id=event.id, _anchor="name"))


@app.route("/admin/<event_id>/participants/delete", methods=["POST"])
@login_required
@before_assignment
def remove_participant(_host: Host, event: Event) -> ResponseReturnValue:
    try:
        participant = db.session.get_one(Participant, request.form["participant_id"])
        assert participant.event == event
    except (NoResultFound, AssertionError):
        return "invalid participant id", 400
    db.session.delete(participant)
    db.session.commit()
    return redirect(url_for("event_detail", event_id=event.id))


@app.route("/admin/<event_id>/assign", methods=["POST"])
@login_required
@before_assignment
def run_assignment(_host: Host, event: Event) -> ResponseReturnValue:
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
    return redirect(url_for("event_detail", event_id=event.id))
