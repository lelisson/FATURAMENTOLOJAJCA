"""Gera relatorios/README_Painel_Vendas_JCA.pdf (fora do git). Uso: python scripts/gerar_readme_pdf.py"""
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
DESTINO = ROOT / "relatorios" / "README_Painel_Vendas_JCA.pdf"

INK = HexColor("#0f172a")
MUTED = HexColor("#475569")
LINE = HexColor("#cbd5e1")
NAVY = HexColor("#1e3a5f")
TEAL = HexColor("#0e7490")
SOFT = HexColor("#f1f5f9")
WHITE = HexColor("#ffffff")


def styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle(name="CoverTitle", fontName="Helvetica-Bold", fontSize=26, leading=32,
                         textColor=WHITE, spaceAfter=8))
    s.add(ParagraphStyle(name="CoverSub", fontName="Helvetica", fontSize=12, leading=16,
                         textColor=HexColor("#e2e8f0"), spaceAfter=4))
    s.add(ParagraphStyle(name="CoverMeta", fontName="Helvetica", fontSize=9, leading=12,
                         textColor=HexColor("#94a3b8")))
    s.add(ParagraphStyle(name="H1", fontName="Helvetica-Bold", fontSize=14, leading=18,
                         textColor=NAVY, spaceBefore=16, spaceAfter=8))
    s.add(ParagraphStyle(name="H2", fontName="Helvetica-Bold", fontSize=11, leading=14,
                         textColor=TEAL, spaceBefore=12, spaceAfter=6))
    s.add(ParagraphStyle(name="Body", fontName="Helvetica", fontSize=9.5, leading=13,
                         textColor=INK, alignment=TA_JUSTIFY, spaceAfter=6))
    s.add(ParagraphStyle(name="ItemBullet", fontName="Helvetica", fontSize=9.5, leading=13,
                         textColor=INK, leftIndent=12, spaceAfter=3))
    s.add(ParagraphStyle(name="Small", fontName="Helvetica", fontSize=8, leading=11,
                         textColor=MUTED, spaceAfter=4))
    s.add(ParagraphStyle(name="Cell", fontName="Helvetica", fontSize=8.5, leading=11, textColor=INK))
    s.add(ParagraphStyle(name="CellB", fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=INK))
    s.add(ParagraphStyle(name="CellH", fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=WHITE))
    s.add(ParagraphStyle(name="FooterTxt", fontName="Helvetica", fontSize=8, textColor=MUTED,
                         alignment=TA_CENTER))
    return s


def bullets(story, st, items):
    for t in items:
        story.append(Paragraph("• " + t, st["ItemBullet"]))


def main() -> None:
    st = styles()
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    story = []

    capa = Table([
        [Paragraph("JCA · Painel de Vendas", st["CoverTitle"])],
        [Paragraph("Relatório do projeto (README técnico e de segurança)", st["CoverSub"])],
        [Paragraph(
            "JCA Filial · Omie (somente leitura) · Streamlit Cloud · GitHub Actions<br/>"
            "Data: 15/10/2026 · Repositório: github.com/lelisson/FATURAMENTOLOJAJCA",
            st["CoverMeta"],
        )],
    ], colWidths=[170 * mm])
    capa.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("TOPPADDING", (0, 0), (-1, 0), 22),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 18),
        ("LEFTPADDING", (0, 0), (-1, -1), 16),
        ("RIGHTPADDING", (0, 0), (-1, -1), 16),
        ("TOPPADDING", (0, 1), (-1, -2), 4),
    ]))
    story.append(capa)
    story.append(Spacer(1, 14))

    story.append(Paragraph("1. Resumo executivo", st["H1"]))
    story.append(Paragraph(
        "Sistema de painel de faturamento da JCA que consulta a API Omie em <b>somente leitura</b>, "
        "consolida vendas (NF-e, devoluções e, na filial, NFC-e/PDV), publica dados criptografados "
        "e exibe o resultado no Streamlit Cloud. O PC local não precisa ficar ligado: a atualização "
        "roda no GitHub Actions. O app na nuvem só visualiza; as chaves da Omie nunca ficam no Streamlit.",
        st["Body"],
    ))

    story.append(Paragraph("2. O que foi feito", st["H1"]))
    story.append(Paragraph("2.1 Escopo do produto", st["H2"]))
    bullets(story, st, [
        "Painel interativo de vendas (KPIs, canais, ranking, detalhamento, oportunidades).",
        "Somente a JCA Filial, período a partir de julho/2026. A Matriz tem repositório próprio "
        "(FATURAMENTOMATRIZJCA), com chave de cifra e senha separadas.",
        "Faturamento líquido: vendas menos devoluções no mês da devolução; transferências e "
        "operações excluídas fora do total.",
        "Card e aba de <b>Devoluções</b>; clientes sem compra e estoque sem giro (oportunidades).",
        "Relatórios HTML geráveis no painel; este PDF documenta o projeto para diretoria e segurança.",
    ])

    story.append(Paragraph("2.2 Arquitetura", st["H2"]))
    bullets(story, st, [
        "<b>Coleta:</b> GitHub Actions executa scripts/publicar_dados.py "
        "a cada 20 min (cada execução agenda a próxima; cron nos minutos 7, 27 e 47 como reserva).",
        "<b>Fonte:</b> Omie API — ListarNF (saídas e entradas), CuponsFiscais (PDV), "
        "ConsultarPedido (canal consumidor final), ListarPosEstoque.",
        "<b>Publicação:</b> JSON compactado (gzip) + cifrado Fernet → painel.enc no branch dados.",
        "<b>Visualização:</b> Streamlit Cloud carrega o snapshot, valida senha (hash) e embute "
        "os dados no frontend estático.",
        "<b>Local (opcional):</b> FastAPI + frontend no PC; chaves só em variáveis de ambiente "
        "do usuário Windows.",
    ])

    story.append(Paragraph("2.3 Regras de negócio implementadas", st["H2"]))
    bullets(story, st, [
        "Operações excluídas do faturamento (ex.: 14, 16, 24, 04) e CFOPs de transferência / não-venda.",
        "Devoluções (CFOP 1201/1202/1410 e equivalentes) abatem no mês da NF de devolução.",
        "Pedidos marcados como devolvidos não excluem a venda original; o abate vem da NF de entrada.",
        "Cache de pedidos (consumidor final) para reduzir chamadas e evitar bloqueio da Omie.",
        "Meses fechados congelados em cache cifrado após o dia 1 às 23:59 do mês seguinte "
        "(prazo usual de cancelamento de NF-e).",
        "Revalidação semanal automática no domingo: reconsulta meses fechados e atualiza o cache.",
        "Botão manual no Actions: “Consultar de novo também os meses fechados”.",
    ])

    story.append(Paragraph("2.4 Operação e desempenho", st["H2"]))
    bullets(story, st, [
        "Tarefa agendada no Windows desligada; atualização independente do PC.",
        "Limite de tempo por execução em ConsultarPedido (PEDIDOS_MAX_SEG); o restante completa "
        "nas próximas rodadas.",
        "Retry com espera em falhas transitórias da Omie (“requisição já em execução”, REDUNDANT).",
        "Cache do Actions para pedidos e meses congelados (arquivos cifrados com a mesma chave do painel).",
    ])

    story.append(Paragraph("3. Níveis de segurança aplicados", st["H1"]))
    story.append(Paragraph(
        "As medidas estão organizadas em camadas. Nenhuma camada sozinha basta; o conjunto reduz "
        "exposição de credenciais, vazamento no frontend e abuso da API.",
        st["Body"],
    ))

    hdr = [Paragraph(x, st["CellH"]) for x in ["Nível", "Controle", "Como está aplicado"]]
    rows = [hdr]
    data_sec = [
        ("1 · Segredo", "Chaves fora do código",
         "App Key/Secret Omie e PAINEL_DATA_KEY não vão para o repositório. No PC: variáveis de "
         "ambiente do usuário Windows. No GitHub: Secrets do Actions. Varredura antes de cada push."),
        ("2 · Mínimo privilégio", "Omie somente leitura",
         "Whitelist READ_ONLY_CALLS: só métodos de consulta (ListarNF, CuponsFiscais, "
         "ConsultarPedido, ListarPosEstoque). Sem escrita, alteração ou exclusão na Omie."),
        ("3 · Separação de papéis", "Coleta ≠ visualização",
         "Streamlit Cloud não possui OMIE_APP_KEY. Só recebe URL do snapshot + chave Fernet + "
         "hash de senha. Quem vê o painel não consulta a Omie."),
        ("4 · Dados em trânsito/repouso", "Criptografia Fernet",
         "Branch público dados contém só o blob cifrado painel.enc. "
         "Sem a PAINEL_DATA_KEY o conteúdo é ilegível."),
        ("5 · Acesso ao app", "Senha com hash",
         "APP_PASSWORD_HASH (PBKDF2-SHA256, 600 mil iterações). Senha em texto nunca fica no HTML "
         "nem nos Secrets do Streamlit. Atraso 1,5 s por erro; bloqueio 5 min após 5 falhas."),
        ("6 · Repositório", "Git hygiene",
         ".env, secrets.toml, caches e relatórios no .gitignore. Branch main sem dados sensíveis. "
         "Logs do Actions mascaram secrets (***)."),
        ("7 · Resiliência da API", "Anti-bloqueio Omie",
         "Cache de pedidos, meses congelados, paralelismo limitado, PEDIDOS_MAX_SEG, retry "
         "controlado. Reduz risco de MISUSE/425 por excesso de chamadas."),
        ("8 · Conta GitHub", "2FA recomendado",
         "Proteção da conta que guarda Secrets e faz push no branch dados. Ativar autenticação "
         "em duas etapas no GitHub."),
    ]
    for nivel, controle, como in data_sec:
        rows.append([
            Paragraph(nivel, st["CellB"]),
            Paragraph(controle, st["CellB"]),
            Paragraph(como, st["Cell"]),
        ])

    t = Table(rows, colWidths=[32 * mm, 38 * mm, 100 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("BACKGROUND", (0, 1), (-1, 1), SOFT),
        ("BACKGROUND", (0, 3), (-1, 3), SOFT),
        ("BACKGROUND", (0, 5), (-1, 5), SOFT),
        ("BACKGROUND", (0, 7), (-1, 7), SOFT),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(t)
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "<b>Limite honesto do nível 1 no Windows:</b> variáveis de ambiente do usuário ficam em "
        "texto no registro (HKCU\\Environment). Só a conta do usuário e administradores do PC leem; "
        "qualquer programa na mesma sessão também pode ler. Alternativa mais forte, se necessária: "
        "Gerenciador de Credenciais (DPAPI).",
        st["Small"],
    ))

    story.append(Paragraph("4. O que NÃO sobe / NÃO fica exposto", st["H1"]))
    bullets(story, st, [
        "App Key e App Secret da Omie no código, no HTML ou no Streamlit.",
        "Senha do painel em texto claro (apenas hash PBKDF2).",
        "JSON de vendas em claro no GitHub (apenas arquivos .enc).",
        "Arquivos .env e .streamlit/secrets.toml no git.",
    ])

    story.append(Paragraph("5. Fluxo de dados (visão de segurança)", st["H1"]))
    fluxo = [
        [Paragraph(f"<b>{x}</b>", st["CellH"]) for x in ("Etapa", "Onde", "Segredo envolvido", "Saída")],
        [Paragraph("1. Consulta Omie", st["Cell"]),
         Paragraph("GitHub Actions", st["Cell"]),
         Paragraph("Secrets OMIE_*", st["Cell"]),
         Paragraph("JSON em memória", st["Cell"])],
        [Paragraph("2. Cifrar + publicar", st["Cell"]),
         Paragraph("Actions → branch dados", st["Cell"]),
         Paragraph("PAINEL_DATA_KEY", st["Cell"]),
         Paragraph("*.enc no GitHub", st["Cell"])],
        [Paragraph("3. Login + decrypt", st["Cell"]),
         Paragraph("Streamlit Cloud", st["Cell"]),
         Paragraph("Hash senha + Fernet", st["Cell"]),
         Paragraph("Painel no navegador", st["Cell"])],
    ]
    tf = Table(fluxo, colWidths=[40 * mm, 40 * mm, 42 * mm, 48 * mm])
    tf.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), TEAL),
        ("BACKGROUND", (0, 2), (-1, 2), SOFT),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(tf)

    story.append(Paragraph("6. Responsabilidades do time", st["H1"]))
    bullets(story, st, [
        "Colar/atualizar Secrets no Streamlit Cloud (PAINEL_DATA_URL, PAINEL_DATA_KEY, "
        "APP_PASSWORD_HASH) sem publicar a senha em texto.",
        "Ativar 2FA na conta GitHub que possui os Secrets.",
        "Apagar o arquivo local da senha após guardar em cofre interno "
        "(~/.painel-omie/senha-streamlit.txt).",
        "Não compartilhar chaves Omie por chat, e-mail ou repositório.",
        "Em caso de suspeita de vazamento: rotacionar App Key/Secret na Omie, regenerar "
        "PAINEL_DATA_KEY e republicar.",
    ])

    story.append(Paragraph("7. Referências técnicas", st["H1"]))
    bullets(story, st, [
        "Repositório: https://github.com/lelisson/FATURAMENTOLOJAJCA",
        "Workflow: .github/workflows/publicar.yml",
        "App: streamlit_app.py · Coleta: scripts/publicar_dados.py · Cliente: backend/app/omie.py",
        "Período padrão: DEFAULT_INICIO=2026-07-01 · Fuso: America/Sao_Paulo",
    ])

    story.append(Spacer(1, 16))
    story.append(HRFlowable(width="100%", thickness=0.5, color=LINE))
    story.append(Paragraph(
        "Documento gerado para apresentação à diretoria e ao responsável de segurança. "
        "Não contém chaves, senhas nem dados de faturamento.",
        st["FooterTxt"],
    ))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.4)
        canvas.line(18 * mm, 12 * mm, A4[0] - 18 * mm, 12 * mm)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(18 * mm, 7 * mm, "JCA · Painel de Vendas · Confidencial interno")
        canvas.drawRightString(A4[0] - 18 * mm, 7 * mm, f"Página {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(DESTINO),
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=18 * mm,
        title="README · Painel de Vendas JCA",
        author="JCA · Automação de Relatórios",
        subject="Relatório do projeto e níveis de segurança",
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(DESTINO)


if __name__ == "__main__":
    main()
