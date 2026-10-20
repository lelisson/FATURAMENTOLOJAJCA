"""Abre o painel no Streamlit Cloud com um navegador real para ele não entrar em suspensão.

O Streamlit Community Cloud suspende apps sem visitas; um GET simples não conta, só uma sessão de navegador.
Se o app já estiver dormindo, clica em "Yes, get this app back up!" e espera ele voltar.

Uso: STREAMLIT_APP_URL=https://<app>.streamlit.app python scripts/manter_ativo.py
"""
import os
import re
import sys
import time

from playwright.sync_api import sync_playwright

URL = os.environ.get("STREAMLIT_APP_URL", "").strip()
ACORDAR = re.compile(r"get this app back up|wake", re.I)


def app_no_ar(page) -> bool:
    """Tela de login (Senha) ou o painel carregado em algum frame."""
    for fr in page.frames:
        try:
            if fr.locator('input[type="password"], input[aria-label="De"]').count():
                return True
        except Exception:
            continue
    return False


def main() -> int:
    if not URL:
        print("STREAMLIT_APP_URL não configurado.")
        return 1
    with sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chrome")
        except Exception:
            b = p.chromium.launch()
        page = b.new_page()
        page.goto(URL, wait_until="domcontentloaded", timeout=120_000)
        acordou = False
        for _ in range(60):
            if app_no_ar(page):
                break
            botao = page.get_by_role("button", name=ACORDAR)
            if not acordou and botao.count():
                print("App estava suspenso; acordando.")
                botao.first.click()
                acordou = True
            time.sleep(5)
        ok = app_no_ar(page)
        # Mantém a sessão aberta um pouco para contar como visita.
        time.sleep(20 if ok else 0)
        b.close()
    print("Painel no ar." if ok else "Painel não respondeu em 5 minutos.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
