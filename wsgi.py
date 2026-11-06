"""Entry point per Apache/mod_wsgi (WSGIScriptAlias / /percorso/ventotene/wsgi.py)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from app import create_app  # noqa: E402

application = create_app()
