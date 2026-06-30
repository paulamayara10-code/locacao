
import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
from datetime import date, datetime
from io import BytesIO

# =========================================================
# CONFIGURAÇÃO
# =========================================================
st.set_page_config(
    page_title="First Medical | Precificação de Locação",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_PATH = "simulacoes_locacao_first.db"

# =========================================================
# BANCO DE DADOS
# =========================================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
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
            tributos_reforma REAL,
            custo_financeiro REAL,
            lucro_liquido REAL,
            margem_liquida REAL,
            roi REAL,
            payback REAL,
            vpl REAL,
            tir_anual REAL,
            aluguel_minimo REAL,
            status TEXT,
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
# ESTILO PREMIUM
# =========================================================
st.markdown("""
<style>
    :root {
        --primary: #0B2F4A;
        --secondary: #155E75;
        --accent: #D7A84F;
        --bg: #F3F6FA;
        --card: #FFFFFF;
        --muted: #64748B;
        --good: #0F766E;
        --warn: #B45309;
        --bad: #B91C1C;
    }

    .stApp {
        background: linear-gradient(180deg, #F5F8FC 0%, #EEF3F8 100%);
    }

    .block-container {
        padding-top: 1.1rem;
        padding-bottom: 2.5rem;
    }

    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #071F33 0%, #0B2F4A 100%);
    }

    section[data-testid="stSidebar"] * {
        color: white !important;
    }

    .hero {
        background: linear-gradient(135deg, #0B2F4A 0%, #155E75 65%, #1B7893 100%);
        border-radius: 24px;
        padding: 28px 32px;
        color: white;
        box-shadow: 0 12px 32px rgba(15, 46, 74, 0.20);
        margin-bottom: 22px;
    }

    .hero h1 {
        font-size: 2.0rem;
        margin: 0;
        font-weight: 800;
        letter-spacing: -0.03em;
    }

    .hero p {
        margin-top: 8px;
        margin-bottom: 0;
        color: rgba(255,255,255,0.88);
        font-size: 1rem;
    }

    .premium-card {
        background: var(--card);
        border-radius: 20px;
        padding: 20px 22px;
        border: 1px solid rgba(15,46,74,0.08);
        box-shadow: 0 8px 24px rgba(15, 46, 74, 0.07);
        margin-bottom: 16px;
    }

    .metric-card {
        background: white;
        border-radius: 20px;
        padding: 18px 20px;
        border: 1px solid rgba(15,46,74,0.08);
        box-shadow: 0 8px 24px rgba(15, 46, 74, 0.07);
        min-height: 128px;
    }

    .metric-label {
        color: var(--muted);
        font-size: 0.82rem;
        text-transform: uppercase;
        letter-spacing: .06em;
        font-weight: 700;
    }

    .metric-value {
        color: var(--primary);
        font-size: 1.55rem;
        font-weight: 850;
        margin-top: 8px;
        letter-spacing: -0.03em;
    }

    .metric-help {
        color: #64748B;
        font-size: 0.86rem;
        margin-top: 6px;
    }

    .section-title {
        color: #0B2F4A;
        font-size: 1.22rem;
        font-weight: 850;
        margin: 16px 0 10px 0;
        letter-spacing: -0.02em;
    }

    .pill-good {
        display: inline-block;
        background: #CCFBF1;
        color: #115E59;
        padding: 7px 12px;
        border-radius: 999px;
        font-weight: 800;
    }

    .pill-warn {
        display: inline-block;
        background: #FEF3C7;
        color: #92400E;
        padding: 7px 12px;
        border-radius: 999px;
        font-weight: 800;
    }

    .pill-bad {
        display: inline-block;
        background: #FEE2E2;
        color: #991B1B;
        padding: 7px 12px;
        border-radius: 999px;
        font-weight: 800;
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
    }

    .small-muted {
        color: #64748B;
        font-size: 0.88rem;
    }

    div[data-testid="stMetricValue"] {
        color: #0B2F4A;
        font-weight: 800;
    }

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
# FUNÇÕES
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

def calcular_tir(fluxos):
    try:
        import numpy_financial as npf
        return npf.irr(fluxos)
    except Exception:
        return None

def calcular_vpl(taxa_mensal, fluxos):
    return sum(fc / ((1 + taxa_mensal) ** i) for i, fc in enumerate(fluxos))

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
        return '<span class="pill-warn">🟡 Revisar premissas</span>'
    return '<span class="pill-bad">🔴 Operação crítica</span>'

def gerar_parecer(status, margem, payback, prazo, ganho_capital, lucro, aluguel, aluguel_minimo, rt_impacto):
    partes = []
    if status == "Saudável":
        partes.append(
            f"A operação apresenta boa atratividade econômica, com margem líquida estimada de {perc(margem)} "
            f"e payback aproximado de {payback:.1f} meses dentro de um contrato de {prazo} meses."
        )
    elif status == "Atenção":
        partes.append(
            f"A operação exige revisão antes da aprovação, pois a margem líquida estimada ficou em {perc(margem)} "
            f"e o payback aproximado foi de {payback:.1f} meses para um prazo de {prazo} meses."
        )
    else:
        partes.append(
            f"A operação não está recomendada nas premissas atuais. O lucro líquido estimado foi de {moeda(lucro)} "
            f"e a margem líquida ficou em {perc(margem)}."
        )

    if aluguel < aluguel_minimo:
        partes.append(
            f"O aluguel informado está abaixo do aluguel mínimo gerencial sugerido de {moeda(aluguel_minimo)}. "
            f"Recomenda-se revisar preço, despesas, comissão ou valor residual."
        )
    else:
        partes.append(
            f"O aluguel informado está acima do aluguel mínimo gerencial estimado de {moeda(aluguel_minimo)}, "
            f"mantendo a operação dentro da política de margem informada."
        )

    if ganho_capital > 0:
        partes.append(
            f"A venda final gera ganho de capital estimado de {moeda(ganho_capital)}, que deve ser considerado "
            f"na decisão de preço e na validação fiscal da proposta."
        )
    else:
        partes.append(
            "Nas premissas informadas, não há ganho de capital positivo na venda final."
        )

    partes.append(
        f"No cenário de Reforma Tributária, o impacto líquido simulado de IBS/CBS foi de {moeda(rt_impacto)}. "
        "As alíquotas permanecem editáveis para atualização conforme orientação fiscal."
    )

    return " ".join(partes)

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

    pis_cofins = receita_locacao * (p["pis"] + p["cofins"]) / 100
    irpj_locacao = (receita_locacao * p["pres_irpj"] / 100) * p["irpj"] / 100
    csll_locacao = (receita_locacao * p["pres_csll"] / 100) * p["csll"] / 100
    icms_venda = p["valor_residual"] * p["icms"] / 100 if p["usar_icms"] else 0
    imposto_ganho = max(ganho_capital, 0) * (p["ganho_irpj"] + p["ganho_csll"]) / 100

    tributos_atuais = pis_cofins + irpj_locacao + csll_locacao + icms_venda + imposto_ganho

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
        - (pis_cofins + irpj_locacao + csll_locacao) / p["prazo"]
        - (p["seguro"] + p["manutencao"] + p["despesas_indiretas"] + p["outras_despesas"]) / p["prazo"]
        - (comissao_total / p["prazo"])
    )
    payback = saida_inicial / entrada_mensal_aprox if entrada_mensal_aprox > 0 else 999

    taxa_mensal = (1 + p["taxa_desconto_anual"] / 100) ** (1 / 12) - 1
    fluxos = [-saida_inicial]
    fluxo = []
    saldo = -saida_inicial

    for m in range(1, int(p["prazo"]) + 1):
        receita_mes = p["aluguel_mensal"]
        trib_loc_mes = (pis_cofins + irpj_locacao + csll_locacao) / p["prazo"]
        desp_mes = (p["seguro"] + p["manutencao"] + p["despesas_indiretas"] + p["outras_despesas"]) / p["prazo"]
        com_mes = comissao_total / p["prazo"]
        custo_fin_mes = custo_financeiro / p["prazo"]
        venda_mes = p["valor_residual"] if m == p["prazo"] else 0
        trib_venda_mes = (icms_venda + imposto_ganho) if m == p["prazo"] else 0
        fluxo_mes = receita_mes + venda_mes - trib_loc_mes - desp_mes - com_mes - custo_fin_mes - trib_venda_mes
        saldo += fluxo_mes
        fluxos.append(fluxo_mes)

        fluxo.append({
            "Mês": m,
            "Receita locação": receita_mes,
            "Venda final": venda_mes,
            "Tributos locação": trib_loc_mes,
            "Despesas": desp_mes,
            "Comissão": com_mes,
            "Custo financeiro": custo_fin_mes,
            "Tributos venda / ganho": trib_venda_mes,
            "Fluxo líquido": fluxo_mes,
            "Saldo acumulado": saldo
        })

    vpl = calcular_vpl(taxa_mensal, fluxos)
    tir = calcular_tir(fluxos)
    tir_anual = ((1 + tir) ** 12 - 1) * 100 if tir is not None and not np.isnan(tir) else None

    # aluguel mínimo por busca
    aluguel_minimo = None
    for aluguel in np.arange(1000, 150000, 100):
        pp = p.copy()
        pp["aluguel_mensal"] = float(aluguel)
        receita_loc = aluguel * p["prazo"]
        receita_tot = receita_loc + p["valor_residual"]
        base_com = receita_loc if p["base_comissao"] == "Receita de locação" else receita_tot
        com = base_com * (p["perc_comissao_vendedor"] + p["perc_comissao_gerente"]) / 100
        pisconf = receita_loc * (p["pis"] + p["cofins"]) / 100
        irpj_loc = (receita_loc * p["pres_irpj"] / 100) * p["irpj"] / 100
        csll_loc = (receita_loc * p["pres_csll"] / 100) * p["csll"] / 100
        lucro = receita_tot - p["valor_aquisicao"] - despesas_total - com - (pisconf + irpj_loc + csll_loc + icms_venda + imposto_ganho) - custo_financeiro
        margem = lucro / receita_tot * 100 if receita_tot else 0
        if margem >= p["margem_desejada"]:
            aluguel_minimo = float(aluguel)
            break
    if aluguel_minimo is None:
        aluguel_minimo = 0

    status = classificar_status(margem_liquida, payback, p["prazo"], lucro_liquido)
    parecer = gerar_parecer(status, margem_liquida, payback, p["prazo"], ganho_capital, lucro_liquido, p["aluguel_mensal"], aluguel_minimo, tributos_reforma)

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
        "pis_cofins": pis_cofins,
        "irpj_locacao": irpj_locacao,
        "csll_locacao": csll_locacao,
        "icms_venda": icms_venda,
        "imposto_ganho": imposto_ganho,
        "tributos_atuais": tributos_atuais,
        "tributos_reforma": tributos_reforma,
        "custo_financeiro": custo_financeiro,
        "lucro_liquido": lucro_liquido,
        "margem_liquida": margem_liquida,
        "roi": roi,
        "payback": payback,
        "vpl": vpl,
        "tir_anual": tir_anual,
        "aluguel_minimo": aluguel_minimo,
        "status": status,
        "parecer": parecer
    }

    return resumo, pd.DataFrame(fluxo)

def exportar_excel(p, resumo, fluxo_df):
    output = BytesIO()
    memorial = pd.DataFrame([
        ["Receita total da locação", resumo["receita_locacao"]],
        ["Valor residual / venda final", p["valor_residual"]],
        ["Receita total da operação", resumo["receita_total"]],
        ["Despesas previstas", resumo["despesas_total"]],
        ["Comissão vendedor", resumo["comissao_vendedor"]],
        ["Comissão gerente", resumo["comissao_gerente"]],
        ["PIS/COFINS", resumo["pis_cofins"]],
        ["IRPJ locação", resumo["irpj_locacao"]],
        ["CSLL locação", resumo["csll_locacao"]],
        ["ICMS venda", resumo["icms_venda"]],
        ["Imposto sobre ganho de capital", resumo["imposto_ganho"]],
        ["Custo financeiro", resumo["custo_financeiro"]],
        ["Valor contábil final", resumo["valor_contabil_final"]],
        ["Ganho de capital", resumo["ganho_capital"]],
        ["Lucro líquido", resumo["lucro_liquido"]],
        ["Margem líquida (%)", resumo["margem_liquida"]],
        ["ROI (%)", resumo["roi"]],
        ["Payback", resumo["payback"]],
        ["VPL", resumo["vpl"]],
        ["TIR anual (%)", resumo["tir_anual"] if resumo["tir_anual"] is not None else 0],
        ["Aluguel mínimo sugerido", resumo["aluguel_minimo"]],
        ["Status", resumo["status"]],
        ["Parecer", resumo["parecer"]],
    ], columns=["Indicador", "Valor"])

    premissas = pd.DataFrame([p])

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
    "Navegação",
    [
        "Visão Executiva",
        "1 - Cadastro da Operação",
        "2 - Precificação Reversa",
        "3 - Parâmetros Tributários",
        "4 - Histórico"
    ]
)
st.sidebar.markdown("---")
st.sidebar.caption("Lucro Presumido | Sem ISS | Locação com opção de compra")

# =========================================================
# VISÃO EXECUTIVA
# =========================================================
if menu == "Visão Executiva":
    st.markdown("""
    <div class="hero">
        <h1>Precificação de Locação com Opção de Compra</h1>
        <p>Modelo executivo para avaliar margem, tributos, ganho de capital, payback e aluguel mínimo recomendado.</p>
    </div>
    """, unsafe_allow_html=True)

    hist = carregar_historico()

    if hist.empty:
        c1, c2, c3, c4 = st.columns(4)
        for label, value, help_text in [
            ("Simulações", "0", "Nenhuma operação salva"),
            ("Receita projetada", moeda(0), "Total simulado"),
            ("Margem média", "0,00%", "Aguardando dados"),
            ("Operações críticas", "0", "Acompanhamento")
        ]:
            with c1 if label == "Simulações" else c2 if label == "Receita projetada" else c3 if label == "Margem média" else c4:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">{label}</div>
                    <div class="metric-value">{value}</div>
                    <div class="metric-help">{help_text}</div>
                </div>
                """, unsafe_allow_html=True)
        st.info("Use o menu **1 - Cadastro da Operação** para criar a primeira simulação.")
    else:
        c1, c2, c3, c4 = st.columns(4)
        metricas = [
            ("Simulações", len(hist), "Histórico salvo em SQLite"),
            ("Receita projetada", moeda(hist["receita_total"].sum()), "Locação + venda final"),
            ("Margem média", perc(hist["margem_liquida"].mean()), "Média das operações"),
            ("Operações críticas", int((hist["status"] == "Crítica").sum()), "Precisam revisão")
        ]
        for col, (label, value, help_text) in zip([c1, c2, c3, c4], metricas):
            with col:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">{label}</div>
                    <div class="metric-value">{value}</div>
                    <div class="metric-help">{help_text}</div>
                </div>
                """, unsafe_allow_html=True)

        st.markdown('<div class="section-title">Painel de rentabilidade</div>', unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Lucro líquido por simulação**")
            chart_df = hist.head(12)[["cliente", "lucro_liquido"]].copy()
            chart_df = chart_df.set_index("cliente")
            st.bar_chart(chart_df)
        with col2:
            st.markdown("**Margem líquida x Payback**")
            chart_df2 = hist[["margem_liquida", "payback"]].copy()
            st.line_chart(chart_df2)

        st.markdown('<div class="section-title">Últimas operações</div>', unsafe_allow_html=True)
        st.dataframe(
            hist[["data_hora", "cliente", "equipamento", "prazo", "aluguel_mensal", "valor_residual", "lucro_liquido", "margem_liquida", "status"]].head(15),
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
        <p>Informe equipamento, contrato, despesas, comissionamento e impostos para obter o parecer automático da Controladoria.</p>
    </div>
    """, unsafe_allow_html=True)

    with st.form("form_premium"):
        st.markdown('<div class="section-title">Dados comerciais</div>', unsafe_allow_html=True)
        col1, col2, col3 = st.columns(3)
        cliente = col1.text_input("Cliente", placeholder="Nome do cliente")
        vendedor = col2.text_input("Vendedor")
        gerente = col3.text_input("Gerente")

        col1, col2, col3 = st.columns(3)
        equipamento = col1.text_input("Equipamento", value="Equipamento médico-hospitalar")
        fabricante = col2.text_input("Fabricante / Linha")
        data_sim = col3.date_input("Data da simulação", value=date.today())

        st.markdown('<div class="section-title">Contrato e ativo</div>', unsafe_allow_html=True)
        col1, col2, col3, col4 = st.columns(4)
        valor_aquisicao = col1.number_input("Valor de aquisição", min_value=0.0, value=400000.0, step=1000.0)
        prazo = col2.number_input("Prazo da locação (meses)", min_value=1, value=24, step=1)
        aluguel_mensal = col3.number_input("Receita mensal da locação", min_value=0.0, value=18000.0, step=500.0)
        valor_residual = col4.number_input("Valor residual previsto", min_value=0.0, value=180000.0, step=1000.0)

        col1, col2, col3, col4 = st.columns(4)
        vida_util_anos = col1.number_input("Vida útil / depreciação (anos)", min_value=1.0, value=10.0, step=0.5)
        taxa_desconto_anual = col2.number_input("Taxa mínima de retorno anual (%)", min_value=0.0, value=18.0, step=0.5)
        custo_financeiro_mensal = col3.number_input("Custo financeiro mensal (%)", min_value=0.0, value=1.2, step=0.1)
        margem_desejada = col4.number_input("Margem líquida desejada (%)", min_value=0.0, value=20.0, step=1.0)

        st.markdown('<div class="section-title">Despesas previstas</div>', unsafe_allow_html=True)
        col1, col2, col3, col4 = st.columns(4)
        frete = col1.number_input("Frete", min_value=0.0, value=0.0, step=100.0)
        instalacao = col2.number_input("Instalação", min_value=0.0, value=0.0, step=100.0)
        seguro = col3.number_input("Seguro total previsto", min_value=0.0, value=0.0, step=100.0)
        manutencao = col4.number_input("Manutenção total prevista", min_value=0.0, value=0.0, step=100.0)

        col1, col2 = st.columns(2)
        despesas_indiretas = col1.number_input("Despesas indiretas / administrativas", min_value=0.0, value=0.0, step=100.0)
        outras_despesas = col2.number_input("Outras despesas previstas", min_value=0.0, value=0.0, step=100.0)

        st.markdown('<div class="section-title">Comissionamento</div>', unsafe_allow_html=True)
        col1, col2, col3 = st.columns(3)
        perc_comissao_vendedor = col1.number_input("Comissão vendedor (%)", min_value=0.0, value=3.0, step=0.25)
        perc_comissao_gerente = col2.number_input("Comissão gerente (%)", min_value=0.0, value=1.0, step=0.25)
        base_comissao = col3.selectbox("Base da comissão", ["Receita de locação", "Receita total locação + residual"])

        st.markdown('<div class="section-title">Tributos atuais — Lucro Presumido, sem ISS</div>', unsafe_allow_html=True)
        col1, col2, col3, col4 = st.columns(4)
        pis = col1.number_input("PIS (%)", value=0.65, step=0.01)
        cofins = col2.number_input("COFINS (%)", value=3.00, step=0.01)
        pres_irpj = col3.number_input("Presunção IRPJ locação (%)", value=32.00, step=1.0)
        pres_csll = col4.number_input("Presunção CSLL locação (%)", value=32.00, step=1.0)

        col1, col2, col3, col4 = st.columns(4)
        irpj = col1.number_input("IRPJ (%)", value=15.00, step=0.5)
        csll = col2.number_input("CSLL (%)", value=9.00, step=0.5)
        ganho_irpj = col3.number_input("IRPJ ganho capital (%)", value=15.00, step=0.5)
        ganho_csll = col4.number_input("CSLL ganho capital (%)", value=9.00, step=0.5)

        col1, col2 = st.columns(2)
        icms = col1.number_input("ICMS na venda do equipamento (%)", value=18.00, step=0.5)
        usar_icms = col2.checkbox("Considerar ICMS na venda final", value=True)

        st.markdown('<div class="section-title">Reforma Tributária — campos editáveis</div>', unsafe_allow_html=True)
        col1, col2, col3 = st.columns(3)
        cbs = col1.number_input("CBS simulada (%)", value=0.90, step=0.10)
        ibs = col2.number_input("IBS simulada (%)", value=0.10, step=0.10)
        credito_rt = col3.number_input("Crédito estimado IBS/CBS (%)", value=0.00, step=0.50)

        observacoes = st.text_area("Observações da operação", height=90)

        submitted = st.form_submit_button("Calcular operação", use_container_width=True)

    if submitted:
        p = dict(
            cliente=cliente or "Cliente não informado",
            vendedor=vendedor,
            gerente=gerente,
            equipamento=equipamento,
            fabricante=fabricante,
            data_sim=str(data_sim),
            valor_aquisicao=valor_aquisicao,
            prazo=int(prazo),
            aluguel_mensal=aluguel_mensal,
            valor_residual=valor_residual,
            vida_util_anos=vida_util_anos,
            taxa_desconto_anual=taxa_desconto_anual,
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
            pis=pis,
            cofins=cofins,
            pres_irpj=pres_irpj,
            pres_csll=pres_csll,
            irpj=irpj,
            csll=csll,
            ganho_irpj=ganho_irpj,
            ganho_csll=ganho_csll,
            icms=icms,
            usar_icms=usar_icms,
            cbs=cbs,
            ibs=ibs,
            credito_rt=credito_rt,
            observacoes=observacoes
        )

        resumo, fluxo_df = calcular_operacao(p)

        st.markdown('<div class="section-title">Resultado executivo</div>', unsafe_allow_html=True)
        st.markdown(status_html(resumo["status"]), unsafe_allow_html=True)

        col1, col2, col3, col4 = st.columns(4)
        cards = [
            ("Receita total", moeda(resumo["receita_total"]), "Locação + venda final"),
            ("Lucro líquido", moeda(resumo["lucro_liquido"]), "Após tributos, despesas e comissão"),
            ("Margem líquida", perc(resumo["margem_liquida"]), "Rentabilidade da operação"),
            ("Aluguel mínimo", moeda(resumo["aluguel_minimo"]), "Para margem desejada")
        ]
        for col, (label, value, help_text) in zip([col1, col2, col3, col4], cards):
            with col:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">{label}</div>
                    <div class="metric-value">{value}</div>
                    <div class="metric-help">{help_text}</div>
                </div>
                """, unsafe_allow_html=True)

        col1, col2, col3, col4 = st.columns(4)
        cards2 = [
            ("Ganho de capital", moeda(resumo["ganho_capital"]), "Venda final - valor contábil"),
            ("Tributos atuais", moeda(resumo["tributos_atuais"]), "Estimativa gerencial"),
            ("IBS/CBS simulado", moeda(resumo["tributos_reforma"]), "Cenário editável"),
            ("Payback", f'{resumo["payback"]:.1f} meses' if resumo["payback"] < 900 else "Não recupera", "Payback simples")
        ]
        for col, (label, value, help_text) in zip([col1, col2, col3, col4], cards2):
            with col:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">{label}</div>
                    <div class="metric-value">{value}</div>
                    <div class="metric-help">{help_text}</div>
                </div>
                """, unsafe_allow_html=True)

        st.markdown('<div class="section-title">Parecer automático da Controladoria</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="parecer">{resumo["parecer"]}</div>', unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Composição do resultado**")
            comp_df = pd.DataFrame({
                "Item": ["Receita total", "Aquisição", "Despesas", "Comissão", "Tributos", "Custo financeiro", "Lucro líquido"],
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
            st.bar_chart(comp_df)
        with col2:
            st.markdown("**Saldo acumulado da operação**")
            st.line_chart(fluxo_df.set_index("Mês")[["Saldo acumulado"]])

        st.markdown('<div class="section-title">Memorial de cálculo</div>', unsafe_allow_html=True)
        memorial = pd.DataFrame([
            ["Receita total da locação", resumo["receita_locacao"]],
            ["Valor residual / venda final", valor_residual],
            ["Receita total da operação", resumo["receita_total"]],
            ["Despesas previstas", resumo["despesas_total"]],
            ["Comissão total", resumo["comissao_total"]],
            ["PIS/COFINS", resumo["pis_cofins"]],
            ["IRPJ locação", resumo["irpj_locacao"]],
            ["CSLL locação", resumo["csll_locacao"]],
            ["ICMS venda", resumo["icms_venda"]],
            ["Imposto ganho de capital", resumo["imposto_ganho"]],
            ["Custo financeiro", resumo["custo_financeiro"]],
            ["Valor contábil final", resumo["valor_contabil_final"]],
            ["Ganho de capital", resumo["ganho_capital"]],
            ["VPL", resumo["vpl"]],
            ["TIR anual", resumo["tir_anual"] if resumo["tir_anual"] is not None else 0],
        ], columns=["Indicador", "Valor"])
        st.dataframe(memorial, use_container_width=True, hide_index=True)

        st.markdown('<div class="section-title">Fluxo mensal</div>', unsafe_allow_html=True)
        st.dataframe(fluxo_df, use_container_width=True, hide_index=True)

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Salvar simulação no histórico", use_container_width=True):
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
                    "tributos_reforma": resumo["tributos_reforma"],
                    "custo_financeiro": resumo["custo_financeiro"],
                    "lucro_liquido": resumo["lucro_liquido"],
                    "margem_liquida": resumo["margem_liquida"],
                    "roi": resumo["roi"],
                    "payback": resumo["payback"],
                    "vpl": resumo["vpl"],
                    "tir_anual": resumo["tir_anual"] if resumo["tir_anual"] is not None else 0,
                    "aluguel_minimo": resumo["aluguel_minimo"],
                    "status": resumo["status"],
                    "parecer": resumo["parecer"]
                }
                salvar_simulacao(dados_db)
                st.success("Simulação salva no histórico.")
        with col2:
            excel = exportar_excel(p, resumo, fluxo_df)
            st.download_button(
                "Baixar relatório em Excel",
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
        <p>Defina a margem desejada e encontre o aluguel mínimo aproximado para a operação.</p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)
    valor = col1.number_input("Valor do equipamento", value=400000.0, step=1000.0)
    prazo = col2.number_input("Prazo (meses)", value=24, step=1)
    residual = col3.number_input("Valor residual previsto", value=180000.0, step=1000.0)

    col1, col2, col3 = st.columns(3)
    despesas = col1.number_input("Despesas totais previstas", value=30000.0, step=1000.0)
    trib_efetivo = col2.number_input("Carga efetiva gerencial (%)", value=18.0, step=0.5)
    margem = col3.number_input("Margem líquida desejada (%)", value=20.0, step=1.0)

    col1, col2 = st.columns(2)
    comissao = col1.number_input("Comissão total (%)", value=4.0, step=0.25)
    custo_fin = col2.number_input("Custo financeiro total estimado", value=80000.0, step=1000.0)

    if st.button("Calcular aluguel mínimo premium", use_container_width=True):
        resultado = None
        for aluguel in np.arange(1000, 150000, 100):
            receita_loc = aluguel * prazo
            receita_total = receita_loc + residual
            trib = receita_total * trib_efetivo / 100
            com = receita_total * comissao / 100
            lucro = receita_total - valor - despesas - trib - com - custo_fin
            margem_calc = lucro / receita_total * 100 if receita_total else 0
            if margem_calc >= margem:
                resultado = (aluguel, receita_total, lucro, margem_calc)
                break

        if resultado:
            aluguel, receita_total, lucro, margem_calc = resultado
            c1, c2, c3, c4 = st.columns(4)
            for col, (label, val, help_text) in zip([c1, c2, c3, c4], [
                ("Aluguel mínimo", moeda(aluguel), "Referência para negociação"),
                ("Receita total", moeda(receita_total), "Locação + residual"),
                ("Lucro estimado", moeda(lucro), "Resultado gerencial"),
                ("Margem estimada", perc(margem_calc), "Meta atingida")
            ]):
                with col:
                    st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-label">{label}</div>
                        <div class="metric-value">{val}</div>
                        <div class="metric-help">{help_text}</div>
                    </div>
                    """, unsafe_allow_html=True)
        else:
            st.error("Não foi possível atingir a margem desejada com os limites simulados.")

# =========================================================
# PARÂMETROS
# =========================================================
elif menu == "3 - Parâmetros Tributários":
    st.markdown("""
    <div class="hero">
        <h1>Parâmetros Tributários</h1>
        <p>Base do modelo: Lucro Presumido, sem ISS, com alíquotas editáveis na simulação.</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="premium-card">As alíquotas abaixo são referências gerenciais pré-parametrizadas. Na tela de cadastro, o usuário pode editar cada campo antes de calcular a operação.</div>', unsafe_allow_html=True)

    df = pd.DataFrame([
        ["PIS", "0,65%", "Receita de locação"],
        ["COFINS", "3,00%", "Receita de locação"],
        ["Presunção IRPJ", "32,00%", "Base presumida da locação"],
        ["Presunção CSLL", "32,00%", "Base presumida da locação"],
        ["IRPJ", "15,00%", "Sobre base presumida"],
        ["CSLL", "9,00%", "Sobre base presumida"],
        ["ICMS", "Editável", "Somente venda final do equipamento"],
        ["IRPJ ganho de capital", "15,00%", "Sobre ganho positivo"],
        ["CSLL ganho de capital", "9,00%", "Sobre ganho positivo"],
        ["CBS", "0,90%", "Simulação / teste"],
        ["IBS", "0,10%", "Simulação / teste"],
    ], columns=["Tributo / parâmetro", "Padrão", "Aplicação"])
    st.dataframe(df, use_container_width=True, hide_index=True)

# =========================================================
# HISTÓRICO
# =========================================================
elif menu == "4 - Histórico":
    st.markdown("""
    <div class="hero">
        <h1>Histórico de Simulações</h1>
        <p>Consultas salvas localmente em SQLite para evitar perda ao reiniciar o app.</p>
    </div>
    """, unsafe_allow_html=True)

    hist = carregar_historico()
    if hist.empty:
        st.info("Nenhuma simulação salva ainda.")
    else:
        st.dataframe(hist, use_container_width=True, hide_index=True)
        csv = hist.to_csv(index=False).encode("utf-8-sig")
        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                "Exportar histórico em CSV",
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
                    st.success("Histórico limpo com sucesso.")
                else:
                    st.error("Senha inválida.")
