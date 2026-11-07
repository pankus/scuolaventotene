"""Entry point per Apache/mod_wsgi (WSGIScriptAlias / /var/www/scuolaventotene/wsgi.py)."""
import logging
import os
import sys

logging.basicConfig(stream=sys.stderr)

ROOT = os.path.dirname(os.path.realpath(__file__))

# server produzione: venv/ accanto a questo file (in locale c'è .venv/ e si salta)
activate_this = os.path.join(ROOT, "venv", "bin", "activate_this.py")
if os.path.exists(activate_this):
    with open(activate_this) as file_:
        exec(file_.read(), dict(__file__=activate_this))

sys.stdout = sys.stderr
sys.path.insert(0, ROOT)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(ROOT, ".env"))

from app import create_app  # noqa: E402

application = create_app()
