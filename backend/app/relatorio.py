"""Relatório executivo em HTML estático (autocontido: CSS e gráficos SVG embutidos, sem internet)."""
from collections import defaultdict
from datetime import date, timedelta
from html import escape

from .transform import ANON, CANAIS

MESES = ["", "janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]
CANAL_NOME = {"PDV": "PDV (balcão)", "Pedido – consumo final": "Consumidor final (pedido)",
              "Pedido – empresas": "Empresas (pedido)"}
CORES = ["#4f46e5", "#0891b2", "#d97706", "#16a34a", "#db2777", "#7c3aed", "#0d9488", "#ea580c", "#64748b"]


# ---------- formatação ----------
def brl(v: float) -> str:
    s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("-R$ " if v < 0 else "R$ ") + s


def brk(v: float) -> str:
    if abs(v) >= 1000:
        return f"R$ {v / 1000:,.1f} mil".replace(",", "X").replace(".", ",").replace("X", ".")
    return brl(v)


def num(v: float) -> str:
    return f"{v:,.0f}".replace(",", ".")


def pct(v: float, casas: int = 1) -> str:
    return f"{v * 100:.{casas}f}%".replace(".", ",")


def dbr(s: str) -> str:
    return f"{s[8:10]}/{s[5:7]}/{s[:4]}" if s else "—"


def var(a: float, b: float):
    return (a / b - 1) if b else None


def var_html(v, inverso: bool = False) -> str:
    if v is None:
        return '<span class="neu">—</span>'
    bom = (v >= 0) != inverso
    return f'<span class="{"up" if bom else "dn"}">{"▲" if v >= 0 else "▼"} {pct(abs(v))}</span>'


def nome_periodo(inicio: str, fim: str) -> str:
    di, df = date.fromisoformat(inicio), date.fromisoformat(fim)
    ultimo = (date(df.year + df.month // 12, df.month % 12 + 1, 1) - timedelta(days=1))
    if di.day == 1 and (di.year, di.month) == (df.year, df.month):
        base = f"{MESES[di.month].capitalize()} de {di.year}"
        return base if df == ultimo else f"{base} (até {df.day:02d}/{df.month:02d})"
    return f"{dbr(inicio)} a {dbr(fim)}"


def periodo_comparacao(inicio: str, fim: str) -> tuple[str, str]:
    """Mês fechado/parcial → mesmo intervalo de dias do mês anterior; senão, período de mesma duração imediatamente antes."""
    di, df = date.fromisoformat(inicio), date.fromisoformat(fim)
    if di.day == 1 and (di.year, di.month) == (df.year, df.month):
        pi = date(di.year - (di.month == 1), (di.month - 2) % 12 + 1, 1)
        ultimo_prev = di - timedelta(days=1)
        ultimo_atual = date(df.year + df.month // 12, df.month % 12 + 1, 1) - timedelta(days=1)
        pf = ultimo_prev if df == ultimo_atual else min(ultimo_prev, pi.replace(day=1) + timedelta(days=df.day - 1))
        return pi.isoformat(), pf.isoformat()
    dias = (df - di).days + 1
    pf = di - timedelta(days=1)
    return (pf - timedelta(days=dias - 1)).isoformat(), pf.isoformat()


# ---------- agregação ----------
def agg(rows):
    vs = {r["v"] for r in rows}
    t = sum(r["x"] for r in rows)
    return {"t": t, "n": len(vs), "items": len(rows), "tk": t / len(vs) if vs else 0}


def por(rows, chave):
    g = defaultdict(lambda: {"t": 0.0, "items": 0, "vs": set()})
    for r in rows:
        o = g[chave(r) if callable(chave) else r[chave]]
        o["t"] += r["x"]
        o["items"] += 1
        o["vs"].add(r["v"])
    return {k: {"t": o["t"], "items": o["items"], "n": len(o["vs"])} for k, o in g.items()}


# ---------- gráficos SVG ----------
def _escala(mx: float) -> tuple[float, list[float]]:
    if mx <= 0:
        return 1, [0]
    passo = 10 ** (len(str(int(mx / 4))) - 1) if mx >= 4 else 1
    for m in (1, 2, 2.5, 5, 10):
        if mx / (passo * m) <= 4:
            passo *= m
            break
    topo = passo * (int(mx / passo) + 1)
    return topo, [passo * i for i in range(int(topo / passo) + 1)]


def svg_diario(inicio: str, fim: str, rows) -> str:
    di, df = date.fromisoformat(inicio), date.fromisoformat(fim)
    dias = [(di + timedelta(days=i)).isoformat() for i in range((df - di).days + 1)]
    tot = por(rows, "d")
    vals = [tot.get(d, {}).get("t", 0.0) for d in dias]
    W, H, L, B, T = 760, 230, 58, 26, 12
    topo, ticks = _escala(max(vals or [0]))
    pw, ph = W - L - 8, H - B - T
    bw = pw / max(len(dias), 1)
    y = lambda v: T + ph - v / topo * ph
    out = [f'<svg viewBox="0 0 {W} {H}" class="chart" role="img" aria-label="Faturamento diário">']
    for tk in ticks:
        out.append(f'<line x1="{L}" x2="{W - 8}" y1="{y(tk):.1f}" y2="{y(tk):.1f}" class="grid"/>'
                   f'<text x="{L - 8}" y="{y(tk) + 4:.1f}" class="ax" text-anchor="end">{brk(tk) if tk else "0"}</text>')
    mx = max(vals) if vals else 0
    ativos = [v for v in vals if v > 0]
    media = sum(ativos) / len(ativos) if ativos else 0
    passo_lbl = 1 if len(dias) <= 16 else 2 if len(dias) <= 35 else 7
    for i, (d, v) in enumerate(zip(dias, vals)):
        x = L + i * bw
        fim_semana = date.fromisoformat(d).weekday() >= 5
        cls = "bar best" if v == mx and v > 0 else "bar wk" if fim_semana else "bar"
        if v > 0:
            out.append(f'<rect x="{x + bw * .18:.1f}" y="{y(v):.1f}" width="{bw * .64:.1f}" height="{T + ph - y(v):.1f}" rx="2" class="{cls}">'
                       f'<title>{dbr(d)}: {brl(v)}</title></rect>')
        if i % passo_lbl == 0:
            out.append(f'<text x="{x + bw / 2:.1f}" y="{H - 8}" class="ax" text-anchor="middle">{d[8:10]}</text>')
    if media:
        out.append(f'<line x1="{L}" x2="{W - 8}" y1="{y(media):.1f}" y2="{y(media):.1f}" class="avg"/>'
                   f'<text x="{W - 10}" y="{y(media) - 5:.1f}" class="avgt" text-anchor="end">média por dia com venda {brk(media)}</text>')
    out.append("</svg>")
    return "".join(out)


def svg_empilhada(partes: list[tuple[str, float, str]]) -> str:
    tot = sum(v for _, v, _ in partes) or 1
    x, out = 0.0, ['<svg viewBox="0 0 1000 28" preserveAspectRatio="none" class="stack" role="img" aria-label="Participação por canal">']
    for nome, v, cor in partes:
        w = v / tot * 1000
        out.append(f'<rect x="{x:.1f}" y="0" width="{w:.1f}" height="28" fill="{cor}"><title>{escape(nome)}: {pct(v / tot)}</title></rect>')
        x += w
    out.append("</svg>")
    return "".join(out)


def barras(itens: list[tuple[str, float, str]], total: float) -> str:
    mx = max((v for _, v, _ in itens), default=0) or 1
    linhas = []
    for nome, v, extra in itens:
        linhas.append(f'<div class="hb"><div class="hb-l" title="{escape(nome)}">{escape(nome)}</div>'
                      f'<div class="hb-t"><div class="hb-f" style="width:{v / mx * 100:.1f}%"></div></div>'
                      f'<div class="hb-v">{brl(v)}</div><div class="hb-p">{pct(v / total) if total else "—"}</div><div class="hb-x">{extra}</div></div>')
    return "".join(linhas)


# ---------- relatório ----------
def gerar(rows, rows_prev, inicio, fim, prev_inicio, prev_fim, empresa, atualizado_em) -> str:
    A, P = agg(rows), agg(rows_prev)
    titulo = nome_periodo(inicio, fim)
    titulo_prev = nome_periodo(prev_inicio, prev_fim)
    comp = f"vs {titulo_prev.lower() if titulo_prev[0].isalpha() else titulo_prev}"

    can, can_p = por(rows, "ch"), por(rows_prev, "ch")
    fam, fam_p = por(rows, "f"), por(rows_prev, "f")
    prod, prod_p = por(rows, "p"), por(rows_prev, "p")
    cli_rows = [r for r in rows if r["c"] != ANON]
    cli, cli_p = por(cli_rows, "c"), por([r for r in rows_prev if r["c"] != ANON], "c")
    dia = por(rows, "d")

    fams = sorted(fam.items(), key=lambda kv: -kv[1]["t"])
    prods = sorted(prod.items(), key=lambda kv: -kv[1]["t"])[:10]
    clis = sorted(cli.items(), key=lambda kv: -kv[1]["t"])
    top5 = sum(o["t"] for _, o in clis[:5])
    melhor_dia = max(dia.items(), key=lambda kv: kv[1]["t"]) if dia else None
    dias_venda = len(dia)
    perdidos = sorted(((k, o) for k, o in cli_p.items() if k not in cli), key=lambda kv: -kv[1]["t"])
    novos = [k for k in cli if k not in cli_p]
    ult_compra = {}
    for r in rows_prev:
        if r["c"] in cli_p and r["d"] > ult_compra.get(r["c"], ""):
            ult_compra[r["c"]] = r["d"]

    # destaques
    dv = var(A["t"], P["t"])
    d = []
    if dv is not None:
        d.append(f'Faturamento de <b>{brl(A["t"])}</b>, {"alta" if dv >= 0 else "queda"} de <b>{pct(abs(dv))}</b> '
                 f'em relação a {titulo_prev.lower() if titulo_prev[0].isalpha() else titulo_prev} ({brl(P["t"])}).')
    else:
        d.append(f'Faturamento de <b>{brl(A["t"])}</b> no período.')
    tv = var(A["tk"], P["tk"])
    d.append(f'<b>{num(A["n"])}</b> vendas com ticket médio de <b>{brl(A["tk"])}</b>'
             + (f' ({"+" if tv >= 0 else "−"}{pct(abs(tv))}).' if tv is not None else '.'))
    if can:
        k, o = max(can.items(), key=lambda kv: kv[1]["t"])
        d.append(f'O canal <b>{CANAL_NOME.get(k, k)}</b> respondeu por <b>{pct(o["t"] / A["t"])}</b> do faturamento.')
    if fams:
        k, o = fams[0]
        d.append(f'<b>{escape(k)}</b> foi a família líder, com <b>{pct(o["t"] / A["t"])}</b> das vendas ({brl(o["t"])}).')
    if clis:
        k, o = clis[0]
        d.append(f'Maior cliente: <b>{escape(k)}</b> ({brl(o["t"])}). Os 5 maiores clientes somam <b>{pct(top5 / A["t"])}</b> do faturamento.')
    if melhor_dia:
        d.append(f'Melhor dia: <b>{dbr(melhor_dia[0])}</b>, com {brl(melhor_dia[1]["t"])} em {num(melhor_dia[1]["n"])} vendas.')
    if cli_p:
        d.append(f'<b>{num(len(novos))}</b> clientes identificados compraram neste período e não no anterior; '
                 f'<b>{num(len(perdidos))}</b> do período anterior não voltaram a comprar ({brl(sum(o["t"] for _, o in perdidos))}).')

    def kpi(l, v, a, b, fmt):
        return (f'<div class="kpi"><div class="kl">{l}</div><div class="kv">{v}</div>'
                f'<div class="kd">{var_html(var(a, b))}<span>{comp}</span></div><div class="kp">anterior: {fmt(b)}</div></div>')

    kpis = (kpi("Faturamento", brl(A["t"]), A["t"], P["t"], brl)
            + kpi("Vendas", num(A["n"]), A["n"], P["n"], num)
            + kpi("Ticket médio", brl(A["tk"]), A["tk"], P["tk"], brl)
            + kpi("Itens faturados", num(A["items"]), A["items"], P["items"], num))

    cores_can = dict(zip(CANAIS, CORES))
    canal_linhas = "".join(
        f'<tr><td><i class="sw" style="background:{cores_can[c]}"></i>{CANAL_NOME[c]}</td>'
        f'<td class="n">{brl(can.get(c, {}).get("t", 0))}</td><td class="n">{pct(can.get(c, {}).get("t", 0) / A["t"]) if A["t"] else "—"}</td>'
        f'<td class="n">{num(can.get(c, {}).get("n", 0))}</td>'
        f'<td class="n">{brl(can[c]["t"] / can[c]["n"]) if c in can and can[c]["n"] else "—"}</td>'
        f'<td class="n">{var_html(var(can.get(c, {}).get("t", 0), can_p.get(c, {}).get("t", 0)))}</td></tr>'
        for c in CANAIS)

    fam_html = barras([(k, o["t"], var_html(var(o["t"], fam_p.get(k, {}).get("t", 0)))) for k, o in fams], A["t"])

    prod_linhas = "".join(
        f'<tr><td class="r">{i}</td><td class="w">{escape(k)}</td><td class="n">{num(o["items"])}</td><td class="n">{brl(o["t"])}</td>'
        f'<td class="n">{pct(o["t"] / A["t"])}</td><td class="n">{var_html(var(o["t"], prod_p.get(k, {}).get("t", 0)))}</td></tr>'
        for i, (k, o) in enumerate(prods, 1))

    cli_linhas = "".join(
        f'<tr><td class="r">{i}</td><td class="w">{escape(k)}</td><td class="n">{num(o["n"])}</td><td class="n">{brl(o["t"])}</td>'
        f'<td class="n">{pct(o["t"] / A["t"])}</td><td class="n">{var_html(var(o["t"], cli_p.get(k, {}).get("t", 0))) if k in cli_p else "<span class=new>novo</span>"}</td></tr>'
        for i, (k, o) in enumerate(clis[:10], 1))

    perd_linhas = "".join(
        f'<tr><td class="w">{escape(k)}</td><td class="n">{brl(o["t"])}</td><td class="n">{num(o["n"])}</td><td class="n">{dbr(ult_compra.get(k, ""))}</td></tr>'
        for k, o in perdidos[:12])

    pdv_t = can.get("PDV", {}).get("t", 0)
    anon_t = sum(r["x"] for r in rows if r["c"] == ANON)

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Relatório de Vendas · {escape(empresa)} · {escape(titulo)}</title>
<style>
@page{{size:A4;margin:12mm}}
*{{box-sizing:border-box}}
body{{margin:0;background:#eef0f5;color:#0f172a;font:13px/1.5 "Segoe UI",Inter,system-ui,-apple-system,Roboto,sans-serif;-webkit-font-smoothing:antialiased}}
.doc{{max-width:900px;margin:24px auto;background:#fff;border-radius:14px;box-shadow:0 4px 24px rgba(15,23,42,.08);overflow:hidden}}
.cover{{background:linear-gradient(135deg,#1e1b4b 0%,#312e81 55%,#0e7490 100%);color:#fff;padding:34px 40px 30px}}
.cover .tag{{display:inline-block;font-size:11px;letter-spacing:.12em;text-transform:uppercase;opacity:.75}}
.cover h1{{margin:6px 0 4px;font-size:30px;font-weight:700;letter-spacing:-.02em}}
.cover .sub{{opacity:.85;font-size:14px}}
.cover .meta{{display:flex;gap:28px;margin-top:22px;font-size:12px;opacity:.8;flex-wrap:wrap}}
.cover .meta b{{display:block;font-size:13px;opacity:1;font-weight:600}}
.body{{padding:28px 40px 36px}}
h2{{font-size:15px;margin:30px 0 12px;padding-bottom:8px;border-bottom:1px solid #e5e7ef;letter-spacing:-.01em;display:flex;justify-content:space-between;align-items:baseline}}
h2 small{{font-weight:400;color:#64748b;font-size:12px}}
h2:first-child{{margin-top:0}}
section+section{{margin-top:34px}}
.kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}}
.kpi{{border:1px solid #e5e7ef;border-radius:10px;padding:14px 16px}}
.kl{{color:#64748b;font-size:12px;font-weight:500}}
.kv{{font-size:21px;font-weight:700;letter-spacing:-.02em;margin:4px 0 2px;font-variant-numeric:tabular-nums;white-space:nowrap}}
.kd{{font-size:12px;display:flex;gap:6px;align-items:center;flex-wrap:wrap}}.kd span:last-child{{color:#94a3b8}}
.kp{{font-size:11.5px;color:#94a3b8;font-variant-numeric:tabular-nums}}
.up{{color:#15803d;font-weight:600}}.dn{{color:#be123c;font-weight:600}}.neu{{color:#94a3b8}}
.new{{color:#4f46e5;font-weight:600;font-size:11.5px}}
ul.hl{{margin:0;padding:0;list-style:none;display:grid;gap:8px}}
ul.hl li{{position:relative;padding:9px 12px 9px 30px;background:#f8f9fc;border-radius:8px}}
ul.hl li::before{{content:"";position:absolute;left:13px;top:16px;width:7px;height:7px;border-radius:50%;background:#4f46e5}}
.chart{{width:100%;height:auto;display:block}}
.chart .grid{{stroke:#eef0f5;stroke-width:1}}.chart .ax{{fill:#94a3b8;font-size:10px}}
.chart .bar{{fill:#a5b4fc}}.chart .bar.wk{{fill:#c7d2fe}}.chart .bar.best{{fill:#4f46e5}}
.chart .avg{{stroke:#d97706;stroke-dasharray:4 4;stroke-width:1.5}}.chart .avgt{{fill:#b45309;font-size:10.5px;font-weight:600}}
.stack{{width:100%;height:14px;border-radius:7px;display:block;margin:4px 0 14px;overflow:hidden}}
table{{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}}
th,td{{padding:7px 10px;border-bottom:1px solid #eef0f5;text-align:left}}
th{{font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;color:#64748b;font-weight:600;background:#f8f9fc}}
td.n,th.n{{text-align:right;white-space:nowrap}}td.r{{color:#94a3b8;width:28px}}td.w{{max-width:380px}}
tr.tot td{{font-weight:700;border-top:1.5px solid #cbd5e1;border-bottom:0}}
.sw{{display:inline-block;width:9px;height:9px;border-radius:3px;margin-right:8px}}
.hb{{display:grid;grid-template-columns:170px 1fr 110px 54px 70px;gap:10px;align-items:center;padding:5px 0;font-variant-numeric:tabular-nums}}
.hb-l{{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-weight:500}}
.hb-t{{background:#f1f2f7;border-radius:5px;height:12px;overflow:hidden}}.hb-f{{height:100%;background:linear-gradient(90deg,#6366f1,#0891b2);border-radius:5px}}
.hb-v{{text-align:right}}.hb-p{{text-align:right;color:#64748b}}.hb-x{{text-align:right;font-size:12px}}
.two{{display:grid;grid-template-columns:1fr 1fr;gap:24px}}
.note{{font-size:11.5px;color:#94a3b8;margin-top:6px}}
footer{{border-top:1px solid #e5e7ef;padding:14px 40px;color:#94a3b8;font-size:11px;display:flex;justify-content:space-between}}
.blk{{break-inside:avoid}}
@media print{{body{{background:#fff}}.doc{{margin:0;box-shadow:none;border-radius:0;max-width:none}}
  .cover,.hb-f,.bar,.sw,.stack rect,ul.hl li{{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
  h2{{break-after:avoid}}tr{{break-inside:avoid}}}}
@media (max-width:760px){{.kpis{{grid-template-columns:1fr 1fr}}.two{{grid-template-columns:1fr}}.body,.cover{{padding-left:20px;padding-right:20px}}.hb{{grid-template-columns:110px 1fr 90px 46px}}.hb-x{{display:none}}}}
</style>
</head>
<body>
<article class="doc">
<header class="cover">
  <span class="tag">Relatório de vendas · {escape(empresa)}</span>
  <h1>{escape(titulo)}</h1>
  <div class="sub">Período de {dbr(inicio)} a {dbr(fim)} · comparativo com {dbr(prev_inicio)} a {dbr(prev_fim)}</div>
  <div class="meta">
    <div><b>{brl(A["t"])}</b>faturamento</div>
    <div><b>{num(A["n"])}</b>vendas</div>
    <div><b>{num(dias_venda)}</b>dias com venda</div>
    <div><b>{num(len(cli))}</b>clientes identificados</div>
  </div>
</header>
<div class="body">
  <section class="blk"><h2>Indicadores</h2><div class="kpis">{kpis}</div></section>

  <section class="blk"><h2>Destaques</h2><ul class="hl">{"".join(f"<li>{x}</li>" for x in d)}</ul></section>

  <section class="blk"><h2>Faturamento diário <small>{escape(titulo)}</small></h2>{svg_diario(inicio, fim, rows)}</section>

  <section class="blk"><h2>Canais de venda</h2>
    {svg_empilhada([(CANAL_NOME[c], can.get(c, {}).get("t", 0), cores_can[c]) for c in CANAIS])}
    <table><thead><tr><th>Canal</th><th class="n">Faturamento</th><th class="n">Part.</th><th class="n">Vendas</th><th class="n">Ticket</th><th class="n">Var.</th></tr></thead>
    <tbody>{canal_linhas}<tr class="tot"><td>Total</td><td class="n">{brl(A["t"])}</td><td class="n">100,0%</td><td class="n">{num(A["n"])}</td><td class="n">{brl(A["tk"])}</td><td class="n">{var_html(dv)}</td></tr></tbody></table>
  </section>

  <section class="blk"><h2>Famílias de produto <small>faturamento · participação · variação</small></h2>{fam_html}</section>

  <section class="blk"><h2>Top 10 produtos</h2>
    <table><thead><tr><th></th><th>Produto</th><th class="n">Itens</th><th class="n">Faturamento</th><th class="n">Part.</th><th class="n">Var.</th></tr></thead><tbody>{prod_linhas}</tbody></table>
  </section>

  <section class="blk"><h2>Top 10 clientes <small>5 maiores = {pct(top5 / A["t"]) if A["t"] else "—"} do faturamento</small></h2>
    <table><thead><tr><th></th><th>Cliente</th><th class="n">Vendas</th><th class="n">Faturamento</th><th class="n">Part.</th><th class="n">Var.</th></tr></thead><tbody>{cli_linhas}</tbody></table>
    <div class="note">Vendas sem cliente identificado (consumidor no balcão): {brl(anon_t)} ({pct(anon_t / A["t"]) if A["t"] else "—"}). PDV total: {brl(pdv_t)}.</div>
  </section>

  {f'''<section class="blk"><h2>Clientes sem recompra <small>compraram em {escape(titulo_prev.lower() if titulo_prev[0].isalpha() else titulo_prev)} e não em {escape(titulo.lower() if titulo[0].isalpha() else titulo)}</small></h2>
    <table><thead><tr><th>Cliente</th><th class="n">Comprou antes</th><th class="n">Vendas</th><th class="n">Última compra</th></tr></thead><tbody>{perd_linhas}</tbody></table>
    {f'<div class="note">Mostrando 12 de {num(len(perdidos))} clientes.</div>' if len(perdidos) > 12 else ''}
  </section>''' if perdidos else ''}
</div>
<footer><span>{escape(empresa)} · Fonte: ERP Omie (NF-e e NFC-e, líquidas de cancelamentos e devoluções)</span><span>Dados de {escape(atualizado_em)}</span></footer>
</article>
</body>
</html>"""
