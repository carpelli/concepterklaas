setup:
  #!/usr/bin/env -S PYTHONPATH=. uv run --script
  from flask import Flask
  from app import create_database
  with Flask("app").app_context():
    create_database()

debug:
  flask run --debug
