
import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
from datetime import date, datetime
from io import BytesIO
import re
from pathlib import Path

st.set_page_config(
    page_title="First Medical | Precificação de Locação",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_PATH = "simulacoes_locacao_first.db"
ATIVOS_CSV = "ativos_pre_cadastro.csv"

IMPOSTO_LOCACAO_PADRAO = 14.30
ALIQUOTA_GANHO_CAPITAL_PADRAO = 34.00
COMISSAO_VENDEDOR_PADRAO = 5.00
COMISSAO_GERENTE_PADRAO = 0.50
VIDA_UTIL_PADRAO = 10.0
TAXA_FINANCIAMENTO_PADRAO = 1.60
PRAZO_FINANCIAMENTO_PADRAO = 36
CBS_REFORMA_PADRAO = 8.80
IBS_REFORMA_PADRAO = 17.70
CREDITO_REFORMA_PADRAO = 100.00

# ======================================================
# BANCO
# ======================================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS simulacoes_v12 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_hora TEXT,
            cliente TEXT,
            equipamento TEXT,
            fabricante TEXT,
            vendedor TEXT,
            gerente TEXT,
            origem_investimento TEXT,
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
            custo_financeiro REAL,
            parcela_financiamento REAL,
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
    conn.execute(f"INSERT INTO simulacoes_v12 ({cols}) VALUES ({placeholders})", list(dados.values()))
    conn.commit()
    conn.close()

def carregar_historico():
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query("SELECT * FROM simulacoes_v12 ORDER BY id DESC", conn)
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df

def limpar_historico():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM simulacoes_v12")
    conn.commit()
    conn.close()

init_db()

# ======================================================
# FORMATAÇÃO
# ======================================================
def parse_moeda(txt):
    if txt is None:
        return 0.0
    s = str(txt).strip().replace("R$", "").replace(" ", "")
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
    txt = st.text_input(label, value=moeda(value), key=key)
    val = parse_moeda(txt)
    st.caption(f"Valor considerado: {moeda(val)}")
    return val

def formatar_df(df, money_cols=None, percent_cols=None, month_cols=None):
    out = df.copy()
    for col in money_cols or []:
        if col in out.columns:
            out[col] = out[col].apply(moeda)
    for col in percent_cols or []:
        if col in out.columns:
            out[col] = out[col].apply(perc)
    for col in month_cols or []:
        if col in out.columns:
            out[col] = out[col].apply(meses)
    return out

def get_col(row, names, default=""):
    for n in names:
        if n in row.index and pd.notna(row[n]):
            return row[n]
    return default

def numero_base(valor):
    """Converte valores da base sem alterar casas decimais.

    Exemplos:
    - 8931.44 (float) -> 8931.44
    - "8.931,44" -> 8931.44
    - "8931.44" -> 8931.44
    """
    if valor is None:
        return 0.0

    if isinstance(valor, (int, float, np.integer, np.floating)):
        try:
            if pd.isna(valor):
                return 0.0
        except Exception:
            pass
        return float(valor)

    texto = str(valor).strip()
    if texto == "" or texto.lower() in {"nan", "none", "-", "--"}:
        return 0.0

    texto = texto.replace("R$", "").replace(" ", "")

    if "," in texto and "." in texto:
        # Formato brasileiro: 8.931,44
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        # Formato brasileiro sem milhar: 8931,44
        texto = texto.replace(",", ".")
    # Se houver apenas ponto, presume formato numérico internacional: 8931.44

    texto = re.sub(r"[^0-9.\-]", "", texto)

    try:
        return float(texto)
    except Exception:
        return 0.0

# ======================================================
# ATIVOS
# ======================================================
@st.cache_data
def carregar_ativos():
    path = Path(ATIVOS_CSV)
    if not path.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(path, sep=None, engine="python", encoding="utf-8-sig")
    except Exception:
        try:
            df = pd.read_csv(path, sep=";", encoding="latin1")
        except Exception:
            return pd.DataFrame()
    return df.fillna("")

def normalizar_data_br(valor):
    if valor is None or str(valor).strip() == "":
        return ""
    dt = pd.to_datetime(valor, errors="coerce", dayfirst=True)
    if pd.isna(dt):
        return str(valor)
    return dt.strftime("%d/%m/%Y")

def converter_data(valor, padrao=None):
    """Converte datas do cadastro ou do formulário para Timestamp."""
    if valor is None or str(valor).strip() == "":
        return pd.Timestamp(padrao if padrao is not None else date.today())
    dt = pd.to_datetime(valor, errors="coerce", dayfirst=True)
    if pd.isna(dt):
        return pd.Timestamp(padrao if padrao is not None else date.today())
    return pd.Timestamp(dt)

def meses_entre(data_inicial, data_final):
    """Meses completos aproximados entre duas datas, sem valores negativos."""
    inicio = converter_data(data_inicial)
    fim = converter_data(data_final)
    if fim <= inicio:
        return 0
    meses = (fim.year - inicio.year) * 12 + (fim.month - inicio.month)
    if fim.day < inicio.day:
        meses -= 1
    return max(int(meses), 0)

def montar_label_ativo(row):
    cod = str(get_col(row, ["Codigo", "Código", "Cod Bem", "Cod_Bem", "codigo", "cod_bem"], "")).strip()
    desc = str(get_col(row, ["Descricao", "Descrição", "Desc Bem", "descricao", "Produto", "produto"], "")).strip()
    serie = str(get_col(row, ["Serie", "Série", "Num Serie", "N Serie", "serie"], "")).strip()
    valor = get_col(row, ["Valor_Aquisicao", "Valor Aquisição", "Vl Aquisicao", "Vl_Aquisicao", "valor_aquisicao"], 0)
    valor_f = numero_base(valor)
    base = " | ".join([x for x in [cod, desc[:60], serie] if x])
    return f"{base} | {moeda(valor_f)}" if base else f"Ativo {moeda(valor_f)}"

def extrair_ativo(row):
    valor = get_col(row, ["Valor_Aquisicao", "Valor Aquisição", "Vl Aquisicao", "Vl_Aquisicao", "valor_aquisicao"], 0)
    valor = numero_base(valor)
    return {
        "equipamento": str(get_col(row, ["Descricao", "Descrição", "Desc Bem", "descricao", "Produto", "produto"], "")),
        "fabricante": str(get_col(row, ["Marca", "Fabricante", "marca", "fabricante"], "")),
        "valor_aquisicao": valor,
        "data_aquisicao": normalizar_data_br(get_col(row, ["Data Aquisicao", "Dt Aquisicao", "Data_Aquisicao", "data_aquisicao"], "")),
        "serie": str(get_col(row, ["Serie", "Série", "Num Serie", "N Serie", "serie"], "")),
        "codigo": str(get_col(row, ["Codigo", "Código", "Cod Bem", "Cod_Bem", "codigo", "cod_bem"], "")),
    }

# ======================================================
# ESTILO
# ======================================================
st.markdown("""
<style>
.stApp { background: linear-gradient(180deg, #F5F8FC 0%, #EEF3F8 100%); }
.block-container { padding-top: 1.1rem; padding-bottom: 2.5rem; }
section[data-testid="stSidebar"] { background: linear-gradient(180deg, #071F33 0%, #0B2F4A 100%); }
section[data-testid="stSidebar"] * { color: white !important; }
.hero { background: linear-gradient(135deg, #0B2F4A 0%, #155E75 70%, #1B7893 100%); border-radius: 24px; padding: 28px 32px; color: white; box-shadow: 0 12px 32px rgba(15,46,74,.20); margin-bottom: 20px; }
.hero h1 { font-size: 2rem; margin:0; font-weight:850; letter-spacing:-.03em; }
.hero p { margin:8px 0 0 0; color:rgba(255,255,255,.88); }
.metric-card { background:white; border-radius:20px; padding:18px 20px; border:1px solid rgba(15,46,74,.08); box-shadow:0 8px 24px rgba(15,46,74,.07); min-height:120px; margin-bottom:14px; }
.metric-label { color:#64748B; font-size:.78rem; text-transform:uppercase; letter-spacing:.06em; font-weight:800; }
.metric-value { color:#0B2F4A; font-size:1.34rem; font-weight:850; margin-top:8px; letter-spacing:-.03em; }
.metric-help { color:#64748B; font-size:.84rem; margin-top:6px; }
.section-title { color:#0B2F4A; font-size:1.18rem; font-weight:850; margin:16px 0 10px 0; letter-spacing:-.02em; }
.parecer { background:#fff; border-left:6px solid #D7A84F; padding:18px 20px; border-radius:16px; box-shadow:0 8px 24px rgba(15,46,74,.07); color:#0B2F4A; line-height:1.55; margin:12px 0 18px 0; font-weight:500; }
.pill-good,.pill-warn,.pill-bad { display:inline-block; padding:8px 14px; border-radius:999px; font-weight:850; margin-bottom:12px; }
.pill-good { background:#CCFBF1; color:#115E59; }
.pill-warn { background:#FEF3C7; color:#92400E; }
.pill-bad { background:#FEE2E2; color:#991B1B; }
.stButton > button, .stDownloadButton > button { border-radius:14px !important; border:0 !important; background:linear-gradient(135deg,#0B2F4A 0%,#155E75 100%) !important; color:white !important; font-weight:800 !important; padding:.75rem 1rem !important; box-shadow:0 8px 18px rgba(11,47,74,.18); }
</style>
""", unsafe_allow_html=True)

# ======================================================
# CÁLCULOS
# ======================================================
def calcular_parcela_price(valor, taxa_mensal_pct, prazo_meses):
    if valor <= 0 or prazo_meses <= 0:
        return 0.0
    i = taxa_mensal_pct / 100
    if i == 0:
        return valor / prazo_meses
    return valor * (i * (1 + i) ** prazo_meses) / ((1 + i) ** prazo_meses - 1)

def estimar_venda(valor_aquisicao, prazo, vida_util_anos, fator_mercado, data_aquisicao, data_inicio_locacao):
    vida_meses = max(int(round(vida_util_anos * 12)), 1)

    meses_anteriores = meses_entre(data_aquisicao, data_inicio_locacao)
    meses_totais_depreciados = min(meses_anteriores + int(prazo), vida_meses)

    percentual_depreciado = min(meses_totais_depreciados / vida_meses, 1) * 100
    valor_contabil = max(valor_aquisicao * (1 - percentual_depreciado / 100), 0)

    valor_base = valor_contabil if percentual_depreciado < 100 else valor_aquisicao * 0.10
    valor_venda = valor_base * (fator_mercado / 100)

    return valor_contabil, valor_venda, percentual_depreciado, meses_anteriores, meses_totais_depreciados

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

def payback(saida, fluxo_mensal):
    if fluxo_mensal <= 0:
        return 999
    return saida / fluxo_mensal

def calcular_operacao(p, interno=False):
    receita_locacao = p["aluguel_mensal"] * p["prazo"]
    despesas_total = (
        p["frete"] + p["instalacao"] + p["treinamento"] + p["adequacoes"] +
        p["seguro"] + p["manutencao"] + p["assistencia"] + p["outros_custos"]
    )

    valor_contabil_final, valor_venda_estimado, percentual_depreciado, meses_depreciados_antes, meses_depreciados_total = estimar_venda(
        p["valor_aquisicao"],
        p["prazo"],
        p["vida_util_anos"],
        p["fator_mercado"],
        p["data_aquisicao"],
        p["data_inicio_locacao"]
    )
    if p["usar_venda_manual"]:
        valor_venda_estimado = p["valor_venda_manual"]

    ganho_capital = valor_venda_estimado - valor_contabil_final
    impostos_ganho_capital = max(ganho_capital, 0) * p["aliquota_ganho_capital"] / 100

    comissao_vendedor = receita_locacao * p["comissao_vendedor"] / 100
    comissao_gerente = receita_locacao * p["comissao_gerente"] / 100
    comissao_total = comissao_vendedor + comissao_gerente

    impostos_locacao = receita_locacao * p["imposto_locacao"] / 100

    if p["origem_investimento"] == "Financiamento bancário":
        parcela_financiamento = calcular_parcela_price(p["valor_financiado"], p["taxa_financiamento"], p["prazo_financiamento"])
        custo_financeiro = max(parcela_financiamento * p["prazo_financiamento"] - p["valor_financiado"], 0)
    else:
        parcela_financiamento = 0.0
        custo_financeiro = 0.0

    saida_inicial = p["valor_aquisicao"] + p["frete"] + p["instalacao"] + p["treinamento"] + p["adequacoes"]
    lucro_locacao = receita_locacao - p["valor_aquisicao"] - despesas_total - comissao_total - impostos_locacao - custo_financeiro
    margem_locacao = lucro_locacao / receita_locacao * 100 if receita_locacao else 0

    fluxo_mensal_locacao = (
        p["aluguel_mensal"]
        - impostos_locacao / p["prazo"]
        - despesas_total / p["prazo"]
        - comissao_total / p["prazo"]
        - custo_financeiro / p["prazo"]
    )
    payback_locacao = payback(saida_inicial, fluxo_mensal_locacao)

    receita_total_com_venda = receita_locacao + valor_venda_estimado
    lucro_locacao_venda = receita_total_com_venda - p["valor_aquisicao"] - despesas_total - comissao_total - impostos_locacao - impostos_ganho_capital - custo_financeiro
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

    # Pós-reforma
    aliquota_reforma = p["cbs_reforma"] + p["ibs_reforma"]
    credito_base = p["valor_aquisicao"] + despesas_total
    credito_reforma = credito_base * aliquota_reforma / 100 * p["credito_reforma"] / 100
    trib_reforma_bruto = receita_total_com_venda * aliquota_reforma / 100
    trib_reforma_liquido = max(trib_reforma_bruto - credito_reforma, 0)
    lucro_reforma_venda = receita_total_com_venda - p["valor_aquisicao"] - despesas_total - comissao_total - trib_reforma_liquido - impostos_ganho_capital - custo_financeiro

    status_locacao = classificar(margem_locacao, lucro_locacao, payback_locacao, p["prazo"])
    status_venda = classificar(margem_locacao_venda, lucro_locacao_venda, payback_venda, p["prazo"])

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
        f"A origem do investimento é {p['origem_investimento'].lower()}. "
        f"O ativo já possuía {meses_depreciados_antes} mês(es) de depreciação antes do início deste contrato. "
        f"Ao final, terá {meses_depreciados_total} mês(es) depreciados, equivalente a {perc(percentual_depreciado)}, "
        f"com valor contábil de {moeda(valor_contabil_final)}. "
        f"Venda estimada: {moeda(valor_venda_estimado)}; ganho de capital: {moeda(ganho_capital)}."
    )

    resumo = {
        "receita_locacao": receita_locacao,
        "despesas_total": despesas_total,
        "valor_contabil_final": valor_contabil_final,
        "valor_venda_estimado": valor_venda_estimado,
        "percentual_depreciado": percentual_depreciado,
        "meses_depreciados_antes": meses_depreciados_antes,
        "meses_depreciados_total": meses_depreciados_total,
        "ganho_capital": ganho_capital,
        "impostos_ganho_capital": impostos_ganho_capital,
        "comissao_vendedor": comissao_vendedor,
        "comissao_gerente": comissao_gerente,
        "comissao_total": comissao_total,
        "impostos_locacao": impostos_locacao,
        "custo_financeiro": custo_financeiro,
        "parcela_financiamento": parcela_financiamento,
        "lucro_locacao": lucro_locacao,
        "margem_locacao": margem_locacao,
        "payback_locacao": payback_locacao,
        "lucro_locacao_venda": lucro_locacao_venda,
        "margem_locacao_venda": margem_locacao_venda,
        "payback_locacao_venda": payback_venda,
        "status_locacao": status_locacao,
        "status_locacao_venda": status_venda,
        "tributos_reforma_bruto": trib_reforma_bruto,
        "credito_reforma": credito_reforma,
        "tributos_reforma_liquido": trib_reforma_liquido,
        "lucro_reforma_venda": lucro_reforma_venda,
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
    memorial = pd.DataFrame([
        ["Origem investimento", p["origem_investimento"]],
        ["Data de aquisição", p["data_aquisicao"]],
        ["Início da locação", p["data_inicio_locacao"]],
        ["Meses depreciados antes do contrato", resumo["meses_depreciados_antes"]],
        ["Meses depreciados ao final", resumo["meses_depreciados_total"]],
        ["Receita locação", resumo["receita_locacao"]],
        ["Valor aquisição", p["valor_aquisicao"]],
        ["Despesas previstas", resumo["despesas_total"]],
        ["Comissão vendedor", resumo["comissao_vendedor"]],
        ["Comissão gerente", resumo["comissao_gerente"]],
        ["Impostos locação", resumo["impostos_locacao"]],
        ["Custo financeiro", resumo["custo_financeiro"]],
        ["Parcela financiamento", resumo["parcela_financiamento"]],
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
        ["IBS/CBS bruto pós-reforma", resumo["tributos_reforma_bruto"]],
        ["Crédito estimado pós-reforma", resumo["credito_reforma"]],
        ["IBS/CBS líquido pós-reforma", resumo["tributos_reforma_liquido"]],
        ["Lucro pós-reforma locação + venda", resumo["lucro_reforma_venda"]],
        ["Parecer", resumo["parecer"]],
    ], columns=["Indicador", "Valor"])

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame([p]).to_excel(writer, index=False, sheet_name="Premissas")
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
    ["Visão Executiva", "1 - Cadastro da Operação", "2 - Precificação Reversa", "3 - Ativos", "4 - Parâmetros", "5 - Histórico"]
)
st.sidebar.markdown("---")
st.sidebar.caption("Capital próprio | Financiamento | Venda posterior")

# ======================================================
# VISÃO
# ======================================================
if menu == "Visão Executiva":
    st.markdown('<div class="hero"><h1>Precificação de Locação</h1><p>Locação pura, locação com venda posterior e origem do investimento.</p></div>', unsafe_allow_html=True)
    hist = carregar_historico()
    if hist.empty:
        cards = [("Simulações","0","Histórico vazio"),("Lucro médio locação",moeda(0),"Sem dados"),("Lucro médio com venda",moeda(0),"Sem dados"),("Ganho médio",moeda(0),"Sem dados")]
    else:
        cards = [("Simulações",len(hist),"Operações salvas"),("Lucro médio locação",moeda(hist["lucro_locacao"].mean()),"Sem venda"),("Lucro médio com venda",moeda(hist["lucro_locacao_venda"].mean()),"Com venda"),("Ganho médio",moeda(hist["ganho_capital"].mean()),"Ganho de capital")]
    cols = st.columns(4)
    for col,(label,value,help_text) in zip(cols,cards):
        with col:
            st.markdown(f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value">{value}</div><div class="metric-help">{help_text}</div></div>', unsafe_allow_html=True)
    if not hist.empty:
        st.markdown('<div class="section-title">Comparativo de lucro</div>', unsafe_allow_html=True)
        st.bar_chart(hist.head(12)[["cliente","lucro_locacao","lucro_locacao_venda"]].set_index("cliente"))
        st.dataframe(formatar_df(hist.head(15), money_cols=["valor_aquisicao","aluguel_mensal","valor_venda_estimado","lucro_locacao","lucro_locacao_venda"], percent_cols=["margem_locacao","margem_locacao_venda","percentual_depreciado"], month_cols=["payback_locacao","payback_locacao_venda"]), use_container_width=True, hide_index=True)

# ======================================================
# CADASTRO
# ======================================================
elif menu == "1 - Cadastro da Operação":
    st.markdown('<div class="hero"><h1>Cadastro da Operação</h1><p>Preencha as premissas e calcule os cenários automaticamente.</p></div>', unsafe_allow_html=True)

    ativos = carregar_ativos()
    ativo_info = {}
    if not ativos.empty:
        st.markdown('<div class="section-title">Ativo pré-cadastrado</div>', unsafe_allow_html=True)
        busca = st.text_input("Buscar ativo", "")
        df_filtrado = ativos.copy()
        if busca:
            mask = df_filtrado.astype(str).apply(lambda col: col.str.contains(busca, case=False, na=False)).any(axis=1)
            df_filtrado = df_filtrado[mask]
        opcoes = ["Não selecionar"] + [montar_label_ativo(row) for _, row in df_filtrado.head(300).iterrows()]
        escolha = st.selectbox("Selecionar ativo", opcoes)
        if escolha != "Não selecionar":
            idx = opcoes.index(escolha) - 1
            ativo_info = extrair_ativo(df_filtrado.iloc[idx])
            st.success(f"Ativo selecionado: {ativo_info.get('equipamento','')} | Aquisição: {moeda(ativo_info.get('valor_aquisicao',0))}")

    with st.form("form_operacao"):
        st.markdown('<div class="section-title">Dados comerciais</div>', unsafe_allow_html=True)
        col1, col2, col3 = st.columns(3)
        cliente = col1.text_input("Cliente")
        vendedor = col2.text_input("Vendedor")
        gerente = col3.text_input("Gerente")

        col1, col2 = st.columns(2)
        equipamento = col1.text_input("Equipamento", value=ativo_info.get("equipamento",""))
        fabricante = col2.text_input("Fabricante / linha", value=ativo_info.get("fabricante",""))

        data_aquisicao_padrao = converter_data(ativo_info.get("data_aquisicao", ""), date.today()).date()

        col1, col2, col3 = st.columns(3)
        data_aquisicao = col1.date_input(
            "Data de aquisição",
            value=data_aquisicao_padrao,
            format="DD/MM/YYYY"
        )
        data_inicio_locacao = col2.date_input(
            "Início da locação",
            value=date.today(),
            format="DD/MM/YYYY"
        )
        data_sim = col3.date_input(
            "Data da simulação",
            value=date.today(),
            format="DD/MM/YYYY"
        )

        st.markdown('<div class="section-title">Contrato e ativo</div>', unsafe_allow_html=True)
        col1, col2, col3 = st.columns(3)
        with col1:
            valor_aquisicao = input_moeda("Valor de aquisição", ativo_info.get("valor_aquisicao",400000.0), "valor_aquisicao")
        with col2:
            prazo = st.number_input("Prazo da locação (meses)", min_value=1, value=24, step=1)
        with col3:
            aluguel_mensal = input_moeda("Aluguel mensal", 18000.0, "aluguel_mensal")

        col1, col2, col3 = st.columns(3)
        vida_util_anos = col1.number_input("Vida útil para depreciação (anos)", min_value=1.0, value=VIDA_UTIL_PADRAO, step=0.5)
        margem_desejada = col3.number_input("Margem líquida desejada (%)", min_value=0.0, value=25.0, step=1.0)

        st.markdown('<div class="section-title">Origem do investimento</div>', unsafe_allow_html=True)
        origem_investimento = st.radio(
            "Selecione a origem",
            ["Capital próprio", "Financiamento bancário"],
            horizontal=True,
            key="origem_investimento_radio"
        )

        # Padrão: capital próprio. Nenhum campo de financiamento aparece nesse caso.
        banco_financiamento = ""
        entrada_financiamento = 0.0
        valor_financiado = 0.0
        taxa_financiamento = TAXA_FINANCIAMENTO_PADRAO
        prazo_financiamento = PRAZO_FINANCIAMENTO_PADRAO

        if origem_investimento == "Financiamento bancário":
            st.markdown('<div class="section-title">Dados do financiamento</div>', unsafe_allow_html=True)
            col1, col2, col3, col4 = st.columns(4)
            banco_financiamento = col1.text_input("Banco")
            with col2:
                entrada_financiamento = input_moeda("Entrada", 0.0, "entrada_financiamento")
            with col3:
                valor_financiado = input_moeda("Valor financiado", max(valor_aquisicao - entrada_financiamento, 0), "valor_financiado")
            prazo_financiamento = col4.number_input("Prazo financiamento (meses)", min_value=1, value=PRAZO_FINANCIAMENTO_PADRAO, step=1)

            col1, col2 = st.columns(2)
            taxa_financiamento = col1.number_input("Taxa financiamento mensal (%)", min_value=0.0, value=TAXA_FINANCIAMENTO_PADRAO, step=0.1)
            parcela_preview = calcular_parcela_price(valor_financiado, taxa_financiamento, prazo_financiamento)
            col2.metric("Parcela estimada", moeda(parcela_preview))

            st.info(f"Custo financeiro total estimado: {moeda(parcela_preview * prazo_financiamento - valor_financiado)}")

        st.markdown('<div class="section-title">Venda posterior</div>', unsafe_allow_html=True)
        col1, col2, col3 = st.columns(3)
        fator_mercado = col1.number_input("Fator de mercado sobre valor contábil (%)", min_value=0.0, value=100.0, step=5.0)
        usar_venda_manual = col2.checkbox("Informar venda manualmente", value=False)
        with col3:
            valor_venda_manual = input_moeda("Venda manual", 0.0, "valor_venda_manual")

        st.markdown('<div class="section-title">Custos iniciais</div>', unsafe_allow_html=True)
        col1, col2, col3, col4 = st.columns(4)
        with col1: frete = input_moeda("Frete", 0.0, "frete")
        with col2: instalacao = input_moeda("Instalação", 0.0, "instalacao")
        with col3: treinamento = input_moeda("Treinamento", 0.0, "treinamento")
        with col4: adequacoes = input_moeda("Adequações", 0.0, "adequacoes")

        st.markdown('<div class="section-title">Custos recorrentes e outros</div>', unsafe_allow_html=True)
        col1, col2, col3, col4 = st.columns(4)
        with col1: seguro = input_moeda("Seguro total", 0.0, "seguro")
        with col2: manutencao = input_moeda("Manutenção total", 0.0, "manutencao")
        with col3: assistencia = input_moeda("Assistência técnica", 0.0, "assistencia")
        with col4: outros_custos = input_moeda("Outros custos", 0.0, "outros_custos")

        st.markdown('<div class="section-title">Comissões e impostos</div>', unsafe_allow_html=True)
        col1, col2, col3, col4 = st.columns(4)
        comissao_vendedor = col1.number_input("Comissão vendedor (%)", min_value=0.0, value=COMISSAO_VENDEDOR_PADRAO, step=0.25)
        comissao_gerente = col2.number_input("Comissão gerente (%)", min_value=0.0, value=COMISSAO_GERENTE_PADRAO, step=0.25)
        imposto_locacao = col3.number_input("Imposto locação (%)", value=IMPOSTO_LOCACAO_PADRAO, step=0.10, disabled=True)
        aliquota_ganho_capital = col4.number_input("Ganho de capital (%)", value=ALIQUOTA_GANHO_CAPITAL_PADRAO, step=0.50)

        st.markdown('<div class="section-title">Simulação pós-reforma</div>', unsafe_allow_html=True)
        col1, col2, col3 = st.columns(3)
        cbs_reforma = col1.number_input("CBS estimada (%)", value=CBS_REFORMA_PADRAO, step=0.10)
        ibs_reforma = col2.number_input("IBS estimado (%)", value=IBS_REFORMA_PADRAO, step=0.10)
        credito_reforma = col3.number_input("Crédito estimado sobre aquisição/despesas (%)", value=CREDITO_REFORMA_PADRAO, step=5.00)

        observacoes = st.text_area("Observações", height=80)
        submitted = st.form_submit_button("Calcular", use_container_width=True)

    if submitted:
        p = dict(
            cliente=cliente or "Cliente não informado",
            vendedor=vendedor,
            gerente=gerente,
            equipamento=equipamento or "Equipamento não informado",
            fabricante=fabricante,
            data_sim=data_sim.strftime("%d/%m/%Y"),
            data_aquisicao=data_aquisicao.strftime("%d/%m/%Y"),
            data_inicio_locacao=data_inicio_locacao.strftime("%d/%m/%Y"),
            valor_aquisicao=valor_aquisicao,
            prazo=int(prazo),
            aluguel_mensal=aluguel_mensal,
            vida_util_anos=vida_util_anos,
            margem_desejada=margem_desejada,
            origem_investimento=origem_investimento,
            banco_financiamento=banco_financiamento,
            entrada_financiamento=entrada_financiamento,
            valor_financiado=valor_financiado,
            taxa_financiamento=taxa_financiamento,
            prazo_financiamento=int(prazo_financiamento),
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
            aliquota_ganho_capital=aliquota_ganho_capital,
            cbs_reforma=cbs_reforma,
            ibs_reforma=ibs_reforma,
            credito_reforma=credito_reforma,
            observacoes=observacoes
        )

        resumo, fluxo_df = calcular_operacao(p)
        estrategia_df = gerar_estrategia(p)

        st.markdown('<div class="section-title">Resultado — somente locação</div>', unsafe_allow_html=True)
        st.markdown(status_html(resumo["status_locacao"], "Somente locação"), unsafe_allow_html=True)
        cards = [("Receita locação", moeda(resumo["receita_locacao"]), "Receita do contrato"),("Lucro locação", moeda(resumo["lucro_locacao"]), "Sem venda posterior"),("Margem locação", perc(resumo["margem_locacao"]), "Lucro sobre aluguel"),("Payback locação", meses(resumo["payback_locacao"]), "Retorno sem venda")]
        cols = st.columns(4)
        for col,(label,value,help_text) in zip(cols,cards):
            with col: st.markdown(f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value">{value}</div><div class="metric-help">{help_text}</div></div>', unsafe_allow_html=True)

        st.markdown('<div class="section-title">Resultado — locação + venda posterior</div>', unsafe_allow_html=True)
        st.markdown(status_html(resumo["status_locacao_venda"], "Locação + venda"), unsafe_allow_html=True)
        cards = [("Venda estimada", moeda(resumo["valor_venda_estimado"]), "Pelo prazo e depreciação"),("Lucro total", moeda(resumo["lucro_locacao_venda"]), "Locação + venda"),("Margem total", perc(resumo["margem_locacao_venda"]), "Lucro sobre receita total"),("Payback total", meses(resumo["payback_locacao_venda"]), "Com venda posterior")]
        cols = st.columns(4)
        for col,(label,value,help_text) in zip(cols,cards):
            with col: st.markdown(f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value">{value}</div><div class="metric-help">{help_text}</div></div>', unsafe_allow_html=True)

        cards = [
            ("Meses já depreciados", f'{resumo["meses_depreciados_antes"]} meses', "Antes deste contrato"),
            ("Depreciação final", perc(resumo["percentual_depreciado"]), f'{resumo["meses_depreciados_total"]} meses no total'),
            ("Valor contábil", moeda(resumo["valor_contabil_final"]), "Ao final da locação"),
            ("Ganho de capital", moeda(resumo["ganho_capital"]), "Venda - valor contábil")
        ]
        cols = st.columns(4)
        for col,(label,value,help_text) in zip(cols,cards):
            with col: st.markdown(f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value">{value}</div><div class="metric-help">{help_text}</div></div>', unsafe_allow_html=True)

        st.markdown(
            f"**Imposto estimado sobre ganho de capital:** {moeda(resumo['impostos_ganho_capital'])}"
        )

        if origem_investimento == "Financiamento bancário":
            st.markdown('<div class="section-title">Financiamento bancário</div>', unsafe_allow_html=True)
            cards = [("Valor financiado", moeda(valor_financiado), "Base financiada"),("Parcela", moeda(resumo["parcela_financiamento"]), "Tabela Price"),("Prazo", f"{prazo_financiamento} meses", "Prazo informado"),("Custo financeiro", moeda(resumo["custo_financeiro"]), "Juros totais")]
            cols = st.columns(4)
            for col,(label,value,help_text) in zip(cols,cards):
                with col: st.markdown(f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value">{value}</div><div class="metric-help">{help_text}</div></div>', unsafe_allow_html=True)

        st.markdown('<div class="section-title">Pós-reforma</div>', unsafe_allow_html=True)
        cards = [("IBS/CBS bruto", moeda(resumo["tributos_reforma_bruto"]), "CBS + IBS"),("Crédito estimado", moeda(resumo["credito_reforma"]), "Aquisição/despesas"),("IBS/CBS líquido", moeda(resumo["tributos_reforma_liquido"]), "Após créditos"),("Lucro pós-reforma", moeda(resumo["lucro_reforma_venda"]), "Locação + venda")]
        cols = st.columns(4)
        for col,(label,value,help_text) in zip(cols,cards):
            with col: st.markdown(f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value">{value}</div><div class="metric-help">{help_text}</div></div>', unsafe_allow_html=True)

        st.markdown('<div class="section-title">Parecer</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="parecer">{resumo["parecer"]}</div>', unsafe_allow_html=True)

        st.markdown('<div class="section-title">Comparativo de saldo</div>', unsafe_allow_html=True)
        st.line_chart(fluxo_df.set_index("Mês")[["Saldo somente locação","Saldo locação + venda"]])

        st.markdown('<div class="section-title">Estratégia de desmobilização</div>', unsafe_allow_html=True)
        st.dataframe(formatar_df(estrategia_df, money_cols=["Valor contábil","Venda estimada","Ganho de capital","Imposto ganho capital","Lucro total"], percent_cols=["Depreciação","Margem total"]), use_container_width=True, hide_index=True)

        st.markdown('<div class="section-title">Fluxo mensal</div>', unsafe_allow_html=True)
        st.dataframe(formatar_df(fluxo_df, money_cols=["Fluxo somente locação","Saldo somente locação","Venda estimada","Imposto ganho capital","Fluxo locação + venda","Saldo locação + venda"]), use_container_width=True, hide_index=True)

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Salvar no histórico", use_container_width=True):
                salvar_simulacao({
                    "data_hora": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                    "cliente": p["cliente"], "equipamento": p["equipamento"], "fabricante": p["fabricante"],
                    "vendedor": p["vendedor"], "gerente": p["gerente"], "origem_investimento": p["origem_investimento"],
                    "valor_aquisicao": p["valor_aquisicao"], "prazo": p["prazo"], "aluguel_mensal": p["aluguel_mensal"],
                    "valor_venda_estimado": resumo["valor_venda_estimado"], "valor_contabil_final": resumo["valor_contabil_final"],
                    "percentual_depreciado": resumo["percentual_depreciado"], "ganho_capital": resumo["ganho_capital"],
                    "lucro_locacao": resumo["lucro_locacao"], "margem_locacao": resumo["margem_locacao"],
                    "lucro_locacao_venda": resumo["lucro_locacao_venda"], "margem_locacao_venda": resumo["margem_locacao_venda"],
                    "impostos_locacao": resumo["impostos_locacao"], "impostos_ganho_capital": resumo["impostos_ganho_capital"],
                    "custo_financeiro": resumo["custo_financeiro"], "parcela_financiamento": resumo["parcela_financiamento"],
                    "payback_locacao": resumo["payback_locacao"], "payback_locacao_venda": resumo["payback_locacao_venda"],
                    "status_locacao": resumo["status_locacao"], "status_locacao_venda": resumo["status_locacao_venda"],
                    "parecer": resumo["parecer"]
                })
                st.success("Simulação salva.")
        with col2:
            excel = exportar_excel(p, resumo, fluxo_df, estrategia_df)
            st.download_button("Baixar Excel", data=excel, file_name="relatorio_precificacao_locacao_first.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

# ======================================================
# PRECIFICAÇÃO REVERSA
# ======================================================
elif menu == "2 - Precificação Reversa":
    st.markdown('<div class="hero"><h1>Precificação Reversa</h1><p>Calcula o aluguel mínimo para atingir a margem desejada.</p></div>', unsafe_allow_html=True)
    tipo = st.radio("Cenário", ["Somente locação", "Locação + venda posterior"], horizontal=True)
    col1, col2, col3 = st.columns(3)
    with col1: valor = input_moeda("Valor do equipamento", 400000.0, "rev_valor")
    prazo = col2.number_input("Prazo (meses)", value=24, step=1)
    margem = col3.number_input("Margem desejada (%)", value=25.0, step=1.0)
    origem = st.radio("Origem do investimento", ["Capital próprio", "Financiamento bancário"], horizontal=True)
    col1, col2, col3 = st.columns(3)
    vida = col1.number_input("Vida útil (anos)", value=VIDA_UTIL_PADRAO, step=0.5)
    fator = col2.number_input("Fator de mercado (%)", value=100.0, step=5.0)
    taxa = col3.number_input("Taxa financiamento mensal (%)", value=TAXA_FINANCIAMENTO_PADRAO, step=0.1, disabled=(origem=="Capital próprio"))
    col1, col2 = st.columns(2)
    with col1: despesas = input_moeda("Despesas totais", 30000.0, "rev_desp")
    prazo_fin = col2.number_input("Prazo financiamento", value=PRAZO_FINANCIAMENTO_PADRAO, step=1, disabled=(origem=="Capital próprio"))

    if st.button("Calcular aluguel mínimo", use_container_width=True):
        valor_contabil, venda_estimada, _, _, _ = estimar_venda(
            valor, prazo, vida, fator, date.today(), date.today()
        )
        if tipo == "Somente locação":
            venda_estimada = 0
        ganho = max(venda_estimada - valor_contabil, 0)
        imposto_gc = ganho * ALIQUOTA_GANHO_CAPITAL_PADRAO / 100
        custo_fin = 0 if origem == "Capital próprio" else max(calcular_parcela_price(valor, taxa, prazo_fin) * prazo_fin - valor, 0)
        resultado = None
        for aluguel in np.arange(1000, 200000, 100):
            receita_loc = aluguel * prazo
            receita_total = receita_loc + venda_estimada
            imposto_loc = receita_loc * IMPOSTO_LOCACAO_PADRAO / 100
            comissao = receita_loc * (COMISSAO_VENDEDOR_PADRAO + COMISSAO_GERENTE_PADRAO) / 100
            lucro = receita_total - valor - despesas - imposto_loc - comissao - custo_fin - imposto_gc
            margem_calc = lucro / receita_total * 100 if receita_total else 0
            if margem_calc >= margem:
                resultado = (aluguel, receita_total, lucro, margem_calc)
                break
        if resultado:
            aluguel, receita_total, lucro, margem_calc = resultado
            cards = [("Aluguel mínimo", moeda(aluguel), "Valor mensal sugerido"),("Receita total", moeda(receita_total), "Conforme cenário"),("Lucro estimado", moeda(lucro), "Resultado gerencial"),("Margem estimada", perc(margem_calc), "Margem atingida")]
            cols = st.columns(4)
            for col,(label,value,help_text) in zip(cols,cards):
                with col: st.markdown(f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value">{value}</div><div class="metric-help">{help_text}</div></div>', unsafe_allow_html=True)
        else:
            st.error("Não foi possível atingir a margem desejada.")

elif menu == "3 - Ativos":
    st.markdown('<div class="hero"><h1>Ativos</h1><p>Consulta da base pré-cadastrada.</p></div>', unsafe_allow_html=True)
    ativos = carregar_ativos()
    if ativos.empty:
        st.warning("Arquivo ativos_pre_cadastro.csv não encontrado ou vazio.")
    else:
        busca = st.text_input("Buscar")
        view = ativos.copy()
        if busca:
            mask = view.astype(str).apply(lambda col: col.str.contains(busca, case=False, na=False)).any(axis=1)
            view = view[mask]
        st.dataframe(view, use_container_width=True, hide_index=True)

elif menu == "4 - Parâmetros":
    st.markdown('<div class="hero"><h1>Parâmetros</h1><p>Premissas padrão usadas no app.</p></div>', unsafe_allow_html=True)
    df = pd.DataFrame([
        ["Regime", "Lucro Presumido"],
        ["ISS", "Não considerado"],
        ["Vida útil padrão", "10 anos"],
        ["Capital próprio", "Custo financeiro R$ 0,00"],
        ["Financiamento bancário", "Tabela Price, taxa padrão 1,60% a.m."],
        ["Margem desejada padrão", "25,00%"],
        ["Impostos sobre locação", "14,30%"],
        ["Ganho de capital", "34,00%"],
        ["Comissão vendedor", "5,00%"],
        ["Comissão gerente", "0,50%"],
        ["CBS pós-reforma", "8,80%"],
        ["IBS pós-reforma", "17,70%"],
    ], columns=["Parâmetro", "Valor"])
    st.dataframe(df, use_container_width=True, hide_index=True)

elif menu == "5 - Histórico":
    st.markdown('<div class="hero"><h1>Histórico</h1><p>Simulações salvas neste app.</p></div>', unsafe_allow_html=True)
    hist = carregar_historico()
    if hist.empty:
        st.info("Nenhuma simulação salva.")
    else:
        st.dataframe(formatar_df(hist, money_cols=["valor_aquisicao","aluguel_mensal","valor_venda_estimado","valor_contabil_final","ganho_capital","lucro_locacao","lucro_locacao_venda","impostos_locacao","impostos_ganho_capital","custo_financeiro","parcela_financiamento"], percent_cols=["percentual_depreciado","margem_locacao","margem_locacao_venda"], month_cols=["payback_locacao","payback_locacao_venda"]), use_container_width=True, hide_index=True)
        csv = hist.to_csv(index=False).encode("utf-8-sig")
        col1, col2 = st.columns(2)
        with col1:
            st.download_button("Exportar CSV", data=csv, file_name="historico_precificacao_locacao.csv", mime="text/csv", use_container_width=True)
        with col2:
            senha = st.text_input("Senha para limpar histórico", type="password")
            if st.button("Limpar histórico", use_container_width=True):
                if senha == "first2026":
                    limpar_historico()
                    st.success("Histórico limpo.")
                else:
                    st.error("Senha inválida.")
