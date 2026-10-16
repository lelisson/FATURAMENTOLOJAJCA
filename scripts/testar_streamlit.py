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
os.environ["OMIE_FILIAL_APP_KEY"] = ""
os.environ["OMIE_FILIAL_APP_SECRET"] = ""
if "snapshot" not in sys.argv:
    os.environ["PAINEL_DATA_URL"] = ""

from streamlit.testing.v1 import AppTest  # noqa: E402

at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=120).run()
arquivo_senha = Path.home() / ".painel-omie" / "senha-streamlit.txt"
if at.text_input and arquivo_senha.exists():
    senha = arquivo_senha.read_text(encoding="utf-8").splitlines()[0].split(": ", 1)[1].strip()
    at.text_input[0].input("errada")
    at.button[0].click().run()
    print("senha errada recusada:", [e.value for e in at.error] == ["Senha incorreta."])
    at.text_input[0].input(senha)
    at.button[0].click().run()
assert not at.exception, at.exception
html = [e for e in at.get("iframe")] or [e for e in at.get("html")]
print("exceções:", len(at.exception))
print("legenda:", [c.value for c in at.caption])
print("componentes de html:", len(html))
print("erros:", [e.value for e in at.error])
print("avisos:", [e.value for e in at.warning])
print("campos de texto:", len(at.text_input))

# Período digitado: válido, inválido e atalhos.
de, ate = at.text_input(key="de"), at.text_input(key="ate")
print("período inicial:", de.value, "a", ate.value)
de.input("01/09/2026").run()
ate = at.text_input(key="ate")
ate.input("30/09/2026").run()
assert not at.exception, at.exception
print("setembro digitado:", [c.value for c in at.caption][-1:])
at.text_input(key="de").input("31/02/2026").run()
print("data inválida avisa:", any("Data inválida" in w.value for w in at.warning))
at.text_input(key="de").input("01092026").run()
print("só dígitos vira:", at.text_input(key="de").value, "| exceções:", len(at.exception))
for atalho in ("Mês anterior", "Trimestre", "Mês atual"):
    at.text_input(key="de").input("01/10/2026").run()
    at.button_group(key="atalho").set_value(atalho).run() if hasattr(at, "button_group") else None
    print(f"atalho {atalho}:", at.text_input(key="de").value, "a", at.text_input(key="ate").value,
          "| exceções:", len(at.exception))
