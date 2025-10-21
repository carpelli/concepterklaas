setup:
  #!/usr/bin/env -S PYTHONPATH=. uv run --script
  from flask import Flask
  from app import app, db
  with Flask("app").app_context():
    with app.app_context():
      db.drop_all()
      db.create_all()
      db.session.commit()

debug:
  flask run --debug
