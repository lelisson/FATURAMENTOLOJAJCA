"""Cliente Omie da JCA Filial — somente leitura (financeiro e cadastros de apoio)."""
from __future__ import annotations

import re
import time

import httpx

from . import ambiente

BASE = "https://app.omie.com.br/api/v1"

# Única porta de saída para a Omie: qualquer método fora desta lista é recusado antes da chamada.
READ_ONLY_CALLS: dict[str, str] = {
    "ListarMovimentos": "/financas/mf/",
    "ListarContasPagar": "/financas/contapagar/",
    "ListarContasReceber": "/financas/contareceber/",
    "ListarCategorias": "/geral/categorias/",
    "ListarContasCorrentes": "/geral/contacorrente/",
    "ListarDepartamentos": "/geral/departamentos/",
    "ListarClientesResumido": "/geral/clientes/",
    "ListarEmpresas": "/geral/empresas/",
    "ListarNF": "/produtos/nfconsultar/",
    "CuponsFiscais": "/produtos/cupomfiscalconsultar/",
}


class OmieBloqueada(RuntimeError):
    """A Omie bloqueou o método por consumo indevido; insistir só prolonga o bloqueio."""


def _credenciais() -> tuple[str, str]:
    k, s = ambiente.ler("OMIE_FILIAL_APP_KEY"), ambiente.ler("OMIE_FILIAL_APP_SECRET")
    if not k or not s:
        raise RuntimeError("OMIE_FILIAL_APP_KEY e OMIE_FILIAL_APP_SECRET não configurados no Windows")
    return k, s


def credenciais_configuradas() -> bool:
    try:
        _credenciais()
        return True
    except RuntimeError:
        return False


# IPv4: em redes sem rota IPv6 a conexão fica pendurada até o timeout em cada tentativa.
_http = httpx.Client(transport=httpx.HTTPTransport(local_address="0.0.0.0"),
                     timeout=httpx.Timeout(120, connect=15))


PAUSA_LIMITE_SEG = 10 * 60
_pausa_ate = 0.0


def pausada_ate() -> float:
    return _pausa_ate


def _pausar(segundos: float, motivo: str) -> OmieBloqueada:
    global _pausa_ate
    _pausa_ate = max(_pausa_ate, time.time() + segundos)
    return OmieBloqueada(f"{motivo} Nova tentativa a partir das {time.strftime('%H:%M', time.localtime(_pausa_ate))}.")


def chamar(call: str, param: dict, tentativas: int = 8) -> dict:
    endpoint = READ_ONLY_CALLS.get(call)
    if endpoint is None:
        raise PermissionError(f"Método Omie não permitido (somente leitura): {call}")
    # Durante bloqueio da Omie nenhuma chamada sai: cada tentativa estende o bloqueio.
    if time.time() < _pausa_ate:
        raise OmieBloqueada(f"Consultas à Omie pausadas até {time.strftime('%H:%M', time.localtime(_pausa_ate))}.")
    app_key, app_secret = _credenciais()
    corpo = {"call": call, "app_key": app_key, "app_secret": app_secret, "param": [param]}
    for i in range(tentativas):
        try:
            r = _http.post(BASE + endpoint, json=corpo)
        except httpx.HTTPError:
            if i == tentativas - 1:
                raise
            time.sleep(3 * (i + 1))
            continue
        try:
            data = r.json()
        except ValueError:
            data = {}
        falha = data.get("faultstring") if isinstance(data, dict) else None
        codigo = str(data.get("faultcode", "")) if isinstance(data, dict) else ""
        if r.status_code == 429:
            raise _pausar(PAUSA_LIMITE_SEG, "A Omie atingiu o limite de requisições.")
        if r.status_code == 425 or "MISUSE" in codigo:
            m = re.search(r"(\d+)\s*segundos", falha or "")
            raise _pausar(int(m.group(1)) + 30 if m else PAUSA_LIMITE_SEG, "A Omie bloqueou o método temporariamente.")
        if falha:
            # Lista vazia vem como erro na Omie
            if "Não existem registros" in falha or "nao existem registros" in falha.lower():
                return {}
            # Repetir antes do prazo pedido renova a espera; por isso a folga de alguns segundos.
            if ("requisição desse método sendo executada" in falha or "REDUNDANT" in falha) and i < tentativas - 1:
                m = re.search(r"(\d+)\s*segundos", falha)
                time.sleep(int(m.group(1)) + 5 if m else 10 * (i + 1))
                continue
            raise RuntimeError(f"Omie ({call}): {falha}")
        if r.status_code in (500, 502, 503, 504) and i < tentativas - 1:
            time.sleep(3 * (i + 1))
            continue
        r.raise_for_status()
        return data
    raise RuntimeError(f"Falha ao chamar a API Omie ({call})")


def paginar(call: str, param, lista: str, total_paginas: str, pausa: float = 0.25) -> list[dict]:
    """Sequencial: a Omie bloqueia o método quando recebe chamadas demais em paralelo."""
    out: list[dict] = []
    pagina, total = 1, 1
    while pagina <= total:
        resp = chamar(call, param(pagina))
        out.extend(resp.get(lista) or [])
        total = int(resp.get(total_paginas) or 1)
        pagina += 1
        if pagina <= total:
            time.sleep(pausa)
    return out


def br(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}"


def iso(d: str) -> str:
    d = (d or "").strip()
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})", d)
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else d[:10]


def movimentos(inicio: str, fim: str) -> list[dict]:
    """Movimento financeiro (contas a pagar, a receber e lançamentos de conta corrente) por vencimento."""
    return paginar(
        "ListarMovimentos",
        lambda p: {"nPagina": p, "nRegPorPagina": 500, "dDtVencDe": br(inicio), "dDtVencAte": br(fim),
                   "cExibirDepartamentos": "S"},
        "movimentos",
        "nTotPaginas",
    )


def movimentos_pagos(inicio: str, fim: str) -> list[dict]:
    """Movimentos baixados (pagos/recebidos) no período, pela data de pagamento."""
    return paginar(
        "ListarMovimentos",
        lambda p: {"nPagina": p, "nRegPorPagina": 500, "dDtPagtoDe": br(inicio), "dDtPagtoAte": br(fim),
                   "cExibirDepartamentos": "S"},
        "movimentos",
        "nTotPaginas",
    )


def categorias() -> list[dict]:
    return paginar("ListarCategorias", lambda p: {"pagina": p, "registros_por_pagina": 500},
                   "categoria_cadastro", "total_de_paginas")


def contas_correntes() -> list[dict]:
    return paginar("ListarContasCorrentes",
                   lambda p: {"pagina": p, "registros_por_pagina": 100, "apenas_importado_api": "N"},
                   "ListarContasCorrentes", "total_de_paginas")


def departamentos() -> list[dict]:
    return paginar("ListarDepartamentos", lambda p: {"pagina": p, "registros_por_pagina": 500},
                   "departamentos", "total_de_paginas")


def empresas() -> list[dict]:
    return paginar("ListarEmpresas",
                   lambda p: {"pagina": p, "registros_por_pagina": 50, "apenas_importado_api": "N"},
                   "empresas_cadastro", "total_de_paginas")


def clientes_fornecedores() -> list[dict]:
    return paginar("ListarClientesResumido",
                   lambda p: {"pagina": p, "registros_por_pagina": 500, "apenas_importado_api": "N"},
                   "clientes_cadastro_resumido", "total_de_paginas")


def notas_fiscais(inicio: str, fim: str, tp_nf: str = "1") -> list[dict]:
    """tp_nf 1 = saída, 0 = entrada (devoluções)."""
    return paginar(
        "ListarNF",
        lambda p: {
            "pagina": p,
            "registros_por_pagina": 50,
            "apenas_importado_api": "N",
            "cDetalhesPedido": "S",
            "dEmiInicial": br(inicio),
            "dEmiFinal": br(fim),
            "tpNF": tp_nf,
        },
        "nfCadastro",
        "total_de_paginas",
    )


def cupons_fiscais(inicio: str, fim: str) -> list[dict]:
    return paginar(
        "CuponsFiscais",
        lambda p: {
            "nPagina": p,
            "nRegPorPagina": 100,
            "dDtEmissaoDe": br(inicio),
            "dDtEmissaoAte": br(fim),
        },
        "cupons",
        "nTotPaginas",
    )
