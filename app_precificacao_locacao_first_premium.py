
import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
from datetime import date, datetime
from io import BytesIO

st.set_page_config(
    page_title="First Medical | Precificação de Locação",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_PATH = "simulacoes_locacao_first.db"

# Padrões gerenciais
IMPOSTO_LOCACAO_PADRAO = 14.30
PIS_COFINS_VENDA_PADRAO = 3.65
ICMS_VENDA_PADRAO = 18.00
IRPJ_GANHO_CAPITAL_PADRAO = 15.00
CSLL_GANHO_CAPITAL_PADRAO = 9.00
COMISSAO_VENDEDOR_PADRAO = 5.00
COMISSAO_GERENTE_PADRAO = 0.50

# =========================================================
# BANCO DE DADOS
# =========================================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS simulacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_hora TEXT,
            cliente TEXT,
            equipamento TEXT,
            fabricante TEXT,
            vendedor TEXT,
            gerente TEXT,
            valor_aquisicao REAL,
            prazo INTEGER,
            aluguel_mensal REAL,
            valor_residual REAL,
            lucro_locacao REAL,
            margem_locacao REAL,
            lucro_locacao_venda REAL,
            margem_locacao_venda REAL,
            ganho_capital REAL,
            impostos_locacao REAL,
            impostos_venda REAL,
            impostos_ganho_capital REAL,
            status_locacao TEXT,
            status_locacao_venda TEXT,
            parecer TEXT
        )
    """)
    conn.commit()
    conn.close()

def salvar_simulacao(dados):
    conn = sqlite3.connect(DB_PATH)
    cols = ", ".join(dados.keys())
    placeholders = ", ".join(["?"] * len(dados))
    conn.execute(f"INSERT INTO simulacoes ({cols}) VALUES ({placeholders})", list(dados.values()))
    conn.commit()
    conn.close()

def carregar_historico():
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query("SELECT * FROM simulacoes ORDER BY id DESC", conn)
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df

def limpar_historico():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM simulacoes")
    conn.commit()
    conn.close()

init_db()

# =========================================================
# FORMATAÇÃO
# =========================================================
def moeda(valor):
    try:
        return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"

def perc(valor):
    try:
        return f"{float(valor):.2f}%".replace(".", ",")
    except Exception:
        return "0,00%"

def meses(valor):
    try:
        if float(valor) >= 900:
            return "Não recupera"
        return f"{float(valor):.1f} meses".replace(".", ",")
    except Exception:
        return "N/A"

def formatar_df(df, money_cols=None, percent_cols=None, month_cols=None):
    df_fmt = df.copy()
    for col in money_cols or []:
        if col in df_fmt.columns:
            df_fmt[col] = df_fmt[col].apply(moeda)
    for col in percent_cols or []:
        if col in df_fmt.columns:
            df_fmt[col] = df_fmt[col].apply(perc)
    for col in month_cols or []:
        if col in df_fmt.columns:
            df_fmt[col] = df_fmt[col].apply(meses)
    return df_fmt

# =========================================================
# ESTILO
# =========================================================
st.markdown("""
<style>
    .stApp { background: linear-gradient(180deg, #F5F8FC 0%, #EEF3F8 100%); }
    .block-container { padding-top: 1.1rem; padding-bottom: 2.4rem; }

    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #071F33 0%, #0B2F4A 100%);
    }
    section[data-testid="stSidebar"] * { color: white !important; }

    .hero {
        background: linear-gradient(135deg, #0B2F4A 0%, #155E75 70%, #1B7893 100%);
        border-radius: 24px;
        padding: 28px 32px;
        color: white;
        box-shadow: 0 12px 32px rgba(15, 46, 74, 0.20);
        margin-bottom: 20px;
    }
    .hero h1 {
        font-size: 2rem;
        margin: 0;
        font-weight: 850;
        letter-spacing: -0.03em;
    }
    .hero p {
        margin: 8px 0 0 0;
        color: rgba(255,255,255,0.88);
        font-size: 1rem;
    }

    .metric-card {
        background: white;
        border-radius: 20px;
        padding: 18px 20px;
        border: 1px solid rgba(15,46,74,0.08);
        box-shadow: 0 8px 24px rgba(15, 46, 74, 0.07);
        min-height: 122px;
        margin-bottom: 14px;
    }
    .metric-label {
        color: #64748B;
        font-size: .78rem;
        text-transform: uppercase;
        letter-spacing: .06em;
        font-weight: 800;
    }
    .metric-value {
        color: #0B2F4A;
        font-size: 1.43rem;
        font-weight: 850;
        margin-top: 8px;
        letter-spacing: -0.03em;
    }
    .metric-help {
        color: #64748B;
        font-size: .84rem;
        margin-top: 6px;
    }

    .section-title {
        color: #0B2F4A;
        font-size: 1.18rem;
        font-weight: 850;
        margin: 16px 0 10px 0;
        letter-spacing: -0.02em;
    }
    .parecer {
        background: #FFFFFF;
        border-left: 6px solid #D7A84F;
        padding: 18px 20px;
        border-radius: 16px;
        box-shadow: 0 8px 24px rgba(15, 46, 74, 0.07);
        color: #0B2F4A;
        line-height: 1.55;
        margin: 12px 0 18px 0;
        font-weight: 500;
    }
    .pill-good, .pill-warn, .pill-bad {
        display: inline-block;
        padding: 8px 14px;
        border-radius: 999px;
        font-weight: 850;
        margin-bottom: 12px;
    }
    .pill-good { background: #CCFBF1; color: #115E59; }
    .pill-warn { background: #FEF3C7; color: #92400E; }
    .pill-bad { background: #FEE2E2; color: #991B1B; }

    .stButton > button, .stDownloadButton > button {
        border-radius: 14px !important;
        border: 0 !important;
        background: linear-gradient(135deg, #0B2F4A 0%, #155E75 100%) !important;
        color: white !important;
        font-weight: 800 !important;
        padding: 0.75rem 1rem !important;
        box-shadow: 0 8px 18px rgba(11,47,74,0.18);
    }
</style>
""", unsafe_allow_html=True)

# =========================================================
# CÁLCULOS
# =========================================================
def classificar_status(margem, lucro, payback, prazo):
    if lucro < 0 or margem < 8:
        return "Crítica"
    if margem < 18 or payback > prazo:
        return "Atenção"
    return "Saudável"

def status_html(status, titulo):
    if status == "Saudável":
        return f'<span class="pill-good">🟢 {titulo}: saudável</span>'
    if status == "Atenção":
        return f'<span class="pill-warn">🟡 {titulo}: revisar</span>'
    return f'<span class="pill-bad">🔴 {titulo}: crítica</span>'

def calcular_payback(saida_inicial, fluxo_mensal):
    if fluxo_mensal <= 0:
        return 999
    return saida_inicial / fluxo_mensal

def calcular_aluguel_minimo(p, considerar_venda):
    for aluguel in np.arange(1000, 150000, 100):
        pp = p.copy()
        pp["aluguel_mensal"] = float(aluguel)
        r, _ = calcular_operacao(pp, interno=True)
        margem = r["margem_locacao_venda"] if considerar_venda else r["margem_locacao"]
        if margem >= p["margem_desejada"]:
            return float(aluguel)
    return 0

def calcular_operacao(p, interno=False):
    receita_locacao = p["aluguel_mensal"] * p["prazo"]

    despesas_total = (
        p["frete"] + p["instalacao"] + p["seguro"] + p["manutencao"] +
        p["despesas_indiretas"] + p["outras_despesas"]
    )

    depreciacao_mensal = p["valor_aquisicao"] / (p["vida_util_anos"] * 12)
    depreciacao_acumulada = min(depreciacao_mensal * p["prazo"], p["valor_aquisicao"])
    valor_contabil_final = max(p["valor_aquisicao"] - depreciacao_acumulada, 0)
    ganho_capital = p["valor_residual"] - valor_contabil_final

    comissao_locacao = receita_locacao * (p["perc_comissao_vendedor"] + p["perc_comissao_gerente"]) / 100
    comissao_vendedor = receita_locacao * p["perc_comissao_vendedor"] / 100
    comissao_gerente = receita_locacao * p["perc_comissao_gerente"] / 100

    impostos_locacao = receita_locacao * p["imposto_locacao"] / 100

    custo_financeiro = p["valor_aquisicao"] * (p["custo_financeiro_mensal"] / 100) * p["prazo"]

    # CENÁRIO 1: SOMENTE LOCAÇÃO
    receita_total_locacao = receita_locacao
    lucro_locacao = receita_locacao - p["valor_aquisicao"] - despesas_total - comissao_locacao - impostos_locacao - custo_financeiro
    margem_locacao = lucro_locacao / receita_total_locacao * 100 if receita_total_locacao else 0

    fluxo_mensal_locacao = (
        p["aluguel_mensal"]
        - impostos_locacao / p["prazo"]
        - despesas_total / p["prazo"]
        - comissao_locacao / p["prazo"]
        - custo_financeiro / p["prazo"]
    )
    payback_locacao = calcular_payback(p["valor_aquisicao"] + p["frete"] + p["instalacao"], fluxo_mensal_locacao)

    # CENÁRIO 2: LOCAÇÃO + VENDA POSTERIOR
    receita_total_venda = receita_locacao + p["valor_residual"]

    impostos_venda = p["valor_residual"] * (p["pis_cofins_venda"] + p["icms_venda"]) / 100 if p["valor_residual"] > 0 else 0
    impostos_ganho_capital = max(ganho_capital, 0) * (p["irpj_ganho"] + p["csll_ganho"]) / 100

    lucro_locacao_venda = (
        receita_total_venda
        - p["valor_aquisicao"]
        - despesas_total
        - comissao_locacao
        - impostos_locacao
        - impostos_venda
        - impostos_ganho_capital
        - custo_financeiro
    )
    margem_locacao_venda = lucro_locacao_venda / receita_total_venda * 100 if receita_total_venda else 0

    fluxo_mensal_base = fluxo_mensal_locacao
    payback_locacao_venda = payback_locacao
    if fluxo_mensal_base > 0:
        saldo = -(p["valor_aquisicao"] + p["frete"] + p["instalacao"])
        payback_locacao_venda = 999
        for m in range(1, int(p["prazo"]) + 1):
            saldo += fluxo_mensal_base
            if m == p["prazo"]:
                saldo += p["valor_residual"] - impostos_venda - impostos_ganho_capital
            if saldo >= 0:
                payback_locacao_venda = m
                break

    status_locacao = classificar_status(margem_locacao, lucro_locacao, payback_locacao, p["prazo"])
    status_locacao_venda = classificar_status(margem_locacao_venda, lucro_locacao_venda, payback_locacao_venda, p["prazo"])

    # IBS/CBS apenas comparativo gerencial sobre receitas
    rt_locacao = receita_locacao * (p["cbs"] + p["ibs"]) / 100
    rt_locacao_venda = receita_total_venda * (p["cbs"] + p["ibs"]) / 100

    aluguel_minimo_locacao = 0 if interno else calcular_aluguel_minimo(p, considerar_venda=False)
    aluguel_minimo_locacao_venda = 0 if interno else calcular_aluguel_minimo(p, considerar_venda=True)

    parecer = (
        f"Somente locação: {status_locacao.lower()}, margem {perc(margem_locacao)} e payback {meses(payback_locacao)}. "
        f"Locação com venda posterior: {status_locacao_venda.lower()}, margem {perc(margem_locacao_venda)} e payback {meses(payback_locacao_venda)}. "
        f"A venda posterior considera impostos sobre a venda de {moeda(impostos_venda)} e tributação estimada sobre ganho de capital de {moeda(impostos_ganho_capital)}."
    )

    fluxo = []
    saldo_loc = -(p["valor_aquisicao"] + p["frete"] + p["instalacao"])
    saldo_venda = saldo_loc
    for m in range(1, int(p["prazo"]) + 1):
        venda_mes = p["valor_residual"] if m == p["prazo"] else 0
        imposto_venda_mes = impostos_venda if m == p["prazo"] else 0
        imposto_gc_mes = impostos_ganho_capital if m == p["prazo"] else 0

        fluxo_loc = fluxo_mensal_base
        fluxo_venda = fluxo_mensal_base + venda_mes - imposto_venda_mes - imposto_gc_mes

        saldo_loc += fluxo_loc
        saldo_venda += fluxo_venda

        fluxo.append({
            "Mês": m,
            "Fluxo somente locação": fluxo_loc,
            "Saldo somente locação": saldo_loc,
            "Venda final": venda_mes,
            "Impostos venda": imposto_venda_mes,
            "Impostos ganho capital": imposto_gc_mes,
            "Fluxo locação + venda": fluxo_venda,
            "Saldo locação + venda": saldo_venda
        })

    resumo = {
        "receita_locacao": receita_locacao,
        "receita_total_locacao": receita_total_locacao,
        "receita_total_venda": receita_total_venda,
        "despesas_total": despesas_total,
        "depreciacao_acumulada": depreciacao_acumulada,
        "valor_contabil_final": valor_contabil_final,
        "ganho_capital": ganho_capital,
        "comissao_vendedor": comissao_vendedor,
        "comissao_gerente": comissao_gerente,
        "comissao_total": comissao_locacao,
        "impostos_locacao": impostos_locacao,
        "impostos_venda": impostos_venda,
        "impostos_ganho_capital": impostos_ganho_capital,
        "custo_financeiro": custo_financeiro,
        "lucro_locacao": lucro_locacao,
        "margem_locacao": margem_locacao,
        "payback_locacao": payback_locacao,
        "lucro_locacao_venda": lucro_locacao_venda,
        "margem_locacao_venda": margem_locacao_venda,
        "payback_locacao_venda": payback_locacao_venda,
        "roi_locacao": lucro_locacao / p["valor_aquisicao"] * 100 if p["valor_aquisicao"] else 0,
        "roi_locacao_venda": lucro_locacao_venda / p["valor_aquisicao"] * 100 if p["valor_aquisicao"] else 0,
        "status_locacao": status_locacao,
        "status_locacao_venda": status_locacao_venda,
        "rt_locacao": rt_locacao,
        "rt_locacao_venda": rt_locacao_venda,
        "aluguel_minimo_locacao": aluguel_minimo_locacao,
        "aluguel_minimo_locacao_venda": aluguel_minimo_locacao_venda,
        "parecer": parecer
    }

    return resumo, pd.DataFrame(fluxo)

def exportar_excel(p, resumo, fluxo_df):
    output = BytesIO()
    premissas = pd.DataFrame([p])
    memorial = pd.DataFrame([
        ["Receita locação", resumo["receita_locacao"]],
        ["Valor de aquisição", p["valor_aquisicao"]],
        ["Despesas previstas", resumo["despesas_total"]],
        ["Comissão vendedor", resumo["comissao_vendedor"]],
        ["Comissão gerente", resumo["comissao_gerente"]],
        ["Impostos locação", resumo["impostos_locacao"]],
        ["Custo financeiro", resumo["custo_financeiro"]],
        ["Lucro somente locação", resumo["lucro_locacao"]],
        ["Margem somente locação", resumo["margem_locacao"]],
        ["Payback somente locação", resumo["payback_locacao"]],
        ["Venda final / residual", p["valor_residual"]],
        ["Valor contábil final", resumo["valor_contabil_final"]],
        ["Ganho de capital", resumo["ganho_capital"]],
        ["Impostos venda", resumo["impostos_venda"]],
        ["Impostos ganho capital", resumo["impostos_ganho_capital"]],
        ["Lucro locação + venda", resumo["lucro_locacao_venda"]],
        ["Margem locação + venda", resumo["margem_locacao_venda"]],
        ["Payback locação + venda", resumo["payback_locacao_venda"]],
    ], columns=["Indicador", "Valor"])

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        premissas.to_excel(writer, index=False, sheet_name="Premissas")
        memorial.to_excel(writer, index=False, sheet_name="Memorial")
        fluxo_df.to_excel(writer, index=False, sheet_name="Fluxo")
    output.seek(0)
    return output

# =========================================================
# SIDEBAR
# =========================================================
st.sidebar.markdown("## FIRST MEDICAL")
st.sidebar.markdown("### Precificação de Locação")
st.sidebar.markdown("---")
menu = st.sidebar.radio(
    "Menu",
    [
        "Visão Executiva",
        "1 - Cadastro da Operação",
        "2 - Precificação Reversa",
        "3 - Parâmetros",
        "4 - Histórico"
    ]
)
st.sidebar.markdown("---")
st.sidebar.caption("Cenários separados: locação | locação + venda")

# =========================================================
# VISÃO EXECUTIVA
# =========================================================
if menu == "Visão Executiva":
    st.markdown("""
    <div class="hero">
        <h1>Precificação de Locação</h1>
        <p>Simulação separada entre locação pura e locação com venda posterior.</p>
    </div>
    """, unsafe_allow_html=True)

    hist = carregar_historico()
    if hist.empty:
        cols = st.columns(4)
        cards = [
            ("Simulações", "0", "Histórico vazio"),
            ("Lucro médio locação", moeda(0), "Sem dados"),
            ("Lucro médio com venda", moeda(0), "Sem dados"),
            ("Operações críticas", "0", "Sem dados"),
        ]
        for col, (label, value, help_text) in zip(cols, cards):
            with col:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">{label}</div>
                    <div class="metric-value">{value}</div>
                    <div class="metric-help">{help_text}</div>
                </div>
                """, unsafe_allow_html=True)
    else:
        cols = st.columns(4)
        cards = [
            ("Simulações", len(hist), "Operações salvas"),
            ("Lucro médio locação", moeda(hist["lucro_locacao"].mean()), "Sem venda residual"),
            ("Lucro médio com venda", moeda(hist["lucro_locacao_venda"].mean()), "Com venda posterior"),
            ("Operações críticas", int(((hist["status_locacao"] == "Crítica") | (hist["status_locacao_venda"] == "Crítica")).sum()), "Revisar"),
        ]
        for col, (label, value, help_text) in zip(cols, cards):
            with col:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">{label}</div>
                    <div class="metric-value">{value}</div>
                    <div class="metric-help">{help_text}</div>
                </div>
                """, unsafe_allow_html=True)

        st.markdown('<div class="section-title">Comparativo de lucro</div>', unsafe_allow_html=True)
        chart_df = hist.head(12)[["cliente", "lucro_locacao", "lucro_locacao_venda"]].set_index("cliente")
        st.bar_chart(chart_df)

        st.markdown('<div class="section-title">Últimas simulações</div>', unsafe_allow_html=True)
        view = hist[["data_hora", "cliente", "equipamento", "prazo", "aluguel_mensal", "valor_residual", "lucro_locacao", "margem_locacao", "lucro_locacao_venda", "margem_locacao_venda"]].head(15)
        st.dataframe(
            formatar_df(
                view,
                money_cols=["aluguel_mensal", "valor_residual", "lucro_locacao", "lucro_locacao_venda"],
                percent_cols=["margem_locacao", "margem_locacao_venda"]
            ),
            use_container_width=True,
            hide_index=True
        )

# =========================================================
# CADASTRO
# =========================================================
elif menu == "1 - Cadastro da Operação":
    st.markdown("""
    <div class="hero">
        <h1>Cadastro da Operação</h1>
        <p>O app calcula separadamente: somente locação e locação com venda posterior.</p>
    </div>
    """, unsafe_allow_html=True)

    with st.form("form_operacao"):
        st.markdown('<div class="section-title">Dados comerciais</div>', unsafe_allow_html=True)
        col1, col2, col3 = st.columns(3)
        cliente = col1.text_input("Cliente")
        vendedor = col2.text_input("Vendedor")
        gerente = col3.text_input("Gerente")

        col1, col2, col3 = st.columns(3)
        equipamento = col1.text_input("Equipamento")
        fabricante = col2.text_input("Fabricante / linha")
        data_sim = col3.date_input("Data", value=date.today())

        st.markdown('<div class="section-title">Contrato</div>', unsafe_allow_html=True)
        col1, col2, col3, col4 = st.columns(4)
        valor_aquisicao = col1.number_input("Valor de aquisição (R$)", min_value=0.0, value=400000.0, step=1000.0, format="%.2f")
        prazo = col2.number_input("Prazo da locação (meses)", min_value=1, value=24, step=1)
        aluguel_mensal = col3.number_input("Aluguel mensal (R$)", min_value=0.0, value=18000.0, step=500.0, format="%.2f")
        valor_residual = col4.number_input("Venda final / residual (R$)", min_value=0.0, value=0.0, step=1000.0, format="%.2f")

        col1, col2, col3 = st.columns(3)
        vida_util_anos = col1.number_input("Vida útil para depreciação (anos)", min_value=1.0, value=10.0, step=0.5)
        custo_financeiro_mensal = col2.number_input("Custo financeiro mensal (%)", min_value=0.0, value=1.2, step=0.1)
        margem_desejada = col3.number_input("Margem líquida desejada (%)", min_value=0.0, value=20.0, step=1.0)

        st.markdown('<div class="section-title">Despesas previstas</div>', unsafe_allow_html=True)
        col1, col2, col3, col4 = st.columns(4)
        frete = col1.number_input("Frete (R$)", min_value=0.0, value=0.0, step=100.0, format="%.2f")
        instalacao = col2.number_input("Instalação (R$)", min_value=0.0, value=0.0, step=100.0, format="%.2f")
        seguro = col3.number_input("Seguro total (R$)", min_value=0.0, value=0.0, step=100.0, format="%.2f")
        manutencao = col4.number_input("Manutenção total (R$)", min_value=0.0, value=0.0, step=100.0, format="%.2f")

        col1, col2 = st.columns(2)
        despesas_indiretas = col1.number_input("Despesas indiretas (R$)", min_value=0.0, value=0.0, step=100.0, format="%.2f")
        outras_despesas = col2.number_input("Outras despesas (R$)", min_value=0.0, value=0.0, step=100.0, format="%.2f")

        st.markdown('<div class="section-title">Comissionamento</div>', unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        perc_comissao_vendedor = col1.number_input("Comissão vendedor (%)", min_value=0.0, value=COMISSAO_VENDEDOR_PADRAO, step=0.25)
        perc_comissao_gerente = col2.number_input("Comissão gerente (%)", min_value=0.0, value=COMISSAO_GERENTE_PADRAO, step=0.25)

        st.markdown('<div class="section-title">Impostos</div>', unsafe_allow_html=True)
        col1, col2, col3, col4 = st.columns(4)
        imposto_locacao = col1.number_input("Impostos sobre locação (%)", value=IMPOSTO_LOCACAO_PADRAO, step=0.10, disabled=True)
        pis_cofins_venda = col2.number_input("PIS/COFINS venda (%)", value=PIS_COFINS_VENDA_PADRAO, step=0.10)
        icms_venda = col3.number_input("ICMS venda (%)", value=ICMS_VENDA_PADRAO, step=0.10)
        irpj_ganho = col4.number_input("IRPJ ganho capital (%)", value=IRPJ_GANHO_CAPITAL_PADRAO, step=0.50)

        col1, col2, col3, col4 = st.columns(4)
        csll_ganho = col1.number_input("CSLL ganho capital (%)", value=CSLL_GANHO_CAPITAL_PADRAO, step=0.50)
        cbs = col2.number_input("CBS simulada (%)", value=0.90, step=0.10)
        ibs = col3.number_input("IBS simulada (%)", value=0.10, step=0.10)
        credito_rt = col4.number_input("Crédito estimado IBS/CBS (%)", value=0.00, step=0.50)

        observacoes = st.text_area("Observações", height=80)

        submitted = st.form_submit_button("Calcular", use_container_width=True)

    if submitted:
        p = dict(
            cliente=cliente or "Cliente não informado",
            vendedor=vendedor,
            gerente=gerente,
            equipamento=equipamento or "Equipamento não informado",
            fabricante=fabricante,
            data_sim=str(data_sim),
            valor_aquisicao=valor_aquisicao,
            prazo=int(prazo),
            aluguel_mensal=aluguel_mensal,
            valor_residual=valor_residual,
            vida_util_anos=vida_util_anos,
            custo_financeiro_mensal=custo_financeiro_mensal,
            margem_desejada=margem_desejada,
            frete=frete,
            instalacao=instalacao,
            seguro=seguro,
            manutencao=manutencao,
            despesas_indiretas=despesas_indiretas,
            outras_despesas=outras_despesas,
            perc_comissao_vendedor=perc_comissao_vendedor,
            perc_comissao_gerente=perc_comissao_gerente,
            imposto_locacao=IMPOSTO_LOCACAO_PADRAO,
            pis_cofins_venda=pis_cofins_venda,
            icms_venda=icms_venda,
            irpj_ganho=irpj_ganho,
            csll_ganho=csll_ganho,
            cbs=cbs,
            ibs=ibs,
            credito_rt=credito_rt,
            observacoes=observacoes
        )

        resumo, fluxo_df = calcular_operacao(p)

        st.markdown('<div class="section-title">Resultado — somente locação</div>', unsafe_allow_html=True)
        st.markdown(status_html(resumo["status_locacao"], "Somente locação"), unsafe_allow_html=True)

        c1, c2, c3, c4 = st.columns(4)
        cards = [
            ("Receita locação", moeda(resumo["receita_locacao"]), "Sem venda residual"),
            ("Lucro locação", moeda(resumo["lucro_locacao"]), "Resultado sem venda"),
            ("Margem locação", perc(resumo["margem_locacao"]), "Lucro sobre aluguel"),
            ("Aluguel mínimo", moeda(resumo["aluguel_minimo_locacao"]), "Para margem desejada"),
        ]
        for col, (label, value, help_text) in zip([c1, c2, c3, c4], cards):
            with col:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">{label}</div>
                    <div class="metric-value">{value}</div>
                    <div class="metric-help">{help_text}</div>
                </div>
                """, unsafe_allow_html=True)

        c1, c2, c3, c4 = st.columns(4)
        cards = [
            ("Impostos locação", moeda(resumo["impostos_locacao"]), "14,30% sobre aluguel"),
            ("Comissão total", moeda(resumo["comissao_total"]), "5% vendedor + 0,5% gerente"),
            ("Custo financeiro", moeda(resumo["custo_financeiro"]), "Capital investido"),
            ("Payback locação", meses(resumo["payback_locacao"]), "Retorno sem venda"),
        ]
        for col, (label, value, help_text) in zip([c1, c2, c3, c4], cards):
            with col:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">{label}</div>
                    <div class="metric-value">{value}</div>
                    <div class="metric-help">{help_text}</div>
                </div>
                """, unsafe_allow_html=True)

        st.markdown('<div class="section-title">Resultado — locação + venda posterior</div>', unsafe_allow_html=True)
        st.markdown(status_html(resumo["status_locacao_venda"], "Locação + venda"), unsafe_allow_html=True)

        c1, c2, c3, c4 = st.columns(4)
        cards = [
            ("Receita total", moeda(resumo["receita_total_venda"]), "Locação + venda"),
            ("Lucro total", moeda(resumo["lucro_locacao_venda"]), "Resultado com venda"),
            ("Margem total", perc(resumo["margem_locacao_venda"]), "Lucro sobre receita total"),
            ("Aluguel mínimo", moeda(resumo["aluguel_minimo_locacao_venda"]), "Para margem desejada"),
        ]
        for col, (label, value, help_text) in zip([c1, c2, c3, c4], cards):
            with col:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">{label}</div>
                    <div class="metric-value">{value}</div>
                    <div class="metric-help">{help_text}</div>
                </div>
                """, unsafe_allow_html=True)

        c1, c2, c3, c4 = st.columns(4)
        cards = [
            ("Valor contábil final", moeda(resumo["valor_contabil_final"]), "Após depreciação"),
            ("Ganho de capital", moeda(resumo["ganho_capital"]), "Venda - valor contábil"),
            ("Impostos venda", moeda(resumo["impostos_venda"]), "PIS/COFINS + ICMS"),
            ("Impostos ganho capital", moeda(resumo["impostos_ganho_capital"]), "IRPJ + CSLL"),
        ]
        for col, (label, value, help_text) in zip([c1, c2, c3, c4], cards):
            with col:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">{label}</div>
                    <div class="metric-value">{value}</div>
                    <div class="metric-help">{help_text}</div>
                </div>
                """, unsafe_allow_html=True)

        st.markdown('<div class="section-title">Parecer</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="parecer">{resumo["parecer"]}</div>', unsafe_allow_html=True)

        st.markdown('<div class="section-title">Comparativo de saldo</div>', unsafe_allow_html=True)
        st.line_chart(fluxo_df.set_index("Mês")[["Saldo somente locação", "Saldo locação + venda"]])

        st.markdown('<div class="section-title">Fluxo mensal</div>', unsafe_allow_html=True)
        st.dataframe(
            formatar_df(
                fluxo_df,
                money_cols=[
                    "Fluxo somente locação", "Saldo somente locação", "Venda final",
                    "Impostos venda", "Impostos ganho capital", "Fluxo locação + venda",
                    "Saldo locação + venda"
                ]
            ),
            use_container_width=True,
            hide_index=True
        )

        memorial = pd.DataFrame([
            ["Receita locação", resumo["receita_locacao"]],
            ["Valor de aquisição", valor_aquisicao],
            ["Despesas previstas", resumo["despesas_total"]],
            ["Comissão vendedor", resumo["comissao_vendedor"]],
            ["Comissão gerente", resumo["comissao_gerente"]],
            ["Impostos locação", resumo["impostos_locacao"]],
            ["Custo financeiro", resumo["custo_financeiro"]],
            ["Lucro somente locação", resumo["lucro_locacao"]],
            ["Margem somente locação", resumo["margem_locacao"]],
            ["Payback somente locação", resumo["payback_locacao"]],
            ["Venda final / residual", valor_residual],
            ["Valor contábil final", resumo["valor_contabil_final"]],
            ["Ganho de capital", resumo["ganho_capital"]],
            ["Impostos venda", resumo["impostos_venda"]],
            ["Impostos ganho capital", resumo["impostos_ganho_capital"]],
            ["Lucro locação + venda", resumo["lucro_locacao_venda"]],
            ["Margem locação + venda", resumo["margem_locacao_venda"]],
            ["Payback locação + venda", resumo["payback_locacao_venda"]],
        ], columns=["Indicador", "Valor"])

        money_ind = [
            "Receita locação", "Valor de aquisição", "Despesas previstas", "Comissão vendedor",
            "Comissão gerente", "Impostos locação", "Custo financeiro", "Lucro somente locação",
            "Venda final / residual", "Valor contábil final", "Ganho de capital", "Impostos venda",
            "Impostos ganho capital", "Lucro locação + venda"
        ]
        perc_ind = ["Margem somente locação", "Margem locação + venda"]
        mes_ind = ["Payback somente locação", "Payback locação + venda"]
        memorial_fmt = memorial.copy()
        memorial_fmt["Valor"] = memorial_fmt.apply(
            lambda row: moeda(row["Valor"]) if row["Indicador"] in money_ind
            else perc(row["Valor"]) if row["Indicador"] in perc_ind
            else meses(row["Valor"]) if row["Indicador"] in mes_ind
            else row["Valor"],
            axis=1
        )

        st.markdown('<div class="section-title">Memorial</div>', unsafe_allow_html=True)
        st.dataframe(memorial_fmt, use_container_width=True, hide_index=True)

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Salvar no histórico", use_container_width=True):
                salvar_simulacao({
                    "data_hora": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                    "cliente": p["cliente"],
                    "equipamento": p["equipamento"],
                    "fabricante": p["fabricante"],
                    "vendedor": p["vendedor"],
                    "gerente": p["gerente"],
                    "valor_aquisicao": p["valor_aquisicao"],
                    "prazo": p["prazo"],
                    "aluguel_mensal": p["aluguel_mensal"],
                    "valor_residual": p["valor_residual"],
                    "lucro_locacao": resumo["lucro_locacao"],
                    "margem_locacao": resumo["margem_locacao"],
                    "lucro_locacao_venda": resumo["lucro_locacao_venda"],
                    "margem_locacao_venda": resumo["margem_locacao_venda"],
                    "ganho_capital": resumo["ganho_capital"],
                    "impostos_locacao": resumo["impostos_locacao"],
                    "impostos_venda": resumo["impostos_venda"],
                    "impostos_ganho_capital": resumo["impostos_ganho_capital"],
                    "status_locacao": resumo["status_locacao"],
                    "status_locacao_venda": resumo["status_locacao_venda"],
                    "parecer": resumo["parecer"]
                })
                st.success("Simulação salva.")
        with col2:
            excel = exportar_excel(p, resumo, fluxo_df)
            st.download_button(
                "Baixar Excel",
                data=excel,
                file_name="relatorio_precificacao_locacao_first.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

# =========================================================
# PRECIFICAÇÃO REVERSA
# =========================================================
elif menu == "2 - Precificação Reversa":
    st.markdown("""
    <div class="hero">
        <h1>Precificação Reversa</h1>
        <p>Calcula o aluguel mínimo para locação pura ou locação com venda posterior.</p>
    </div>
    """, unsafe_allow_html=True)

    tipo = st.radio("Cenário", ["Somente locação", "Locação + venda posterior"], horizontal=True)

    col1, col2, col3 = st.columns(3)
    valor = col1.number_input("Valor do equipamento (R$)", value=400000.0, step=1000.0, format="%.2f")
    prazo = col2.number_input("Prazo (meses)", value=24, step=1)
    residual = col3.number_input("Venda final / residual (R$)", value=0.0 if tipo == "Somente locação" else 180000.0, step=1000.0, format="%.2f")

    col1, col2, col3 = st.columns(3)
    despesas = col1.number_input("Despesas totais (R$)", value=30000.0, step=1000.0, format="%.2f")
    comissao = col2.number_input("Comissão total (%)", value=5.50, step=0.25)
    margem = col3.number_input("Margem desejada (%)", value=20.0, step=1.0)

    col1, col2, col3 = st.columns(3)
    imposto_loc = col1.number_input("Impostos locação (%)", value=IMPOSTO_LOCACAO_PADRAO, disabled=True)
    imposto_venda = col2.number_input("Impostos venda (%)", value=PIS_COFINS_VENDA_PADRAO + ICMS_VENDA_PADRAO, step=0.10)
    imposto_gc = col3.number_input("IRPJ/CSLL ganho capital (%)", value=IRPJ_GANHO_CAPITAL_PADRAO + CSLL_GANHO_CAPITAL_PADRAO, step=0.50)

    custo_fin = st.number_input("Custo financeiro total (R$)", value=80000.0, step=1000.0, format="%.2f")

    if st.button("Calcular aluguel mínimo", use_container_width=True):
        resultado = None
        for aluguel in np.arange(1000, 150000, 100):
            receita_loc = aluguel * prazo
            receita_total = receita_loc + (residual if tipo == "Locação + venda posterior" else 0)
            trib_loc = receita_loc * IMPOSTO_LOCACAO_PADRAO / 100
            trib_venda = residual * imposto_venda / 100 if tipo == "Locação + venda posterior" else 0
            # Simplificação: ganho de capital estimado como residual menos valor depreciado padrão 10 anos.
            valor_contabil = max(valor - (valor / (10 * 12) * prazo), 0)
            ganho = max(residual - valor_contabil, 0)
            trib_gc = ganho * imposto_gc / 100 if tipo == "Locação + venda posterior" else 0
            com = receita_loc * comissao / 100
            lucro = receita_total - valor - despesas - trib_loc - trib_venda - trib_gc - com - custo_fin
            margem_calc = lucro / receita_total * 100 if receita_total else 0
            if margem_calc >= margem:
                resultado = (aluguel, receita_total, lucro, margem_calc)
                break

        if resultado:
            aluguel, receita_total, lucro, margem_calc = resultado
            c1, c2, c3, c4 = st.columns(4)
            cards = [
                ("Aluguel mínimo", moeda(aluguel), "Valor mensal sugerido"),
                ("Receita total", moeda(receita_total), "Conforme cenário"),
                ("Lucro estimado", moeda(lucro), "Resultado gerencial"),
                ("Margem estimada", perc(margem_calc), "Margem atingida"),
            ]
            for col, (label, value, help_text) in zip([c1, c2, c3, c4], cards):
                with col:
                    st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-label">{label}</div>
                        <div class="metric-value">{value}</div>
                        <div class="metric-help">{help_text}</div>
                    </div>
                    """, unsafe_allow_html=True)
        else:
            st.error("Não foi possível atingir a margem desejada.")

# =========================================================
# PARÂMETROS
# =========================================================
elif menu == "3 - Parâmetros":
    st.markdown("""
    <div class="hero">
        <h1>Parâmetros</h1>
        <p>Premissas padrão usadas no app.</p>
    </div>
    """, unsafe_allow_html=True)

    df = pd.DataFrame([
        ["Regime", "Lucro Presumido"],
        ["ISS", "Não considerado"],
        ["Impostos sobre locação", "14,30%"],
        ["PIS/COFINS venda", "3,65%"],
        ["ICMS venda", "18,00%"],
        ["IRPJ ganho de capital", "15,00%"],
        ["CSLL ganho de capital", "9,00%"],
        ["Comissão vendedor", "5,00%"],
        ["Comissão gerente", "0,50%"],
        ["CBS padrão", "0,90%"],
        ["IBS padrão", "0,10%"],
    ], columns=["Parâmetro", "Valor"])
    st.dataframe(df, use_container_width=True, hide_index=True)

# =========================================================
# HISTÓRICO
# =========================================================
elif menu == "4 - Histórico":
    st.markdown("""
    <div class="hero">
        <h1>Histórico</h1>
        <p>Simulações salvas neste app.</p>
    </div>
    """, unsafe_allow_html=True)

    hist = carregar_historico()
    if hist.empty:
        st.info("Nenhuma simulação salva.")
    else:
        st.dataframe(
            formatar_df(
                hist,
                money_cols=[
                    "valor_aquisicao", "aluguel_mensal", "valor_residual",
                    "lucro_locacao", "lucro_locacao_venda", "ganho_capital",
                    "impostos_locacao", "impostos_venda", "impostos_ganho_capital"
                ],
                percent_cols=["margem_locacao", "margem_locacao_venda"]
            ),
            use_container_width=True,
            hide_index=True
        )

        csv = hist.to_csv(index=False).encode("utf-8-sig")
        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                "Exportar CSV",
                data=csv,
                file_name="historico_precificacao_locacao.csv",
                mime="text/csv",
                use_container_width=True
            )
        with col2:
            senha = st.text_input("Senha para limpar histórico", type="password")
            if st.button("Limpar histórico", use_container_width=True):
                if senha == "first2026":
                    limpar_historico()
                    st.success("Histórico limpo.")
                else:
                    st.error("Senha inválida.")
