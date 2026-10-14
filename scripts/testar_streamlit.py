"""Executa o streamlit_app.py com dados fictícios (sem chaves) e verifica se o painel é montado."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
os.environ["OMIE_APP_KEY"] = ""
os.environ["OMIE_APP_SECRET"] = ""

from streamlit.testing.v1 import AppTest  # noqa: E402

at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=120).run()
assert not at.exception, at.exception
html = [e for e in at.get("iframe")] or [e for e in at.get("html")]
print("exceções:", len(at.exception))
print("legenda:", [c.value for c in at.caption])
print("componentes de html:", len(html))
