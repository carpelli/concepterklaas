import random
from collections.abc import Callable
from datetime import UTC, datetime
from functools import wraps
from typing import ParamSpec

from flask import abort, flash, redirect, render_template, request, session, url_for
from flask.typing import ResponseReturnValue
from sqlalchemy.exc import NoResultFound

from app.utils import slugify

from . import app, db
from .models import Event, Host, Participant

P = ParamSpec("P")


def login_required(f: Callable) -> Callable:
    @wraps(f)
    def decorated(*args: P.args, **kwargs: P.kwargs) -> ResponseReturnValue:
        if "host_id" not in session:
            return redirect(url_for("index")), 401
        host = db.get_or_404(Host, session["host_id"])
        return f(host, *args, **kwargs)

    return decorated


def check_event_and_participant(f: Callable) -> Callable:
    @wraps(f)
    def decorated(
        host: Host, event_id: int, *args: P.args, **kwargs: P.kwargs
    ) -> ResponseReturnValue:
        event = db.get_or_404(Event, event_id)
        if event.host != host:
            abort(404)
        if "participant_id" in kwargs:
            kwargs["participant"] = db.get_or_404(Participant, kwargs["participant_id"])
            del kwargs["participant_id"]
            if kwargs["participant"].event != event:
                abort(404)
        return f(host, event, *args, **kwargs)

    return decorated


def check_token(f: Callable) -> Callable:
    @wraps(f)
    def decorated(token: str, *args: P.args, **kwargs: P.kwargs) -> ResponseReturnValue:
        try:
            participant = Participant.query.filter_by(token=token).one()
        except (NoResultFound, AssertionError):
            abort(404)
        return f(participant, *args, **kwargs)

    return decorated


def before_assignment(f: Callable) -> Callable:
    @wraps(f)
    def decorated(
        host: Host, event: Event, *args: P.args, **kwargs: P.kwargs
    ) -> ResponseReturnValue:
        if event.assignment_run_at is not None:
            return "assignment already run", 409
        return f(host, event, *args, **kwargs)

    return decorated


def event_from_session(f: Callable) -> Callable:
    @wraps(f)
    def decorated(*args: P.args, **kwargs: P.kwargs) -> ResponseReturnValue:
        if "event_id" not in session:
            return redirect(url_for("index"))
        event = db.get_or_404(Event, session["event_id"])
        return f(event, *args, **kwargs)

    return decorated


def clear_event_session() -> None:
    session.pop("event_id", None)
    session.pop("host_participant_id", None)


@app.route("/")
def index() -> ResponseReturnValue:
    if "host_id" in session:
        return redirect(url_for("admin"))
    clear_event_session()
    return redirect(url_for("new_event_step1"))


@app.route("/new-event/step1", methods=["GET", "POST"])
def new_event_step1() -> ResponseReturnValue:
    if request.method == "POST":
        host_name = request.form["host_name"]
        if not slugify(host_name):
            flash("Host name cannot be empty", "warning")
            return redirect(url_for("new_event_step1"))
        event = Event(name=request.form["title"])
        if "participate" in request.form:
            event.host_participant = Participant(name=host_name, event=event)
        db.session.add(event)
        db.session.commit()
        session["event_id"] = event.id
        return redirect(url_for("new_event_step2"))
    return render_template("new-event/step1.html")


@app.route("/new-event/step2", methods=["GET", "POST"])
@event_from_session
def new_event_step2(event: Event) -> ResponseReturnValue:
    if request.method == "POST":
        if request.form.get("action") == "add_participant":
            name = request.form["name"]
            if name:
                participant = Participant(name=name, event=event)
                db.session.add(participant)
                db.session.commit()
        elif request.form.get("action") == "remove_participant":
            participant_id = request.form["participant_id"]
            participant = db.get_or_404(Participant, participant_id)
            db.session.delete(participant)
            db.session.commit()
        elif request.form.get("action") == "next":
            return redirect(url_for("new_event_step3"))
    return render_template("new-event/step2.html", event=event)


@app.route("/new-event/step3", methods=["GET", "POST"])
@event_from_session
def new_event_step3(event: Event) -> ResponseReturnValue:
    if request.method == "POST":
        host = Host(email=request.form["email"])
        host.set_password(request.form["password"])
        event.host = host
        db.session.add(host)
        db.session.commit()
        session["host_id"] = host.id
        clear_event_session()
        return redirect(url_for("admin"))
    return render_template("new-event/step3.html", event=event)


@app.route("/login", methods=["GET", "POST"])
def login() -> ResponseReturnValue:
    if request.method == "POST":
        host = db.session.query(Host).filter_by(email=request.form["email"]).one_or_none()
        if host and host.check_password(request.form["password"]):
            session["host_id"] = host.id
            return redirect(url_for("admin"))
        flash("Invalid email or password.")
    return render_template("login.html")


@app.route("/refer")
def refer() -> ResponseReturnValue:
    if "participant_id" not in session:
        return redirect(url_for("index"))
    participant = Participant.query.get(session["participant_id"])
    if not participant:
        session.pop("participant_id", None)
        return redirect(url_for("index"))
    return render_template("refer.html", event=participant.event, participant=participant)


@app.route("/e/<event_slug>/<participant_slug>/<token>")
@check_token
def participant_view(
    participant: Participant, event_slug: str, participant_slug: str
) -> ResponseReturnValue:
    session["participant_id"] = participant.id
    if participant.slug != participant_slug or participant.event.slug != event_slug:
        return redirect(url_for("participant_view", **participant.public_url_info()))
    if not participant.concept:
        return render_template("change_concept.html", participant=participant)
    return render_template("dashboard.html", participant=participant)


@app.route("/token/<token>/change", methods=["GET", "POST"])
@check_token
def change_concept(participant: Participant) -> ResponseReturnValue:
    if request.method == "GET":
        return render_template("change_concept.html", participant=participant)
    participant.concept = request.form["concept"]
    db.session.commit()
    return redirect(url_for("participant_view", **participant.public_url_info()))


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
        event = Event(name=request.form["event_name"])
        event.host = host
        db.session.add(event)
        db.session.commit()
        return redirect(url_for("admin"))
    return render_template("admin.html", host=host)


@app.route("/admin/<event_id>", methods=["GET"])
@login_required
@check_event_and_participant
def event_detail(_host: Host, event: Event) -> ResponseReturnValue:
    return render_template(
        "event.html",
        event=event,
        assignment_has_run=event.assignment_run_at is not None,
        can_run_assignment=all(p.concept for p in event.participants),
    )


@app.route("/admin/<event_id>/delete", methods=["POST"])
@login_required
@check_event_and_participant
@before_assignment
def remove_event(_host: Host, event: Event) -> ResponseReturnValue:
    db.session.delete(event)
    db.session.commit()
    return redirect(url_for("admin"))


@app.route("/admin/<event_id>/participants/add", methods=["POST"])
@login_required
@check_event_and_participant
@before_assignment
def add_participant(_host: Host, event: Event) -> ResponseReturnValue:
    name = request.form["name"]
    participant = Participant(name=name, event=event)
    if participant.slug:
        if request.form.get("is_host"):
            event.host_participant = participant
        db.session.add(participant)
        db.session.commit()
    else:
        flash("Name cannot be empty", "warning")
    return redirect(url_for("event_detail", event_id=event.id, _anchor="name"))


@app.route("/admin/<event_id>/participants/<participant_id>/delete", methods=["POST"])
@login_required
@check_event_and_participant
@before_assignment
def remove_participant(_host: Host, event: Event, participant: Participant) -> ResponseReturnValue:
    db.session.delete(participant)
    db.session.commit()
    return redirect(url_for("event_detail", event_id=event.id))


@app.route("/admin/<event_id>/assign", methods=["POST"])
@login_required
@check_event_and_participant
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
