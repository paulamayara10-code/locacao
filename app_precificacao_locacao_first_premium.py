
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
    abas=pd.read_excel(arquivo,sheet_name=None,engine='openpyxl')
    nome=next((n for n in abas if 'BANCO DE DADOS FATURAMENTO' in normalizar_texto_coluna(n)),None)
    if not nome: raise ValueError('A aba BANCO DE DADOS FATURAMENTO não foi encontrada.')
    df=abas[nome].dropna(how='all').copy()
    c={k:localizar_coluna(df,v) for k,v in {
      'categoria':['CATEGORIA'],'numero':['NUMERO','NÚMERO'],'data':['DT EMISSAO','DT EMISSÃO'],'cod':['CLIENTE'],'cliente':['NOME DO CLIENTE'],'resp':['VENDEDOR / REPRESENTANTE'],'produto':['PRODUTO'],'desc':['DESCRIÇÃO','DESCRICAO'],'qtd':['QUANTIDADE'],'preco':['PREÇO UNITÁRIO','PRECO UNITARIO'],'valor':['VALOR'],'bruto':['VALOR BRUTO'],'nf':['NOTA FISCAL'],'segmento':['SEGMENTO'],'gerente':['GERENTE'],'fornecedor':['FORNECEDOR'],'linha':['LINHA DE PRODUTO'],'nova':['NOVA']}.items()}
    if not c['cliente'] or not c['produto']: raise ValueError('Colunas mínimas não encontradas na BASE BI.')
    mask=pd.Series(False,index=df.index)
    for col in [c['categoria'],c['nova'],c['segmento']]:
        if col: mask |= df[col].fillna('').astype(str).map(normalizar_texto_coluna).str.contains(r'LOCA|ALUG',regex=True,na=False)
    df=df[mask].copy(); agora=datetime.now(ZoneInfo('America/Sao_Paulo')).strftime('%d/%m/%Y %H:%M:%S'); regs=[]
    for _,r in df.iterrows():
        cliente=texto_limpo(r.get(c['cliente'])); produto=texto_limpo(r.get(c['produto'])); desc=texto_limpo(r.get(c['desc'])) if c['desc'] else ''
        nota=texto_limpo(r.get(c['nf'])) if c['nf'] else ''; numero=texto_limpo(r.get(c['numero'])) if c['numero'] else ''
        qtd=numero_limpo(r.get(c['qtd'])) if c['qtd'] else 0; preco=numero_limpo(r.get(c['preco'])) if c['preco'] else 0
        total=numero_limpo(r.get(c['bruto'])) if c['bruto'] else 0
        if total<=0 and c['valor']: total=numero_limpo(r.get(c['valor']))
        if not cliente or not produto or (preco<=0 and total<=0): continue
        regs.append({'chave_unica':chave_historica('FATURAMENTO',nota,numero,produto,cliente,qtd,preco,total),'data_importacao':agora,'fonte':'BASE BI - Faturamento','tipo_referencia':'Locação faturada','identificador':numero,'data_referencia':data_excel_para_br(r.get(c['data'])) if c['data'] else '','cliente_codigo':texto_limpo(r.get(c['cod'])) if c['cod'] else '','cliente':cliente,'cnpj':'','equipamento_codigo':produto,'equipamento':desc or produto,'linha_produto':texto_limpo(r.get(c['linha'])) if c['linha'] else '','quantidade':qtd,'valor_unitario':preco,'valor_mensal':total,'valor_total':total,'vendedor':texto_limpo(r.get(c['resp'])) if c['resp'] else '','gerente':texto_limpo(r.get(c['gerente'])) if c['gerente'] else '','sla':'','origem_contrato':texto_limpo(r.get(c['fornecedor'])) if c['fornecedor'] else '','nota_fiscal':nota,'observacao':'Referência de faturamento de locação; valores preservados conforme a base.'})
    return salvar_referencias(regs)

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
            "Proposta de Locação",
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
            f"Proposta de Locação - Equipamento {texto_pdf(tipo)}",
            estilos["FirstTitle"],
        )
    )
    story.append(
        Paragraph(
            f"Validade da proposta: {validade.strftime('%d/%m/%Y')}",
            estilos["FirstSub"],
        )
    )
    story.append(Spacer(1, 7 * mm))

    story.append(Paragraph("Dados da proposta", estilos["Section"]))

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
            ["FIRST MEDICAL", texto_pdf(cliente or "CLIENTE")],
            ["Responsável comercial", "Aceite do cliente"],
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
        "5 - Histórico de Cotações",
        "6 - Parâmetros",
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

    data_ptax = ""
    consulta_brasilia = datetime.now(
        ZoneInfo("America/Sao_Paulo")
    ).strftime("%d/%m/%Y %H:%M")
    ptax_automatica = False

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

        col1, col2 = st.columns(2)
        validade_proposta_usado = col1.number_input(
            "Validade da proposta (dias)",
            min_value=1,
            value=15,
            step=1,
            key="usado_validade_proposta",
        )
        observacoes_proposta_usado = col2.text_area(
            "Observações da proposta",
            height=90,
            key="usado_observacoes_proposta",
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
                "Baixar proposta em PDF",
                data=proposta_pdf_novo,
                file_name=(
                    f"proposta_locacao_novo_"
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
        com_pct = comissao_total(cv, cg, cr)
        st.info(f"Comissão total considerada: {perc(com_pct)}")

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

        detalhes_proposta_usado = {
            "modelo_precificacao": modelo_usado,
            "data_aquisicao": data_aquisicao.strftime("%d/%m/%Y"),
            "depreciacao_atual_pct": dep_atual_form["taxa"],
            "depreciacao_final_pct": dep["taxa"],
            "valor_contabil_final": dep["valor_contabil"],
            "manutencao_mensal": manutencao,
            "pecas_mensais": pecas,
            "seguro_mensal": seguro,
            "horas_tecnicas_mes": horas_tecnico,
            "valor_hora_tecnica": valor_hora,
            "deslocamento_mensal": deslocamento,
            "reserva_risco_pct": reserva_risco_pct,
            "comissao_vendedor_pct": cv,
            "comissao_gerente_pct": cg,
            "comissao_representante_pct": cr,
        }

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
            observacoes=observacoes_proposta_usado,
            validade_dias=validade_proposta_usado,
        )

        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                "Baixar proposta em PDF",
                data=proposta_pdf_usado,
                file_name=(
                    f"proposta_locacao_usado_"
                    f"{_slug_widget(cliente or equipamento or 'cliente')}.pdf"
                ),
                mime="application/pdf",
                use_container_width=True,
            )

        with col2:
            salvar_usado = st.button(
                "Salvar precificação de usado",
                use_container_width=True,
            )

        if salvar_usado:
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
    st.markdown("""<div class="hero"><h1>Histórico de Precificação</h1><p>Simulações do app e referências reais importadas das bases.</p></div>""",unsafe_allow_html=True)
    aba_sim,aba_ref,aba_imp=st.tabs(["Simulações do app","Referências históricas","Importar bases"])
    with aba_sim:
        h=historico()
        if h.empty: st.info("Nenhuma precificação criada no app.")
        else:
            c1,c2,c3=st.columns(3); tipos=c1.multiselect("Tipo",["Novo","Usado"],default=["Novo","Usado"],key="hist_tipo_sim"); cli=c2.text_input("Cliente",key="hist_cliente_sim"); eq=c3.text_input("Equipamento",key="hist_equip_sim")
            view=h.copy()
            if tipos:view=view[view["tipo"].isin(tipos)]
            if cli:view=view[view["cliente"].str.contains(cli,case=False,na=False)]
            if eq:view=view[view["equipamento"].str.contains(eq,case=False,na=False)]
            cols=["id","data_hora","tipo","cliente","equipamento","fabricante","prazo","investimento","aluguel","aluguel_minimo","lucro","lucro_reforma","margem","payback","depreciacao","valor_contabil","origem"]
            st.dataframe(tabela_formatada(view[cols],money=["investimento","aluguel","aluguel_minimo","lucro","lucro_reforma","valor_contabil"],percent=["margem","depreciacao"],months=["payback"]),use_container_width=True,hide_index=True)
            st.download_button("Exportar simulações",view.to_csv(index=False).encode("utf-8-sig"),"historico_simulacoes.csv","text/csv",use_container_width=True)
    with aba_ref:
        refs=referencias_historicas()
        if refs.empty: st.info("Nenhuma referência importada. Use a aba Importar bases.")
        else:
            c1,c2,c3,c4=st.columns(4); fontes=c1.multiselect("Fonte",sorted(refs['fonte'].dropna().unique()),default=sorted(refs['fonte'].dropna().unique()),key='ref_fontes'); cli=c2.text_input('Cliente contém',key='ref_cliente'); eq=c3.text_input('Equipamento contém',key='ref_equipamento'); ger=c4.text_input('Gerente contém',key='ref_gerente')
            view=refs.copy()
            if fontes:view=view[view['fonte'].isin(fontes)]
            if cli:view=view[view['cliente'].str.contains(cli,case=False,na=False)]
            if eq:view=view[view['equipamento'].str.contains(eq,case=False,na=False)]
            if ger:view=view[view['gerente'].str.contains(ger,case=False,na=False)]
            cards=[('Referências',len(view),'Registros filtrados'),('Valor mensal médio',moeda(view['valor_mensal'].mean()),'Contratos e faturamentos'),('Menor referência',moeda(view['valor_mensal'].min()),'Base filtrada'),('Maior referência',moeda(view['valor_mensal'].max()),'Base filtrada')]
            for col,item in zip(st.columns(4),cards):
                with col: card(*item)
            cols=['id','fonte','tipo_referencia','identificador','data_referencia','cliente_codigo','cliente','cnpj','equipamento_codigo','equipamento','linha_produto','quantidade','valor_unitario','valor_mensal','valor_total','vendedor','gerente','sla','origem_contrato','nota_fiscal']
            st.dataframe(tabela_formatada(view[cols],money=['valor_unitario','valor_mensal','valor_total']),use_container_width=True,hide_index=True)
            c1,c2=st.columns(2)
            with c1: st.download_button('Exportar referências',view.to_csv(index=False).encode('utf-8-sig'),'referencias_historicas_precificacao.csv','text/csv',use_container_width=True)
            with c2:
                ids=st.text_input('IDs para excluir',placeholder='Ex.: 2, 8',key='ids_excluir_ref')
                if st.button('Excluir referências',use_container_width=True,key='excluir_ref'):
                    try: excluir_referencias([int(x.strip()) for x in ids.split(',') if x.strip()]); st.success('Referências excluídas.'); st.rerun()
                    except Exception: st.error('Informe IDs válidos separados por vírgula.')
    with aba_imp:
        st.markdown('<div class="section-title">Importação do histórico real</div>',unsafe_allow_html=True)
        st.info('O Controle de Contratos entra como valor mensal contratado. A BASE BI é filtrada para locação e entra como faturamento histórico. Duplicados são ignorados automaticamente.')
        c1,c2=st.columns(2)
        with c1:
            arq=st.file_uploader('Controle de Contratos',type=['xlsx','xlsm'],key='upload_contratos_hist')
            if st.button('Importar contratos',use_container_width=True,key='btn_importar_contratos'):
                if arq is None: st.warning('Selecione o arquivo de contratos.')
                else:
                    try:r=importar_controle_contratos(arq); st.success(f"{r['inseridos']} contratos importados; {r['ignorados']} duplicados ignorados.")
                    except Exception as e: st.error(f'Não foi possível importar: {e}')
        with c2:
            arq=st.file_uploader('BASE BI',type=['xlsx','xlsm'],key='upload_base_bi_hist')
            if st.button('Importar faturamento de locação',use_container_width=True,key='btn_importar_bi'):
                if arq is None: st.warning('Selecione o arquivo BASE BI.')
                else:
                    try:r=importar_base_bi(arq); st.success(f"{r['inseridos']} linhas de locação importadas; {r['ignorados']} duplicadas ignoradas.")
                    except Exception as e: st.error(f'Não foi possível importar: {e}')

# ======================================================
# HISTÓRICO DE COTAÇÕES
# ======================================================
elif menu == "5 - Histórico de Cotações":
    st.markdown(
        """
        <div class="hero">
            <h1>Histórico de Cotações</h1>
            <p>Banco de referências cambiais utilizadas nas precificações.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Consultar e salvar PTAX agora", use_container_width=True):
            try:
                valor_ptax, data_cot, data_consulta = ptax()
                novo_id = salvar_cotacao(
                    {
                        "data_hora_registro": datetime.now(
                            ZoneInfo("America/Sao_Paulo")
                        ).strftime("%d/%m/%Y %H:%M:%S"),
                        "data_hora_cotacao": data_cot,
                        "data_hora_consulta_brasilia": data_consulta,
                        "valor": valor_ptax,
                        "fonte": "PTAX de venda - Banco Central do Brasil",
                        "origem": "Automática",
                        "finalidade": "Referência cambial",
                        "cliente": "",
                        "equipamento": "",
                        "observacao": "",
                        "usada_em_precificacao": 0,
                    }
                )
                st.success(f"PTAX salva no registro {novo_id}.")
                st.rerun()
            except Exception as exc:
                st.error(f"Não foi possível consultar a PTAX: {exc}")

    with col2:
        with st.expander("Cadastrar cotação manual"):
            valor_manual = st.number_input(
                "Cotação em R$", 0.01, value=5.50, step=0.01, format="%.4f"
            )
            data_manual = st.date_input(
                "Data da cotação", date.today(), format="DD/MM/YYYY"
            )
            finalidade_manual = st.text_input("Finalidade")
            cliente_manual = st.text_input("Cliente")
            equipamento_manual = st.text_input("Equipamento")
            observacao_manual = st.text_area("Observação")
            if st.button("Salvar cotação manual", use_container_width=True):
                agora_br = datetime.now(
                    ZoneInfo("America/Sao_Paulo")
                ).strftime("%d/%m/%Y %H:%M:%S")
                salvar_cotacao(
                    {
                        "data_hora_registro": agora_br,
                        "data_hora_cotacao": data_manual.strftime("%d/%m/%Y"),
                        "data_hora_consulta_brasilia": agora_br,
                        "valor": valor_manual,
                        "fonte": "Informada manualmente",
                        "origem": "Manual",
                        "finalidade": finalidade_manual,
                        "cliente": cliente_manual,
                        "equipamento": equipamento_manual,
                        "observacao": observacao_manual,
                        "usada_em_precificacao": 0,
                    }
                )
                st.success("Cotação manual salva.")
                st.rerun()

    cotacoes = historico_cotacoes()
    if cotacoes.empty:
        st.info("Nenhuma cotação salva.")
    else:
        cards_cot = [
            ("Última cotação", f"R$ {cotacoes.iloc[0]['valor']:.4f}", cotacoes.iloc[0]['origem']),
            ("Média histórica", f"R$ {cotacoes['valor'].mean():.4f}", f"{len(cotacoes)} registros"),
            ("Menor cotação", f"R$ {cotacoes['valor'].min():.4f}", "Base salva"),
            ("Maior cotação", f"R$ {cotacoes['valor'].max():.4f}", "Base salva"),
        ]
        cols = st.columns(4)
        for col, item in zip(cols, cards_cot):
            with col:
                card(*item)

        st.markdown(
            '<div class="section-title">Evolução das cotações</div>',
            unsafe_allow_html=True,
        )
        grafico = cotacoes.sort_values("id")[["id", "valor"]].set_index("id")
        st.line_chart(grafico)

        col1, col2, col3 = st.columns(3)
        origens = sorted(cotacoes["origem"].dropna().unique().tolist())
        filtro_origem = col1.multiselect("Origem", origens, default=origens)
        filtro_finalidade = col2.text_input("Finalidade contém")
        somente_usadas = col3.checkbox("Somente usadas em precificação")

        view = cotacoes.copy()
        if filtro_origem:
            view = view[view["origem"].isin(filtro_origem)]
        if filtro_finalidade:
            view = view[
                view["finalidade"].str.contains(
                    filtro_finalidade, case=False, na=False
                )
            ]
        if somente_usadas:
            view = view[view["usada_em_precificacao"] == 1]

        exibicao = view.copy()
        exibicao["valor"] = exibicao["valor"].map(lambda x: f"R$ {x:.4f}")
        exibicao["usada_em_precificacao"] = exibicao[
            "usada_em_precificacao"
        ].map({1: "Sim", 0: "Não"})
        st.dataframe(exibicao, use_container_width=True, hide_index=True)

        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                "Exportar cotações",
                data=view.to_csv(index=False).encode("utf-8-sig"),
                file_name="historico_cotacoes.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with col2:
            ids_texto = st.text_input("IDs para excluir", placeholder="Ex.: 2, 5")
            if st.button("Excluir cotações", use_container_width=True):
                try:
                    ids = [
                        int(x.strip())
                        for x in ids_texto.split(",")
                        if x.strip()
                    ]
                    excluir_cotacoes(ids)
                    st.success("Cotações excluídas.")
                    st.rerun()
                except Exception:
                    st.error("Informe IDs válidos separados por vírgula.")

# ======================================================
# PARÂMETROS
# ======================================================
elif menu == "6 - Parâmetros":
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
            ["Banco de cotações", "SQLite com PTAX automática e registros manuais"],
            ["Proposta comercial", "Download em PDF para novos e usados"],
            ["Comissão vendedor", "5,00%"],
            ["Comissão gerente", "0,50%"],
            ["Comissões", "Vendedor, gerente e representante podem ser cumulativas"],
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
