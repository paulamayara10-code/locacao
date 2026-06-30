
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
IMPOSTO_ATUAL_PADRAO = 14.30
IMPOSTO_VENDA_PADRAO = 14.30

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
            receita_total REAL,
            despesas_total REAL,
            comissao_total REAL,
            valor_contabil_final REAL,
            ganho_capital REAL,
            tributos_atuais REAL,
            tributos_venda REAL,
            tributos_reforma REAL,
            custo_financeiro REAL,
            lucro_liquido REAL,
            margem_liquida REAL,
            roi REAL,
            payback REAL,
            aluguel_minimo REAL,
            status TEXT,
            parecer TEXT
        )
    """)
    conn.commit()

    try:
        conn.execute("ALTER TABLE simulacoes ADD COLUMN tributos_venda REAL DEFAULT 0")
        conn.commit()
    except Exception:
        pass
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
        font-size: 1.48rem;
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
def classificar_status(margem_liquida, payback, prazo, lucro_liquido):
    if lucro_liquido < 0 or margem_liquida < 8:
        return "Crítica"
    if margem_liquida < 18 or payback > prazo:
        return "Atenção"
    return "Saudável"

def status_html(status):
    if status == "Saudável":
        return '<span class="pill-good">🟢 Operação saudável</span>'
    if status == "Atenção":
        return '<span class="pill-warn">🟡 Revisar operação</span>'
    return '<span class="pill-bad">🔴 Operação crítica</span>'

def gerar_parecer(status, margem, payback, prazo, ganho_capital, lucro, aluguel, aluguel_minimo, tributos_atual, tributos_reforma):
    if status == "Saudável":
        texto = (
            f"Operação recomendada nas premissas informadas. A margem líquida estimada é de {perc(margem)} "
            f"e o investimento retorna em aproximadamente {meses(payback)}, dentro do prazo contratual de {prazo} meses."
        )
    elif status == "Atenção":
        texto = (
            f"Operação exige revisão antes da aprovação. A margem líquida estimada é de {perc(margem)} "
            f"e o payback ficou em {meses(payback)} para um contrato de {prazo} meses."
        )
    else:
        texto = (
            f"Operação não recomendada nas premissas atuais. O lucro líquido estimado é {moeda(lucro)} "
            f"e a margem líquida ficou em {perc(margem)}."
        )

    if aluguel_minimo > 0 and aluguel < aluguel_minimo:
        texto += f" O aluguel informado está abaixo do mínimo sugerido de {moeda(aluguel_minimo)}."
    elif aluguel_minimo > 0:
        texto += f" O aluguel informado está acima do mínimo sugerido de {moeda(aluguel_minimo)}."

    if ganho_capital > 0:
        texto += f" A venda final gera ganho de capital estimado de {moeda(ganho_capital)}."

    texto += f" Impostos atuais considerados: {moeda(tributos_atual)}. IBS/CBS simulado: {moeda(tributos_reforma)}."

    return texto

def calcular_operacao(p):
    receita_locacao = p["aluguel_mensal"] * p["prazo"]
    receita_total = receita_locacao + p["valor_residual"]

    despesas_total = (
        p["frete"] + p["instalacao"] + p["seguro"] + p["manutencao"] +
        p["despesas_indiretas"] + p["outras_despesas"]
    )

    depreciacao_mensal = p["valor_aquisicao"] / (p["vida_util_anos"] * 12)
    depreciacao_acumulada = min(depreciacao_mensal * p["prazo"], p["valor_aquisicao"])
    valor_contabil_final = max(p["valor_aquisicao"] - depreciacao_acumulada, 0)
    ganho_capital = p["valor_residual"] - valor_contabil_final

    base_comissao = receita_locacao if p["base_comissao"] == "Receita de locação" else receita_total
    comissao_vendedor = base_comissao * p["perc_comissao_vendedor"] / 100
    comissao_gerente = base_comissao * p["perc_comissao_gerente"] / 100
    comissao_total = comissao_vendedor + comissao_gerente

    tributos_locacao = receita_locacao * p["imposto_atual"] / 100
    tributos_venda = p["valor_residual"] * p["imposto_venda"] / 100 if p["considerar_venda"] else 0
    tributos_atuais = tributos_locacao + tributos_venda

    rt_bruto = receita_total * (p["cbs"] + p["ibs"]) / 100
    rt_credito = rt_bruto * p["credito_rt"] / 100
    tributos_reforma = max(rt_bruto - rt_credito, 0)

    custo_financeiro = p["valor_aquisicao"] * (p["custo_financeiro_mensal"] / 100) * p["prazo"]

    lucro_liquido = receita_total - p["valor_aquisicao"] - despesas_total - comissao_total - tributos_atuais - custo_financeiro
    margem_liquida = (lucro_liquido / receita_total * 100) if receita_total else 0
    roi = (lucro_liquido / p["valor_aquisicao"] * 100) if p["valor_aquisicao"] else 0

    saida_inicial = p["valor_aquisicao"] + p["frete"] + p["instalacao"]
    entrada_mensal_aprox = (
        p["aluguel_mensal"]
        - (tributos_atuais / p["prazo"])
        - ((p["seguro"] + p["manutencao"] + p["despesas_indiretas"] + p["outras_despesas"]) / p["prazo"])
        - (comissao_total / p["prazo"])
        - (custo_financeiro / p["prazo"])
    )
    payback = saida_inicial / entrada_mensal_aprox if entrada_mensal_aprox > 0 else 999

    fluxo = []
    saldo = -saida_inicial
    for m in range(1, int(p["prazo"]) + 1):
        receita_mes = p["aluguel_mensal"]
        venda_mes = p["valor_residual"] if m == p["prazo"] else 0
        trib_mes = tributos_locacao / p["prazo"]
        desp_mes = (p["seguro"] + p["manutencao"] + p["despesas_indiretas"] + p["outras_despesas"]) / p["prazo"]
        com_mes = comissao_total / p["prazo"]
        custo_fin_mes = custo_financeiro / p["prazo"]
        trib_venda_mes = tributos_venda if m == p["prazo"] else 0
        fluxo_mes = receita_mes + venda_mes - trib_mes - trib_venda_mes - desp_mes - com_mes - custo_fin_mes
        saldo += fluxo_mes
        fluxo.append({
            "Mês": m,
            "Receita locação": receita_mes,
            "Venda final": venda_mes,
            "Impostos locação": trib_mes,
            "Impostos venda": trib_venda_mes,
            "Despesas": desp_mes,
            "Comissão": com_mes,
            "Custo financeiro": custo_fin_mes,
            "Fluxo líquido": fluxo_mes,
            "Saldo acumulado": saldo
        })

    aluguel_minimo = 0
    for aluguel in np.arange(1000, 150000, 100):
        receita_loc = aluguel * p["prazo"]
        receita_tot = receita_loc + p["valor_residual"]
        base_com = receita_loc if p["base_comissao"] == "Receita de locação" else receita_tot
        com = base_com * (p["perc_comissao_vendedor"] + p["perc_comissao_gerente"]) / 100
        trib = receita_tot * p["imposto_atual"] / 100
        lucro = receita_tot - p["valor_aquisicao"] - despesas_total - com - trib - custo_financeiro
        margem = lucro / receita_tot * 100 if receita_tot else 0
        if margem >= p["margem_desejada"]:
            aluguel_minimo = float(aluguel)
            break

    status = classificar_status(margem_liquida, payback, p["prazo"], lucro_liquido)
    parecer = gerar_parecer(
        status, margem_liquida, payback, p["prazo"], ganho_capital,
        lucro_liquido, p["aluguel_mensal"], aluguel_minimo,
        tributos_atuais, tributos_reforma
    )

    resumo = {
        "receita_locacao": receita_locacao,
        "receita_total": receita_total,
        "despesas_total": despesas_total,
        "depreciacao_acumulada": depreciacao_acumulada,
        "valor_contabil_final": valor_contabil_final,
        "ganho_capital": ganho_capital,
        "comissao_vendedor": comissao_vendedor,
        "comissao_gerente": comissao_gerente,
        "comissao_total": comissao_total,
        "tributos_locacao": tributos_locacao,
        "tributos_venda": tributos_venda,
        "tributos_atuais": tributos_atuais,
        "tributos_reforma": tributos_reforma,
        "custo_financeiro": custo_financeiro,
        "lucro_liquido": lucro_liquido,
        "margem_liquida": margem_liquida,
        "roi": roi,
        "payback": payback,
        "aluguel_minimo": aluguel_minimo,
        "status": status,
        "parecer": parecer
    }
    return resumo, pd.DataFrame(fluxo)

def exportar_excel(p, resumo, fluxo_df):
    output = BytesIO()
    premissas = pd.DataFrame([p])
    memorial = pd.DataFrame([
        ["Receita total da locação", resumo["receita_locacao"]],
        ["Valor residual / venda final", p["valor_residual"]],
        ["Receita total da operação", resumo["receita_total"]],
        ["Valor de aquisição", p["valor_aquisicao"]],
        ["Despesas previstas", resumo["despesas_total"]],
        ["Comissão total", resumo["comissao_total"]],
        ["Impostos sobre locação", "Impostos sobre venda", "Impostos atuais", resumo["tributos_atuais"]],
        ["IBS/CBS simulado", resumo["tributos_reforma"]],
        ["Custo financeiro", resumo["custo_financeiro"]],
        ["Valor contábil final", resumo["valor_contabil_final"]],
        ["Ganho de capital", resumo["ganho_capital"]],
        ["Lucro líquido", resumo["lucro_liquido"]],
        ["Margem líquida (%)", resumo["margem_liquida"]],
        ["ROI (%)", resumo["roi"]],
        ["Payback", resumo["payback"]],
        ["Aluguel mínimo sugerido", resumo["aluguel_minimo"]],
        ["Status", resumo["status"]],
        ["Parecer", resumo["parecer"]],
    ], columns=["Indicador", "Valor"])

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        premissas.to_excel(writer, index=False, sheet_name="Premissas")
        memorial.to_excel(writer, index=False, sheet_name="Memorial")
        fluxo_df.to_excel(writer, index=False, sheet_name="Fluxo Mensal")
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
st.sidebar.caption("Lucro Presumido | Locação 14,30% | Venda editável")

# =========================================================
# VISÃO EXECUTIVA
# =========================================================
if menu == "Visão Executiva":
    st.markdown("""
    <div class="hero">
        <h1>Precificação de Locação com Opção de Compra</h1>
        <p>Margem, impostos, ganho de capital, payback e aluguel mínimo recomendado.</p>
    </div>
    """, unsafe_allow_html=True)

    hist = carregar_historico()
    if hist.empty:
        c1, c2, c3, c4 = st.columns(4)
        cards = [
            ("Simulações", "0", "Histórico vazio"),
            ("Receita projetada", moeda(0), "Sem operações salvas"),
            ("Margem média", "0,00%", "Sem dados"),
            ("Operações críticas", "0", "Sem dados")
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
        c1, c2, c3, c4 = st.columns(4)
        cards = [
            ("Simulações", len(hist), "Operações salvas"),
            ("Receita projetada", moeda(hist["receita_total"].sum()), "Locação + venda"),
            ("Margem média", perc(hist["margem_liquida"].mean()), "Média do histórico"),
            ("Operações críticas", int((hist["status"] == "Crítica").sum()), "Revisar")
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

        st.markdown('<div class="section-title">Rentabilidade</div>', unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            chart_df = hist.head(12)[["cliente", "lucro_liquido"]].set_index("cliente")
            st.bar_chart(chart_df)
        with col2:
            chart_df2 = hist.head(12)[["cliente", "margem_liquida"]].set_index("cliente")
            st.bar_chart(chart_df2)

        st.markdown('<div class="section-title">Últimas simulações</div>', unsafe_allow_html=True)
        view = hist[["data_hora", "cliente", "equipamento", "prazo", "aluguel_mensal", "valor_residual", "lucro_liquido", "margem_liquida", "payback", "status"]].head(15)
        st.dataframe(
            formatar_df(
                view,
                money_cols=["aluguel_mensal", "valor_residual", "lucro_liquido"],
                percent_cols=["margem_liquida"],
                month_cols=["payback"]
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
        <p>Preencha as premissas e calcule a viabilidade da locação.</p>
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
        valor_residual = col4.number_input("Venda final / residual (R$)", min_value=0.0, value=180000.0, step=1000.0, format="%.2f")

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
        col1, col2, col3 = st.columns(3)
        perc_comissao_vendedor = col1.number_input("Comissão vendedor (%)", min_value=0.0, value=3.0, step=0.25)
        perc_comissao_gerente = col2.number_input("Comissão gerente (%)", min_value=0.0, value=1.0, step=0.25)
        base_comissao = col3.selectbox("Base da comissão", ["Receita de locação", "Receita total locação + residual"])

        st.markdown('<div class="section-title">Impostos</div>', unsafe_allow_html=True)
        col1, col2, col3, col4 = st.columns(4)
        imposto_atual = col1.number_input("Impostos sobre locação (%)", value=IMPOSTO_ATUAL_PADRAO, step=0.10, disabled=True)
        considerar_venda = col2.checkbox("Considerar venda final", value=True)
        imposto_venda = col3.number_input("Impostos sobre venda (%)", value=IMPOSTO_VENDA_PADRAO, step=0.10)
        credito_rt = col4.number_input("Crédito estimado IBS/CBS (%)", value=0.00, step=0.50)

        col1, col2 = st.columns(2)
        cbs = col1.number_input("CBS simulada (%)", value=0.90, step=0.10)
        ibs = col2.number_input("IBS simulada (%)", value=0.10, step=0.10)

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
            base_comissao=base_comissao,
            imposto_atual=IMPOSTO_ATUAL_PADRAO,
            considerar_venda=considerar_venda,
            imposto_venda=imposto_venda,
            cbs=cbs,
            ibs=ibs,
            credito_rt=credito_rt,
            observacoes=observacoes
        )

        resumo, fluxo_df = calcular_operacao(p)

        st.markdown('<div class="section-title">Resultado</div>', unsafe_allow_html=True)
        st.markdown(status_html(resumo["status"]), unsafe_allow_html=True)

        c1, c2, c3, c4 = st.columns(4)
        cards = [
            ("Receita total", moeda(resumo["receita_total"]), "Locação + venda final"),
            ("Lucro líquido", moeda(resumo["lucro_liquido"]), "Resultado estimado"),
            ("Margem líquida", perc(resumo["margem_liquida"]), "Lucro sobre receita"),
            ("Aluguel mínimo", moeda(resumo["aluguel_minimo"]), "Para a margem desejada")
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
            ("Ganho de capital", moeda(resumo["ganho_capital"]), "Venda final - valor contábil"),
            ("Impostos sobre locação", "Impostos sobre venda", "Impostos atuais", moeda(resumo["tributos_atuais"]), "Locação + venda final"),
            ("IBS/CBS simulado", moeda(resumo["tributos_reforma"]), "Cenário editável"),
            ("Payback", meses(resumo["payback"]), "Retorno do investimento")
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

        col1, col2 = st.columns(2)
        with col1:
            st.markdown('<div class="section-title">Composição do resultado</div>', unsafe_allow_html=True)
            comp = pd.DataFrame({
                "Item": ["Receita total", "Aquisição", "Despesas", "Comissão", "Impostos", "Custo financeiro", "Lucro líquido"],
                "Valor": [
                    resumo["receita_total"],
                    -valor_aquisicao,
                    -resumo["despesas_total"],
                    -resumo["comissao_total"],
                    -resumo["tributos_atuais"],
                    -resumo["custo_financeiro"],
                    resumo["lucro_liquido"],
                ]
            }).set_index("Item")
            st.bar_chart(comp)
        with col2:
            st.markdown('<div class="section-title">Saldo acumulado</div>', unsafe_allow_html=True)
            st.line_chart(fluxo_df.set_index("Mês")[["Saldo acumulado"]])

        st.markdown('<div class="section-title">Memorial</div>', unsafe_allow_html=True)
        memorial = pd.DataFrame([
            ["Receita locação", resumo["receita_locacao"]],
            ["Venda final / residual", valor_residual],
            ["Receita total", resumo["receita_total"]],
            ["Valor de aquisição", valor_aquisicao],
            ["Despesas previstas", resumo["despesas_total"]],
            ["Comissão vendedor", resumo["comissao_vendedor"]],
            ["Comissão gerente", resumo["comissao_gerente"]],
            ["Impostos sobre locação", resumo["tributos_locacao"]],
            ["Impostos sobre venda", resumo["tributos_venda"]],
            ["Impostos sobre locação", "Impostos sobre venda", "Impostos atuais", resumo["tributos_atuais"]],
            ["IBS/CBS simulado", resumo["tributos_reforma"]],
            ["Custo financeiro", resumo["custo_financeiro"]],
            ["Valor contábil final", resumo["valor_contabil_final"]],
            ["Ganho de capital", resumo["ganho_capital"]],
            ["Lucro líquido", resumo["lucro_liquido"]],
            ["Margem líquida", resumo["margem_liquida"]],
            ["ROI", resumo["roi"]],
            ["Payback", resumo["payback"]],
        ], columns=["Indicador", "Valor"])

        memorial_fmt = memorial.copy()
        money_indicators = [
            "Receita locação", "Venda final / residual", "Receita total", "Valor de aquisição",
            "Despesas previstas", "Comissão vendedor", "Comissão gerente", "Impostos sobre locação", "Impostos sobre venda", "Impostos atuais",
            "IBS/CBS simulado", "Custo financeiro", "Valor contábil final", "Ganho de capital",
            "Lucro líquido"
        ]
        percent_indicators = ["Margem líquida", "ROI"]
        month_indicators = ["Payback"]
        memorial_fmt["Valor"] = memorial_fmt.apply(
            lambda row: moeda(row["Valor"]) if row["Indicador"] in money_indicators
            else perc(row["Valor"]) if row["Indicador"] in percent_indicators
            else meses(row["Valor"]) if row["Indicador"] in month_indicators
            else row["Valor"],
            axis=1
        )
        st.dataframe(memorial_fmt, use_container_width=True, hide_index=True)

        st.markdown('<div class="section-title">Fluxo mensal</div>', unsafe_allow_html=True)
        st.dataframe(
            formatar_df(
                fluxo_df,
                money_cols=["Receita locação", "Venda final", "Impostos locação", "Impostos venda", "Despesas", "Comissão", "Custo financeiro", "Fluxo líquido", "Saldo acumulado"]
            ),
            use_container_width=True,
            hide_index=True
        )

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Salvar no histórico", use_container_width=True):
                dados_db = {
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
                    "receita_total": resumo["receita_total"],
                    "despesas_total": resumo["despesas_total"],
                    "comissao_total": resumo["comissao_total"],
                    "valor_contabil_final": resumo["valor_contabil_final"],
                    "ganho_capital": resumo["ganho_capital"],
                    "tributos_atuais": resumo["tributos_atuais"],
                    "tributos_venda": resumo["tributos_venda"],
                    "tributos_reforma": resumo["tributos_reforma"],
                    "custo_financeiro": resumo["custo_financeiro"],
                    "lucro_liquido": resumo["lucro_liquido"],
                    "margem_liquida": resumo["margem_liquida"],
                    "roi": resumo["roi"],
                    "payback": resumo["payback"],
                    "aluguel_minimo": resumo["aluguel_minimo"],
                    "status": resumo["status"],
                    "parecer": resumo["parecer"]
                }
                salvar_simulacao(dados_db)
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
        <p>Informe a margem desejada e encontre o aluguel mínimo sugerido.</p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)
    valor = col1.number_input("Valor do equipamento (R$)", value=400000.0, step=1000.0, format="%.2f")
    prazo = col2.number_input("Prazo (meses)", value=24, step=1)
    residual = col3.number_input("Venda final / residual (R$)", value=180000.0, step=1000.0, format="%.2f")

    col1, col2, col3 = st.columns(3)
    despesas = col1.number_input("Despesas totais (R$)", value=30000.0, step=1000.0, format="%.2f")
    comissao = col2.number_input("Comissão total (%)", value=4.0, step=0.25)
    margem = col3.number_input("Margem desejada (%)", value=20.0, step=1.0)

    col1, col2 = st.columns(2)
    imposto = col1.number_input("Impostos atuais incidentes (%)", value=IMPOSTO_ATUAL_PADRAO, step=0.10, disabled=True)
    custo_fin = col2.number_input("Custo financeiro total (R$)", value=80000.0, step=1000.0, format="%.2f")

    if st.button("Calcular aluguel mínimo", use_container_width=True):
        resultado = None
        for aluguel in np.arange(1000, 150000, 100):
            receita_loc = aluguel * prazo
            receita_total = receita_loc + residual
            trib = receita_total * IMPOSTO_ATUAL_PADRAO / 100
            com = receita_total * comissao / 100
            lucro = receita_total - valor - despesas - trib - com - custo_fin
            margem_calc = lucro / receita_total * 100 if receita_total else 0
            if margem_calc >= margem:
                resultado = (aluguel, receita_total, lucro, margem_calc)
                break

        if resultado:
            aluguel, receita_total, lucro, margem_calc = resultado
            c1, c2, c3, c4 = st.columns(4)
            cards = [
                ("Aluguel mínimo", moeda(aluguel), "Valor mensal sugerido"),
                ("Receita total", moeda(receita_total), "Locação + venda"),
                ("Lucro estimado", moeda(lucro), "Resultado da operação"),
                ("Margem estimada", perc(margem_calc), "Margem atingida")
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
        <p>Configuração usada nas simulações.</p>
    </div>
    """, unsafe_allow_html=True)

    df = pd.DataFrame([
        ["Regime", "Lucro Presumido"],
        ["ISS", "Não considerado"],
        ["Impostos sobre locação", "14,30%"],
        ["Impostos sobre venda", "14,30% editável"],
        ["CBS padrão", "0,90%"],
        ["IBS padrão", "0,10%"],
        ["Histórico", "SQLite local"],
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
        view = hist.copy()
        st.dataframe(
            formatar_df(
                view,
                money_cols=[
                    "valor_aquisicao", "aluguel_mensal", "valor_residual", "receita_total",
                    "despesas_total", "comissao_total", "valor_contabil_final", "ganho_capital",
                    "tributos_atuais", "tributos_venda", "tributos_reforma", "custo_financeiro", "lucro_liquido",
                    "aluguel_minimo"
                ],
                percent_cols=["margem_liquida", "roi"],
                month_cols=["payback"]
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
