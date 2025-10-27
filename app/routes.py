import random
from collections.abc import Callable
from datetime import UTC, datetime
from functools import wraps
from typing import ParamSpec

from flask import abort, flash, redirect, render_template, request, session, url_for
from flask.typing import ResponseReturnValue
from sqlalchemy.exc import IntegrityError

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


def check_event_and_participant(f: Callable) -> Callable:  # TODO CHECK
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
        participant = Participant.query.filter_by(token=token).first_or_404()
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
    if "participant_id" in session:
        return redirect(url_for("refer"))
    clear_event_session()
    return redirect(url_for("new_event_step1"))


@app.route("/new-event/step1", methods=["GET", "POST"])
def new_event_step1() -> ResponseReturnValue:
    logged_in = "host_id" in session
    if request.method == "GET":
        return render_template("new-event/step1.html", logged_in=logged_in)

    host_name = request.form.get("host_name", "")
    event = Event(name=request.form["title"])

    # Handle host participation
    if "participate" in request.form:
        if not host_name:
            flash("Host name cannot be empty", "error")
            return redirect(url_for("new_event_step1"))
        event.host_participant = Participant(name=host_name, event=event)

    # Save event
    if logged_in:
        event.host_id = session["host_id"]

    try:
        db.session.add(event)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("Event with the same name already exists", "error")
        return redirect(url_for("new_event_step1"))

    # Redirect based on login status
    if logged_in:
        return redirect(url_for("event_detail", event_slug=event.slug))

    session["event_id"] = event.id
    return redirect(url_for("new_event_step2"))


@app.route("/new-event/step2", methods=["GET", "POST"])
@event_from_session
def new_event_step2(event: Event) -> ResponseReturnValue:
    if request.method == "GET":
        return render_template("new-event/step2.html", event=event)

    action = request.form.get("action")

    if action == "add_participant":
        name = request.form.get("name", "").strip()
        if name:
            participant = Participant(name=name, event=event)
            db.session.add(participant)
            db.session.commit()
    elif action == "remove_participant":
        participant = db.get_or_404(Participant, request.form["participant_id"])
        db.session.delete(participant)
        db.session.commit()
    elif action == "next":
        return redirect(url_for("new_event_step3"))

    return render_template("new-event/step2.html", event=event)


@app.route("/new-event/step3", methods=["GET", "POST"])
@event_from_session
def new_event_step3(event: Event) -> ResponseReturnValue:
    if request.method == "POST":
        host = Host(email=request.form["email"])
        host.set_password(request.form["password"])
        event.host = host

        try:
            db.session.add(host)
            db.session.commit()
            session["host_id"] = host.id
            clear_event_session()
            return redirect(url_for("admin"))
        except IntegrityError:
            db.session.rollback()
            flash("A host with this email already exists", "warning")
            return redirect(url_for("new_event_step3"))
    return render_template("new-event/step3.html", event=event)


@app.route("/refer")
def refer() -> ResponseReturnValue:
    if "participant_id" not in session:
        return redirect(url_for("index"))
    participant = Participant.query.get(session["participant_id"])
    if not participant:
        session.pop("participant_id", None)
        return redirect(url_for("index"))
    return render_template("participant/refer.html", participant=participant)


@app.route("/e/<event_slug>/<participant_slug>/<token>")
@check_token
def participant_view(
    participant: Participant, event_slug: str, participant_slug: str
) -> ResponseReturnValue:
    session["participant_id"] = participant.id

    # Redirect to canonical URL if needed
    if participant.slug != participant_slug or participant.event.slug != event_slug:
        return redirect(url_for("participant_view", **participant.public_url_info()))
    if not participant.concept:
        return render_template("participant/change.html", participant=participant)
    return render_template("participant/index.html", participant=participant)


@app.route("/token/<token>/change", methods=["GET", "POST"])
@check_token
def change_concept(participant: Participant) -> ResponseReturnValue:
    if request.method == "GET":
        return render_template("participant/change.html", participant=participant)
    participant.concept = request.form["concept"]
    db.session.commit()
    return redirect(url_for("participant_view", **participant.public_url_info()))


@app.route("/login", methods=["GET", "POST"])
def login() -> ResponseReturnValue:
    if request.method != "POST":
        return render_template("admin/login.html")

    host = Host.query.filter_by(email=request.form["email"]).first()
    if not host or not host.check_password(request.form["password"]):
        flash("Invalid email or password.")
        return render_template("admin/login.html")

    session["host_id"] = host.id

    # Handle pending event from session
    if request.args.get("new_event") and "event_id" in session:
        event = Event.query.get(session["event_id"])
        if event:
            event.host_id = host.id
            try:
                db.session.commit()
                clear_event_session()
            except IntegrityError:
                db.session.rollback()
                flash("You already have an event with this name")
                return redirect(url_for("new_event_step1"))

    return redirect(url_for("admin"))


@app.route("/logout")
def logout() -> ResponseReturnValue:
    session.clear()
    flash("You have been logged out.")
    return redirect(url_for("index"))


@app.route("/admin", methods=["GET", "POST"])
@login_required
def admin(host: Host) -> ResponseReturnValue:
    return render_template("admin/index.html", host=host)


@app.route("/admin/<event_slug>", methods=["GET"])
@login_required
def event_detail(host: Host, event_slug: str) -> ResponseReturnValue:
    event = Event.query.filter_by(host=host, slug=event_slug).one_or_404()
    return render_template(
        "admin/event.html",
        event=event,
        assignment_has_run=event.assignment_run_at is not None,
        can_run_assignment=event.participants and all(p.concept for p in event.participants),
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
    return redirect(url_for("event_detail", event_slug=event.slug, _anchor="name"))


@app.route("/admin/<event_id>/participants/<participant_id>/delete", methods=["POST"])
@login_required
@check_event_and_participant
@before_assignment
def remove_participant(_host: Host, event: Event, participant: Participant) -> ResponseReturnValue:
    db.session.delete(participant)
    db.session.commit()
    return redirect(url_for("event_detail", event_slug=event.slug))


@app.route("/admin/<event_id>/assign", methods=["POST"])
@login_required
@check_event_and_participant
@before_assignment
def run_assignment(_host: Host, event: Event) -> ResponseReturnValue:
    participants = [*event.participants]  # don't manipulate the data model list
    if not participants or any(not p.concept for p in participants):
        return "not all participants have a concept", 409

    # Simple circular assignment
    random.shuffle(participants)
    for i, participant in enumerate(participants):
        participant.receiver = participants[(i + 1) % len(participants)]

    event.assignment_run_at = datetime.now(UTC)
    db.session.commit()
    return redirect(url_for("event_detail", event_slug=event.slug))
