
import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
from datetime import date, datetime
from io import BytesIO
import re

# ======================================================
# CONFIGURAÇÃO
# ======================================================
st.set_page_config(
    page_title="First Medical | Precificação de Locação",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_PATH = "simulacoes_locacao_first.db"

IMPOSTO_LOCACAO_PADRAO = 14.30
IRPJ_GANHO_CAPITAL_PADRAO = 15.00
CSLL_GANHO_CAPITAL_PADRAO = 9.00
COMISSAO_VENDEDOR_PADRAO = 5.00
COMISSAO_GERENTE_PADRAO = 0.50
VIDA_UTIL_PADRAO = 10.0

# ======================================================
# BANCO DE DADOS
# ======================================================
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
            valor_venda_estimado REAL,
            valor_contabil_final REAL,
            percentual_depreciado REAL,
            ganho_capital REAL,
            lucro_locacao REAL,
            margem_locacao REAL,
            lucro_locacao_venda REAL,
            margem_locacao_venda REAL,
            impostos_locacao REAL,
            impostos_ganho_capital REAL,
            payback_locacao REAL,
            payback_locacao_venda REAL,
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

# ======================================================
# FORMATAÇÃO
# ======================================================
def parse_moeda(txt):
    if txt is None:
        return 0.0
    s = str(txt).strip()
    s = s.replace("R$", "").replace(" ", "")
    s = re.sub(r"[^0-9,.-]", "", s)
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return 0.0

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

def input_moeda(label, value=0.0, key=None):
    texto = st.text_input(label, value=moeda(value), key=key)
    valor = parse_moeda(texto)
    st.caption(f"Valor considerado: {moeda(valor)}")
    return valor

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

# ======================================================
# ESTILO PREMIUM
# ======================================================
st.markdown("""
<style>
    .stApp { background: linear-gradient(180deg, #F5F8FC 0%, #EEF3F8 100%); }
    .block-container { padding-top: 1.1rem; padding-bottom: 2.5rem; }

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
        min-height: 120px;
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
        font-size: 1.34rem;
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

# ======================================================
# CÁLCULOS
# ======================================================
def estimar_venda(valor_aquisicao, prazo, vida_util_anos, fator_mercado):
    vida_meses = vida_util_anos * 12
    percentual_depreciado = min(prazo / vida_meses, 1) * 100
    valor_contabil = max(valor_aquisicao * (1 - percentual_depreciado / 100), 0)

    valor_base = valor_contabil
    if percentual_depreciado >= 100:
        valor_base = valor_aquisicao * 0.10

    valor_venda = valor_base * (fator_mercado / 100)
    return valor_contabil, valor_venda, percentual_depreciado

def classificar(margem, lucro, payback, prazo):
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

def calcular_payback(saida, fluxo_mensal):
    if fluxo_mensal <= 0:
        return 999
    return saida / fluxo_mensal

def calcular_operacao(p, interno=False):
    receita_locacao = p["aluguel_mensal"] * p["prazo"]
    despesas_total = (
        p["frete"] + p["instalacao"] + p["treinamento"] + p["adequacoes"]
        + p["seguro"] + p["manutencao"] + p["assistencia"] + p["outros_custos"]
    )

    valor_contabil_final, valor_venda_estimado, percentual_depreciado = estimar_venda(
        p["valor_aquisicao"], p["prazo"], p["vida_util_anos"], p["fator_mercado"]
    )

    if p["usar_venda_manual"]:
        valor_venda_estimado = p["valor_venda_manual"]

    ganho_capital = valor_venda_estimado - valor_contabil_final
    impostos_ganho_capital = max(ganho_capital, 0) * (p["irpj_ganho"] + p["csll_ganho"]) / 100

    comissao_vendedor = receita_locacao * p["comissao_vendedor"] / 100
    comissao_gerente = receita_locacao * p["comissao_gerente"] / 100
    comissao_total = comissao_vendedor + comissao_gerente

    impostos_locacao = receita_locacao * p["imposto_locacao"] / 100
    custo_financeiro = p["valor_aquisicao"] * (p["custo_financeiro_mensal"] / 100) * p["prazo"]

    lucro_locacao = (
        receita_locacao
        - p["valor_aquisicao"]
        - despesas_total
        - comissao_total
        - impostos_locacao
        - custo_financeiro
    )
    margem_locacao = lucro_locacao / receita_locacao * 100 if receita_locacao else 0

    fluxo_mensal_locacao = (
        p["aluguel_mensal"]
        - impostos_locacao / p["prazo"]
        - despesas_total / p["prazo"]
        - comissao_total / p["prazo"]
        - custo_financeiro / p["prazo"]
    )

    saida_inicial = p["valor_aquisicao"] + p["frete"] + p["instalacao"] + p["treinamento"] + p["adequacoes"]
    payback_locacao = calcular_payback(saida_inicial, fluxo_mensal_locacao)

    receita_total_com_venda = receita_locacao + valor_venda_estimado
    lucro_locacao_venda = (
        receita_total_com_venda
        - p["valor_aquisicao"]
        - despesas_total
        - comissao_total
        - impostos_locacao
        - impostos_ganho_capital
        - custo_financeiro
    )
    margem_locacao_venda = lucro_locacao_venda / receita_total_com_venda * 100 if receita_total_com_venda else 0

    saldo = -saida_inicial
    payback_venda = 999
    for mes in range(1, p["prazo"] + 1):
        saldo += fluxo_mensal_locacao
        if mes == p["prazo"]:
            saldo += valor_venda_estimado - impostos_ganho_capital
        if saldo >= 0:
            payback_venda = mes
            break

    status_locacao = classificar(margem_locacao, lucro_locacao, payback_locacao, p["prazo"])
    status_venda = classificar(margem_locacao_venda, lucro_locacao_venda, payback_venda, p["prazo"])

    aluguel_min_locacao = 0
    aluguel_min_venda = 0
    if not interno:
        for aluguel in np.arange(1000, 200000, 100):
            pp = p.copy()
            pp["aluguel_mensal"] = float(aluguel)
            r, _ = calcular_operacao(pp, interno=True)
            if aluguel_min_locacao == 0 and r["margem_locacao"] >= p["margem_desejada"]:
                aluguel_min_locacao = float(aluguel)
            if aluguel_min_venda == 0 and r["margem_locacao_venda"] >= p["margem_desejada"]:
                aluguel_min_venda = float(aluguel)
            if aluguel_min_locacao and aluguel_min_venda:
                break

    fluxo = []
    saldo_loc = -saida_inicial
    saldo_venda = -saida_inicial
    for mes in range(1, p["prazo"] + 1):
        venda_mes = valor_venda_estimado if mes == p["prazo"] else 0
        imposto_gc_mes = impostos_ganho_capital if mes == p["prazo"] else 0
        fluxo_loc = fluxo_mensal_locacao
        fluxo_venda = fluxo_mensal_locacao + venda_mes - imposto_gc_mes
        saldo_loc += fluxo_loc
        saldo_venda += fluxo_venda
        fluxo.append({
            "Mês": mes,
            "Fluxo somente locação": fluxo_loc,
            "Saldo somente locação": saldo_loc,
            "Venda estimada": venda_mes,
            "Imposto ganho capital": imposto_gc_mes,
            "Fluxo locação + venda": fluxo_venda,
            "Saldo locação + venda": saldo_venda,
        })

    parecer = (
        f"Somente locação: {status_locacao.lower()}, margem {perc(margem_locacao)} e payback {meses(payback_locacao)}. "
        f"Locação com venda posterior: {status_venda.lower()}, margem {perc(margem_locacao_venda)} e payback {meses(payback_venda)}. "
        f"Ao final do contrato, o ativo estará {perc(percentual_depreciado)} depreciado, com valor contábil estimado de {moeda(valor_contabil_final)}. "
        f"O valor de venda estimado é {moeda(valor_venda_estimado)} e o ganho de capital estimado é {moeda(ganho_capital)}."
    )

    resumo = {
        "receita_locacao": receita_locacao,
        "despesas_total": despesas_total,
        "valor_contabil_final": valor_contabil_final,
        "valor_venda_estimado": valor_venda_estimado,
        "percentual_depreciado": percentual_depreciado,
        "ganho_capital": ganho_capital,
        "impostos_ganho_capital": impostos_ganho_capital,
        "comissao_vendedor": comissao_vendedor,
        "comissao_gerente": comissao_gerente,
        "comissao_total": comissao_total,
        "impostos_locacao": impostos_locacao,
        "custo_financeiro": custo_financeiro,
        "lucro_locacao": lucro_locacao,
        "margem_locacao": margem_locacao,
        "payback_locacao": payback_locacao,
        "lucro_locacao_venda": lucro_locacao_venda,
        "margem_locacao_venda": margem_locacao_venda,
        "payback_locacao_venda": payback_venda,
        "status_locacao": status_locacao,
        "status_locacao_venda": status_venda,
        "aluguel_minimo_locacao": aluguel_min_locacao,
        "aluguel_minimo_venda": aluguel_min_venda,
        "parecer": parecer,
    }

    return resumo, pd.DataFrame(fluxo)

def gerar_estrategia(p):
    linhas = []
    for prazo in [24, 36, 48, 60, 72, 84, 96, 120]:
        pp = p.copy()
        pp["prazo"] = prazo
        r, _ = calcular_operacao(pp, interno=True)
        linhas.append({
            "Prazo": prazo,
            "Depreciação": r["percentual_depreciado"],
            "Valor contábil": r["valor_contabil_final"],
            "Venda estimada": r["valor_venda_estimado"],
            "Ganho de capital": r["ganho_capital"],
            "Imposto ganho capital": r["impostos_ganho_capital"],
            "Lucro total": r["lucro_locacao_venda"],
            "Margem total": r["margem_locacao_venda"],
        })
    return pd.DataFrame(linhas)

def exportar_excel(p, resumo, fluxo_df, estrategia_df):
    output = BytesIO()
    premissas = pd.DataFrame([p])
    memorial = pd.DataFrame([
        ["Receita locação", resumo["receita_locacao"]],
        ["Valor aquisição", p["valor_aquisicao"]],
        ["Despesas previstas", resumo["despesas_total"]],
        ["Comissão vendedor", resumo["comissao_vendedor"]],
        ["Comissão gerente", resumo["comissao_gerente"]],
        ["Impostos locação", resumo["impostos_locacao"]],
        ["Custo financeiro", resumo["custo_financeiro"]],
        ["Lucro somente locação", resumo["lucro_locacao"]],
        ["Margem somente locação", resumo["margem_locacao"]],
        ["Payback somente locação", resumo["payback_locacao"]],
        ["Depreciação", resumo["percentual_depreciado"]],
        ["Valor contábil final", resumo["valor_contabil_final"]],
        ["Venda estimada", resumo["valor_venda_estimado"]],
        ["Ganho de capital", resumo["ganho_capital"]],
        ["Imposto ganho capital", resumo["impostos_ganho_capital"]],
        ["Lucro locação + venda", resumo["lucro_locacao_venda"]],
        ["Margem locação + venda", resumo["margem_locacao_venda"]],
        ["Payback locação + venda", resumo["payback_locacao_venda"]],
        ["Parecer", resumo["parecer"]],
    ], columns=["Indicador", "Valor"])

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        premissas.to_excel(writer, index=False, sheet_name="Premissas")
        memorial.to_excel(writer, index=False, sheet_name="Memorial")
        fluxo_df.to_excel(writer, index=False, sheet_name="Fluxo")
        estrategia_df.to_excel(writer, index=False, sheet_name="Desmobilizacao")
    output.seek(0)
    return output

# ======================================================
# MENU
# ======================================================
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
st.sidebar.caption("Locação | Venda posterior | Ganho de capital")

# ======================================================
# VISÃO EXECUTIVA
# ======================================================
if menu == "Visão Executiva":
    st.markdown("""
    <div class="hero">
        <h1>Precificação de Locação</h1>
        <p>Locação pura, locação com venda posterior e estratégia de desmobilização.</p>
    </div>
    """, unsafe_allow_html=True)

    hist = carregar_historico()

    if hist.empty:
        cols = st.columns(4)
        cards = [
            ("Simulações", "0", "Histórico vazio"),
            ("Lucro médio locação", moeda(0), "Sem dados"),
            ("Lucro médio com venda", moeda(0), "Sem dados"),
            ("Ganho médio", moeda(0), "Sem dados"),
        ]
    else:
        cols = st.columns(4)
        cards = [
            ("Simulações", len(hist), "Operações salvas"),
            ("Lucro médio locação", moeda(hist["lucro_locacao"].mean()), "Sem venda"),
            ("Lucro médio com venda", moeda(hist["lucro_locacao_venda"].mean()), "Com venda"),
            ("Ganho médio", moeda(hist["ganho_capital"].mean()), "Ganho de capital"),
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

    if not hist.empty:
        st.markdown('<div class="section-title">Comparativo de lucro</div>', unsafe_allow_html=True)
        st.bar_chart(hist.head(12)[["cliente", "lucro_locacao", "lucro_locacao_venda"]].set_index("cliente"))

        st.markdown('<div class="section-title">Últimas simulações</div>', unsafe_allow_html=True)
        view = hist[["data_hora", "cliente", "equipamento", "prazo", "aluguel_mensal", "valor_venda_estimado", "lucro_locacao", "margem_locacao", "lucro_locacao_venda", "margem_locacao_venda"]].head(15)
        st.dataframe(
            formatar_df(
                view,
                money_cols=["aluguel_mensal", "valor_venda_estimado", "lucro_locacao", "lucro_locacao_venda"],
                percent_cols=["margem_locacao", "margem_locacao_venda"]
            ),
            use_container_width=True,
            hide_index=True
        )

# ======================================================
# CADASTRO
# ======================================================
elif menu == "1 - Cadastro da Operação":
    st.markdown("""
    <div class="hero">
        <h1>Cadastro da Operação</h1>
        <p>Preencha as premissas e calcule os dois cenários automaticamente.</p>
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

        st.markdown('<div class="section-title">Contrato e ativo</div>', unsafe_allow_html=True)
        col1, col2, col3 = st.columns(3)
        with col1:
            valor_aquisicao = input_moeda("Valor de aquisição", 400000.0, "valor_aquisicao")
        with col2:
            prazo = st.number_input("Prazo da locação (meses)", min_value=1, value=24, step=1)
        with col3:
            aluguel_mensal = input_moeda("Aluguel mensal", 18000.0, "aluguel_mensal")

        col1, col2, col3 = st.columns(3)
        vida_util_anos = col1.number_input("Vida útil para depreciação (anos)", min_value=1.0, value=VIDA_UTIL_PADRAO, step=0.5)
        custo_financeiro_mensal = col2.number_input("Custo financeiro mensal (%)", min_value=0.0, value=1.2, step=0.1)
        margem_desejada = col3.number_input("Margem líquida desejada (%)", min_value=0.0, value=20.0, step=1.0)

        st.markdown('<div class="section-title">Venda posterior</div>', unsafe_allow_html=True)
        col1, col2, col3 = st.columns(3)
        fator_mercado = col1.number_input("Fator de mercado sobre valor contábil (%)", min_value=0.0, value=100.0, step=5.0)
        usar_venda_manual = col2.checkbox("Informar venda manualmente", value=False)
        with col3:
            valor_venda_manual = input_moeda("Venda manual", 0.0, "valor_venda_manual")

        st.markdown('<div class="section-title">Custos iniciais</div>', unsafe_allow_html=True)
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            frete = input_moeda("Frete", 0.0, "frete")
        with col2:
            instalacao = input_moeda("Instalação", 0.0, "instalacao")
        with col3:
            treinamento = input_moeda("Treinamento", 0.0, "treinamento")
        with col4:
            adequacoes = input_moeda("Adequações", 0.0, "adequacoes")

        st.markdown('<div class="section-title">Custos recorrentes e outros</div>', unsafe_allow_html=True)
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            seguro = input_moeda("Seguro total", 0.0, "seguro")
        with col2:
            manutencao = input_moeda("Manutenção total", 0.0, "manutencao")
        with col3:
            assistencia = input_moeda("Assistência técnica", 0.0, "assistencia")
        with col4:
            outros_custos = input_moeda("Outros custos", 0.0, "outros_custos")

        st.markdown('<div class="section-title">Comissões e impostos</div>', unsafe_allow_html=True)
        col1, col2, col3, col4, col5 = st.columns(5)
        comissao_vendedor = col1.number_input("Comissão vendedor (%)", min_value=0.0, value=COMISSAO_VENDEDOR_PADRAO, step=0.25)
        comissao_gerente = col2.number_input("Comissão gerente (%)", min_value=0.0, value=COMISSAO_GERENTE_PADRAO, step=0.25)
        imposto_locacao = col3.number_input("Imposto locação (%)", value=IMPOSTO_LOCACAO_PADRAO, step=0.10, disabled=True)
        irpj_ganho = col4.number_input("IRPJ ganho capital (%)", value=IRPJ_GANHO_CAPITAL_PADRAO, step=0.50)
        csll_ganho = col5.number_input("CSLL ganho capital (%)", value=CSLL_GANHO_CAPITAL_PADRAO, step=0.50)

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
            vida_util_anos=vida_util_anos,
            custo_financeiro_mensal=custo_financeiro_mensal,
            margem_desejada=margem_desejada,
            fator_mercado=fator_mercado,
            usar_venda_manual=usar_venda_manual,
            valor_venda_manual=valor_venda_manual,
            frete=frete,
            instalacao=instalacao,
            treinamento=treinamento,
            adequacoes=adequacoes,
            seguro=seguro,
            manutencao=manutencao,
            assistencia=assistencia,
            outros_custos=outros_custos,
            comissao_vendedor=comissao_vendedor,
            comissao_gerente=comissao_gerente,
            imposto_locacao=IMPOSTO_LOCACAO_PADRAO,
            irpj_ganho=irpj_ganho,
            csll_ganho=csll_ganho,
            observacoes=observacoes
        )

        resumo, fluxo_df = calcular_operacao(p)
        estrategia_df = gerar_estrategia(p)

        st.markdown('<div class="section-title">Resultado — somente locação</div>', unsafe_allow_html=True)
        st.markdown(status_html(resumo["status_locacao"], "Somente locação"), unsafe_allow_html=True)
        cols = st.columns(4)
        cards = [
            ("Receita locação", moeda(resumo["receita_locacao"]), "Receita do contrato"),
            ("Lucro locação", moeda(resumo["lucro_locacao"]), "Sem venda posterior"),
            ("Margem locação", perc(resumo["margem_locacao"]), "Lucro sobre aluguel"),
            ("Payback locação", meses(resumo["payback_locacao"]), "Retorno sem venda"),
        ]
        for col, (label, value, help_text) in zip(cols, cards):
            with col:
                st.markdown(f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value">{value}</div><div class="metric-help">{help_text}</div></div>', unsafe_allow_html=True)

        st.markdown('<div class="section-title">Resultado — locação + venda posterior</div>', unsafe_allow_html=True)
        st.markdown(status_html(resumo["status_locacao_venda"], "Locação + venda"), unsafe_allow_html=True)
        cols = st.columns(4)
        cards = [
            ("Venda estimada", moeda(resumo["valor_venda_estimado"]), "Pelo prazo e depreciação"),
            ("Lucro total", moeda(resumo["lucro_locacao_venda"]), "Locação + venda"),
            ("Margem total", perc(resumo["margem_locacao_venda"]), "Lucro sobre receita total"),
            ("Payback total", meses(resumo["payback_locacao_venda"]), "Com venda posterior"),
        ]
        for col, (label, value, help_text) in zip(cols, cards):
            with col:
                st.markdown(f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value">{value}</div><div class="metric-help">{help_text}</div></div>', unsafe_allow_html=True)

        cols = st.columns(4)
        cards = [
            ("Depreciação", perc(resumo["percentual_depreciado"]), "Ao final do prazo"),
            ("Valor contábil", moeda(resumo["valor_contabil_final"]), "Valor líquido contábil"),
            ("Ganho de capital", moeda(resumo["ganho_capital"]), "Venda - valor contábil"),
            ("Imposto ganho capital", moeda(resumo["impostos_ganho_capital"]), "IRPJ + CSLL"),
        ]
        for col, (label, value, help_text) in zip(cols, cards):
            with col:
                st.markdown(f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value">{value}</div><div class="metric-help">{help_text}</div></div>', unsafe_allow_html=True)

        st.markdown('<div class="section-title">Parecer</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="parecer">{resumo["parecer"]}</div>', unsafe_allow_html=True)

        st.markdown('<div class="section-title">Comparativo de saldo</div>', unsafe_allow_html=True)
        st.line_chart(fluxo_df.set_index("Mês")[["Saldo somente locação", "Saldo locação + venda"]])

        st.markdown('<div class="section-title">Estratégia de desmobilização</div>', unsafe_allow_html=True)
        st.dataframe(
            formatar_df(
                estrategia_df,
                money_cols=["Valor contábil", "Venda estimada", "Ganho de capital", "Imposto ganho capital", "Lucro total"],
                percent_cols=["Depreciação", "Margem total"]
            ),
            use_container_width=True,
            hide_index=True
        )

        st.markdown('<div class="section-title">Fluxo mensal</div>', unsafe_allow_html=True)
        st.dataframe(
            formatar_df(
                fluxo_df,
                money_cols=[
                    "Fluxo somente locação", "Saldo somente locação", "Venda estimada",
                    "Imposto ganho capital", "Fluxo locação + venda", "Saldo locação + venda"
                ]
            ),
            use_container_width=True,
            hide_index=True
        )

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
                    "valor_venda_estimado": resumo["valor_venda_estimado"],
                    "valor_contabil_final": resumo["valor_contabil_final"],
                    "percentual_depreciado": resumo["percentual_depreciado"],
                    "ganho_capital": resumo["ganho_capital"],
                    "lucro_locacao": resumo["lucro_locacao"],
                    "margem_locacao": resumo["margem_locacao"],
                    "lucro_locacao_venda": resumo["lucro_locacao_venda"],
                    "margem_locacao_venda": resumo["margem_locacao_venda"],
                    "impostos_locacao": resumo["impostos_locacao"],
                    "impostos_ganho_capital": resumo["impostos_ganho_capital"],
                    "payback_locacao": resumo["payback_locacao"],
                    "payback_locacao_venda": resumo["payback_locacao_venda"],
                    "status_locacao": resumo["status_locacao"],
                    "status_locacao_venda": resumo["status_locacao_venda"],
                    "parecer": resumo["parecer"]
                })
                st.success("Simulação salva.")
        with col2:
            excel = exportar_excel(p, resumo, fluxo_df, estrategia_df)
            st.download_button(
                "Baixar Excel",
                data=excel,
                file_name="relatorio_precificacao_locacao_first.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

# ======================================================
# PRECIFICAÇÃO REVERSA
# ======================================================
elif menu == "2 - Precificação Reversa":
    st.markdown("""
    <div class="hero">
        <h1>Precificação Reversa</h1>
        <p>Calcula o aluguel mínimo para atingir a margem desejada.</p>
    </div>
    """, unsafe_allow_html=True)

    tipo = st.radio("Cenário", ["Somente locação", "Locação + venda posterior"], horizontal=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        valor = input_moeda("Valor do equipamento", 400000.0, "rev_valor")
    with col2:
        prazo = st.number_input("Prazo (meses)", value=24, step=1)
    with col3:
        margem = st.number_input("Margem desejada (%)", value=20.0, step=1.0)

    col1, col2, col3 = st.columns(3)
    vida = col1.number_input("Vida útil (anos)", value=VIDA_UTIL_PADRAO, step=0.5)
    fator = col2.number_input("Fator de mercado (%)", value=100.0, step=5.0)
    custo_fin_mensal = col3.number_input("Custo financeiro mensal (%)", value=1.2, step=0.1)

    col1, col2 = st.columns(2)
    with col1:
        despesas = input_moeda("Despesas totais", 30000.0, "rev_desp")
    with col2:
        venda_manual = input_moeda("Venda manual opcional", 0.0, "rev_venda")

    if st.button("Calcular aluguel mínimo", use_container_width=True):
        resultado = None
        valor_contabil, venda_estimada, _ = estimar_venda(valor, prazo, vida, fator)
        if venda_manual > 0:
            venda_estimada = venda_manual
        if tipo == "Somente locação":
            venda_estimada = 0.0

        ganho = max(venda_estimada - valor_contabil, 0)
        imposto_gc = ganho * (IRPJ_GANHO_CAPITAL_PADRAO + CSLL_GANHO_CAPITAL_PADRAO) / 100
        custo_fin = valor * (custo_fin_mensal / 100) * prazo

        for aluguel in np.arange(1000, 200000, 100):
            receita_loc = aluguel * prazo
            receita_total = receita_loc + venda_estimada
            imposto_loc = receita_loc * IMPOSTO_LOCACAO_PADRAO / 100
            comissao = receita_loc * (COMISSAO_VENDEDOR_PADRAO + COMISSAO_GERENTE_PADRAO) / 100
            lucro = receita_total - valor - despesas - imposto_loc - comissao - custo_fin - imposto_gc
            margem_calc = lucro / receita_total * 100 if receita_total else 0
            if margem_calc >= margem:
                resultado = (aluguel, receita_total, lucro, margem_calc, venda_estimada, imposto_gc)
                break

        if resultado:
            aluguel, receita_total, lucro, margem_calc, venda_estimada, imposto_gc = resultado
            cols = st.columns(4)
            cards = [
                ("Aluguel mínimo", moeda(aluguel), "Valor mensal sugerido"),
                ("Receita total", moeda(receita_total), "Conforme cenário"),
                ("Lucro estimado", moeda(lucro), "Resultado gerencial"),
                ("Margem estimada", perc(margem_calc), "Margem atingida"),
            ]
            for col, (label, value, help_text) in zip(cols, cards):
                with col:
                    st.markdown(f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value">{value}</div><div class="metric-help">{help_text}</div></div>', unsafe_allow_html=True)
            st.info(f"Venda considerada: {moeda(venda_estimada)} | Imposto sobre ganho de capital: {moeda(imposto_gc)}")
        else:
            st.error("Não foi possível atingir a margem desejada.")

# ======================================================
# PARÂMETROS
# ======================================================
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
        ["Vida útil padrão", "10 anos"],
        ["Impostos sobre locação", "14,30%"],
        ["Tributação da venda do ativo", "Ganho de capital"],
        ["IRPJ ganho de capital", "15,00%"],
        ["CSLL ganho de capital", "9,00%"],
        ["Comissão vendedor", "5,00%"],
        ["Comissão gerente", "0,50%"],
        ["Valor de venda", "Estimado por prazo/depreciação, com opção manual"],
    ], columns=["Parâmetro", "Valor"])
    st.dataframe(df, use_container_width=True, hide_index=True)

# ======================================================
# HISTÓRICO
# ======================================================
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
                    "valor_aquisicao", "aluguel_mensal", "valor_venda_estimado",
                    "valor_contabil_final", "ganho_capital", "lucro_locacao",
                    "lucro_locacao_venda", "impostos_locacao", "impostos_ganho_capital"
                ],
                percent_cols=["percentual_depreciado", "margem_locacao", "margem_locacao_venda"],
                month_cols=["payback_locacao", "payback_locacao_venda"]
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
