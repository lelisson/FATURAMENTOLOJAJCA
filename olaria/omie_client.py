# -*- coding: utf-8 -*-
"""Cliente Omie somente leitura (finanças / consultas)."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from .config import ENV_OMIE

READ_ONLY_CALLS = frozenset(
    {
        "ListarContasReceber",
        "ListarContasPagar",
        "ListarNF",
        "ConsultarNF",
        "StatusAplicativo",
    }
)

EP_CONTAS_RECEBER = "https://app.omie.com.br/api/v1/financas/contareceber/"
EP_CONTAS_PAGAR = "https://app.omie.com.br/api/v1/financas/contapagar/"


def _secrets_omie() -> tuple[str, str]:
    try:
        import streamlit as st

        block = st.secrets.get("omie", {})
        k = (block.get("app_key") or "").strip()
        s = (block.get("app_secret") or "").strip()
        if k and s:
            return k, s
    except Exception:
        pass
    env_path = ENV_OMIE
    if env_path.exists():
        from dotenv import load_dotenv

        load_dotenv(env_path, override=True)
    k = (os.getenv("OMIE_APP_KEY") or "").strip()
    s = (os.getenv("OMIE_APP_SECRET") or "").strip()
    return k, s


def credenciais_configuradas() -> bool:
    k, s = _secrets_omie()
    return bool(k and s)


def omie_call(call: str, endpoint: str, param: dict) -> dict:
    if call not in READ_ONLY_CALLS:
        raise PermissionError(f"Método Omie não permitido (somente leitura): {call}")

    app_key, app_secret = _secrets_omie()
    if not app_key or not app_secret:
        raise RuntimeError("Credenciais Omie não configuradas (secrets ou .env).")

    payload = {
        "call": call,
        "app_key": app_key,
        "app_secret": app_secret,
        "param": [param],
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    for tentativa in range(1, 6):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            if isinstance(body, dict) and body.get("faultstring"):
                raise RuntimeError(f"Omie ({call}): {body['faultstring']}")
            return body
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and tentativa < 5:
                time.sleep(1.5 * tentativa)
                continue
            det = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Omie HTTP {e.code}: {det[:400]}") from e
    raise RuntimeError("Omie: falha após várias tentativas.")


def testar_conexao() -> str:
    """Lista 1 registro de contas a receber para validar chave."""
    omie_call(
        "ListarContasReceber",
        EP_CONTAS_RECEBER,
        {"nPagina": 1, "nRegPorPagina": 1},
    )
    return "Conexão Omie OK (somente leitura)."
