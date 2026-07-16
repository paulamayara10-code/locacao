
import json
import re
import sqlite3
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import streamlit as st

# ======================================================
# CONFIGURAÇÃO
# ======================================================
st.set_page_config(
    page_title="First Medical | Precificação de Locação",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ======================================================
# PERSISTÊNCIA DOS PREENCHIMENTOS ENTRE ABAS
# ======================================================
# O Streamlit mantém os valores do session_state durante a sessão.
# Não reatribuímos as chaves dos widgets, pois isso pode causar conflito
# quando um formulário está sendo renderizado.


def _slug_widget(texto):
    texto = re.sub(r"[^a-zA-Z0-9_]+", "_", str(texto)).strip("_").lower()
    return texto[:80] or "campo"


def _persistent_key(label, explicit_key=None):
    if explicit_key:
        return explicit_key
    prefixo = st.session_state.get("_active_menu", "global")
    return f"draft__{_slug_widget(prefixo)}__{_slug_widget(label)}"


# Wrappers para que widgets sem key explícita também tenham estado persistente.
_original_text_input = st.text_input
_original_number_input = st.number_input
_original_date_input = st.date_input
_original_radio = st.radio
_original_selectbox = st.selectbox
_original_checkbox = st.checkbox
_original_multiselect = st.multiselect


def _text_input(label, *args, **kwargs):
    key = _persistent_key(label, kwargs.get("key"))
    kwargs["key"] = key

    if key in st.session_state:
        kwargs.pop("value", None)

    return _original_text_input(label, *args, **kwargs)


def _number_input(label, *args, **kwargs):
    kwargs["key"] = _persistent_key(label, kwargs.get("key"))
    return _original_number_input(label, *args, **kwargs)


def _date_input(label, *args, **kwargs):
    kwargs["key"] = _persistent_key(label, kwargs.get("key"))
    return _original_date_input(label, *args, **kwargs)


def _radio(label, *args, **kwargs):
    kwargs["key"] = _persistent_key(label, kwargs.get("key"))
    return _original_radio(label, *args, **kwargs)


def _selectbox(label, *args, **kwargs):
    kwargs["key"] = _persistent_key(label, kwargs.get("key"))
    return _original_selectbox(label, *args, **kwargs)


def _checkbox(label, *args, **kwargs):
    kwargs["key"] = _persistent_key(label, kwargs.get("key"))
    return _original_checkbox(label, *args, **kwargs)


def _multiselect(label, *args, **kwargs):
    kwargs["key"] = _persistent_key(label, kwargs.get("key"))
    return _original_multiselect(label, *args, **kwargs)


st.text_input = _text_input
st.number_input = _number_input
st.date_input = _date_input
st.radio = _radio
st.selectbox = _selectbox
st.checkbox = _checkbox
st.multiselect = _multiselect

DB_PATH = "historico_precificacao.db"
ATIVOS_CSV = "ativos_pre_cadastro.csv"

IMPOSTO_ATUAL = 14.30
NACIONALIZACAO_PADRAO = 65.00
COMISSAO_VENDEDOR = 5.00
COMISSAO_GERENTE = 0.50
COMISSAO_REPRESENTANTE = 14.00
MARGEM_PADRAO = 25.00
TAXA_FINANCIAMENTO = 1.60
PRAZO_FINANCIAMENTO = 36
VIDA_UTIL_PADRAO = 10.0

# Premissas gerenciais pós-reforma — sempre editáveis
CBS_PADRAO = 8.80
IBS_PADRAO = 17.70
CREDITO_PADRAO = 100.00

# ======================================================
# ESTILO
# ======================================================
st.markdown(
    """
<style>
.stApp{background:linear-gradient(180deg,#F5F8FC 0%,#EEF3F8 100%)}
.block-container{padding-top:1.1rem;padding-bottom:2.5rem}
section[data-testid="stSidebar"]{background:linear-gradient(180deg,#071F33 0%,#0B2F4A 100%)}
section[data-testid="stSidebar"] *{color:white!important}
.hero{background:linear-gradient(135deg,#0B2F4A 0%,#155E75 70%,#1B7893 100%);border-radius:24px;padding:28px 32px;color:white;box-shadow:0 12px 32px rgba(15,46,74,.20);margin-bottom:20px}
.hero h1{font-size:2rem;margin:0;font-weight:850;letter-spacing:-.03em}
.hero p{margin:8px 0 0;color:rgba(255,255,255,.88)}
.metric-card{background:white;border-radius:20px;padding:18px 20px;border:1px solid rgba(15,46,74,.08);box-shadow:0 8px 24px rgba(15,46,74,.07);min-height:120px;margin-bottom:14px}
.metric-label{color:#64748B;font-size:.78rem;text-transform:uppercase;letter-spacing:.06em;font-weight:800}
.metric-value{color:#0B2F4A;font-size:1.34rem;font-weight:850;margin-top:8px;letter-spacing:-.03em}
.metric-help{color:#64748B;font-size:.84rem;margin-top:6px}
.section-title{color:#0B2F4A;font-size:1.18rem;font-weight:850;margin:16px 0 10px}
.parecer{background:#fff;border-left:6px solid #D7A84F;padding:18px 20px;border-radius:16px;box-shadow:0 8px 24px rgba(15,46,74,.07);color:#0B2F4A;line-height:1.55;margin:12px 0 18px}
.stButton>button,.stDownloadButton>button{border-radius:14px!important;border:0!important;background:linear-gradient(135deg,#0B2F4A,#155E75)!important;color:white!important;font-weight:800!important;padding:.75rem 1rem!important}
</style>
""",
    unsafe_allow_html=True,
)

# ======================================================
# BANCO DE DADOS
# ======================================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS historico_v17(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_hora TEXT,
            tipo TEXT,
            cliente TEXT,
            equipamento TEXT,
            fabricante TEXT,
            responsavel TEXT,
            prazo INTEGER,
            investimento REAL,
            aluguel REAL,
            receita REAL,
            custos REAL,
            impostos REAL,
            comissao REAL,
            lucro REAL,
            margem REAL,
            payback REAL,
            aluguel_minimo REAL,
            depreciacao REAL,
            valor_contabil REAL,
            lucro_reforma REAL,
            origem TEXT,
            detalhes TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def salvar(registro):
    conn = sqlite3.connect(DB_PATH)
    cols = ", ".join(registro.keys())
    marks = ", ".join(["?"] * len(registro))
    conn.execute(
        f"INSERT INTO historico_v17({cols}) VALUES({marks})",
        list(registro.values()),
    )
    conn.commit()
    conn.close()


def historico():
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query(
            "SELECT * FROM historico_v17 ORDER BY id DESC",
            conn,
        )
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df


init_db()

# ======================================================
# FORMATAÇÃO
# ======================================================
def moeda(v):
    try:
        return (
            f"R$ {float(v):,.2f}"
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )
    except Exception:
        return "R$ 0,00"


def perc(v):
    try:
        return f"{float(v):.2f}%".replace(".", ",")
    except Exception:
        return "0,00%"


def meses(v):
    try:
        if float(v) >= 900:
            return "Não recupera"
        return f"{float(v):.1f} meses".replace(".", ",")
    except Exception:
        return "N/A"


def parse(v):
    if isinstance(v, (int, float, np.integer, np.floating)):
        return float(v)
    s = str(v or "").replace("R$", "").replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    s = re.sub(r"[^0-9.\-]", "", s)
    try:
        return float(s)
    except Exception:
        return 0.0


def input_rs(label, value, key):
    texto = st.text_input(label, value=moeda(value), key=key)
    val = parse(texto)
    st.caption(f"Valor considerado: {moeda(val)}")
    return val


def card(label, value, help_text):
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
            <div class="metric-help">{help_text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def tabela_formatada(df, money=None, percent=None, months=None):
    out = df.copy()
    for c in money or []:
        if c in out.columns:
            out[c] = out[c].map(moeda)
    for c in percent or []:
        if c in out.columns:
            out[c] = out[c].map(perc)
    for c in months or []:
        if c in out.columns:
            out[c] = out[c].map(meses)
    return out

# ======================================================
# CÁLCULOS GERAIS
# ======================================================
def price(valor, taxa, prazo):
    if valor <= 0 or prazo <= 0:
        return 0.0
    i = taxa / 100
    if i == 0:
        return valor / prazo
    return valor * (i * (1 + i) ** prazo) / ((1 + i) ** prazo - 1)


def comissao_total(tipo, vendedor, gerente, representante):
    if tipo == "Vendedor + gerente":
        return vendedor + gerente
    if tipo == "Representante":
        return representante
    return 0.0


def calcular_depreciacao(valor, data_aquisicao, data_inicio, prazo, vida_anos):
    data_aq = pd.to_datetime(data_aquisicao, errors="coerce", dayfirst=True)
    data_ini = pd.to_datetime(data_inicio, errors="coerce", dayfirst=True)

    if pd.isna(data_aq):
        data_aq = pd.Timestamp(data_ini if not pd.isna(data_ini) else date.today())
    if pd.isna(data_ini):
        data_ini = pd.Timestamp(date.today())

    meses_antes = max(
        (data_ini.year - data_aq.year) * 12
        + data_ini.month
        - data_aq.month
        - (1 if data_ini.day < data_aq.day else 0),
        0,
    )

    vida_meses = max(int(vida_anos * 12), 1)
    meses_finais = min(meses_antes + int(prazo), vida_meses)
    taxa = meses_finais / vida_meses
    depreciacao = valor * taxa
    valor_contabil = max(valor - depreciacao, 0)

    return {
        "meses_antes": meses_antes,
        "meses_finais": meses_finais,
        "taxa": taxa * 100,
        "depreciacao": depreciacao,
        "valor_contabil": valor_contabil,
    }


def taxa_manutencao_por_depreciacao(depreciacao_atual_pct):
    """Curva gerencial inicial de manutenção anual sobre o valor de aquisição.

    Quanto mais depreciado/antigo o ativo, maior a reserva de manutenção.
    As faixas são premissas iniciais e permanecem editáveis no formulário.
    """
    if depreciacao_atual_pct <= 20:
        return 2.0
    if depreciacao_atual_pct <= 40:
        return 3.0
    if depreciacao_atual_pct <= 60:
        return 5.0
    if depreciacao_atual_pct <= 80:
        return 7.0
    return 10.0


def horas_tecnicas_por_depreciacao(depreciacao_atual_pct):
    """Estimativa inicial de horas técnicas mensais."""
    if depreciacao_atual_pct <= 20:
        return 1.0
    if depreciacao_atual_pct <= 40:
        return 2.0
    if depreciacao_atual_pct <= 60:
        return 3.0
    if depreciacao_atual_pct <= 80:
        return 4.0
    return 6.0


def simulacao_base_usado(
    valor_ativo,
    data_aquisicao,
    data_inicio,
    prazo=24,
    vida_util=10.0,
    imposto_pct=IMPOSTO_ATUAL,
    comissao_pct=COMISSAO_VENDEDOR + COMISSAO_GERENTE,
    margem_pct=MARGEM_PADRAO,
    reserva_risco_pct=5.0,
):
    """Gera uma referência de manutenção e aluguel para o ativo usado."""
    dep_atual = calcular_depreciacao(
        valor_ativo,
        data_aquisicao,
        data_inicio,
        0,
        vida_util,
    )
    dep_final = calcular_depreciacao(
        valor_ativo,
        data_aquisicao,
        data_inicio,
        prazo,
        vida_util,
    )

    taxa_anual = taxa_manutencao_por_depreciacao(dep_atual["taxa"])
    manutencao_mensal = valor_ativo * taxa_anual / 100 / 12

    depreciacao_contrato = max(
        dep_final["depreciacao"] - dep_atual["depreciacao"],
        0.0,
    )

    custo_operacional = manutencao_mensal * prazo
    reserva = custo_operacional * reserva_risco_pct / 100

    denominador = (
        1
        - imposto_pct / 100
        - comissao_pct / 100
        - margem_pct / 100
    )
    aluguel_sugerido = (
        (depreciacao_contrato + custo_operacional + reserva)
        / prazo
        / denominador
        if prazo > 0 and denominador > 0
        else 0.0
    )

    return {
        "depreciacao_atual": dep_atual["taxa"],
        "depreciacao_final": dep_final["taxa"],
        "taxa_manutencao_anual": taxa_anual,
        "manutencao_mensal": manutencao_mensal,
        "horas_tecnicas": horas_tecnicas_por_depreciacao(
            dep_atual["taxa"]
        ),
        "depreciacao_contrato": depreciacao_contrato,
        "aluguel_sugerido": aluguel_sugerido,
    }


def calcular_resultado(
    investimento,
    prazo,
    aluguel,
    custos_operacionais,
    imposto_pct,
    comissao_pct,
    margem_desejada,
    custo_financeiro=0.0,
    reserva_risco=0.0,
):
    receita = aluguel * prazo
    impostos = receita * imposto_pct / 100
    comissao = receita * comissao_pct / 100
    custo_total = (
        investimento
        + custos_operacionais
        + custo_financeiro
        + reserva_risco
    )
    lucro = receita - custo_total - impostos - comissao
    margem = lucro / receita * 100 if receita else 0

    fluxo_mensal = (
        aluguel
        - impostos / prazo
        - comissao / prazo
        - custos_operacionais / prazo
        - custo_financeiro / prazo
        - reserva_risco / prazo
    )
    payback = investimento / fluxo_mensal if fluxo_mensal > 0 else 999

    denominador = (
        1
        - imposto_pct / 100
        - comissao_pct / 100
        - margem_desejada / 100
    )
    aluguel_minimo = (
        (custo_total / prazo) / denominador
        if denominador > 0 and prazo > 0
        else 0.0
    )

    return {
        "receita": receita,
        "impostos": impostos,
        "comissao": comissao,
        "custo_total": custo_total,
        "lucro": lucro,
        "margem": margem,
        "payback": payback,
        "aluguel_minimo": aluguel_minimo,
    }


def calcular_reforma(
    receita,
    base_credito,
    cbs,
    ibs,
    credito_pct,
    demais_custos,
):
    aliquota = cbs + ibs
    tributo_bruto = receita * aliquota / 100
    credito = base_credito * aliquota / 100 * credito_pct / 100
    tributo_liquido = max(tributo_bruto - credito, 0)
    lucro = receita - demais_custos - tributo_liquido

    return {
        "aliquota": aliquota,
        "tributo_bruto": tributo_bruto,
        "credito": credito,
        "tributo_liquido": tributo_liquido,
        "lucro": lucro,
    }

# ======================================================
# PTAX
# ======================================================
@st.cache_data(ttl=3600, show_spinner=False)
def ptax():
    fim = date.today()
    ini = fim - timedelta(days=10)
    url = (
        "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
        "CotacaoDolarPeriodo(dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)"
        f"?@dataInicial='{ini.strftime('%m-%d-%Y')}'"
        f"&@dataFinalCotacao='{fim.strftime('%m-%d-%Y')}'"
        "&$top=100&$orderby=dataHoraCotacao%20desc"
        "&$format=json&$select=cotacaoVenda,dataHoraCotacao"
    )
    r = requests.get(url, timeout=12)
    r.raise_for_status()
    valores = r.json().get("value", [])
    if not valores:
        raise RuntimeError("sem cotação")
    reg = valores[0]
    dt = pd.to_datetime(reg["dataHoraCotacao"], errors="coerce")

    if pd.isna(dt):
        data_hora_brasilia = ""
    else:
        # A PTAX normalmente é retornada sem indicação explícita de fuso.
        # Quando vier sem timezone, tratamos o horário como Brasília.
        if getattr(dt, "tzinfo", None) is None:
            dt_brasilia = dt.tz_localize("America/Sao_Paulo")
        else:
            dt_brasilia = dt.tz_convert("America/Sao_Paulo")

        data_hora_brasilia = dt_brasilia.strftime(
            "%d/%m/%Y %H:%M"
        )

    consulta_brasilia = datetime.now(
        ZoneInfo("America/Sao_Paulo")
    ).strftime("%d/%m/%Y %H:%M")

    return (
        float(reg["cotacaoVenda"]),
        data_hora_brasilia,
        consulta_brasilia,
    )

# ======================================================
# ATIVOS
# ======================================================
@st.cache_data
def carregar_ativos():
    p = Path(ATIVOS_CSV)
    if not p.exists():
        return pd.DataFrame()
    for params in [
        dict(sep=None, engine="python", encoding="utf-8-sig"),
        dict(sep=";", encoding="latin1"),
    ]:
        try:
            return pd.read_csv(p, **params).fillna("")
        except Exception:
            pass
    return pd.DataFrame()


def coluna(row, nomes, default=""):
    for nome in nomes:
        if nome in row.index and pd.notna(row[nome]):
            return row[nome]
    return default


def ativo_info(row):
    valor = parse(
        coluna(
            row,
            [
                "Valor_Aquisicao",
                "Valor Aquisição",
                "Vl Aquisicao",
                "Vl_Aquisicao",
                "valor_aquisicao",
            ],
            0,
        )
    )
    data_aquisicao = coluna(
        row,
        [
            "Data Aquisicao",
            "Dt Aquisicao",
            "Data_Aquisicao",
            "data_aquisicao",
        ],
        "",
    )
    dt = pd.to_datetime(data_aquisicao, errors="coerce", dayfirst=True)

    return {
        "equipamento": str(
            coluna(
                row,
                ["Descricao", "Descrição", "Desc Bem", "descricao", "Produto"],
                "",
            )
        ),
        "fabricante": str(
            coluna(row, ["Marca", "Fabricante", "marca"], "")
        ),
        "valor": valor,
        "codigo": str(
            coluna(
                row,
                ["Codigo", "Código", "Cod Bem", "Cod_Bem", "codigo"],
                "",
            )
        ),
        "data_aquisicao": (
            dt.strftime("%d/%m/%Y")
            if not pd.isna(dt)
            else ""
        ),
    }


def label_ativo(row):
    info = ativo_info(row)
    return (
        f"{info['codigo']} | {info['equipamento'][:65]} | "
        f"{moeda(info['valor'])}"
    )

# ======================================================
# MENU
# ======================================================
st.sidebar.markdown("## FIRST MEDICAL")
st.sidebar.markdown("### Precificação de Locação")
st.sidebar.markdown("---")

menu = st.sidebar.radio(
    "Menu",
    [
        "Resumo Executivo",
        "1 - Locação de Novos",
        "2 - Locação de Usados",
        "3 - Ativos",
        "4 - Histórico",
        "5 - Parâmetros",
    ],
)

# Define o prefixo usado pelas chaves persistentes de cada aba.
st.session_state["_active_menu"] = menu

st.sidebar.markdown("---")
st.sidebar.caption(
    "Atual | Pós-reforma | Novos | Usados"
)

if st.sidebar.button("Limpar rascunho da aba atual", use_container_width=True):
    _prefix = f"draft__{_slug_widget(menu)}__"
    _explicit_keys = {
        "u_manut",
        "u_aluguel",
        "u_horas_tecnico",
        "u_taxa_manutencao_anual",
        "u_usar_manut_auto",
        "u_pecas",
        "u_seguro",
        "u_hora",
        "u_desloc",
        "u_revisao",
        "u_outros",
        "ucbs",
        "uibs",
        "ucredito",
        "ucv",
        "ucg",
        "ucr",
        "comissao_usados",
    }

    for _key in list(st.session_state.keys()):
        if (
            str(_key).startswith(_prefix)
            or _key in _explicit_keys
            or str(_key).startswith("_base_")
            or _key == "_ativo_usado_base"
        ):
            del st.session_state[_key]

    st.rerun()

# ======================================================
# RESUMO EXECUTIVO
# ======================================================
if menu == "Resumo Executivo":
    st.markdown(
        """
        <div class="hero">
            <h1>Resumo Executivo</h1>
            <p>Histórico consolidado de equipamentos novos e usados.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    h = historico()

    indicadores = [
        ("Precificações", len(h), "Registros salvos"),
        (
            "Aluguel médio",
            moeda(h["aluguel"].mean()) if not h.empty else moeda(0),
            "Contratos simulados",
        ),
        (
            "Margem média",
            perc(h["margem"].mean()) if not h.empty else "0,00%",
            "Cenário atual",
        ),
        (
            "Payback médio",
            meses(h[h["payback"] < 900]["payback"].mean())
            if not h.empty and (h["payback"] < 900).any()
            else "N/A",
            "Registros recuperáveis",
        ),
    ]

    cols = st.columns(4)
    for col, item in zip(cols, indicadores):
        with col:
            card(*item)

    if not h.empty:
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(
                '<div class="section-title">Lucro por precificação</div>',
                unsafe_allow_html=True,
            )
            st.bar_chart(
                h.head(20)[
                    ["equipamento", "lucro"]
                ].set_index("equipamento")
            )

        with col2:
            st.markdown(
                '<div class="section-title">Margem por tipo</div>',
                unsafe_allow_html=True,
            )
            margem_tipo = (
                h.groupby("tipo", as_index=False)["margem"]
                .mean()
                .set_index("tipo")
            )
            st.bar_chart(margem_tipo)

        st.markdown(
            '<div class="section-title">Últimas precificações</div>',
            unsafe_allow_html=True,
        )
        view = h[
            [
                "data_hora",
                "tipo",
                "cliente",
                "equipamento",
                "prazo",
                "aluguel",
                "aluguel_minimo",
                "lucro",
                "margem",
                "payback",
            ]
        ].head(20)

        st.dataframe(
            tabela_formatada(
                view,
                money=[
                    "aluguel",
                    "aluguel_minimo",
                    "lucro",
                ],
                percent=["margem"],
                months=["payback"],
            ),
            use_container_width=True,
            hide_index=True,
        )

# ======================================================
# NOVOS
# ======================================================
elif menu == "1 - Locação de Novos":
    st.markdown(
        """
        <div class="hero">
            <h1>Locação de Equipamentos Novos</h1>
            <p>FOB, dólar, nacionalização, financiamento, impostos e pós-reforma.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    try:
        dolar_padrao, data_ptax, consulta_brasilia = ptax()
        st.success(
            f"PTAX de venda: R$ {dolar_padrao:.4f} | "
            f"Cotação de {data_ptax} | "
            f"Consulta em {consulta_brasilia} — horário de Brasília"
        )
    except Exception:
        dolar_padrao = 5.50
        st.warning(
            "Não foi possível consultar a PTAX. "
            "Informe a cotação manualmente."
        )

    with st.form("novos"):
        col1, col2, col3 = st.columns(3)
        cliente = col1.text_input("Cliente")
        equipamento = col2.text_input("Equipamento")
        fabricante = col3.text_input("Fabricante / linha")

        col1, col2, col3 = st.columns(3)
        responsavel = col1.text_input("Vendedor / representante")
        prazo = col2.number_input(
            "Prazo (meses)", 1, 120, 24
        )
        data_inicio = col3.date_input(
            "Início da locação",
            date.today(),
            format="DD/MM/YYYY",
        )

        st.markdown(
            '<div class="section-title">Origem do equipamento</div>',
            unsafe_allow_html=True,
        )

        origem_produto = st.radio(
            "Tipo de aquisição",
            ["Produto importado", "Produto nacional"],
            horizontal=True,
            key="novo_origem_produto",
        )

        fob = 0.0
        dolar = float(dolar_padrao)
        nacionalizacao = 0.0
        fob_reais = 0.0
        custo_nac = 0.0
        valor_nacional = 0.0

        if origem_produto == "Produto importado":
            st.markdown(
                '<div class="section-title">Importação e nacionalização</div>',
                unsafe_allow_html=True,
            )
            col1, col2, col3 = st.columns(3)
            fob = col1.number_input(
                "Valor FOB (US$)",
                0.0,
                step=100.0,
                format="%.2f",
            )
            dolar = col2.number_input(
                "Dólar utilizado (R$)",
                0.01,
                value=float(dolar_padrao),
                step=0.01,
                format="%.4f",
            )
            nacionalizacao = col3.number_input(
                "Nacionalização (%)",
                0.0,
                value=NACIONALIZACAO_PADRAO,
                step=1.0,
            )

            fob_reais = fob * dolar
            custo_nac = fob_reais * nacionalizacao / 100
            investimento = fob_reais + custo_nac

            st.info(
                f"FOB convertido: {moeda(fob_reais)} | "
                f"Nacionalização: {moeda(custo_nac)} | "
                f"Investimento: {moeda(investimento)}"
            )
        else:
            st.markdown(
                '<div class="section-title">Aquisição nacional</div>',
                unsafe_allow_html=True,
            )
            valor_nacional = input_rs(
                "Valor de aquisição em R$",
                0.0,
                "novo_valor_nacional",
            )
            investimento = valor_nacional

            st.info(
                f"Investimento nacional considerado: {moeda(investimento)}"
            )

        st.markdown(
            '<div class="section-title">Origem do investimento</div>',
            unsafe_allow_html=True,
        )
        origem = st.radio(
            "Origem",
            ["Capital próprio", "Financiamento bancário"],
            horizontal=True,
        )

        custo_financeiro = 0.0
        parcela = 0.0
        valor_financiado = 0.0
        taxa_fin = TAXA_FINANCIAMENTO
        prazo_fin = PRAZO_FINANCIAMENTO

        if origem == "Financiamento bancário":
            col1, col2, col3 = st.columns(3)
            with col1:
                entrada = input_rs(
                    "Entrada",
                    0,
                    "novo_entrada",
                )
            with col2:
                valor_financiado = input_rs(
                    "Valor financiado",
                    max(investimento - entrada, 0),
                    "novo_financiado",
                )
            prazo_fin = col3.number_input(
                "Prazo financiamento",
                1,
                120,
                PRAZO_FINANCIAMENTO,
            )

            col1, col2 = st.columns(2)
            taxa_fin = col1.number_input(
                "Taxa mensal (%)",
                0.0,
                value=TAXA_FINANCIAMENTO,
                step=0.1,
            )
            parcela = price(
                valor_financiado,
                taxa_fin,
                prazo_fin,
            )
            custo_financeiro = max(
                parcela * prazo_fin - valor_financiado,
                0,
            )
            col2.metric(
                "Parcela estimada",
                moeda(parcela),
            )

        st.markdown(
            '<div class="section-title">Comissão</div>',
            unsafe_allow_html=True,
        )
        tipo_comissao = st.radio(
            "Modelo",
            [
                "Vendedor + gerente",
                "Representante",
                "Sem comissão",
            ],
            horizontal=True,
        )
        col1, col2, col3 = st.columns(3)
        cv = col1.number_input(
            "Vendedor (%)",
            0.0,
            value=COMISSAO_VENDEDOR,
            step=0.25,
            disabled=tipo_comissao != "Vendedor + gerente",
        )
        cg = col2.number_input(
            "Gerente (%)",
            0.0,
            value=COMISSAO_GERENTE,
            step=0.25,
            disabled=tipo_comissao != "Vendedor + gerente",
        )
        cr = col3.number_input(
            "Representante (%)",
            0.0,
            value=COMISSAO_REPRESENTANTE,
            step=0.5,
            disabled=tipo_comissao != "Representante",
        )
        com_pct = comissao_total(
            tipo_comissao,
            cv,
            cg,
            cr,
        )

        st.markdown(
            '<div class="section-title">Receita e cenário pós-reforma</div>',
            unsafe_allow_html=True,
        )
        col1, col2, col3 = st.columns(3)
        with col1:
            aluguel = input_rs(
                "Aluguel mensal",
                0,
                "novo_aluguel",
            )
        with col2:
            despesas = input_rs(
                "Despesas adicionais totais",
                0,
                "novo_despesas",
            )
        margem = col3.number_input(
            "Margem desejada (%)",
            0.0,
            value=MARGEM_PADRAO,
            step=1.0,
        )

        col1, col2, col3 = st.columns(3)
        cbs = col1.number_input(
            "CBS estimada (%)",
            value=CBS_PADRAO,
            step=0.1,
        )
        ibs = col2.number_input(
            "IBS estimado (%)",
            value=IBS_PADRAO,
            step=0.1,
        )
        credito_pct = col3.number_input(
            "Crédito estimado (%)",
            value=CREDITO_PADRAO,
            step=5.0,
        )

        st.number_input(
            "Impostos atuais (%)",
            value=IMPOSTO_ATUAL,
            disabled=True,
        )

        ok = st.form_submit_button(
            "Calcular precificação",
            use_container_width=True,
        )

    if ok:
        atual = calcular_resultado(
            investimento,
            int(prazo),
            aluguel,
            despesas,
            IMPOSTO_ATUAL,
            com_pct,
            margem,
            custo_financeiro,
        )

        base_credito = investimento + despesas
        demais_custos_reforma = (
            investimento
            + despesas
            + custo_financeiro
            + atual["comissao"]
        )
        reforma = calcular_reforma(
            atual["receita"],
            base_credito,
            cbs,
            ibs,
            credito_pct,
            demais_custos_reforma,
        )

        st.markdown(
            '<div class="section-title">Resumo executivo</div>',
            unsafe_allow_html=True,
        )
        cards = [
            (
                "Investimento",
                moeda(investimento),
                (
                    "FOB + nacionalização"
                    if origem_produto == "Produto importado"
                    else "Aquisição nacional"
                ),
            ),
            (
                "Aluguel mínimo",
                moeda(atual["aluguel_minimo"]),
                f"Margem {perc(margem)}",
            ),
            (
                "Lucro atual",
                moeda(atual["lucro"]),
                "Impostos atuais",
            ),
            (
                "Payback",
                meses(atual["payback"]),
                "Recuperação do investimento",
            ),
        ]
        cols = st.columns(4)
        for c, item in zip(cols, cards):
            with c:
                card(*item)

        st.markdown(
            '<div class="section-title">Cenário atual x pós-reforma</div>',
            unsafe_allow_html=True,
        )
        cards = [
            (
                "Impostos atuais",
                moeda(atual["impostos"]),
                "14,30%",
            ),
            (
                "IBS/CBS bruto",
                moeda(reforma["tributo_bruto"]),
                perc(reforma["aliquota"]),
            ),
            (
                "Crédito estimado",
                moeda(reforma["credito"]),
                perc(credito_pct),
            ),
            (
                "Lucro pós-reforma",
                moeda(reforma["lucro"]),
                "Após créditos",
            ),
        ]
        cols = st.columns(4)
        for c, item in zip(cols, cards):
            with c:
                card(*item)

        if st.button(
            "Salvar precificação de novo",
            use_container_width=True,
        ):
            salvar(
                {
                    "data_hora": datetime.now().strftime(
                        "%d/%m/%Y %H:%M:%S"
                    ),
                    "tipo": "Novo",
                    "cliente": cliente,
                    "equipamento": equipamento,
                    "fabricante": fabricante,
                    "responsavel": responsavel,
                    "prazo": int(prazo),
                    "investimento": investimento,
                    "aluguel": aluguel,
                    "receita": atual["receita"],
                    "custos": atual["custo_total"],
                    "impostos": atual["impostos"],
                    "comissao": atual["comissao"],
                    "lucro": atual["lucro"],
                    "margem": atual["margem"],
                    "payback": atual["payback"],
                    "aluguel_minimo": atual["aluguel_minimo"],
                    "depreciacao": 0.0,
                    "valor_contabil": investimento,
                    "lucro_reforma": reforma["lucro"],
                    "origem": origem,
                    "detalhes": json.dumps(
                        {
                            "origem_produto": origem_produto,
                            "fob_usd": fob,
                            "dolar": dolar,
                            "nacionalizacao": nacionalizacao,
                            "valor_nacional": valor_nacional,
                            "comissao_pct": com_pct,
                            "cbs": cbs,
                            "ibs": ibs,
                            "credito_pct": credito_pct,
                            "inicio": data_inicio.strftime(
                                "%d/%m/%Y"
                            ),
                        },
                        ensure_ascii=False,
                    ),
                }
            )
            st.success("Precificação salva.")

# ======================================================
# USADOS
# ======================================================
elif menu == "2 - Locação de Usados":
    st.markdown(
        """
        <div class="hero">
            <h1>Locação de Equipamentos Usados</h1>
            <p>Custo de propriedade + custo operacional + risco + margem.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    ativos = carregar_ativos()
    info = {}

    if not ativos.empty:
        busca = st.text_input("Buscar ativo")
        filtrados = ativos.copy()
        if busca:
            filtrados = filtrados[
                filtrados.astype(str)
                .apply(
                    lambda x: x.str.contains(
                        busca,
                        case=False,
                        na=False,
                    )
                )
                .any(axis=1)
            ]

        opcoes = ["Não selecionar"] + [
            label_ativo(row)
            for _, row in filtrados.head(300).iterrows()
        ]
        selecionado = st.selectbox(
            "Selecionar ativo",
            opcoes,
        )
        if selecionado != "Não selecionar":
            info = ativo_info(
                filtrados.iloc[
                    opcoes.index(selecionado) - 1
                ]
            )
            st.success(
                f"Ativo: {info['equipamento']} | "
                f"Aquisição: {moeda(info['valor'])} | "
                f"Data: {info['data_aquisicao'] or 'não informada'}"
            )

    # Gera valores-base quando um ativo é selecionado.
    simulacao_inicial = None
    if info and info.get("valor", 0) > 0:
        data_base_aquisicao = (
            info.get("data_aquisicao")
            or date.today().strftime("%d/%m/%Y")
        )
        simulacao_inicial = simulacao_base_usado(
            valor_ativo=info.get("valor", 0.0),
            data_aquisicao=data_base_aquisicao,
            data_inicio=date.today(),
            prazo=24,
            vida_util=VIDA_UTIL_PADRAO,
        )

        assinatura_ativo = (
            f"{info.get('codigo', '')}|"
            f"{info.get('valor', 0)}|"
            f"{info.get('data_aquisicao', '')}"
        )

        # Valores-base são usados como padrão dos campos.
        # Não escrevemos diretamente nas chaves dos widgets dentro do formulário.
        if st.session_state.get("_ativo_usado_base") != assinatura_ativo:
            st.session_state["_ativo_usado_base"] = assinatura_ativo
            st.session_state["_base_manutencao_usado"] = float(
                simulacao_inicial["manutencao_mensal"]
            )
            st.session_state["_base_aluguel_usado"] = float(
                simulacao_inicial["aluguel_sugerido"]
            )
            st.session_state["_base_horas_usado"] = float(
                simulacao_inicial["horas_tecnicas"]
            )
            st.session_state["_base_taxa_manut_usado"] = float(
                simulacao_inicial["taxa_manutencao_anual"]
            )

        st.markdown(
            '<div class="section-title">Simulação-base do ativo usado</div>',
            unsafe_allow_html=True,
        )
        cols_base = st.columns(4)
        with cols_base[0]:
            card(
                "Depreciação atual",
                perc(simulacao_inicial["depreciacao_atual"]),
                "Na data de início",
            )
        with cols_base[1]:
            card(
                "Reserva anual de manutenção",
                perc(simulacao_inicial["taxa_manutencao_anual"]),
                "Sobre o valor de aquisição",
            )
        with cols_base[2]:
            card(
                "Manutenção mensal-base",
                moeda(simulacao_inicial["manutencao_mensal"]),
                "Estimativa automática",
            )
        with cols_base[3]:
            card(
                "Aluguel-base sugerido",
                moeda(simulacao_inicial["aluguel_sugerido"]),
                "24 meses, margem de 25%",
            )

    with st.form("usados"):
        col1, col2, col3 = st.columns(3)
        cliente = col1.text_input("Cliente")
        equipamento = col2.text_input(
            "Equipamento",
            value=info.get("equipamento", ""),
        )
        fabricante = col3.text_input(
            "Fabricante / linha",
            value=info.get("fabricante", ""),
        )

        col1, col2, col3 = st.columns(3)
        responsavel = col1.text_input(
            "Vendedor / representante"
        )
        prazo = col2.number_input(
            "Prazo (meses)",
            1,
            120,
            24,
        )
        data_inicio = col3.date_input(
            "Início da locação",
            date.today(),
            format="DD/MM/YYYY",
        )

        st.markdown(
            '<div class="section-title">Ativo e depreciação</div>',
            unsafe_allow_html=True,
        )
        col1, col2, col3 = st.columns(3)
        with col1:
            valor_ativo = input_rs(
                "Valor de aquisição",
                info.get("valor", 0.0),
                "usado_valor",
            )

        data_aq_default = pd.to_datetime(
            info.get("data_aquisicao", ""),
            errors="coerce",
            dayfirst=True,
        )
        if pd.isna(data_aq_default):
            data_aq_default = pd.Timestamp(date.today())

        data_aquisicao = col2.date_input(
            "Data de aquisição",
            value=data_aq_default.date(),
            format="DD/MM/YYYY",
        )
        vida_util = col3.number_input(
            "Vida útil (anos)",
            1.0,
            value=VIDA_UTIL_PADRAO,
            step=0.5,
        )

        st.markdown(
            '<div class="section-title">Custo operacional</div>',
            unsafe_allow_html=True,
        )

        dep_atual_form = calcular_depreciacao(
            valor_ativo,
            data_aquisicao,
            data_inicio,
            0,
            vida_util,
        )
        taxa_manut_sugerida = taxa_manutencao_por_depreciacao(
            dep_atual_form["taxa"]
        )

        col1, col2, col3 = st.columns(3)
        taxa_manutencao_anual = col1.number_input(
            "Reserva anual de manutenção (% do valor de aquisição)",
            min_value=0.0,
            value=float(
                st.session_state.get(
                    "_base_taxa_manut_usado",
                    taxa_manut_sugerida,
                )
            ),
            step=0.5,
            key="u_taxa_manutencao_anual",
            help=(
                "Faixa automática pela depreciação atual. "
                "Pode ser alterada conforme a experiência da First."
            ),
        )
        manutencao_calculada = (
            valor_ativo * taxa_manutencao_anual / 100 / 12
        )
        usar_manutencao_automatica = col2.checkbox(
            "Usar manutenção automática",
            value=True,
            key="u_usar_manut_auto",
        )
        with col3:
            manutencao_manual = input_rs(
                "Manutenção mensal manual",
                float(
                    st.session_state.get(
                        "_base_manutencao_usado",
                        manutencao_calculada,
                    )
                ),
                "u_manut",
            )

        manutencao = (
            manutencao_calculada
            if usar_manutencao_automatica
            else manutencao_manual
        )
        st.caption(
            f"Manutenção considerada no cálculo: {moeda(manutencao)}"
        )

        col1, col2, col3 = st.columns(3)
        with col1:
            pecas = input_rs(
                "Peças / consumíveis mensais",
                0,
                "u_pecas",
            )
        with col2:
            seguro = input_rs(
                "Seguro mensal",
                0,
                "u_seguro",
            )
        horas_tecnico = col3.number_input(
            "Horas técnicas por mês",
            0.0,
            value=float(
                st.session_state.get(
                    "_base_horas_usado",
                    horas_tecnicas_por_depreciacao(
                        dep_atual_form["taxa"]
                    ),
                )
            ),
            step=1.0,
            key="u_horas_tecnico",
        )

        col1, col2 = st.columns(2)
        with col1:
            valor_hora = input_rs(
                "Valor da hora técnica",
                0,
                "u_hora",
            )
        with col2:
            deslocamento = input_rs(
                "Deslocamento mensal",
                0,
                "u_desloc",
            )

        col1, col2, col3 = st.columns(3)
        with col1:
            revisao_inicial = input_rs(
                "Revisão inicial / recuperação",
                0,
                "u_revisao",
            )
        with col2:
            outros = input_rs(
                "Outros custos mensais",
                0,
                "u_outros",
            )
        reserva_risco_pct = col3.number_input(
            "Reserva técnica / indisponibilidade (%)",
            0.0,
            value=5.0,
            step=0.5,
            help=(
                "Reserva gerencial sobre os custos operacionais "
                "para falhas, indisponibilidade e substituições."
            ),
        )

        st.markdown(
            '<div class="section-title">Modelo de recuperação do ativo</div>',
            unsafe_allow_html=True,
        )
        modelo_usado = st.radio(
            "Base da precificação",
            [
                "Somente custos incrementais",
                "Custos + depreciação do contrato",
                "Custos + valor contábil integral",
            ],
            horizontal=True,
        )

        st.markdown(
            '<div class="section-title">Comissão</div>',
            unsafe_allow_html=True,
        )
        tipo_comissao = st.radio(
            "Modelo",
            [
                "Vendedor + gerente",
                "Representante",
                "Sem comissão",
            ],
            horizontal=True,
            key="comissao_usados",
        )
        col1, col2, col3 = st.columns(3)
        cv = col1.number_input(
            "Vendedor (%)",
            0.0,
            value=COMISSAO_VENDEDOR,
            step=0.25,
            disabled=tipo_comissao != "Vendedor + gerente",
            key="ucv",
        )
        cg = col2.number_input(
            "Gerente (%)",
            0.0,
            value=COMISSAO_GERENTE,
            step=0.25,
            disabled=tipo_comissao != "Vendedor + gerente",
            key="ucg",
        )
        cr = col3.number_input(
            "Representante (%)",
            0.0,
            value=COMISSAO_REPRESENTANTE,
            step=0.5,
            disabled=tipo_comissao != "Representante",
            key="ucr",
        )
        com_pct = comissao_total(
            tipo_comissao,
            cv,
            cg,
            cr,
        )

        st.markdown(
            '<div class="section-title">Receita e pós-reforma</div>',
            unsafe_allow_html=True,
        )
        col1, col2, col3 = st.columns(3)
        simulacao_form = simulacao_base_usado(
            valor_ativo=valor_ativo,
            data_aquisicao=data_aquisicao,
            data_inicio=data_inicio,
            prazo=int(prazo),
            vida_util=vida_util,
            imposto_pct=IMPOSTO_ATUAL,
            comissao_pct=com_pct,
            margem_pct=MARGEM_PADRAO,
            reserva_risco_pct=reserva_risco_pct,
        )
        aluguel_base_form = simulacao_form["aluguel_sugerido"]

        aluguel_padrao = float(
            st.session_state.get(
                "_base_aluguel_usado",
                aluguel_base_form,
            )
        )

        with col1:
            aluguel = input_rs(
                "Aluguel mensal proposto",
                aluguel_padrao,
                "u_aluguel",
            )
        margem = col2.number_input(
            "Margem desejada (%)",
            0.0,
            value=MARGEM_PADRAO,
            step=1.0,
        )
        imposto = col3.number_input(
            "Impostos atuais (%)",
            value=IMPOSTO_ATUAL,
            disabled=True,
        )

        col1, col2, col3 = st.columns(3)
        cbs = col1.number_input(
            "CBS estimada (%)",
            value=CBS_PADRAO,
            step=0.1,
            key="ucbs",
        )
        ibs = col2.number_input(
            "IBS estimado (%)",
            value=IBS_PADRAO,
            step=0.1,
            key="uibs",
        )
        credito_pct = col3.number_input(
            "Crédito estimado (%)",
            value=CREDITO_PADRAO,
            step=5.0,
            key="ucredito",
        )

        ok = st.form_submit_button(
            "Calcular precificação",
            use_container_width=True,
        )

    if ok:
        dep = calcular_depreciacao(
            valor_ativo,
            data_aquisicao,
            data_inicio,
            int(prazo),
            vida_util,
        )

        custo_tecnico = horas_tecnico * valor_hora
        custo_mensal = (
            manutencao
            + pecas
            + seguro
            + custo_tecnico
            + deslocamento
            + outros
        )
        custo_operacional = (
            custo_mensal * prazo
            + revisao_inicial
        )
        reserva_risco = (
            custo_operacional * reserva_risco_pct / 100
        )

        if modelo_usado == "Somente custos incrementais":
            investimento_recuperar = 0.0
        elif modelo_usado == "Custos + depreciação do contrato":
            depreciacao_no_contrato = min(
                valor_ativo / (vida_util * 12) * prazo,
                dep["valor_contabil"]
                + min(
                    valor_ativo / (vida_util * 12) * prazo,
                    valor_ativo,
                ),
            )
            investimento_recuperar = depreciacao_no_contrato
        else:
            investimento_recuperar = dep["valor_contabil"]

        atual = calcular_resultado(
            investimento_recuperar,
            int(prazo),
            aluguel,
            custo_operacional,
            IMPOSTO_ATUAL,
            com_pct,
            margem,
            0.0,
            reserva_risco,
        )

        base_credito = (
            custo_operacional
            + reserva_risco
        )
        demais_custos_reforma = (
            investimento_recuperar
            + custo_operacional
            + reserva_risco
            + atual["comissao"]
        )
        reforma = calcular_reforma(
            atual["receita"],
            base_credito,
            cbs,
            ibs,
            credito_pct,
            demais_custos_reforma,
        )

        st.markdown(
            '<div class="section-title">Resumo executivo</div>',
            unsafe_allow_html=True,
        )
        cards = [
            (
                "Aluguel mínimo",
                moeda(atual["aluguel_minimo"]),
                f"Margem {perc(margem)}",
            ),
            (
                "Custo mensal operacional",
                moeda(custo_mensal),
                "Manutenção + técnico + outros",
            ),
            (
                "Lucro atual",
                moeda(atual["lucro"]),
                "Com aluguel informado",
            ),
            (
                "Payback",
                meses(atual["payback"]),
                modelo_usado,
            ),
        ]
        cols = st.columns(4)
        for c, item in zip(cols, cards):
            with c:
                card(*item)

        st.markdown(
            '<div class="section-title">Depreciação e ativo</div>',
            unsafe_allow_html=True,
        )
        cards = [
            (
                "Meses já depreciados",
                f"{dep['meses_antes']} meses",
                "Antes do contrato",
            ),
            (
                "Taxa de depreciação",
                perc(dep["taxa"]),
                f"{dep['meses_finais']} meses totais",
            ),
            (
                "Valor contábil final",
                moeda(dep["valor_contabil"]),
                "Após o contrato",
            ),
            (
                "Capital recuperado",
                moeda(investimento_recuperar),
                modelo_usado,
            ),
        ]
        cols = st.columns(4)
        for c, item in zip(cols, cards):
            with c:
                card(*item)

        st.markdown(
            '<div class="section-title">Atual x pós-reforma</div>',
            unsafe_allow_html=True,
        )
        cards = [
            (
                "Impostos atuais",
                moeda(atual["impostos"]),
                "14,30%",
            ),
            (
                "IBS/CBS bruto",
                moeda(reforma["tributo_bruto"]),
                perc(reforma["aliquota"]),
            ),
            (
                "Crédito estimado",
                moeda(reforma["credito"]),
                perc(credito_pct),
            ),
            (
                "Lucro pós-reforma",
                moeda(reforma["lucro"]),
                "Após créditos",
            ),
        ]
        cols = st.columns(4)
        for c, item in zip(cols, cards):
            with c:
                card(*item)

        parecer = (
            f"O modelo adotado foi '{modelo_usado}'. "
            f"O equipamento terá {perc(dep['taxa'])} de depreciação acumulada "
            f"ao final do contrato e valor contábil estimado de "
            f"{moeda(dep['valor_contabil'])}. O custo operacional mensal "
            f"estimado é {moeda(custo_mensal)}, acrescido de reserva técnica "
            f"de {perc(reserva_risco_pct)}. O aluguel mínimo recomendado é "
            f"{moeda(atual['aluguel_minimo'])}."
        )
        st.markdown(
            '<div class="section-title">Parecer</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="parecer">{parecer}</div>',
            unsafe_allow_html=True,
        )

        if st.button(
            "Salvar precificação de usado",
            use_container_width=True,
        ):
            salvar(
                {
                    "data_hora": datetime.now().strftime(
                        "%d/%m/%Y %H:%M:%S"
                    ),
                    "tipo": "Usado",
                    "cliente": cliente,
                    "equipamento": equipamento,
                    "fabricante": fabricante,
                    "responsavel": responsavel,
                    "prazo": int(prazo),
                    "investimento": investimento_recuperar,
                    "aluguel": aluguel,
                    "receita": atual["receita"],
                    "custos": atual["custo_total"],
                    "impostos": atual["impostos"],
                    "comissao": atual["comissao"],
                    "lucro": atual["lucro"],
                    "margem": atual["margem"],
                    "payback": atual["payback"],
                    "aluguel_minimo": atual["aluguel_minimo"],
                    "depreciacao": dep["taxa"],
                    "valor_contabil": dep["valor_contabil"],
                    "lucro_reforma": reforma["lucro"],
                    "origem": "Ativo próprio",
                    "detalhes": json.dumps(
                        {
                            "modelo_usado": modelo_usado,
                            "manutencao": manutencao,
                            "manutencao_automatica": usar_manutencao_automatica,
                            "taxa_manutencao_anual": taxa_manutencao_anual,
                            "depreciacao_atual": dep_atual_form["taxa"],
                            "pecas": pecas,
                            "horas_tecnico": horas_tecnico,
                            "valor_hora": valor_hora,
                            "custo_tecnico": custo_tecnico,
                            "reserva_risco_pct": reserva_risco_pct,
                            "cbs": cbs,
                            "ibs": ibs,
                            "credito_pct": credito_pct,
                            "data_aquisicao": data_aquisicao.strftime(
                                "%d/%m/%Y"
                            ),
                            "data_inicio": data_inicio.strftime(
                                "%d/%m/%Y"
                            ),
                        },
                        ensure_ascii=False,
                    ),
                }
            )
            st.success("Precificação salva.")

# ======================================================
# ATIVOS
# ======================================================
elif menu == "3 - Ativos":
    st.markdown(
        """
        <div class="hero">
            <h1>Ativos</h1>
            <p>Consulta da base pré-cadastrada.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    ativos = carregar_ativos()
    if ativos.empty:
        st.warning(
            "Arquivo ativos_pre_cadastro.csv não encontrado ou vazio."
        )
    else:
        busca = st.text_input("Buscar")
        view = ativos.copy()
        if busca:
            view = view[
                view.astype(str)
                .apply(
                    lambda x: x.str.contains(
                        busca,
                        case=False,
                        na=False,
                    )
                )
                .any(axis=1)
            ]
        st.dataframe(
            view,
            use_container_width=True,
            hide_index=True,
        )

# ======================================================
# HISTÓRICO
# ======================================================
elif menu == "4 - Histórico":
    st.markdown(
        """
        <div class="hero">
            <h1>Histórico de Precificação</h1>
            <p>Lista única de novos e usados já precificados.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    h = historico()
    if h.empty:
        st.info("Nenhuma precificação salva.")
    else:
        col1, col2, col3 = st.columns(3)
        tipos = col1.multiselect(
            "Tipo",
            ["Novo", "Usado"],
            default=["Novo", "Usado"],
        )
        cliente = col2.text_input("Cliente")
        equipamento = col3.text_input("Equipamento")

        view = h.copy()
        if tipos:
            view = view[view["tipo"].isin(tipos)]
        if cliente:
            view = view[
                view["cliente"].str.contains(
                    cliente,
                    case=False,
                    na=False,
                )
            ]
        if equipamento:
            view = view[
                view["equipamento"].str.contains(
                    equipamento,
                    case=False,
                    na=False,
                )
            ]

        cols = [
            "id",
            "data_hora",
            "tipo",
            "cliente",
            "equipamento",
            "fabricante",
            "prazo",
            "investimento",
            "aluguel",
            "aluguel_minimo",
            "lucro",
            "lucro_reforma",
            "margem",
            "payback",
            "depreciacao",
            "valor_contabil",
            "origem",
        ]

        st.dataframe(
            tabela_formatada(
                view[cols],
                money=[
                    "investimento",
                    "aluguel",
                    "aluguel_minimo",
                    "lucro",
                    "lucro_reforma",
                    "valor_contabil",
                ],
                percent=[
                    "margem",
                    "depreciacao",
                ],
                months=["payback"],
            ),
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            "Exportar histórico",
            data=view.to_csv(index=False).encode("utf-8-sig"),
            file_name="historico_precificacao.csv",
            mime="text/csv",
            use_container_width=True,
        )

# ======================================================
# PARÂMETROS
# ======================================================
elif menu == "5 - Parâmetros":
    st.markdown(
        """
        <div class="hero">
            <h1>Parâmetros</h1>
            <p>Premissas usadas nas precificações.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    parametros = pd.DataFrame(
        [
            ["Impostos atuais", "14,30%"],
            ["Nacionalização de novos importados", "65,00% editável"],
            ["Aquisição nacional", "Valor informado diretamente em R$"],
            ["Dólar", "PTAX de venda do Banco Central"],
            ["Comissão vendedor", "5,00%"],
            ["Comissão gerente", "0,50%"],
            ["Comissão representante", "14,00% editável"],
            ["Margem desejada", "25,00%"],
            ["Financiamento", "Tabela Price; 1,60% a.m."],
            ["Vida útil padrão", "10 anos"],
            ["CBS pós-reforma", "8,80% editável"],
            ["IBS pós-reforma", "17,70% editável"],
            ["Crédito pós-reforma", "100% da base elegível, editável"],
            [
                "Modelo de usados",
                (
                    "Custos operacionais + reserva técnica + "
                    "recuperação de capital escolhida"
                ),
            ],
            [
                "Curva de manutenção dos usados",
                "2%, 3%, 5%, 7% ou 10% ao ano conforme depreciação",
            ],
            [
                "Horas técnicas sugeridas",
                "1 a 6 horas/mês conforme depreciação atual",
            ],
        ],
        columns=["Parâmetro", "Valor"],
    )

    st.dataframe(
        parametros,
        use_container_width=True,
        hide_index=True,
    )
