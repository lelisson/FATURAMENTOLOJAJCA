# -*- coding: utf-8 -*-
"""Acesso restrito ao painel (senha em secrets — uso interno)."""

from __future__ import annotations

import streamlit as st


def _auth_cfg() -> dict:
    try:
        return dict(st.secrets.get("auth", {}))
    except Exception:
        return {}


def acesso_autorizado() -> bool:
    cfg = _auth_cfg()
    if not cfg.get("habilitado"):
        return True
    if st.session_state.get("galpao_auth_ok"):
        return True

    st.markdown("### Acesso restrito")
    st.caption("Uso interno da empresa. Informe a senha configurada no Streamlit Secrets.")
    senha = st.text_input("Senha", type="password", key="galpao_senha_input")
    if st.button("Entrar", type="primary"):
        esperada = str(cfg.get("senha") or "")
        if senha and senha == esperada:
            st.session_state["galpao_auth_ok"] = True
            st.rerun()
        else:
            st.error("Senha incorreta.")
    return False
