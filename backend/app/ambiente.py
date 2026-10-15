"""Chaves vêm de variáveis de ambiente do usuário do Windows (ou do ambiente, no GitHub Actions / Streamlit).

Processos abertos antes de a variável ser criada não a enxergam em os.environ; por isso, no Windows,
lê também direto do registro do usuário (HKCU\\Environment), que só esse usuário e administradores acessam.
"""
import os


def ler(nome: str) -> str:
    valor = (os.getenv(nome) or "").strip()
    if valor or os.name != "nt":
        return valor
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            return str(winreg.QueryValueEx(k, nome)[0]).strip()
    except OSError:
        return ""
