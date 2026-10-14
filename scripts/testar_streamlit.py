"""Executa o streamlit_app.py e verifica se o painel é montado.

Uso: python scripts/testar_streamlit.py            (dados fictícios, sem chaves)
     python scripts/testar_streamlit.py snapshot   (dados publicados no GitHub, usa PAINEL_DATA_* do .env)
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
os.environ["OMIE_APP_KEY"] = ""
os.environ["OMIE_APP_SECRET"] = ""
if "snapshot" not in sys.argv:
    os.environ["PAINEL_DATA_URL"] = ""

from streamlit.testing.v1 import AppTest  # noqa: E402

at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=120).run()
assert not at.exception, at.exception
html = [e for e in at.get("iframe")] or [e for e in at.get("html")]
print("exceções:", len(at.exception))
print("legenda:", [c.value for c in at.caption])
print("componentes de html:", len(html))
