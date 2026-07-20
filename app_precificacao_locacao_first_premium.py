
import json
import re
import sqlite3
import hashlib
from io import BytesIO
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import streamlit as st

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
)

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

# Base histórica mantida no próprio repositório Git.
# Nome recomendado: base_bi.xlsx na raiz do projeto.
BASE_BI_GIT = "base_bi.xlsx"
BASE_BI_GIT_ALTERNATIVAS = [
    BASE_BI_GIT,
    "BASE BI.xlsx",
    "BASE_BI.xlsx",
    "BASE BI(2).xlsx",
]

# Sempre que a regra de leitura da BASE BI mudar, altere esta versão.
# Isso força a limpeza e a reconstrução das referências importadas.
BASE_BI_REGRA_IMPORTACAO = (
    "V31_NOVA_LOCACAO_DIRETO_CENTRAL_VALOR_BRUTO"
)

IMPOSTO_ATUAL = 14.30
NACIONALIZACAO_PADRAO = 65.00
COMISSAO_VENDEDOR = 5.00
COMISSAO_GERENTE = 0.50
COMISSAO_REPRESENTANTE = 14.00
MARGEM_PADRAO = 25.00
MARGEM_USADO_PADRAO = 30.00
RESERVA_RISCO_USADO_PADRAO = 10.00
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
.resultado-fixo{position:sticky;top:.5rem;z-index:80;background:rgba(255,255,255,.97);backdrop-filter:blur(10px);border:1px solid rgba(15,46,74,.12);border-radius:18px;padding:12px 16px;box-shadow:0 10px 30px rgba(15,46,74,.14);margin:0 0 14px}
.resultado-fixo-titulo{font-size:.78rem;text-transform:uppercase;letter-spacing:.08em;font-weight:850;color:#64748B;margin-bottom:8px}
.resultado-fixo-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px}
.resultado-fixo-item{border-right:1px solid #E5E7EB;padding-right:10px}
.resultado-fixo-item:last-child{border-right:0}
.resultado-fixo-label{font-size:.70rem;color:#64748B;text-transform:uppercase;font-weight:750}
.resultado-fixo-valor{font-size:1.05rem;color:#0B2F4A;font-weight:900;margin-top:3px}
.resultado-fixo-alerta{margin-top:8px;font-size:.82rem;color:#8A4B08;font-weight:750}
@media(max-width:900px){.resultado-fixo-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.resultado-fixo-item{border-right:0}}
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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS referencias_historicas(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chave_unica TEXT UNIQUE,
            data_importacao TEXT, fonte TEXT, tipo_referencia TEXT,
            identificador TEXT, data_referencia TEXT,
            cliente_codigo TEXT, cliente TEXT, cnpj TEXT,
            equipamento_codigo TEXT, equipamento TEXT, linha_produto TEXT,
            quantidade REAL, valor_unitario REAL, valor_mensal REAL, valor_total REAL,
            vendedor TEXT, gerente TEXT, sla TEXT, origem_contrato TEXT,
            nota_fiscal TEXT, observacao TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS referencias_preco(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chave_unica TEXT UNIQUE,
            data_registro TEXT,
            data_referencia TEXT,
            fonte TEXT,
            tipo_fonte TEXT,
            confianca_pct REAL DEFAULT 0,
            status TEXT,
            equipamento_codigo TEXT,
            equipamento TEXT,
            fabricante TEXT,
            linha_produto TEXT,
            condicao TEXT,
            origem_produto TEXT,
            cliente_codigo TEXT,
            cliente TEXT,
            uf TEXT,
            prazo_meses INTEGER,
            quantidade REAL DEFAULT 1,
            preco_mensal_unitario REAL,
            valor_mensal_total REAL,
            valor_investimento REAL,
            aluguel_minimo_calculado REAL,
            margem_pct REAL,
            payback_meses REAL,
            vendedor TEXT,
            gerente TEXT,
            representante TEXT,
            nota_fiscal TEXT,
            contrato TEXT,
            simulacao_id INTEGER,
            observacao TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ref_preco_equipamento
        ON referencias_preco(equipamento_codigo, equipamento)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ref_preco_fonte_status
        ON referencias_preco(fonte, status)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS arquivos_importados(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            caminho TEXT,
            nome_arquivo TEXT,
            hash_sha256 TEXT UNIQUE,
            data_importacao TEXT,
            fonte TEXT,
            registros_inseridos INTEGER DEFAULT 0,
            registros_ignorados INTEGER DEFAULT 0,
            status TEXT,
            mensagem TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cotacoes_dolar(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_hora_registro TEXT,
            data_hora_cotacao TEXT,
            data_hora_consulta_brasilia TEXT,
            valor REAL,
            fonte TEXT,
            origem TEXT,
            finalidade TEXT,
            cliente TEXT,
            equipamento TEXT,
            observacao TEXT,
            usada_em_precificacao INTEGER DEFAULT 0
        )
        """
    )
    conn.commit()
    conn.close()



def confianca_referencia(fonte, status):
    fonte_n = normalizar_texto_coluna(fonte)
    status_n = normalizar_texto_coluna(status)

    if "FATURAMENTO" in fonte_n or status_n == "FATURADA":
        return 100.0
    if "CONTRATO" in fonte_n or status_n in {"CONTRATADA", "CONTRATO ATIVO"}:
        return 95.0
    if status_n == "APROVADA":
        return 85.0
    if status_n in {"ENVIADA", "EM NEGOCIACAO"}:
        return 65.0
    if status_n == "PERDIDA":
        return 20.0
    if "SIMULACAO" in fonte_n or status_n == "RASCUNHO":
        return 40.0
    return 50.0


def salvar_referencia_preco(registro):
    dados = dict(registro)
    dados.setdefault(
        "data_registro",
        datetime.now(ZoneInfo("America/Sao_Paulo")).strftime(
            "%d/%m/%Y %H:%M:%S"
        ),
    )
    dados.setdefault("quantidade", 1.0)
    dados.setdefault("status", "Rascunho")
    dados.setdefault(
        "confianca_pct",
        confianca_referencia(
            dados.get("fonte", ""), dados.get("status", "")
        ),
    )

    conn = sqlite3.connect(DB_PATH)
    try:
        cols = ", ".join(dados.keys())
        marks = ", ".join(["?"] * len(dados))
        cur = conn.execute(
            f"INSERT OR IGNORE INTO referencias_preco({cols}) VALUES({marks})",
            list(dados.values()),
        )
        conn.commit()
        return cur.lastrowid if cur.rowcount else None
    finally:
        conn.close()


def referencias_preco():
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query(
            "SELECT * FROM referencias_preco ORDER BY id DESC", conn
        )
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df


def excluir_referencias_preco(ids):
    if not ids:
        return
    conn = sqlite3.connect(DB_PATH)
    placeholders = ",".join(["?"] * len(ids))
    conn.execute(
        f"DELETE FROM referencias_preco WHERE id IN ({placeholders})",
        [int(item) for item in ids],
    )
    conn.commit()
    conn.close()


def atualizar_status_referencia(ref_id, status):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT fonte FROM referencias_preco WHERE id = ?", (int(ref_id),)
    ).fetchone()
    if not row:
        conn.close()
        raise ValueError("Referência não encontrada.")
    confianca = confianca_referencia(row[0], status)
    conn.execute(
        """
        UPDATE referencias_preco
           SET status = ?, confianca_pct = ?
         WHERE id = ?
        """,
        (status, confianca, int(ref_id)),
    )
    conn.commit()
    conn.close()


def salvar_referencias_preco_lote(registros):
    """Insere referências em uma única transação SQLite."""
    if not registros:
        return {"inseridos": 0, "ignorados": 0}

    agora = datetime.now(
        ZoneInfo("America/Sao_Paulo")
    ).strftime("%d/%m/%Y %H:%M:%S")

    preparados = []
    for registro in registros:
        dados = dict(registro)
        dados.setdefault("data_registro", agora)
        dados.setdefault("quantidade", 1.0)
        dados.setdefault("status", "Rascunho")
        dados.setdefault(
            "confianca_pct",
            confianca_referencia(
                dados.get("fonte", ""),
                dados.get("status", ""),
            ),
        )
        preparados.append(dados)

    colunas = list(preparados[0].keys())
    valores = [
        tuple(registro.get(coluna) for coluna in colunas)
        for registro in preparados
    ]

    conn = sqlite3.connect(DB_PATH)
    try:
        antes = conn.total_changes
        nomes = ", ".join(colunas)
        marcadores = ", ".join(["?"] * len(colunas))
        conn.executemany(
            f"""
            INSERT OR IGNORE INTO referencias_preco({nomes})
            VALUES({marcadores})
            """,
            valores,
        )
        conn.commit()
        inseridos = conn.total_changes - antes
    finally:
        conn.close()

    return {
        "inseridos": int(inseridos),
        "ignorados": int(len(preparados) - inseridos),
    }


def migrar_referencias_historicas_para_pricing():
    legadas = referencias_historicas()
    if legadas.empty:
        return {"inseridos": 0, "ignorados": 0}

    registros = []

    for _, row in legadas.iterrows():
        fonte = texto_limpo(row.get("fonte"))
        tipo_ref = texto_limpo(row.get("tipo_referencia"))
        faturada = (
            "FATUR" in normalizar_texto_coluna(fonte)
            or "FATUR" in normalizar_texto_coluna(tipo_ref)
        )
        status = "Faturada" if faturada else "Contratada"
        tipo_fonte = (
            "Faturamento real"
            if faturada
            else "Contrato ativo"
        )

        qtd = max(
            numero_limpo(row.get("quantidade")),
            1.0,
        )
        preco = numero_limpo(row.get("valor_unitario"))
        total = numero_limpo(row.get("valor_mensal"))

        if preco <= 0 and total > 0:
            preco = total / qtd
        if total <= 0:
            total = preco * qtd

        registros.append({
            "chave_unica": (
                "LEGADO|"
                + texto_limpo(row.get("chave_unica"))
            ),
            "data_referencia": texto_limpo(
                row.get("data_referencia")
            ),
            "fonte": fonte,
            "tipo_fonte": tipo_fonte,
            "confianca_pct": confianca_referencia(
                fonte,
                status,
            ),
            "status": status,
            "equipamento_codigo": texto_limpo(
                row.get("equipamento_codigo")
            ),
            "equipamento": texto_limpo(
                row.get("equipamento")
            ),
            "fabricante": "",
            "linha_produto": texto_limpo(
                row.get("linha_produto")
            ),
            "condicao": "Não informado",
            "origem_produto": "Não informado",
            "cliente_codigo": texto_limpo(
                row.get("cliente_codigo")
            ),
            "cliente": texto_limpo(row.get("cliente")),
            "uf": "",
            "prazo_meses": None,
            "quantidade": qtd,
            "preco_mensal_unitario": preco,
            "valor_mensal_total": total,
            "valor_investimento": None,
            "aluguel_minimo_calculado": None,
            "margem_pct": None,
            "payback_meses": None,
            "vendedor": texto_limpo(row.get("vendedor")),
            "gerente": texto_limpo(row.get("gerente")),
            "representante": "",
            "nota_fiscal": texto_limpo(
                row.get("nota_fiscal")
            ),
            "contrato": (
                texto_limpo(row.get("identificador"))
                if not faturada
                else ""
            ),
            "simulacao_id": None,
            "observacao": texto_limpo(
                row.get("observacao")
            ),
        })

    return salvar_referencias_preco_lote(registros)


def migrar_simulacoes_para_pricing():
    sims = historico()
    if sims.empty:
        return {"inseridos": 0, "ignorados": 0}

    registros = []

    for _, row in sims.iterrows():
        try:
            detalhes = json.loads(
                row.get("detalhes") or "{}"
            )
        except Exception:
            detalhes = {}

        status = detalhes.get(
            "status_referencia",
            "Rascunho",
        )

        registros.append({
            "chave_unica": (
                f"SIMULACAO|{int(row['id'])}"
            ),
            "data_referencia": texto_limpo(
                row.get("data_hora")
            ),
            "fonte": "Simulação interna",
            "tipo_fonte": "Simulação",
            "confianca_pct": confianca_referencia(
                "Simulação interna",
                status,
            ),
            "status": status,
            "equipamento_codigo": detalhes.get(
                "equipamento_codigo",
                "",
            ),
            "equipamento": texto_limpo(
                row.get("equipamento")
            ),
            "fabricante": texto_limpo(
                row.get("fabricante")
            ),
            "linha_produto": detalhes.get(
                "linha_produto",
                "",
            ),
            "condicao": texto_limpo(
                row.get("tipo")
            ),
            "origem_produto": detalhes.get(
                "origem_produto",
                "Não informado",
            ),
            "cliente_codigo": detalhes.get(
                "cliente_codigo",
                "",
            ),
            "cliente": texto_limpo(
                row.get("cliente")
            ),
            "uf": detalhes.get("uf", ""),
            "prazo_meses": int(
                row.get("prazo") or 0
            ),
            "quantidade": detalhes.get(
                "quantidade",
                1.0,
            ),
            "preco_mensal_unitario": numero_limpo(
                row.get("aluguel")
            ),
            "valor_mensal_total": numero_limpo(
                row.get("aluguel")
            ),
            "valor_investimento": numero_limpo(
                row.get("investimento")
            ),
            "aluguel_minimo_calculado": numero_limpo(
                row.get("aluguel_minimo")
            ),
            "margem_pct": numero_limpo(
                row.get("margem")
            ),
            "payback_meses": numero_limpo(
                row.get("payback")
            ),
            "vendedor": texto_limpo(
                row.get("responsavel")
            ),
            "gerente": "",
            "representante": "",
            "nota_fiscal": "",
            "contrato": "",
            "simulacao_id": int(row.get("id")),
            "observacao": detalhes.get(
                "observacao_referencia",
                "",
            ),
        })

    return salvar_referencias_preco_lote(registros)


def contar_registros_tabela(tabela):
    tabelas_permitidas = {
        "referencias_historicas",
        "referencias_preco",
        "historico_v17",
    }
    if tabela not in tabelas_permitidas:
        raise ValueError("Tabela não autorizada.")

    conn = sqlite3.connect(DB_PATH)
    try:
        return int(
            conn.execute(
                f"SELECT COUNT(*) FROM {tabela}"
            ).fetchone()[0]
        )
    except Exception:
        return 0
    finally:
        conn.close()


def sincronizar_central_pricing(forcar=False):
    legadas = contar_registros_tabela(
        "referencias_historicas"
    )
    simulacoes = contar_registros_tabela(
        "historico_v17"
    )
    pricing = contar_registros_tabela(
        "referencias_preco"
    )

    # Depois da primeira migração, as novas simulações já são
    # incluídas diretamente na tabela de pricing.
    precisa_migrar = (
        forcar
        or pricing == 0
        or pricing < (legadas + simulacoes)
    )

    if not precisa_migrar:
        return {
            "inseridos": 0,
            "ignorados": 0,
            "status": "Sem alterações",
        }

    r1 = migrar_referencias_historicas_para_pricing()
    r2 = migrar_simulacoes_para_pricing()

    return {
        "inseridos": (
            r1["inseridos"]
            + r2["inseridos"]
        ),
        "ignorados": (
            r1["ignorados"]
            + r2["ignorados"]
        ),
        "status": "Sincronizada",
    }


@st.cache_resource(show_spinner=False)
def inicializar_bases_pricing():
    """Executa as rotinas pesadas somente uma vez por processo."""
    status_regra = aplicar_regra_base_bi_atual()
    status_base = sincronizar_base_bi_git()

    # A migração é forçada quando a regra mudou, quando a base mudou
    # ou quando ainda não há referências consolidadas.
    forcar = (
        status_regra.get("aplicada", False)
        or status_base.get("status") == "Importada"
    )
    status_pricing = sincronizar_central_pricing(
        forcar=forcar
    )

    return status_base, status_pricing


def percentil_ponderado(valores, pesos, quantil):
    valores = np.asarray(valores, dtype=float)
    pesos = np.asarray(pesos, dtype=float)
    mascara = np.isfinite(valores) & np.isfinite(pesos) & (pesos > 0)
    valores, pesos = valores[mascara], pesos[mascara]
    if len(valores) == 0:
        return 0.0
    ordem = np.argsort(valores)
    valores, pesos = valores[ordem], pesos[ordem]
    acumulado = np.cumsum(pesos) / np.sum(pesos)
    return float(np.interp(float(quantil), acumulado, valores))


def analisar_referencias_preco(df, aluguel_minimo_atual=0.0):
    if df is None or df.empty:
        return {
            "quantidade": 0,
            "ultimo": 0.0,
            "mediana": 0.0,
            "minimo_historico": 0.0,
            "maximo_historico": 0.0,
            "preco_minimo": aluguel_minimo_atual,
            "preco_recomendado": aluguel_minimo_atual,
            "preco_premium": aluguel_minimo_atual,
            "confianca": "Baixa",
            "confianca_media": 0.0,
        }

    base = df.copy()
    base["preco_base"] = pd.to_numeric(
        base["preco_mensal_unitario"], errors="coerce"
    )
    faltantes = base["preco_base"].isna() | (base["preco_base"] <= 0)
    qtd = pd.to_numeric(base["quantidade"], errors="coerce").fillna(1).replace(0, 1)
    total = pd.to_numeric(base["valor_mensal_total"], errors="coerce")
    base.loc[faltantes, "preco_base"] = total[faltantes] / qtd[faltantes]
    base = base[(base["preco_base"] > 0)].copy()
    if base.empty:
        return analisar_referencias_preco(pd.DataFrame(), aluguel_minimo_atual)

    # Perdidas ficam disponíveis para consulta, mas não formam a recomendação.
    recomendacao = base[
        ~base["status"].fillna("").map(normalizar_texto_coluna).eq("PERDIDA")
    ].copy()
    if recomendacao.empty:
        recomendacao = base.copy()

    pesos = pd.to_numeric(
        recomendacao["confianca_pct"], errors="coerce"
    ).fillna(40).clip(lower=1)
    valores = recomendacao["preco_base"].astype(float)

    mediana = percentil_ponderado(valores, pesos, .50)
    p25 = percentil_ponderado(valores, pesos, .25)
    p75 = percentil_ponderado(valores, pesos, .75)

    confiaveis = recomendacao[
        pd.to_numeric(recomendacao["confianca_pct"], errors="coerce").fillna(0) >= 85
    ]
    minimo_confiavel = (
        float(confiaveis["preco_base"].min())
        if not confiaveis.empty
        else p25
    )

    datas = pd.to_datetime(
        base["data_referencia"], errors="coerce", dayfirst=True
    )
    if datas.notna().any():
        ultimo_idx = datas.idxmax()
    else:
        ultimo_idx = base.index[0]
    ultimo = float(base.loc[ultimo_idx, "preco_base"])

    conf_media = float(
        pd.to_numeric(base["confianca_pct"], errors="coerce")
        .fillna(0)
        .mean()
    )
    n = len(base)
    if n >= 5 and conf_media >= 80:
        nivel = "Alta"
    elif n >= 2 and conf_media >= 55:
        nivel = "Média"
    else:
        nivel = "Baixa"

    return {
        "quantidade": n,
        "ultimo": ultimo,
        "mediana": mediana,
        "minimo_historico": float(base["preco_base"].min()),
        "maximo_historico": float(base["preco_base"].max()),
        "preco_minimo": max(float(aluguel_minimo_atual or 0), minimo_confiavel),
        "preco_recomendado": max(float(aluguel_minimo_atual or 0), mediana),
        "preco_premium": max(float(aluguel_minimo_atual or 0), p75),
        "confianca": nivel,
        "confianca_media": conf_media,
    }


def salvar(registro):
    conn = sqlite3.connect(DB_PATH)
    cols = ", ".join(registro.keys())
    marks = ", ".join(["?"] * len(registro))
    cur = conn.execute(
        f"INSERT INTO historico_v17({cols}) VALUES({marks})",
        list(registro.values()),
    )
    simulacao_id = cur.lastrowid
    conn.commit()
    conn.close()

    try:
        detalhes = json.loads(registro.get("detalhes") or "{}")
    except Exception:
        detalhes = {}
    status = detalhes.get("status_referencia", "Rascunho")
    salvar_referencia_preco({
        "chave_unica": f"SIMULACAO|{simulacao_id}",
        "data_referencia": registro.get("data_hora", ""),
        "fonte": "Simulação interna",
        "tipo_fonte": "Simulação",
        "confianca_pct": confianca_referencia("Simulação interna", status),
        "status": status,
        "equipamento_codigo": detalhes.get("equipamento_codigo", ""),
        "equipamento": registro.get("equipamento", ""),
        "fabricante": registro.get("fabricante", ""),
        "linha_produto": detalhes.get("linha_produto", ""),
        "condicao": registro.get("tipo", ""),
        "origem_produto": detalhes.get("origem_produto", "Não informado"),
        "cliente_codigo": detalhes.get("cliente_codigo", ""),
        "cliente": registro.get("cliente", ""),
        "uf": detalhes.get("uf", ""),
        "prazo_meses": registro.get("prazo", 0),
        "quantidade": detalhes.get("quantidade", 1.0),
        "preco_mensal_unitario": registro.get("aluguel", 0),
        "valor_mensal_total": registro.get("aluguel", 0),
        "valor_investimento": registro.get("investimento", 0),
        "aluguel_minimo_calculado": registro.get("aluguel_minimo", 0),
        "margem_pct": registro.get("margem", 0),
        "payback_meses": registro.get("payback", 0),
        "vendedor": registro.get("responsavel", ""),
        "gerente": detalhes.get("gerente", ""),
        "representante": detalhes.get("representante", ""),
        "nota_fiscal": "",
        "contrato": "",
        "simulacao_id": simulacao_id,
        "observacao": detalhes.get("observacao_referencia", ""),
    })
    return simulacao_id


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



def salvar_referencias(registros):
    if not registros: return {"inseridos": 0, "ignorados": 0}
    conn=sqlite3.connect(DB_PATH); inseridos=ignorados=0
    for registro in registros:
        try:
            cols=", ".join(registro.keys()); marks=", ".join(["?"]*len(registro))
            conn.execute(f"INSERT INTO referencias_historicas({cols}) VALUES({marks})",list(registro.values())); inseridos+=1
        except sqlite3.IntegrityError: ignorados+=1
    conn.commit(); conn.close(); return {"inseridos":inseridos,"ignorados":ignorados}

def referencias_historicas():
    conn=sqlite3.connect(DB_PATH)
    try: df=pd.read_sql_query("SELECT * FROM referencias_historicas ORDER BY id DESC",conn)
    except Exception: df=pd.DataFrame()
    conn.close(); return df

def excluir_referencias(ids):
    if not ids: return
    conn=sqlite3.connect(DB_PATH); placeholders=','.join(['?']*len(ids))
    conn.execute(f"DELETE FROM referencias_historicas WHERE id IN ({placeholders})",[int(x) for x in ids]); conn.commit(); conn.close()

def normalizar_texto_coluna(valor):
    texto=str(valor or '').strip().upper()
    mapa=str.maketrans('ÁÀÃÂÉÊÍÓÔÕÚÇ','AAAAEEIOOOUC')
    return re.sub(r'\s+',' ',texto.translate(mapa))


SUFIXOS_VARIACAO_EQUIPAMENTO = {
    "RV",
    "TC",
    "DEMO",
    "TESTE",
    "LOC",
    "LOCACAO",
}


def normalizar_codigo_equipamento(valor):
    """Cria o código-base usado para agrupar variações do mesmo item.

    Exemplos:
    E360, E360_01, E360_RV e E360_TC passam a ser E360.

    A remoção numérica é conservadora: considera apenas sufixos
    iniciados por zero, como _01, _02 ou _001, evitando alterar
    códigos em que o número após o separador faça parte do modelo.
    """
    texto = normalizar_texto_coluna(valor)

    if not texto:
        return ""

    # Corrige códigos numéricos que vieram do Excel como 123.0.
    if re.fullmatch(r"\d+\.0", texto):
        texto = texto[:-2]

    texto = re.sub(r"[\s/\\-]+", "_", texto)
    texto = re.sub(r"_+", "_", texto).strip("_")

    while texto:
        partes = texto.split("_")
        if len(partes) <= 1:
            break

        sufixo = partes[-1]
        sufixo_numerico = bool(
            re.fullmatch(r"0\d{1,2}", sufixo)
        )
        sufixo_conhecido = (
            sufixo in SUFIXOS_VARIACAO_EQUIPAMENTO
        )

        if not (sufixo_numerico or sufixo_conhecido):
            break

        texto = "_".join(partes[:-1]).strip("_")

    return texto


def normalizar_nome_equipamento(valor):
    """Agrupa nomes que diferem somente por sufixos operacionais."""
    texto = normalizar_texto_coluna(valor)

    if not texto:
        return ""

    # Mantém a descrição legível, mas normaliza separadores finais.
    texto = re.sub(r"[\s/\\-]+", "_", texto)
    texto = re.sub(r"_+", "_", texto).strip("_")

    while texto:
        partes = texto.split("_")
        if len(partes) <= 1:
            break

        sufixo = partes[-1]
        if (
            re.fullmatch(r"0\d{1,2}", sufixo)
            or sufixo in SUFIXOS_VARIACAO_EQUIPAMENTO
        ):
            texto = "_".join(partes[:-1]).strip("_")
        else:
            break

    return texto


def chave_agrupamento_equipamento(codigo, equipamento):
    codigo_base = normalizar_codigo_equipamento(codigo)
    if codigo_base:
        return f"COD|{codigo_base}"

    nome_base = normalizar_nome_equipamento(equipamento)
    return f"DESC|{nome_base}" if nome_base else ""


def texto_mais_frequente(valores):
    serie = pd.Series(valores).fillna("").astype(str).str.strip()
    serie = serie[serie.ne("")]
    if serie.empty:
        return ""
    moda = serie.mode()
    return str(moda.iloc[0] if not moda.empty else serie.iloc[0])


@st.cache_data(ttl=300, show_spinner=False)
def carregar_referencias_para_cotacao():
    return referencias_preco()


def buscar_preco_historico_equipamento(
    codigo="",
    equipamento="",
    termo="",
):
    refs = carregar_referencias_para_cotacao()

    if refs.empty:
        return pd.DataFrame(), "", []

    refs = refs.copy()
    refs["_codigo_base"] = (
        refs["equipamento_codigo"]
        .fillna("")
        .map(normalizar_codigo_equipamento)
    )
    refs["_equipamento_base"] = (
        refs["equipamento"]
        .fillna("")
        .map(normalizar_nome_equipamento)
    )
    refs["_chave_equipamento"] = refs.apply(
        lambda linha: chave_agrupamento_equipamento(
            linha.get("equipamento_codigo", ""),
            linha.get("equipamento", ""),
        ),
        axis=1,
    )

    chave_alvo = chave_agrupamento_equipamento(
        codigo,
        equipamento,
    )

    if chave_alvo:
        base = refs[
            refs["_chave_equipamento"].eq(chave_alvo)
        ].copy()
    else:
        termo_n = normalizar_texto_coluna(termo)
        if not termo_n:
            return pd.DataFrame(), "", []

        mascara = (
            refs["_codigo_base"]
            .fillna("")
            .map(normalizar_texto_coluna)
            .str.contains(re.escape(termo_n), na=False)
            |
            refs["_equipamento_base"]
            .fillna("")
            .map(normalizar_texto_coluna)
            .str.contains(re.escape(termo_n), na=False)
        )
        candidatos = refs[mascara].copy()

        if candidatos.empty:
            return pd.DataFrame(), "", []

        chave_alvo = (
            candidatos["_chave_equipamento"]
            .value_counts()
            .index[0]
        )
        base = candidatos[
            candidatos["_chave_equipamento"].eq(chave_alvo)
        ].copy()

    variacoes = sorted(
        {
            texto_limpo(valor)
            for valor in base["equipamento_codigo"].tolist()
            if texto_limpo(valor)
        }
    )

    return base, chave_alvo, variacoes


def localizar_coluna(df, possibilidades):
    mapa={normalizar_texto_coluna(c):c for c in df.columns}
    for p in possibilidades:
        if normalizar_texto_coluna(p) in mapa: return mapa[normalizar_texto_coluna(p)]
    return None

def data_excel_para_br(valor):
    if pd.isna(valor) or valor=='': return ''
    if isinstance(valor,(int,float,np.integer,np.floating)):
        try:return (pd.Timestamp('1899-12-30')+pd.to_timedelta(float(valor),unit='D')).strftime('%d/%m/%Y')
        except Exception:pass
    dt=pd.to_datetime(valor,errors='coerce',dayfirst=True)
    return str(valor) if pd.isna(dt) else dt.strftime('%d/%m/%Y')

def texto_limpo(valor): return '' if pd.isna(valor) else str(valor).strip()
def numero_limpo(valor): return parse(valor)

def chave_historica(*partes):
    import hashlib
    base='|'.join(normalizar_texto_coluna(p) for p in partes)
    return hashlib.sha256(base.encode('utf-8')).hexdigest()

def importar_controle_contratos(arquivo):
    abas=pd.read_excel(arquivo,sheet_name=None,engine='openpyxl')
    nome=next((n for n in abas if normalizar_texto_coluna(n)=='FIRST'),None)
    if not nome: raise ValueError('A aba FIRST não foi encontrada.')
    df=abas[nome].dropna(how='all').copy()
    c={
      'contrato':localizar_coluna(df,['Nº CT','N CT','CONTRATO']), 'origem':localizar_coluna(df,['ORIGEM']),
      'cod':localizar_coluna(df,['COD. CLIENTE','COD CLIENTE']), 'cnpj':localizar_coluna(df,['CNPJ/CPF','CNPJ']),
      'cliente':localizar_coluna(df,['RAZÃO SOCIAL','RAZAO SOCIAL']), 'inicio':localizar_coluna(df,['INICIO','INÍCIO']),
      'sla':localizar_coluna(df,['SLA']), 'valor':localizar_coluna(df,['VALOR FATURAMENTO','VALOR']),
      'vendedor':localizar_coluna(df,['VENDEDOR']), 'gerente':localizar_coluna(df,['GERENTE']),
      'linha':localizar_coluna(df,['LINHA DE PRODUTO'])}
    if not c['contrato'] or not c['cliente'] or not c['valor']: raise ValueError('Colunas obrigatórias não encontradas.')
    agora=datetime.now(ZoneInfo('America/Sao_Paulo')).strftime('%d/%m/%Y %H:%M:%S'); regs=[]
    for _,r in df.iterrows():
        contrato=texto_limpo(r.get(c['contrato'])); cliente=texto_limpo(r.get(c['cliente'])); valor=numero_limpo(r.get(c['valor']))
        if (not contrato and not cliente) or valor<=0: continue
        linha=texto_limpo(r.get(c['linha'])) if c['linha'] else ''; cod=texto_limpo(r.get(c['cod'])) if c['cod'] else ''
        regs.append({'chave_unica':chave_historica('CONTRATO',contrato,cod,cliente,valor),'data_importacao':agora,'fonte':'Controle de Contratos','tipo_referencia':'Contrato ativo','identificador':contrato,'data_referencia':data_excel_para_br(r.get(c['inicio'])) if c['inicio'] else '', 'cliente_codigo':cod,'cliente':cliente,'cnpj':texto_limpo(r.get(c['cnpj'])) if c['cnpj'] else '','equipamento_codigo':'','equipamento':linha,'linha_produto':linha,'quantidade':1.0,'valor_unitario':valor,'valor_mensal':valor,'valor_total':valor,'vendedor':texto_limpo(r.get(c['vendedor'])) if c['vendedor'] else '','gerente':texto_limpo(r.get(c['gerente'])) if c['gerente'] else '','sla':texto_limpo(r.get(c['sla'])) if c['sla'] else '','origem_contrato':texto_limpo(r.get(c['origem'])) if c['origem'] else '','nota_fiscal':'','observacao':'Valor mensal contratual importado; sem custos, margem ou payback.'})
    return salvar_referencias(regs)

def importar_base_bi(arquivo):
    """Leva os preços faturados de locação diretamente à Central.

    Regras adotadas:
    - somente linhas com NOVA = LOCAÇÃO;
    - valor total da referência = VALOR BRUTO;
    - preço por equipamento = VALOR BRUTO / QUANTIDADE;
    - linhas sem cliente, produto ou valor bruto positivo são descartadas.
    """
    excel = pd.ExcelFile(arquivo, engine="openpyxl")
    nome = next(
        (
            nome_aba
            for nome_aba in excel.sheet_names
            if "BANCO DE DADOS FATURAMENTO"
            in normalizar_texto_coluna(nome_aba)
        ),
        None,
    )

    if not nome:
        raise ValueError(
            "A planilha de faturamento não foi encontrada na BASE BI."
        )

    # Carrega somente a aba necessária, evitando abrir as demais abas.
    df = pd.read_excel(
        arquivo,
        sheet_name=nome,
        engine="openpyxl",
    ).dropna(how="all")

    c = {
        chave: localizar_coluna(df, alternativas)
        for chave, alternativas in {
            "numero": ["NUMERO", "NÚMERO"],
            "data": ["DT EMISSAO", "DT EMISSÃO"],
            "cod": ["CLIENTE"],
            "cliente": ["NOME DO CLIENTE"],
            "resp": ["VENDEDOR / REPRESENTANTE", "VENDEDOR"],
            "produto": ["PRODUTO"],
            "desc": ["DESCRIÇÃO", "DESCRICAO"],
            "qtd": ["QUANTIDADE"],
            "bruto": ["VALOR BRUTO"],
            "nf": ["NOTA FISCAL"],
            "gerente": ["GERENTE"],
            "fornecedor": ["FORNECEDOR"],
            "linha": ["LINHA DE PRODUTO"],
            "nova": ["NOVA"],
        }.items()
    }

    obrigatorias = [
        c["nova"],
        c["cliente"],
        c["produto"],
        c["bruto"],
    ]
    if any(coluna is None for coluna in obrigatorias):
        raise ValueError(
            "A BASE BI precisa conter NOVA, NOME DO CLIENTE, "
            "PRODUTO e VALOR BRUTO."
        )

    natureza = (
        df[c["nova"]]
        .fillna("")
        .astype(str)
        .map(normalizar_texto_coluna)
    )
    df = df[natureza.eq("LOCACAO")].copy()

    agora = datetime.now(
        ZoneInfo("America/Sao_Paulo")
    ).strftime("%d/%m/%Y %H:%M:%S")

    registros_historicos = []
    referencias_central = []

    for _, row in df.iterrows():
        cliente = texto_limpo(row.get(c["cliente"]))
        produto = texto_limpo(row.get(c["produto"]))
        descricao = (
            texto_limpo(row.get(c["desc"]))
            if c["desc"]
            else ""
        )
        nota = (
            texto_limpo(row.get(c["nf"]))
            if c["nf"]
            else ""
        )
        numero = (
            texto_limpo(row.get(c["numero"]))
            if c["numero"]
            else ""
        )
        data_referencia = (
            data_excel_para_br(row.get(c["data"]))
            if c["data"]
            else ""
        )

        quantidade = (
            numero_limpo(row.get(c["qtd"]))
            if c["qtd"]
            else 1.0
        )
        if quantidade <= 0:
            quantidade = 1.0

        valor_bruto = numero_limpo(row.get(c["bruto"]))

        if not cliente or not produto or valor_bruto <= 0:
            continue

        preco_por_equipamento = valor_bruto / quantidade
        equipamento = descricao or produto
        linha = (
            texto_limpo(row.get(c["linha"]))
            if c["linha"]
            else ""
        )
        vendedor = (
            texto_limpo(row.get(c["resp"]))
            if c["resp"]
            else ""
        )
        gerente = (
            texto_limpo(row.get(c["gerente"]))
            if c["gerente"]
            else ""
        )
        cliente_codigo = (
            texto_limpo(row.get(c["cod"]))
            if c["cod"]
            else ""
        )
        fornecedor = (
            texto_limpo(row.get(c["fornecedor"]))
            if c["fornecedor"]
            else ""
        )

        chave_base = chave_historica(
            BASE_BI_REGRA_IMPORTACAO,
            nota,
            numero,
            produto,
            cliente,
            quantidade,
            valor_bruto,
        )

        registros_historicos.append(
            {
                "chave_unica": chave_base,
                "data_importacao": agora,
                "fonte": "BASE BI - Locação faturada",
                "tipo_referencia": "Preço faturado",
                "identificador": numero,
                "data_referencia": data_referencia,
                "cliente_codigo": cliente_codigo,
                "cliente": cliente,
                "cnpj": "",
                "equipamento_codigo": produto,
                "equipamento": equipamento,
                "linha_produto": linha,
                "quantidade": quantidade,
                "valor_unitario": preco_por_equipamento,
                "valor_mensal": valor_bruto,
                "valor_total": valor_bruto,
                "vendedor": vendedor,
                "gerente": gerente,
                "sla": "",
                "origem_contrato": fornecedor,
                "nota_fiscal": nota,
                "observacao": (
                    "Preço faturado de locação. Valor total conforme "
                    "VALOR BRUTO e valor por equipamento conforme quantidade."
                ),
            }
        )

        # Grava diretamente na tabela consultada pela Central de Preços.
        referencias_central.append(
            {
                "chave_unica": "BASEBI|" + chave_base,
                "data_referencia": data_referencia,
                "fonte": "BASE BI - Locação faturada",
                "tipo_fonte": "Faturamento real",
                "confianca_pct": 100.0,
                "status": "Faturada",
                "equipamento_codigo": produto,
                "equipamento": equipamento,
                "fabricante": fornecedor,
                "linha_produto": linha,
                "condicao": "Não informado",
                "origem_produto": "Não informado",
                "cliente_codigo": cliente_codigo,
                "cliente": cliente,
                "uf": "",
                "prazo_meses": None,
                "quantidade": quantidade,
                "preco_mensal_unitario": preco_por_equipamento,
                "valor_mensal_total": valor_bruto,
                "valor_investimento": None,
                "aluguel_minimo_calculado": None,
                "margem_pct": None,
                "payback_meses": None,
                "vendedor": vendedor,
                "gerente": gerente,
                "representante": "",
                "nota_fiscal": nota,
                "contrato": "",
                "simulacao_id": None,
                "observacao": (
                    "Referência real de locação faturada, obtida da BASE BI."
                ),
            }
        )

    resultado_historico = salvar_referencias(
        registros_historicos
    )
    resultado_central = salvar_referencias_preco_lote(
        referencias_central
    )

    return {
        "inseridos": resultado_historico["inseridos"],
        "ignorados": resultado_historico["ignorados"],
        "central_inseridos": resultado_central["inseridos"],
        "central_ignorados": resultado_central["ignorados"],
        "linhas_locacao": int(len(df)),
        "referencias_validas": int(len(referencias_central)),
    }


def localizar_base_bi_git():
    """Localiza a BASE BI disponível no repositório."""
    for nome in BASE_BI_GIT_ALTERNATIVAS:
        caminho = Path(nome)
        if caminho.exists() and caminho.is_file():
            return caminho
    return None


@st.cache_data(show_spinner=False)
def _hash_sha256_cache(caminho_str, tamanho, mtime_ns):
    """Calcula o hash apenas uma vez por versão física do arquivo."""
    digest = hashlib.sha256()
    with open(caminho_str, "rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


def hash_sha256_arquivo(caminho):
    caminho = Path(caminho)
    stat = caminho.stat()
    return _hash_sha256_cache(
        str(caminho.resolve()),
        int(stat.st_size),
        int(stat.st_mtime_ns),
    )


def consultar_importacao_por_hash(hash_arquivo):
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            """
            SELECT id, caminho, nome_arquivo, data_importacao,
                   registros_inseridos, registros_ignorados, status
            FROM arquivos_importados
            WHERE hash_sha256 = ?
            LIMIT 1
            """,
            (hash_arquivo,),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return None

    return {
        "id": row[0],
        "caminho": row[1],
        "nome_arquivo": row[2],
        "data_importacao": row[3],
        "inseridos": row[4],
        "ignorados": row[5],
        "status": row[6],
    }


def registrar_arquivo_importado(
    caminho,
    hash_arquivo,
    resultado,
    status="Importado",
    mensagem="",
):
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO arquivos_importados(
                caminho,
                nome_arquivo,
                hash_sha256,
                data_importacao,
                fonte,
                registros_inseridos,
                registros_ignorados,
                status,
                mensagem
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(caminho),
                Path(caminho).name,
                hash_arquivo,
                datetime.now(
                    ZoneInfo("America/Sao_Paulo")
                ).strftime("%d/%m/%Y %H:%M:%S"),
                "BASE BI no Git",
                int(resultado.get("inseridos", 0)),
                int(resultado.get("ignorados", 0)),
                status,
                mensagem,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def historico_importacoes_git():
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query(
            """
            SELECT id, nome_arquivo, data_importacao, fonte,
                   registros_inseridos, registros_ignorados,
                   status, mensagem
            FROM arquivos_importados
            ORDER BY id DESC
            """,
            conn,
        )
    except Exception:
        df = pd.DataFrame()
    finally:
        conn.close()
    return df



def hash_regra_base_bi():
    return hashlib.sha256(
        BASE_BI_REGRA_IMPORTACAO.encode("utf-8")
    ).hexdigest()


def regra_base_bi_ja_aplicada():
    return consultar_importacao_por_hash(
        hash_regra_base_bi()
    ) is not None


def limpar_referencias_antigas_base_bi():
    """Remove referências importadas pelas regras anteriores.

    Não afeta contratos, simulações nem referências manuais.
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        historicas = conn.execute(
            """
            DELETE FROM referencias_historicas
            WHERE UPPER(COALESCE(fonte, ''))
                  LIKE 'BASE BI%'
            """
        ).rowcount

        pricing = conn.execute(
            """
            DELETE FROM referencias_preco
            WHERE UPPER(COALESCE(fonte, ''))
                  LIKE 'BASE BI%'
            """
        ).rowcount

        conn.commit()
    finally:
        conn.close()

    return {
        "historicas_excluidas": max(int(historicas or 0), 0),
        "pricing_excluidas": max(int(pricing or 0), 0),
    }


def registrar_regra_base_bi_aplicada(resultado_limpeza):
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO arquivos_importados(
                caminho,
                nome_arquivo,
                hash_sha256,
                data_importacao,
                fonte,
                registros_inseridos,
                registros_ignorados,
                status,
                mensagem
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "",
                BASE_BI_REGRA_IMPORTACAO,
                hash_regra_base_bi(),
                datetime.now(
                    ZoneInfo("America/Sao_Paulo")
                ).strftime("%d/%m/%Y %H:%M:%S"),
                "Regra de importação BASE BI",
                0,
                0,
                "Regra aplicada",
                (
                    f"{resultado_limpeza['historicas_excluidas']} "
                    "referências históricas antigas e "
                    f"{resultado_limpeza['pricing_excluidas']} "
                    "referências de pricing antigas removidas."
                ),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def aplicar_regra_base_bi_atual():
    if regra_base_bi_ja_aplicada():
        return {
            "aplicada": False,
            "mensagem": "Regra atual já aplicada.",
        }

    resultado = limpar_referencias_antigas_base_bi()
    registrar_regra_base_bi_aplicada(resultado)

    return {
        "aplicada": True,
        "mensagem": (
            "Referências antigas da BASE BI foram removidas "
            "para reconstrução pela regra atual."
        ),
        **resultado,
    }



def sincronizar_base_bi_git():
    """Importa a BASE BI do Git somente quando o conteúdo mudar.

    Se o banco SQLite for recriado após um reinício, a base do Git será
    importada novamente e reconstruirá o histórico de consulta.
    """
    caminho = localizar_base_bi_git()

    if caminho is None:
        return {
            "status": "Ausente",
            "mensagem": (
                "Nenhum arquivo base_bi.xlsx foi encontrado "
                "na raiz do repositório."
            ),
            "caminho": "",
            "inseridos": 0,
            "ignorados": 0,
        }

    hash_conteudo = hash_sha256_arquivo(caminho)
    hash_arquivo = hashlib.sha256(
        (
            hash_conteudo
            + "|"
            + BASE_BI_REGRA_IMPORTACAO
        ).encode("utf-8")
    ).hexdigest()
    existente = consultar_importacao_por_hash(hash_arquivo)

    if existente:
        return {
            "status": "Atualizada",
            "mensagem": (
                f"{caminho.name} já foi sincronizada em "
                f"{existente['data_importacao']}."
            ),
            "caminho": str(caminho),
            "inseridos": existente["inseridos"],
            "ignorados": existente["ignorados"],
        }

    try:
        resultado = importar_base_bi(caminho)
        registrar_arquivo_importado(
            caminho=caminho,
            hash_arquivo=hash_arquivo,
            resultado=resultado,
            status="Importado",
            mensagem="Sincronização automática concluída.",
        )
        return {
            "status": "Importada",
            "mensagem": (
                f"{resultado.get('central_inseridos', resultado['inseridos'])} "
                "preços disponibilizados para consulta; "
                f"{resultado.get('central_ignorados', resultado['ignorados'])} "
                "registros repetidos ignorados."
            ),
            "caminho": str(caminho),
            "inseridos": resultado["inseridos"],
            "ignorados": resultado["ignorados"],
        }
    except Exception as erro:
        return {
            "status": "Erro",
            "mensagem": str(erro),
            "caminho": str(caminho),
            "inseridos": 0,
            "ignorados": 0,
        }


def salvar_cotacao(registro):
    conn = sqlite3.connect(DB_PATH)
    cols = ", ".join(registro.keys())
    marks = ", ".join(["?"] * len(registro))
    cur = conn.execute(
        f"INSERT INTO cotacoes_dolar({cols}) VALUES({marks})",
        list(registro.values()),
    )
    conn.commit()
    cotacao_id = cur.lastrowid
    conn.close()
    return cotacao_id


def historico_cotacoes():
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query(
            "SELECT * FROM cotacoes_dolar ORDER BY id DESC",
            conn,
        )
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df


def excluir_cotacoes(ids):
    if not ids:
        return
    conn = sqlite3.connect(DB_PATH)
    placeholders = ",".join(["?"] * len(ids))
    conn.execute(
        f"DELETE FROM cotacoes_dolar WHERE id IN ({placeholders})",
        [int(x) for x in ids],
    )
    conn.commit()
    conn.close()


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


def input_rs_compacto(label, value, key, help_text=None):
    texto = st.text_input(
        label,
        value=moeda(value),
        key=key,
        help=help_text,
    )
    return parse(texto)


def aplicar_valor_monetario(chave, valor):
    """Atualiza um campo monetário por callback, antes do novo render."""
    st.session_state[chave] = moeda(valor)


def avaliar_preco_negociado(
    aluguel,
    preco_minimo,
    preco_recomendado,
    preco_protegido,
):
    """Classifica a condição comercial informada pelo vendedor."""
    aluguel = float(aluguel or 0)
    preco_minimo = float(preco_minimo or 0)
    preco_recomendado = float(preco_recomendado or 0)
    preco_protegido = float(preco_protegido or 0)

    if aluguel <= 0:
        return {
            "classificacao": "Informe o valor",
            "nivel": "neutro",
            "mensagem": (
                "Digite o aluguel que está sendo negociado para receber "
                "a avaliação da operação."
            ),
            "exige_aval": False,
        }

    if aluguel < preco_minimo:
        falta = preco_minimo - aluguel
        pct = (
            falta / preco_minimo * 100
            if preco_minimo > 0
            else 0
        )
        return {
            "classificacao": "Não recomendado",
            "nivel": "critico",
            "mensagem": (
                f"O valor está {moeda(falta)} ({perc(pct)}) abaixo do "
                "mínimo necessário. A operação exige justificativa e "
                "aval expresso da gerência."
            ),
            "exige_aval": True,
        }

    if aluguel < preco_recomendado:
        falta = preco_recomendado - aluguel
        pct = (
            falta / preco_recomendado * 100
            if preco_recomendado > 0
            else 0
        )
        return {
            "classificacao": "Viável com atenção",
            "nivel": "atencao",
            "mensagem": (
                f"A operação cobre o mínimo, mas está {moeda(falta)} "
                f"({perc(pct)}) abaixo da faixa recomendada. "
                "Solicite aval da gerência antes de liberar."
            ),
            "exige_aval": True,
        }

    if aluguel < preco_protegido:
        ganho = aluguel - preco_recomendado
        return {
            "classificacao": "Boa negociação",
            "nivel": "bom",
            "mensagem": (
                f"O valor está dentro da faixa recomendada e possui "
                f"{moeda(ganho)} de proteção acima da referência."
            ),
            "exige_aval": False,
        }

    ganho = aluguel - preco_protegido
    return {
        "classificacao": "Excelente negociação",
        "nivel": "excelente",
        "mensagem": (
            f"O valor alcançou a faixa protegida e está "
            f"{moeda(ganho)} acima dela."
        ),
        "exige_aval": False,
    }


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


def comissao_total(vendedor, gerente, representante):
    """Soma todas as comissões informadas.

    Os três campos são independentes e podem ser usados simultaneamente.
    """
    return (
        max(float(vendedor), 0.0)
        + max(float(gerente), 0.0)
        + max(float(representante), 0.0)
    )


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
    """Percentual anual aplicado sobre o valor econômico atual."""
    if depreciacao_atual_pct <= 20:
        return 4.0
    if depreciacao_atual_pct <= 40:
        return 5.0
    if depreciacao_atual_pct <= 60:
        return 6.0
    if depreciacao_atual_pct <= 80:
        return 7.0
    return 8.0


def horas_tecnicas_por_depreciacao(depreciacao_atual_pct):
    """Estimativa inicial de horas técnicas mensais."""
    if depreciacao_atual_pct <= 20:
        return 2.0
    if depreciacao_atual_pct <= 40:
        return 3.0
    if depreciacao_atual_pct <= 60:
        return 4.0
    if depreciacao_atual_pct <= 80:
        return 5.0
    return 6.0


def fator_conservacao_usado(estado):
    return {
        "Excelente": 0.80,
        "Bom": 1.00,
        "Regular": 1.25,
    }.get(estado, 1.00)


def base_manutencao_usado(valor_aquisicao, valor_contabil):
    """Valor atual do ativo, com piso residual de 20% do original."""
    valor_aquisicao = max(float(valor_aquisicao or 0), 0.0)
    valor_contabil = max(float(valor_contabil or 0), 0.0)
    return max(valor_contabil, valor_aquisicao * 0.20)


def fatores_faixa_preco_usado(depreciacao_atual_pct):
    """A proteção adicional cai gradualmente conforme a depreciação."""
    if depreciacao_atual_pct <= 20:
        return 1.15, 1.25
    if depreciacao_atual_pct <= 40:
        return 1.12, 1.22
    if depreciacao_atual_pct <= 60:
        return 1.10, 1.20
    if depreciacao_atual_pct <= 80:
        return 1.08, 1.18
    return 1.05, 1.15


def simulacao_base_usado(
    valor_ativo,
    data_aquisicao,
    data_inicio,
    prazo=24,
    vida_util=10.0,
    imposto_pct=IMPOSTO_ATUAL,
    comissao_pct=COMISSAO_VENDEDOR + COMISSAO_GERENTE,
    margem_pct=MARGEM_USADO_PADRAO,
    reserva_risco_pct=RESERVA_RISCO_USADO_PADRAO,
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
    base_manutencao = base_manutencao_usado(
        valor_ativo,
        dep_atual["valor_contabil"],
    )
    manutencao_mensal = (
        base_manutencao * taxa_anual / 100 / 12
    )

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
        "base_manutencao": base_manutencao,
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
# PROPOSTA EM PDF
# ======================================================
def texto_pdf(valor):
    texto = str(valor or "")
    return (
        texto.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def gerar_proposta_pdf(
    tipo,
    cliente,
    equipamento,
    fabricante,
    responsavel,
    prazo,
    aluguel,
    investimento,
    resultado_atual,
    resultado_reforma,
    comissao_pct,
    origem_investimento,
    detalhes=None,
    observacoes="",
    validade_dias=15,
):
    buffer = BytesIO()

    largura, altura = A4
    margem = 16 * mm

    estilos = getSampleStyleSheet()
    estilos.add(
        ParagraphStyle(
            name="FirstTitle",
            parent=estilos["Title"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#0B2F4A"),
            alignment=TA_LEFT,
            spaceAfter=6,
        )
    )
    estilos.add(
        ParagraphStyle(
            name="FirstSub",
            parent=estilos["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#64748B"),
            alignment=TA_LEFT,
        )
    )
    estilos.add(
        ParagraphStyle(
            name="Section",
            parent=estilos["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#0B2F4A"),
            spaceBefore=8,
            spaceAfter=6,
        )
    )
    estilos.add(
        ParagraphStyle(
            name="BodySmall",
            parent=estilos["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#243447"),
        )
    )
    estilos.add(
        ParagraphStyle(
            name="Footer",
            parent=estilos["Normal"],
            fontName="Helvetica",
            fontSize=7.5,
            textColor=colors.HexColor("#64748B"),
            alignment=TA_CENTER,
        )
    )

    def cabecalho_rodape(canvas, doc):
        canvas.saveState()

        # Faixa superior
        canvas.setFillColor(colors.HexColor("#0B2F4A"))
        canvas.rect(0, altura - 18 * mm, largura, 18 * mm, fill=1, stroke=0)

        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 13)
        canvas.drawString(margem, altura - 11 * mm, "FIRST MEDICAL")

        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(
            largura - margem,
            altura - 11 * mm,
            "Análise interna de locação",
        )

        # Rodapé
        canvas.setStrokeColor(colors.HexColor("#D9E3EC"))
        canvas.line(
            margem,
            13 * mm,
            largura - margem,
            13 * mm,
        )

        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.setFont("Helvetica", 7)
        canvas.drawCentredString(
            largura / 2,
            8 * mm,
            f"Documento gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')} - Página {doc.page}",
        )
        canvas.restoreState()

    frame = Frame(
        margem,
        18 * mm,
        largura - 2 * margem,
        altura - 42 * mm,
        id="normal",
    )
    template = PageTemplate(
        id="First",
        frames=[frame],
        onPage=cabecalho_rodape,
    )
    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=margem,
        leftMargin=margem,
        topMargin=24 * mm,
        bottomMargin=18 * mm,
        pageTemplates=[template],
    )

    story = []

    validade = date.today() + timedelta(days=int(validade_dias))

    story.append(
        Paragraph(
            f"Formação Interna de Preço - Equipamento {texto_pdf(tipo)}",
            estilos["FirstTitle"],
        )
    )
    story.append(
        Paragraph(
            (
                f"Validade da análise: {validade.strftime('%d/%m/%Y')} | "
                "Documento interno sujeito à aprovação da gerência"
            ),
            estilos["FirstSub"],
        )
    )
    story.append(Spacer(1, 7 * mm))

    story.append(Paragraph("Dados da análise", estilos["Section"]))

    dados = [
        ["Cliente", texto_pdf(cliente or "Não informado")],
        ["Equipamento", texto_pdf(equipamento or "Não informado")],
        ["Fabricante / linha", texto_pdf(fabricante or "Não informado")],
        ["Responsável comercial", texto_pdf(responsavel or "Não informado")],
        ["Prazo da locação", f"{int(prazo)} meses"],
        ["Origem do investimento", texto_pdf(origem_investimento)],
    ]

    tabela_dados = Table(
        dados,
        colWidths=[48 * mm, 127 * mm],
        repeatRows=0,
    )
    tabela_dados.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EEF3F8")),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#0B2F4A")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D9E3EC")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(tabela_dados)
    story.append(Spacer(1, 5 * mm))

    story.append(Paragraph("Condições comerciais", estilos["Section"]))

    condicoes = [
        ["Aluguel mensal proposto", moeda(aluguel)],
        ["Investimento considerado", moeda(investimento)],
        ["Receita total estimada", moeda(resultado_atual["receita"])],
        ["Impostos atuais", moeda(resultado_atual["impostos"])],
        ["Comissões consideradas", f"{perc(comissao_pct)} - {moeda(resultado_atual['comissao'])}"],
        ["Lucro estimado", moeda(resultado_atual["lucro"])],
        ["Margem estimada", perc(resultado_atual["margem"])],
        ["Payback estimado", meses(resultado_atual["payback"])],
        ["Aluguel mínimo calculado", moeda(resultado_atual["aluguel_minimo"])],
    ]

    tabela_condicoes = Table(
        condicoes,
        colWidths=[75 * mm, 100 * mm],
    )
    tabela_condicoes.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F6F9FC")),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#0B2F4A")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D9E3EC")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(tabela_condicoes)
    story.append(Spacer(1, 5 * mm))

    if resultado_reforma:
        story.append(
            Paragraph(
                "Simulação pós-reforma tributária",
                estilos["Section"],
            )
        )

        reforma = [
            ["IBS/CBS bruto estimado", moeda(resultado_reforma["tributo_bruto"])],
            ["Crédito estimado", moeda(resultado_reforma["credito"])],
            ["IBS/CBS líquido", moeda(resultado_reforma["tributo_liquido"])],
            ["Lucro estimado pós-reforma", moeda(resultado_reforma["lucro"])],
        ]

        tabela_reforma = Table(
            reforma,
            colWidths=[75 * mm, 100 * mm],
        )
        tabela_reforma.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EFFAF6")),
                    ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#115E59")),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CFE8DE")),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(tabela_reforma)
        story.append(Spacer(1, 5 * mm))

    if detalhes:
        story.append(Paragraph("Premissas da operação", estilos["Section"]))

        linhas_detalhes = []
        for chave, valor in detalhes.items():
            rotulo = (
                str(chave)
                .replace("_", " ")
                .strip()
                .capitalize()
            )
            if isinstance(valor, float):
                valor_texto = (
                    moeda(valor)
                    if any(
                        termo in chave
                        for termo in [
                            "valor",
                            "custo",
                            "fob",
                            "investimento",
                            "manutencao",
                            "pecas",
                            "seguro",
                            "parcela",
                            "hora",
                            "aluguel",
                        ]
                    )
                    else f"{valor:.2f}"
                )
            else:
                valor_texto = str(valor)
            linhas_detalhes.append(
                [texto_pdf(rotulo), texto_pdf(valor_texto)]
            )

        if linhas_detalhes:
            tabela_detalhes = Table(
                linhas_detalhes,
                colWidths=[75 * mm, 100 * mm],
            )
            tabela_detalhes.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#FAFAFA")),
                        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                        ("FONTSIZE", (0, 0), (-1, -1), 7.8),
                        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E5E7EB")),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ]
                )
            )
            story.append(tabela_detalhes)
            story.append(Spacer(1, 5 * mm))

    story.append(Paragraph("Observações", estilos["Section"]))
    texto_obs = observacoes.strip() if observacoes else (
        "Valores sujeitos à validação comercial, técnica, tributária e "
        "disponibilidade do equipamento. Reajustes, fretes, instalações, "
        "treinamentos, peças, consumíveis e demais condições deverão seguir "
        "o contrato definitivo."
    )
    story.append(
        Paragraph(
            texto_pdf(texto_obs),
            estilos["BodySmall"],
        )
    )
    story.append(Spacer(1, 10 * mm))

    assinaturas = Table(
        [
            ["", ""],
            [
                texto_pdf(responsavel or "RESPONSÁVEL PELA ANÁLISE"),
                "GERÊNCIA",
            ],
            [
                "Elaborado por",
                "Aval e liberação do preço",
            ],
        ],
        colWidths=[82 * mm, 82 * mm],
    )
    assinaturas.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, 1), (0, 1), 0.6, colors.HexColor("#64748B")),
                ("LINEABOVE", (1, 1), (1, 1), 0.6, colors.HexColor("#64748B")),
                ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
                ("FONTNAME", (0, 2), (-1, 2), "Helvetica"),
                ("FONTSIZE", (0, 1), (-1, 2), 8),
                ("ALIGN", (0, 1), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 1), (-1, -1), 4),
            ]
        )
    )
    story.append(assinaturas)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


# ======================================================
# SINCRONIZAÇÃO AUTOMÁTICA DA BASE HISTÓRICA DO GIT
# ======================================================
status_base_bi_git, status_central_pricing = (
    inicializar_bases_pricing()
)

# Caso uma versão anterior tenha registrado a atualização sem alimentar
# a Central, reconstrói as referências automaticamente uma única vez.
if contar_registros_tabela("referencias_preco") == 0:
    _base_para_recuperacao = localizar_base_bi_git()
    if _base_para_recuperacao is not None:
        try:
            _resultado_recuperacao = importar_base_bi(
                _base_para_recuperacao
            )
            status_central_pricing = sincronizar_central_pricing(
                forcar=True
            )
            status_base_bi_git = {
                **status_base_bi_git,
                "status": "Importada",
                "mensagem": (
                    f"{_resultado_recuperacao.get('central_inseridos', 0)} "
                    "preços carregados para consulta."
                ),
            }
        except Exception as _erro_recuperacao:
            status_base_bi_git = {
                **status_base_bi_git,
                "status": "Erro",
                "mensagem": str(_erro_recuperacao),
            }

# ======================================================
# MENU
# ======================================================
st.sidebar.markdown("## FIRST MEDICAL")
st.sidebar.markdown("### Central de Preços de Locação")
st.sidebar.markdown("---")

menu = st.sidebar.radio(
    "Menu",
    [
        "Resumo Executivo",
        "1 - Central de Consulta",
        "2 - Formação de Preço - Novos",
        "3 - Formação de Preço - Usados",
        "4 - Histórico de Simulações",
        "5 - Equipamentos e Ativos",
        "6 - Configurações de Cálculo",
    ],
)

# Define o prefixo usado pelas chaves persistentes de cada aba.
st.session_state["_active_menu"] = menu

st.sidebar.markdown("---")
st.sidebar.caption(
    "Consulte preços, monte propostas e acompanhe as simulações."
)

with st.sidebar.expander(
    "Atualização do histórico de preços",
    expanded=False,
):
    status_atualizacao = status_base_bi_git.get("status", "")

    if status_atualizacao == "Importada":
        st.success("Novos preços foram incluídos no histórico.")
    elif status_atualizacao == "Atualizada":
        st.success("O histórico de preços está atualizado.")
    elif status_atualizacao == "Ausente":
        st.warning("A BASE BI não foi encontrada.")
        st.caption(
            "Inclua o arquivo base_bi.xlsx na raiz do repositório."
        )
    else:
        st.error("Não foi possível atualizar o histórico.")
        if status_base_bi_git.get("mensagem"):
            st.caption(status_base_bi_git["mensagem"])

    if status_base_bi_git.get("caminho"):
        st.caption(
            f"Base utilizada: "
            f"{Path(status_base_bi_git['caminho']).name}"
        )

    status_referencias = status_central_pricing.get(
        "status",
        "",
    )
    if status_referencias in {
        "Sincronizada",
        "Sem alterações",
    }:
        st.caption("Referências prontas para consulta.")
    else:
        st.caption("As referências serão atualizadas no próximo acesso.")

    if st.button(
        "Atualizar base de preços",
        use_container_width=True,
        key="sincronizar_historico_manual",
    ):
        _hash_sha256_cache.clear()
        inicializar_bases_pricing.clear()
        st.rerun()

if st.sidebar.button("Limpar dados desta tela", use_container_width=True):
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
        "usado_busca_ativo",
        "usado_ativo_selecionado",
        "usado_cliente",
        "usado_equipamento",
        "usado_fabricante",
        "usado_responsavel",
        "usado_prazo",
        "usado_data_inicio",
        "usado_valor",
        "usado_data_aquisicao",
        "usado_vida_util",
        "usado_modelo_recuperacao",
        "usado_incluir_atendimento",
        "usado_reserva_risco",
        "usado_margem",
        "usado_validade_proposta",
        "usado_status_referencia",
        "usado_observacoes_proposta",
        "usado_aval_gerencia",
        "usado_justificativa_negociacao",
        "usado_estado_conservacao",
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
            <p>Visão geral dos preços praticados, das simulações salvas e das oportunidades de ajuste.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    h = historico()
    refs_pricing = referencias_preco()
    refs_reais = refs_pricing[
        refs_pricing["tipo_fonte"].isin(["Faturamento real", "Contrato ativo"])
    ] if not refs_pricing.empty else pd.DataFrame()

    indicadores = [
        ("Precificações", len(h), "Simulações salvas"),
        ("Referências reais", len(refs_reais), "Contratos e faturamentos"),
        (
            "Preço médio praticado",
            moeda(refs_reais["preco_mensal_unitario"].mean())
            if not refs_reais.empty else moeda(0),
            "Referências reais",
        ),
        (
            "Payback médio",
            meses(h[h["payback"] < 900]["payback"].mean())
            if not h.empty and (h["payback"] < 900).any()
            else "N/A",
            "Simulações recuperáveis",
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
# CENTRAL DE CONSULTA
# ======================================================
elif menu == "1 - Central de Consulta":
    st.markdown(
        """
        <div class="hero">
            <h1>Central de Consulta e Formação de Preço</h1>
            <p>Consulte quanto já foi cobrado e compare com o valor mínimo necessário para montar uma nova proposta.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    refs = referencias_preco()

    if not refs.empty:
        refs["_codigo_base"] = (
            refs["equipamento_codigo"]
            .fillna("")
            .map(normalizar_codigo_equipamento)
        )
        refs["_equipamento_base"] = (
            refs["equipamento"]
            .fillna("")
            .map(normalizar_nome_equipamento)
        )
        refs["_chave_equipamento"] = refs.apply(
            lambda linha: chave_agrupamento_equipamento(
                linha.get("equipamento_codigo", ""),
                linha.get("equipamento", ""),
            ),
            axis=1,
        )

    if refs.empty:
        if status_base_bi_git.get("status") == "Ausente":
            st.warning(
                "A BASE BI não foi encontrada. Inclua o arquivo "
                "base_bi.xlsx na raiz do repositório para carregar "
                "os preços já faturados."
            )
        else:
            st.warning(
                "A base foi localizada, mas os preços ainda não foram "
                "carregados para consulta."
            )
            if status_base_bi_git.get("mensagem"):
                st.caption(status_base_bi_git["mensagem"])

        if st.button(
            "Carregar histórico de preços agora",
            use_container_width=True,
            key="central_recarregar_historico",
        ):
            _hash_sha256_cache.clear()
            inicializar_bases_pricing.clear()
            caminho_base = localizar_base_bi_git()
            if caminho_base is None:
                st.error("O arquivo base_bi.xlsx não foi encontrado.")
            else:
                try:
                    with st.spinner("Carregando os preços de locação..."):
                        importar_base_bi(caminho_base)
                        sincronizar_central_pricing(forcar=True)
                    st.success("Histórico de preços carregado.")
                    st.rerun()
                except Exception as erro:
                    st.error(
                        "Não foi possível carregar o histórico: "
                        f"{erro}"
                    )
    else:
        st.caption(
            f"{len(refs):,} referências disponíveis para consulta."
            .replace(",", ".")
        )
        col1, col2 = st.columns([2, 1])
        busca = col1.text_input(
            "Buscar por código, equipamento, fabricante ou linha",
            key="central_busca_equipamento",
        )
        condicoes = col2.multiselect(
            "Condição",
            sorted(refs["condicao"].fillna("").replace("", "Não informado").unique().tolist()),
            default=[],
            key="central_condicao",
        )

        candidatos = refs.copy()
        if busca:
            termo = normalizar_texto_coluna(busca)
            mascara = pd.Series(False, index=candidatos.index)
            for coluna_busca in [
                "equipamento_codigo",
                "equipamento",
                "fabricante",
                "linha_produto",
                "_codigo_base",
                "_equipamento_base",
            ]:
                mascara |= (
                    candidatos[coluna_busca]
                    .fillna("")
                    .map(normalizar_texto_coluna)
                    .str.contains(
                        re.escape(termo),
                        na=False,
                    )
                )
            candidatos = candidatos[mascara]
        if condicoes:
            cond_series = candidatos["condicao"].fillna("").replace("", "Não informado")
            candidatos = candidatos[cond_series.isin(condicoes)]

        if candidatos.empty:
            st.warning("Nenhuma referência encontrada para a pesquisa.")
        else:
            agrupados = (
                candidatos[
                    candidatos["_chave_equipamento"].fillna("").ne("")
                ]
                .groupby(
                    "_chave_equipamento",
                    dropna=False,
                )
                .agg(
                    codigo_base=(
                        "_codigo_base",
                        texto_mais_frequente,
                    ),
                    equipamento=(
                        "equipamento",
                        texto_mais_frequente,
                    ),
                    referencias=(
                        "_chave_equipamento",
                        "size",
                    ),
                    variacoes_codigo=(
                        "equipamento_codigo",
                        lambda serie: int(
                            pd.Series(serie)
                            .fillna("")
                            .astype(str)
                            .str.strip()
                            .replace("", np.nan)
                            .dropna()
                            .nunique()
                        ),
                    ),
                )
                .reset_index()
                .sort_values(
                    ["referencias", "equipamento"],
                    ascending=[False, True],
                )
            )

            opcoes = []
            mapa_opcoes = {}

            for _, item in agrupados.iterrows():
                codigo = texto_limpo(
                    item["codigo_base"]
                )
                equip = texto_limpo(
                    item["equipamento"]
                )
                label_base = " | ".join(
                    [
                        parte
                        for parte in [codigo, equip]
                        if parte
                    ]
                )

                detalhes_label = (
                    f"{int(item['referencias'])} referências"
                )
                if int(item["variacoes_codigo"]) > 1:
                    detalhes_label += (
                        f"; {int(item['variacoes_codigo'])} "
                        "códigos agrupados"
                    )

                label = (
                    f"{label_base} ({detalhes_label})"
                )
                opcoes.append(label)
                mapa_opcoes[label] = (
                    item["_chave_equipamento"],
                    codigo,
                    equip,
                )

            escolha = st.selectbox(
                "Equipamento para análise",
                opcoes,
                key="central_equipamento_selecionado",
            )

            (
                chave_equipamento_sel,
                codigo_sel,
                equipamento_sel,
            ) = mapa_opcoes[escolha]

            base_equip = refs[
                refs["_chave_equipamento"].eq(
                    chave_equipamento_sel
                )
            ].copy()

            variacoes = sorted(
                {
                    texto_limpo(valor)
                    for valor in base_equip[
                        "equipamento_codigo"
                    ].tolist()
                    if texto_limpo(valor)
                }
            )

            if len(variacoes) > 1:
                st.caption(
                    "Códigos reunidos nesta análise: "
                    + ", ".join(variacoes)
                )

            col1, col2, col3 = st.columns(3)
            fontes_disp = sorted(base_equip["tipo_fonte"].dropna().unique().tolist())
            fontes_sel = col1.multiselect(
                "Fontes consideradas",
                fontes_disp,
                default=fontes_disp,
                key="central_fontes",
            )
            status_disp = sorted(base_equip["status"].dropna().unique().tolist())
            status_sel = col2.multiselect(
                "Status",
                status_disp,
                default=[s for s in status_disp if normalizar_texto_coluna(s) != "PERDIDA"],
                key="central_status",
            )
            janela = col3.selectbox(
                "Período",
                ["Todo o histórico", "Últimos 12 meses", "Últimos 24 meses", "Últimos 36 meses"],
                key="central_periodo",
            )

            view = base_equip.copy()
            if fontes_sel:
                view = view[view["tipo_fonte"].isin(fontes_sel)]
            if status_sel:
                view = view[view["status"].isin(status_sel)]
            datas = pd.to_datetime(view["data_referencia"], errors="coerce", dayfirst=True)
            meses_janela = {"Últimos 12 meses": 12, "Últimos 24 meses": 24, "Últimos 36 meses": 36}.get(janela)
            if meses_janela:
                limite = pd.Timestamp.today() - pd.DateOffset(months=meses_janela)
                view = view[datas >= limite]

            minimo_simulacoes = pd.to_numeric(
                base_equip["aluguel_minimo_calculado"], errors="coerce"
            ).dropna()
            minimo_padrao = float(minimo_simulacoes.iloc[0]) if not minimo_simulacoes.empty else 0.0
            aluguel_minimo_atual = st.number_input(
                "Aluguel mínimo financeiro atual (pode ajustar)",
                min_value=0.0,
                value=float(minimo_padrao),
                step=100.0,
                key=(
                    "central_minimo_"
                    f"{_slug_widget(chave_equipamento_sel)}"
                ),
            )

            analise = analisar_referencias_preco(view, aluguel_minimo_atual)
            cols = st.columns(4)
            for col, item in zip(cols, [
                ("Último preço", moeda(analise["ultimo"]), "Referência mais recente"),
                ("Mediana histórica", moeda(analise["mediana"]), f"{analise['quantidade']} referências"),
                ("Menor / maior", f"{moeda(analise['minimo_historico'])} / {moeda(analise['maximo_historico'])}", "Faixa observada"),
                ("Confiabilidade", analise["confianca"], f"Peso médio {perc(analise['confianca_media'])}"),
            ]):
                with col:
                    card(*item)

            st.markdown(
                '<div class="section-title">Faixa sugerida para nova proposta</div>',
                unsafe_allow_html=True,
            )
            cols = st.columns(3)
            for col, item in zip(cols, [
                ("Preço mínimo", moeda(analise["preco_minimo"]), "Não reduzir abaixo desta faixa"),
                ("Preço recomendado", moeda(analise["preco_recomendado"]), "Mediana ponderada + viabilidade"),
                ("Preço premium", moeda(analise["preco_premium"]), "Faixa superior das referências"),
            ]):
                with col:
                    card(*item)

            if analise["mediana"] > 0 and aluguel_minimo_atual > analise["mediana"]:
                st.warning(
                    "O preço histórico mediano não cobre o aluguel mínimo financeiro atual. "
                    "Não é recomendável repetir automaticamente os valores anteriores."
                )
            elif analise["quantidade"] < 3:
                st.info(
                    "A faixa ainda possui poucas referências. Use o custo calculado como base "
                    "principal até o histórico ganhar volume."
                )
            else:
                st.success(
                    "A recomendação combina viabilidade financeira com referências comerciais, "
                    "priorizando contratos e faturamentos reais."
                )

            st.markdown(
                '<div class="section-title">Referências utilizadas</div>',
                unsafe_allow_html=True,
            )
            cols_view = [
                "id", "data_referencia", "fonte", "tipo_fonte", "status",
                "confianca_pct", "cliente", "condicao", "prazo_meses",
                "quantidade", "preco_mensal_unitario", "valor_mensal_total",
                "aluguel_minimo_calculado", "margem_pct", "vendedor", "gerente",
            ]
            st.dataframe(
                tabela_formatada(
                    view[cols_view],
                    money=["preco_mensal_unitario", "valor_mensal_total", "aluguel_minimo_calculado"],
                    percent=["confianca_pct", "margem_pct"],
                ),
                use_container_width=True,
                hide_index=True,
            )

# ======================================================
# NOVOS
# ======================================================
elif menu == "2 - Formação de Preço - Novos":
    st.markdown(
        """
        <div class="hero">
            <h1>Locação de Equipamentos Novos</h1>
            <p>Calcule a locação de equipamentos nacionais ou importados e gere uma proposta comercial completa.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="section-title">Origem do equipamento</div>',
        unsafe_allow_html=True,
    )

    # Fora do formulário para que a tela mude imediatamente.
    origem_produto = st.radio(
        "Tipo de aquisição",
        ["Produto importado", "Produto nacional"],
        horizontal=True,
        key="novo_origem_produto",
    )

    data_ptax = ""
    consulta_brasilia = datetime.now(
        ZoneInfo("America/Sao_Paulo")
    ).strftime("%d/%m/%Y %H:%M")
    ptax_automatica = False
    dolar_padrao = 0.0

    if origem_produto == "Produto importado":
        try:
            dolar_padrao, data_ptax, consulta_brasilia = ptax()
            ptax_automatica = True
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
    else:
        st.info(
            "Produto nacional: informe apenas o valor de aquisição "
            "da mercadoria em reais. FOB, dólar e nacionalização "
            "não serão considerados."
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
                '<div class="section-title">Aquisição da mercadoria nacional</div>',
                unsafe_allow_html=True,
            )
            valor_nacional = input_rs(
                "Valor de aquisição da mercadoria (R$)",
                0.0,
                "novo_valor_nacional",
            )
            investimento = valor_nacional

            st.caption(
                "Para mercadoria nacional, este valor substitui integralmente "
                "FOB, dólar e nacionalização."
            )
            st.info(
                f"Valor de aquisição considerado: {moeda(investimento)}"
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
            '<div class="section-title">Comissões</div>',
            unsafe_allow_html=True,
        )
        st.caption(
            "Os campos são independentes e podem ser usados simultaneamente. "
            "Mantenha em 0,00% quando a comissão não se aplicar."
        )
        col1, col2, col3 = st.columns(3)
        cv = col1.number_input(
            "Vendedor (%)",
            min_value=0.0,
            value=COMISSAO_VENDEDOR,
            step=0.25,
            key="novo_comissao_vendedor",
        )
        cg = col2.number_input(
            "Gerente (%)",
            min_value=0.0,
            value=COMISSAO_GERENTE,
            step=0.25,
            key="novo_comissao_gerente",
        )
        cr = col3.number_input(
            "Representante (%)",
            min_value=0.0,
            value=0.0,
            step=0.50,
            key="novo_comissao_representante",
        )
        com_pct = comissao_total(cv, cg, cr)
        st.info(f"Comissão total considerada: {perc(com_pct)}")

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

        col1, col2 = st.columns(2)
        validade_proposta = col1.number_input(
            "Validade da proposta (dias)",
            min_value=1,
            value=15,
            step=1,
            key="novo_validade_proposta",
        )
        observacoes_proposta = col2.text_area(
            "Observações da proposta",
            height=90,
            key="novo_observacoes_proposta",
        )
        status_referencia = st.selectbox(
            "Status comercial da referência",
            ["Rascunho", "Enviada", "Em negociação", "Aprovada", "Perdida", "Contratada"],
            index=0,
            key="novo_status_referencia",
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

        detalhes_proposta_novo = {
            "tipo_aquisicao": origem_produto,
            "valor_fob_usd": fob,
            "dolar_utilizado": dolar,
            "nacionalizacao_pct": nacionalizacao,
            "valor_nacional": valor_nacional,
            "despesas_adicionais": despesas,
            "comissao_vendedor_pct": cv,
            "comissao_gerente_pct": cg,
            "comissao_representante_pct": cr,
            "taxa_financiamento_pct": taxa_fin if origem == "Financiamento bancário" else 0.0,
            "prazo_financiamento_meses": prazo_fin if origem == "Financiamento bancário" else 0,
            "parcela_financiamento": parcela,
        }

        proposta_pdf_novo = gerar_proposta_pdf(
            tipo="Novo",
            cliente=cliente,
            equipamento=equipamento,
            fabricante=fabricante,
            responsavel=responsavel,
            prazo=prazo,
            aluguel=aluguel,
            investimento=investimento,
            resultado_atual=atual,
            resultado_reforma=reforma,
            comissao_pct=com_pct,
            origem_investimento=origem,
            detalhes=detalhes_proposta_novo,
            observacoes=observacoes_proposta,
            validade_dias=validade_proposta,
        )

        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                "Baixar análise interna em PDF",
                data=proposta_pdf_novo,
                file_name=(
                    f"analise_interna_locacao_novo_"
                    f"{_slug_widget(cliente or equipamento or 'cliente')}.pdf"
                ),
                mime="application/pdf",
                use_container_width=True,
            )

        with col2:
            salvar_novo = st.button(
                "Salvar precificação de novo",
                use_container_width=True,
            )

        if salvar_novo:
            cotacao_id = None
            if origem_produto == "Produto importado":
                cotacao_id = salvar_cotacao(
                    {
                        "data_hora_registro": datetime.now(
                            ZoneInfo("America/Sao_Paulo")
                        ).strftime("%d/%m/%Y %H:%M:%S"),
                        "data_hora_cotacao": data_ptax or data_inicio.strftime("%d/%m/%Y"),
                        "data_hora_consulta_brasilia": consulta_brasilia,
                        "valor": dolar,
                        "fonte": (
                            "PTAX de venda - Banco Central do Brasil"
                            if ptax_automatica
                            else "Informada manualmente"
                        ),
                        "origem": "Automática" if ptax_automatica else "Manual",
                        "finalidade": "Precificação de equipamento novo",
                        "cliente": cliente,
                        "equipamento": equipamento,
                        "observacao": observacoes_proposta,
                        "usada_em_precificacao": 1,
                    }
                )

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
                            "status_referencia": status_referencia,
                            "observacao_referencia": observacoes_proposta,
                            "fob_usd": fob,
                            "dolar": dolar,
                            "cotacao_id": cotacao_id,
                            "nacionalizacao": nacionalizacao,
                            "valor_nacional": valor_nacional,
                            "comissao_vendedor_pct": cv,
                            "comissao_gerente_pct": cg,
                            "comissao_representante_pct": cr,
                            "comissao_vendedor_pct": cv,
                            "comissao_gerente_pct": cg,
                            "comissao_representante_pct": cr,
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
elif menu == "3 - Formação de Preço - Usados":
    st.markdown(
        """
        <div class="hero">
            <h1>Locação de Equipamentos Usados</h1>
            <p>Monte o preço em três etapas e acompanhe o resultado enquanto preenche.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.caption(
        "Os valores são atualizados automaticamente. "
        "A consulta de preços já praticados permanece somente na Central de Consulta."
    )

    resumo_final_usado = st.container()

    ativos = carregar_ativos()
    info = {}

    st.markdown(
        '<div class="section-title">Selecione o equipamento</div>',
        unsafe_allow_html=True,
    )

    if not ativos.empty:
        col_busca, col_ativo = st.columns([1, 2])

        busca = col_busca.text_input(
            "Buscar na base de ativos",
            key="usado_busca_ativo",
            placeholder="Código, descrição ou fabricante",
        )

        filtrados = ativos.copy()
        if busca:
            filtrados = filtrados[
                filtrados.astype(str)
                .apply(
                    lambda coluna: coluna.str.contains(
                        busca,
                        case=False,
                        na=False,
                    )
                )
                .any(axis=1)
            ]

        linhas_disponiveis = filtrados.head(300).copy()
        opcoes = ["Preencher manualmente"] + [
            label_ativo(row)
            for _, row in linhas_disponiveis.iterrows()
        ]

        selecionado = col_ativo.selectbox(
            "Equipamento cadastrado",
            opcoes,
            key="usado_ativo_selecionado",
        )

        if selecionado != "Preencher manualmente":
            indice = opcoes.index(selecionado) - 1
            info = ativo_info(
                linhas_disponiveis.iloc[indice]
            )

            assinatura_ativo = (
                f"{info.get('codigo', '')}|"
                f"{info.get('valor', 0)}|"
                f"{info.get('data_aquisicao', '')}"
            )

            if (
                st.session_state.get("_ativo_usado_base")
                != assinatura_ativo
            ):
                st.session_state["_ativo_usado_base"] = assinatura_ativo
                for chave in [
                    "usado_equipamento",
                    "usado_fabricante",
                    "usado_valor",
                    "usado_data_aquisicao",
                    "u_taxa_manutencao_anual",
                    "u_horas_tecnico",
                    "u_manut",
                    "u_aluguel",
                ]:
                    st.session_state.pop(chave, None)

            st.success(
                f"Equipamento selecionado: {info['equipamento']} | "
                f"Valor de aquisição: {moeda(info['valor'])} | "
                f"Data: {info['data_aquisicao'] or 'não informada'}"
            )
    else:
        st.info(
            "A base de ativos não está disponível. "
            "Os dados podem ser preenchidos manualmente."
        )

    etapa_1, etapa_2, etapa_3 = st.tabs(
        [
            "1. Equipamento e contrato",
            "2. Custos da locação",
            "3. Preço e aprovação",
        ]
    )

    with etapa_1:
        st.markdown(
            '<div class="section-title">Dados da operação</div>',
            unsafe_allow_html=True,
        )

        col1, col2, col3 = st.columns(3)
        cliente = col1.text_input(
            "Cliente",
            key="usado_cliente",
        )
        equipamento = col2.text_input(
            "Equipamento",
            value=info.get("equipamento", ""),
            key="usado_equipamento",
        )
        fabricante = col3.text_input(
            "Fabricante / linha",
            value=info.get("fabricante", ""),
            key="usado_fabricante",
        )

        col1, col2, col3 = st.columns(3)
        responsavel = col1.text_input(
            "Responsável pela análise",
            key="usado_responsavel",
        )
        prazo = col2.number_input(
            "Prazo da locação (meses)",
            min_value=1,
            max_value=120,
            value=24,
            key="usado_prazo",
        )
        data_inicio = col3.date_input(
            "Início da locação",
            value=date.today(),
            format="DD/MM/YYYY",
            key="usado_data_inicio",
        )

        st.markdown(
            '<div class="section-title">Dados do ativo</div>',
            unsafe_allow_html=True,
        )

        col1, col2, col3 = st.columns(3)
        with col1:
            valor_ativo = input_rs_compacto(
                "Valor de aquisição",
                info.get("valor", 0.0),
                "usado_valor",
                "Valor original ou melhor referência disponível para o ativo.",
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
            key="usado_data_aquisicao",
        )
        vida_util = col3.number_input(
            "Vida útil (anos)",
            min_value=1.0,
            value=VIDA_UTIL_PADRAO,
            step=0.5,
            key="usado_vida_util",
        )

        dep_atual_form = calcular_depreciacao(
            valor_ativo,
            data_aquisicao,
            data_inicio,
            0,
            vida_util,
        )

        opcoes_modelo = [
            "incremental",
            "depreciacao",
            "contabil",
        ]
        nomes_modelo = {
            "incremental": "Cobrir somente os custos da locação",
            "depreciacao": (
                "Recuperar a perda de valor durante o contrato "
                "(recomendado)"
            ),
            "contabil": "Recuperar todo o valor contábil atual",
        }

        modelo_codigo = st.selectbox(
            "Como o valor do ativo deve entrar no preço?",
            opcoes_modelo,
            index=1,
            format_func=lambda item: nomes_modelo[item],
            key="usado_modelo_recuperacao",
        )
        modelo_usado = nomes_modelo[modelo_codigo]

        col1, col2, col3 = st.columns(3)
        col1.metric(
            "Depreciação atual",
            perc(dep_atual_form["taxa"]),
        )
        col2.metric(
            "Valor contábil atual",
            moeda(dep_atual_form["valor_contabil"]),
        )
        col3.metric(
            "Tempo já depreciado",
            f"{dep_atual_form['meses_antes']} meses",
        )

    with etapa_2:
        st.markdown(
            '<div class="section-title">Manutenção e atendimento</div>',
            unsafe_allow_html=True,
        )

        taxa_manut_sugerida = taxa_manutencao_por_depreciacao(
            dep_atual_form["taxa"]
        )

        col1, col2, col3 = st.columns(3)

        estado_conservacao = col1.selectbox(
            "Estado de conservação",
            ["Excelente", "Bom", "Regular"],
            index=1,
            key="usado_estado_conservacao",
        )

        fator_conservacao = fator_conservacao_usado(
            estado_conservacao
        )

        taxa_manutencao_anual = col2.number_input(
            "Reserva anual de manutenção (%)",
            min_value=0.0,
            value=float(taxa_manut_sugerida),
            step=0.5,
            key="u_taxa_manutencao_anual",
        )

        usar_manutencao_automatica = col3.checkbox(
            "Calcular automaticamente",
            value=True,
            key="u_usar_manut_auto",
        )

        base_manutencao = base_manutencao_usado(
            valor_ativo,
            dep_atual_form["valor_contabil"],
        )

        manutencao_calculada = (
            base_manutencao
            * taxa_manutencao_anual
            / 100
            / 12
            * fator_conservacao
        )

        if usar_manutencao_automatica:
            manutencao = manutencao_calculada
            st.info(
                f"Manutenção mensal considerada: {moeda(manutencao)} | "
                f"Base econômica: {moeda(base_manutencao)} | "
                f"Conservação: {estado_conservacao}"
            )
        else:
            manutencao = input_rs_compacto(
                "Manutenção mensal informada",
                manutencao_calculada,
                "u_manut",
            )

        incluir_atendimento = st.checkbox(
            "Prever atendimento técnico mensal",
            value=True,
            key="usado_incluir_atendimento",
        )

        if incluir_atendimento:
            col1, col2, col3 = st.columns(3)
            horas_tecnico = col1.number_input(
                "Horas técnicas por mês",
                min_value=0.0,
                value=float(
                    horas_tecnicas_por_depreciacao(
                        dep_atual_form["taxa"]
                    )
                ),
                step=1.0,
                key="u_horas_tecnico",
            )
            with col2:
                valor_hora = input_rs_compacto(
                    "Valor da hora técnica",
                    0.0,
                    "u_hora",
                )
            with col3:
                deslocamento = input_rs_compacto(
                    "Deslocamento mensal",
                    0.0,
                    "u_desloc",
                )
        else:
            horas_tecnico = 0.0
            valor_hora = 0.0
            deslocamento = 0.0

        col1, col2 = st.columns(2)
        with col1:
            pecas = input_rs_compacto(
                "Peças e consumíveis mensais",
                0.0,
                "u_pecas",
            )
        with col2:
            seguro = input_rs_compacto(
                "Seguro mensal",
                0.0,
                "u_seguro",
            )

        with st.expander(
            "Custos adicionais",
            expanded=False,
        ):
            col1, col2 = st.columns(2)
            with col1:
                revisao_inicial = input_rs_compacto(
                    "Revisão inicial ou recuperação",
                    0.0,
                    "u_revisao",
                )
            with col2:
                outros = input_rs_compacto(
                    "Outros custos mensais",
                    0.0,
                    "u_outros",
                )

        reserva_risco_pct = st.number_input(
            "Reserva para falhas e indisponibilidade (%)",
            min_value=0.0,
            value=RESERVA_RISCO_USADO_PADRAO,
            step=0.5,
            key="usado_reserva_risco",
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
            custo_operacional
            * reserva_risco_pct
            / 100
        )

        st.markdown(
            '<div class="section-title">Resumo dos custos</div>',
            unsafe_allow_html=True,
        )
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Custo mensal", moeda(custo_mensal))
        col2.metric("Custo do contrato", moeda(custo_operacional))
        col3.metric("Reserva de risco", moeda(reserva_risco))
        col4.metric("Base de manutenção", moeda(base_manutencao))

        st.caption(
            "O risco técnico aumenta com a idade, mas a manutenção "
            "é calculada sobre o valor econômico atual do equipamento."
        )

    with etapa_3:
        st.markdown(
            '<div class="section-title">Comissões e retorno</div>',
            unsafe_allow_html=True,
        )

        col1, col2, col3, col4 = st.columns(4)
        cv = col1.number_input(
            "Vendedor (%)",
            min_value=0.0,
            value=COMISSAO_VENDEDOR,
            step=0.25,
            key="ucv",
        )
        cg = col2.number_input(
            "Gerente (%)",
            min_value=0.0,
            value=COMISSAO_GERENTE,
            step=0.25,
            key="ucg",
        )
        cr = col3.number_input(
            "Representante (%)",
            min_value=0.0,
            value=0.0,
            step=0.50,
            key="ucr",
        )
        margem = col4.number_input(
            "Margem desejada (%)",
            min_value=0.0,
            value=MARGEM_USADO_PADRAO,
            step=1.0,
            key="usado_margem",
        )

        com_pct = comissao_total(cv, cg, cr)

        dep = calcular_depreciacao(
            valor_ativo,
            data_aquisicao,
            data_inicio,
            int(prazo),
            vida_util,
        )

        if modelo_codigo == "incremental":
            investimento_recuperar = 0.0
        elif modelo_codigo == "depreciacao":
            depreciacao_no_contrato = max(
                dep["depreciacao"]
                - dep_atual_form["depreciacao"],
                0.0,
            )
            investimento_recuperar = min(
                depreciacao_no_contrato,
                dep_atual_form["valor_contabil"],
            )
        else:
            investimento_recuperar = (
                dep_atual_form["valor_contabil"]
            )

        resultado_base = calcular_resultado(
            investimento_recuperar,
            int(prazo),
            0.0,
            custo_operacional,
            IMPOSTO_ATUAL,
            com_pct,
            margem,
            0.0,
            reserva_risco,
        )

        preco_minimo = resultado_base["aluguel_minimo"]

        (
            fator_preco_recomendado,
            fator_preco_protegido,
        ) = fatores_faixa_preco_usado(
            dep_atual_form["taxa"]
        )

        preco_recomendado = (
            preco_minimo * fator_preco_recomendado
        )
        preco_seguro = (
            preco_minimo * fator_preco_protegido
        )

        st.markdown(
            '<div class="section-title">Valor em negociação</div>',
            unsafe_allow_html=True,
        )

        aluguel = input_rs_compacto(
            "Aluguel mensal negociado pelo vendedor",
            preco_recomendado,
            "u_aluguel",
            (
                "Digite o valor que está sendo tratado com o cliente. "
                "O sistema avaliará a condição imediatamente."
            ),
        )

        resultado_negociacao = calcular_resultado(
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

        avaliacao_negociacao = avaliar_preco_negociado(
            aluguel,
            preco_minimo,
            preco_recomendado,
            preco_seguro,
        )

        if avaliacao_negociacao["nivel"] == "critico":
            st.error(
                f"**{avaliacao_negociacao['classificacao']}** — "
                f"{avaliacao_negociacao['mensagem']}"
            )
        elif avaliacao_negociacao["nivel"] == "atencao":
            st.warning(
                f"**{avaliacao_negociacao['classificacao']}** — "
                f"{avaliacao_negociacao['mensagem']}"
            )
        elif avaliacao_negociacao["nivel"] == "bom":
            st.success(
                f"**{avaliacao_negociacao['classificacao']}** — "
                f"{avaliacao_negociacao['mensagem']}"
            )
        elif avaliacao_negociacao["nivel"] == "excelente":
            st.success(
                f"**{avaliacao_negociacao['classificacao']}** — "
                f"{avaliacao_negociacao['mensagem']}"
            )
        else:
            st.info(avaliacao_negociacao["mensagem"])

        diferenca_minimo = aluguel - preco_minimo
        diferenca_recomendado = aluguel - preco_recomendado

        col1, col2, col3, col4 = st.columns(4)
        col1.metric(
            "Valor negociado",
            moeda(aluguel),
        )
        col2.metric(
            "Diferença para o mínimo",
            moeda(diferenca_minimo),
            delta=(
                "Acima do mínimo"
                if diferenca_minimo >= 0
                else "Abaixo do mínimo"
            ),
            delta_color=(
                "normal"
                if diferenca_minimo >= 0
                else "inverse"
            ),
        )
        col3.metric(
            "Diferença para o recomendado",
            moeda(diferenca_recomendado),
            delta=(
                "Dentro da faixa"
                if diferenca_recomendado >= 0
                else "Abaixo da faixa"
            ),
            delta_color=(
                "normal"
                if diferenca_recomendado >= 0
                else "inverse"
            ),
        )
        col4.metric(
            "Margem desta negociação",
            perc(resultado_negociacao["margem"]),
        )

        with st.expander(
            "Comparar com outras faixas de preço",
            expanded=False,
        ):
            col1, col2, col3 = st.columns(3)

            with col1:
                card(
                    "Preço mínimo",
                    moeda(preco_minimo),
                    "Menor valor financeiramente aceitável",
                )
                st.button(
                    "Usar como contraproposta",
                    use_container_width=True,
                    key="usado_aplicar_minimo",
                    on_click=aplicar_valor_monetario,
                    args=("u_aluguel", preco_minimo),
                )

            with col2:
                card(
                    "Preço recomendado",
                    moeda(preco_recomendado),
                    (
                        f"Proteção de "
                        f"{perc((fator_preco_recomendado - 1) * 100)}"
                    ),
                )
                st.button(
                    "Usar como contraproposta",
                    use_container_width=True,
                    key="usado_aplicar_recomendado",
                    on_click=aplicar_valor_monetario,
                    args=("u_aluguel", preco_recomendado),
                )

            with col3:
                card(
                    "Preço protegido",
                    moeda(preco_seguro),
                    (
                        f"Proteção de "
                        f"{perc((fator_preco_protegido - 1) * 100)}"
                    ),
                )
                st.button(
                    "Usar como contraproposta",
                    use_container_width=True,
                    key="usado_aplicar_seguro",
                    on_click=aplicar_valor_monetario,
                    args=("u_aluguel", preco_seguro),
                )

        with st.expander(
            "Simulação após a reforma tributária",
            expanded=False,
        ):
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

        with st.expander(
            "Informações para aprovação",
            expanded=avaliacao_negociacao["exige_aval"],
        ):
            col1, col2, col3 = st.columns(3)

            validade_proposta_usado = col1.number_input(
                "Validade da análise (dias)",
                min_value=1,
                value=15,
                step=1,
                key="usado_validade_proposta",
            )

            opcoes_status = [
                "Rascunho",
                "Enviada",
                "Em negociação",
                "Aprovada",
                "Perdida",
                "Contratada",
            ]
            nomes_status = {
                "Rascunho": "Rascunho",
                "Enviada": "Aguardando aval da gerência",
                "Em negociação": "Em revisão",
                "Aprovada": "Aprovada pela gerência",
                "Perdida": "Reprovada",
                "Contratada": "Liberada e contratada",
            }
            status_referencia_usado = col2.selectbox(
                "Situação da análise",
                opcoes_status,
                format_func=lambda item: nomes_status[item],
                key="usado_status_referencia",
            )

            opcoes_aval = [
                "Pendente",
                "Aprovado",
                "Reprovado",
            ]
            aval_gerencia_usado = col3.selectbox(
                "Aval da gerência",
                opcoes_aval,
                key="usado_aval_gerencia",
                help=(
                    "Preços abaixo da faixa recomendada devem permanecer "
                    "como pendentes até a decisão da gerência."
                ),
            )

            justificativa_negociacao_usado = st.text_area(
                (
                    "Justificativa comercial obrigatória"
                    if avaliacao_negociacao["exige_aval"]
                    else "Justificativa comercial"
                ),
                height=85,
                key="usado_justificativa_negociacao",
                placeholder=(
                    "Informe concorrência, prazo, volume, estratégia, "
                    "cliente-chave ou outra condição da negociação."
                ),
            )

            observacoes_proposta_usado = st.text_area(
                "Outras observações para a gerência",
                height=75,
                key="usado_observacoes_proposta",
            )

            if (
                avaliacao_negociacao["exige_aval"]
                and not justificativa_negociacao_usado.strip()
            ):
                st.warning(
                    "Inclua a justificativa comercial para salvar "
                    "esta condição e encaminhá-la à gerência."
                )


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

    base_credito = custo_operacional + reserva_risco
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

    alerta_preco = (
        f"{avaliacao_negociacao['classificacao']}: "
        f"{avaliacao_negociacao['mensagem']}"
    )

    detalhes_proposta_usado = {
        "modelo_precificacao": modelo_usado,
        "data_aquisicao": data_aquisicao.strftime("%d/%m/%Y"),
        "depreciacao_atual_pct": dep_atual_form["taxa"],
        "depreciacao_final_pct": dep["taxa"],
        "valor_contabil_final": dep["valor_contabil"],
        "estado_conservacao": estado_conservacao,
        "fator_conservacao": fator_conservacao,
        "base_economica_manutencao": base_manutencao,
        "manutencao_mensal": manutencao,
        "pecas_mensais": pecas,
        "seguro_mensal": seguro,
        "horas_tecnicas_mes": horas_tecnico,
        "valor_hora_tecnica": valor_hora,
        "deslocamento_mensal": deslocamento,
        "reserva_risco_pct": reserva_risco_pct,
        "preco_minimo": preco_minimo,
        "preco_recomendado": preco_recomendado,
        "preco_protegido": preco_seguro,
        "classificacao_negociacao": (
            avaliacao_negociacao["classificacao"]
        ),
        "diferenca_para_minimo": diferenca_minimo,
        "diferenca_para_recomendado": diferenca_recomendado,
        "aval_gerencia": aval_gerencia_usado,
        "justificativa_comercial": justificativa_negociacao_usado,
        "comissao_vendedor_pct": cv,
        "comissao_gerente_pct": cg,
        "comissao_representante_pct": cr,
    }

    observacoes_pdf_usado = (
        f"Parecer da negociação: "
        f"{avaliacao_negociacao['classificacao']}. "
        f"{avaliacao_negociacao['mensagem']} "
        f"Aval da gerência: {aval_gerencia_usado}. "
    )
    if justificativa_negociacao_usado.strip():
        observacoes_pdf_usado += (
            "Justificativa comercial: "
            f"{justificativa_negociacao_usado.strip()}. "
        )
    if observacoes_proposta_usado.strip():
        observacoes_pdf_usado += (
            "Observações adicionais: "
            f"{observacoes_proposta_usado.strip()}"
        )

    proposta_pdf_usado = gerar_proposta_pdf(
        tipo="Usado",
        cliente=cliente,
        equipamento=equipamento,
        fabricante=fabricante,
        responsavel=responsavel,
        prazo=prazo,
        aluguel=aluguel,
        investimento=investimento_recuperar,
        resultado_atual=atual,
        resultado_reforma=reforma,
        comissao_pct=com_pct,
        origem_investimento="Ativo próprio",
        detalhes=detalhes_proposta_usado,
        observacoes=observacoes_pdf_usado,
        validade_dias=validade_proposta_usado,
    )

    justificativa_ok = (
        not avaliacao_negociacao["exige_aval"]
        or bool(justificativa_negociacao_usado.strip())
    )

    pronto_para_salvar = (
        bool(equipamento.strip())
        and valor_ativo > 0
        and aluguel > 0
        and justificativa_ok
    )

    salvar_usado = False

    with resumo_final_usado:
        st.markdown(
            f"""
            <div class="resultado-fixo">
                <div class="resultado-fixo-titulo">
                    Resultado atualizado automaticamente
                </div>
                <div class="resultado-fixo-grid">
                    <div class="resultado-fixo-item">
                        <div class="resultado-fixo-label">Aluguel escolhido</div>
                        <div class="resultado-fixo-valor">{moeda(aluguel)}</div>
                    </div>
                    <div class="resultado-fixo-item">
                        <div class="resultado-fixo-label">Preço mínimo</div>
                        <div class="resultado-fixo-valor">{moeda(preco_minimo)}</div>
                    </div>
                    <div class="resultado-fixo-item">
                        <div class="resultado-fixo-label">Preço recomendado</div>
                        <div class="resultado-fixo-valor">{moeda(preco_recomendado)}</div>
                    </div>
                    <div class="resultado-fixo-item">
                        <div class="resultado-fixo-label">Margem estimada</div>
                        <div class="resultado-fixo-valor">{perc(atual["margem"])}</div>
                    </div>
                    <div class="resultado-fixo-item">
                        <div class="resultado-fixo-label">Payback</div>
                        <div class="resultado-fixo-valor">{meses(atual["payback"])}</div>
                    </div>
                </div>
                <div class="resultado-fixo-alerta">{alerta_preco}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        col1, col2 = st.columns(2)

        with col1:
            if pronto_para_salvar:
                st.download_button(
                    "Baixar análise interna em PDF",
                    data=proposta_pdf_usado,
                    file_name=(
                        "analise_interna_locacao_usado_"
                        f"{_slug_widget(cliente or equipamento or 'cliente')}.pdf"
                    ),
                    mime="application/pdf",
                    use_container_width=True,
                )
            else:
                st.button(
                    "Baixar análise interna em PDF",
                    disabled=True,
                    use_container_width=True,
                    key="usado_pdf_desabilitado",
                )

        with col2:
            texto_botao_salvar = (
                "Salvar para aval da gerência"
                if (
                    avaliacao_negociacao["exige_aval"]
                    and aval_gerencia_usado == "Pendente"
                )
                else "Salvar análise"
            )
            salvar_usado = st.button(
                texto_botao_salvar,
                disabled=not pronto_para_salvar,
                use_container_width=True,
                key="salvar_usado_v35",
            )

    with st.expander(
        "Ver memória completa do cálculo",
        expanded=False,
    ):
        st.markdown(
            '<div class="section-title">Resultado financeiro</div>',
            unsafe_allow_html=True,
        )
        cards = [
            (
                "Receita do contrato",
                moeda(atual["receita"]),
                f"{int(prazo)} meses",
            ),
            (
                "Custo total",
                moeda(atual["custo_total"]),
                "Ativo + operação + riscos",
            ),
            (
                "Lucro estimado",
                moeda(atual["lucro"]),
                "Com o aluguel escolhido",
            ),
            (
                "Comissão total",
                moeda(atual["comissao"]),
                perc(com_pct),
            ),
        ]
        cols = st.columns(4)
        for coluna, item in zip(cols, cards):
            with coluna:
                card(*item)

        st.markdown(
            '<div class="section-title">Ativo e depreciação</div>',
            unsafe_allow_html=True,
        )
        cards = [
            (
                "Depreciação atual",
                perc(dep_atual_form["taxa"]),
                f"{dep_atual_form['meses_antes']} meses",
            ),
            (
                "Depreciação final",
                perc(dep["taxa"]),
                f"{dep['meses_finais']} meses",
            ),
            (
                "Valor contábil final",
                moeda(dep["valor_contabil"]),
                "Após o contrato",
            ),
            (
                "Valor recuperado",
                moeda(investimento_recuperar),
                modelo_usado,
            ),
        ]
        cols = st.columns(4)
        for coluna, item in zip(cols, cards):
            with coluna:
                card(*item)

        st.markdown(
            '<div class="section-title">Impostos</div>',
            unsafe_allow_html=True,
        )
        cards = [
            (
                "Impostos atuais",
                moeda(atual["impostos"]),
                perc(IMPOSTO_ATUAL),
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
        for coluna, item in zip(cols, cards):
            with coluna:
                card(*item)

        parecer = (
            f"Classificação da negociação: "
            f"{avaliacao_negociacao['classificacao']}. "
            f"{avaliacao_negociacao['mensagem']} "
            f"O preço mínimo calculado é {moeda(preco_minimo)}, "
            f"a faixa recomendada inicia em {moeda(preco_recomendado)} "
            f"e a faixa protegida em {moeda(preco_seguro)}. "
            f"A margem estimada para o valor negociado é "
            f"{perc(atual['margem'])}, com payback de "
            f"{meses(atual['payback'])}. "
            f"A manutenção considera a base econômica de "
            f"{moeda(base_manutencao)} e conservação "
            f"{estado_conservacao}. "
            f"Aval da gerência: {aval_gerencia_usado}."
        )

        st.markdown(
            '<div class="section-title">Parecer para aprovação</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="parecer">{parecer}</div>',
            unsafe_allow_html=True,
        )

    if salvar_usado:
        salvar(
            {
                "data_hora": datetime.now(
                    ZoneInfo("America/Sao_Paulo")
                ).strftime("%d/%m/%Y %H:%M:%S"),
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
                        "status_referencia": status_referencia_usado,
                        "observacao_referencia": (
                            observacoes_proposta_usado
                        ),
                        "estado_conservacao": estado_conservacao,
                        "fator_conservacao": fator_conservacao,
                        "base_economica_manutencao": base_manutencao,
                        "manutencao": manutencao,
                        "manutencao_automatica": (
                            usar_manutencao_automatica
                        ),
                        "taxa_manutencao_anual": (
                            taxa_manutencao_anual
                        ),
                        "depreciacao_atual": (
                            dep_atual_form["taxa"]
                        ),
                        "pecas": pecas,
                        "horas_tecnico": horas_tecnico,
                        "valor_hora": valor_hora,
                        "custo_tecnico": custo_tecnico,
                        "reserva_risco_pct": reserva_risco_pct,
                        "preco_minimo": preco_minimo,
                        "preco_recomendado": preco_recomendado,
                        "preco_protegido": preco_seguro,
                        "classificacao_negociacao": (
                            avaliacao_negociacao["classificacao"]
                        ),
                        "mensagem_avaliacao": (
                            avaliacao_negociacao["mensagem"]
                        ),
                        "diferenca_para_minimo": diferenca_minimo,
                        "diferenca_para_recomendado": (
                            diferenca_recomendado
                        ),
                        "exige_aval_gerencia": (
                            avaliacao_negociacao["exige_aval"]
                        ),
                        "aval_gerencia": aval_gerencia_usado,
                        "justificativa_comercial": (
                            justificativa_negociacao_usado
                        ),
                        "cbs": cbs,
                        "ibs": ibs,
                        "credito_pct": credito_pct,
                        "data_aquisicao": (
                            data_aquisicao.strftime("%d/%m/%Y")
                        ),
                        "data_inicio": (
                            data_inicio.strftime("%d/%m/%Y")
                        ),
                    },
                    ensure_ascii=False,
                ),
            }
        )
        st.success("Análise salva com sucesso.")

# ======================================================
# ATIVOS
# ======================================================
elif menu == "5 - Equipamentos e Ativos":
    st.markdown(
        """
        <div class="hero">
            <h1>Equipamentos e Ativos</h1>
            <p>Localize equipamentos cadastrados e utilize seus dados como ponto de partida para uma simulação.</p>
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
elif menu == "4 - Histórico de Simulações":
    st.markdown(
        """
        <div class="hero">
            <h1>Histórico de Simulações</h1>
            <p>Consulte propostas já calculadas e reaproveite condições em novas negociações.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    h = historico()
    if h.empty:
        st.info("Ainda não há simulações salvas.")
    else:
        c1, c2, c3 = st.columns(3)
        tipos = c1.multiselect("Tipo", ["Novo", "Usado"], default=["Novo", "Usado"], key="sim_hist_tipo")
        cli = c2.text_input("Cliente", key="sim_hist_cliente")
        eq = c3.text_input("Equipamento", key="sim_hist_equip")
        view = h.copy()
        if tipos:
            view = view[view["tipo"].isin(tipos)]
        if cli:
            view = view[view["cliente"].str.contains(cli, case=False, na=False)]
        if eq:
            view = view[view["equipamento"].str.contains(eq, case=False, na=False)]
        cols = ["id", "data_hora", "tipo", "cliente", "equipamento", "fabricante", "prazo", "investimento", "aluguel", "aluguel_minimo", "lucro", "lucro_reforma", "margem", "payback", "depreciacao", "valor_contabil", "origem"]
        st.dataframe(
            tabela_formatada(
                view[cols],
                money=["investimento", "aluguel", "aluguel_minimo", "lucro", "lucro_reforma", "valor_contabil"],
                percent=["margem", "depreciacao"],
                months=["payback"],
            ),
            use_container_width=True,
            hide_index=True,
        )
        st.download_button(
            "Exportar simulações",
            view.to_csv(index=False).encode("utf-8-sig"),
            "historico_simulacoes.csv",
            "text/csv",
            use_container_width=True,
        )

# ======================================================
# HISTÓRICO DE COTAÇÕES
# ======================================================
elif menu == "6 - Configurações de Cálculo":
    st.markdown(
        """
        <div class="hero">
            <h1>Configurações de Cálculo</h1>
            <p>Consulte os percentuais e critérios adotados na formação dos preços.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    parametros = pd.DataFrame(
        [
            ["Impostos sobre a locação", "14,30%"],
            ["Equipamento importado", "FOB convertido em reais mais o custo de nacionalização"],
            ["Custo de nacionalização", "65,00% como valor inicial, com edição permitida"],
            ["Equipamento nacional", "Valor de aquisição informado diretamente em reais"],
            ["Dólar para importação", "Cotação de venda do Banco Central, com edição permitida"],
            ["Referência histórica", "Somente linhas em que a coluna NOVA esteja como LOCAÇÃO"],
            ["Preço histórico", "VALOR BRUTO total dividido pela quantidade faturada"],
            [
                "Variações do equipamento",
                "Sufixos como _01, _RV e _TC são reunidos no mesmo código-base",
            ],
            ["Comissões", "Vendedor, gerente e representante podem ser somados"],
            ["Comissão inicial do vendedor", "5,00%"],
            ["Comissão inicial do gerente", "0,50%"],
            ["Margem desejada", "25,00%"],
            ["Financiamento", "Parcelas fixas, com taxa inicial de 1,60% ao mês"],
            ["Vida útil inicial do equipamento", "10 anos"],
            ["Simulação após a reforma tributária", "Percentuais de CBS, IBS e créditos podem ser ajustados"],
            ["Equipamentos usados", "Considera manutenção, atendimento técnico, risco e recuperação do valor do ativo"],
            [
                "Manutenção de equipamentos usados",
                "De 4% a 8% ao ano sobre o valor econômico atual",
            ],
            [
                "Estado de conservação",
                "Excelente reduz 20%, bom mantém e regular aumenta 25%",
            ],
            [
                "Base da manutenção",
                "Valor contábil atual, com piso de 20% do valor original",
            ],
            [
                "Faixas comerciais dos usados",
                "A proteção adicional diminui conforme a depreciação",
            ],
        ],
        columns=["Critério", "Como o sistema considera"],
    )


    st.dataframe(
        parametros,
        use_container_width=True,
        hide_index=True,
    )
