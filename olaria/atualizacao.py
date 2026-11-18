# -*- coding: utf-8 -*-
"""Orquestra atualização manual/automática: Omie (opcional) + recarga da planilha."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import OMIE_SYNC_HABILITADO


@dataclass
class ResultadoAtualizacao:
    ok: bool
    mensagens: list[str]


def forcar_atualizacao(planilha: Path, ano: int, usar_omie: bool = True) -> ResultadoAtualizacao:
    msgs: list[str] = []
    ok = True
    if usar_omie and OMIE_SYNC_HABILITADO:
        try:
            from .omie_client import credenciais_configuradas
            from .omie_sync import sincronizar_omie

            if credenciais_configuradas():
                msgs.append(sincronizar_omie(planilha, ano))
            else:
                msgs.append("Omie: credenciais não configuradas — apenas recarregou a planilha.")
        except Exception as e:
            ok = False
            msgs.append(f"Omie: falha na sincronização ({e}). Planilha local mantida.")
    else:
        msgs.append("Planilha recarregada (Omie desligado nas configurações).")
    return ResultadoAtualizacao(ok=ok, mensagens=msgs)
