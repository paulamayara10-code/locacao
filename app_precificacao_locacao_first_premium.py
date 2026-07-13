import json, re, sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
import numpy as np
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title='First Medical | Precificação', page_icon='💼', layout='wide')
DB='historico_precificacao.db'; ATIVOS='ativos_pre_cadastro.csv'
IMP=14.30; NAC=65.0; CV=5.0; CG=0.5; CR=14.0; MARGEM=25.0; TAXA_FIN=1.60; PRAZO_FIN=36

st.markdown('''<style>
.stApp{background:linear-gradient(180deg,#F5F8FC 0%,#EEF3F8 100%)}
section[data-testid="stSidebar"]{background:linear-gradient(180deg,#071F33 0%,#0B2F4A 100%)}
section[data-testid="stSidebar"] *{color:white!important}
.hero{background:linear-gradient(135deg,#0B2F4A 0%,#155E75 70%,#1B7893 100%);border-radius:24px;padding:28px 32px;color:white;margin-bottom:20px}
.hero h1{margin:0;font-size:2rem}.hero p{margin:8px 0 0;color:#e8f2f8}
.metric-card{background:white;border-radius:18px;padding:18px 20px;box-shadow:0 8px 24px rgba(15,46,74,.07);min-height:112px;margin-bottom:12px}
.metric-label{color:#64748B;font-size:.78rem;text-transform:uppercase;font-weight:800}.metric-value{color:#0B2F4A;font-size:1.35rem;font-weight:850;margin-top:8px}.metric-help{color:#64748B;font-size:.84rem;margin-top:6px}
.section-title{color:#0B2F4A;font-size:1.18rem;font-weight:850;margin:16px 0 10px}
.stButton>button,.stDownloadButton>button{border-radius:14px!important;border:0!important;background:linear-gradient(135deg,#0B2F4A,#155E75)!important;color:white!important;font-weight:800!important}
</style>''', unsafe_allow_html=True)

def init_db():
    c=sqlite3.connect(DB); c.execute('''CREATE TABLE IF NOT EXISTS historico(
    id INTEGER PRIMARY KEY AUTOINCREMENT,data_hora TEXT,tipo TEXT,cliente TEXT,equipamento TEXT,fabricante TEXT,responsavel TEXT,prazo INTEGER,investimento REAL,aluguel REAL,receita REAL,custos REAL,impostos REAL,comissao REAL,lucro REAL,margem REAL,aluguel_minimo REAL,origem TEXT,detalhes TEXT)'''); c.commit(); c.close()
def salvar(d):
    c=sqlite3.connect(DB); cols=', '.join(d); vals=', '.join(['?']*len(d)); c.execute(f'INSERT INTO historico({cols}) VALUES({vals})',list(d.values())); c.commit(); c.close()
def hist():
    c=sqlite3.connect(DB)
    try: df=pd.read_sql_query('SELECT * FROM historico ORDER BY id DESC',c)
    except: df=pd.DataFrame()
    c.close(); return df
init_db()

def moeda(v):
    try:return f'R$ {float(v):,.2f}'.replace(',','X').replace('.',',').replace('X','.')
    except:return 'R$ 0,00'
def perc(v):
    try:return f'{float(v):.2f}%'.replace('.',',')
    except:return '0,00%'
def parse(v):
    if isinstance(v,(int,float,np.integer,np.floating)): return float(v)
    s=str(v or '').replace('R$','').replace(' ','')
    if ',' in s and '.' in s:s=s.replace('.','').replace(',','.')
    elif ',' in s:s=s.replace(',','.')
    s=re.sub(r'[^0-9.\-]','',s)
    try:return float(s)
    except:return 0.0
def input_rs(label,valor,key):
    t=st.text_input(label,value=moeda(valor),key=key); v=parse(t); st.caption(f'Valor considerado: {moeda(v)}'); return v
def card(l,v,h): st.markdown(f'<div class="metric-card"><div class="metric-label">{l}</div><div class="metric-value">{v}</div><div class="metric-help">{h}</div></div>',unsafe_allow_html=True)

def price(valor,taxa,prazo):
    if valor<=0 or prazo<=0:return 0.0
    i=taxa/100
    return valor/prazo if i==0 else valor*(i*(1+i)**prazo)/((1+i)**prazo-1)

def calc(invest,prazo,aluguel,custos,imp,com,margem,custo_fin=0):
    rec=aluguel*prazo; impostos=rec*imp/100; comissao=rec*com/100; ct=invest+custos+custo_fin; lucro=rec-ct-impostos-comissao; mg=lucro/rec*100 if rec else 0
    den=1-imp/100-com/100-margem/100; minimo=(ct/prazo)/den if den>0 and prazo>0 else 0
    return dict(receita=rec,impostos=impostos,comissao=comissao,custos=ct,lucro=lucro,margem=mg,minimo=minimo)

def com_pct(tipo,v,g,r): return v+g if tipo=='Vendedor + gerente' else r if tipo=='Representante' else 0.0

@st.cache_data(ttl=3600,show_spinner=False)
def ptax():
    fim=date.today(); ini=fim-timedelta(days=10)
    url=('https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/'
         'CotacaoDolarPeriodo(dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)'
         f"?@dataInicial='{ini.strftime('%m-%d-%Y')}'&@dataFinalCotacao='{fim.strftime('%m-%d-%Y')}'"
         '&$top=100&$orderby=dataHoraCotacao%20desc&$format=json&$select=cotacaoVenda,dataHoraCotacao')
    r=requests.get(url,timeout=12); r.raise_for_status(); vals=r.json().get('value',[])
    if not vals: raise RuntimeError('sem cotação')
    x=vals[0]; dt=pd.to_datetime(x['dataHoraCotacao'],errors='coerce')
    return float(x['cotacaoVenda']), (dt.strftime('%d/%m/%Y %H:%M') if not pd.isna(dt) else '')

@st.cache_data
def ativos():
    p=Path(ATIVOS)
    if not p.exists(): return pd.DataFrame()
    for kw in [dict(sep=None,engine='python',encoding='utf-8-sig'),dict(sep=';',encoding='latin1')]:
        try:return pd.read_csv(p,**kw).fillna('')
        except:pass
    return pd.DataFrame()
def col(r,nomes,default=''):
    for n in nomes:
        if n in r.index and pd.notna(r[n]):return r[n]
    return default
def ativo_info(r):
    return {'equipamento':str(col(r,['Descricao','Descrição','Desc Bem','descricao','Produto'],'')),'fabricante':str(col(r,['Marca','Fabricante','marca'],'')),'valor':parse(col(r,['Valor_Aquisicao','Valor Aquisição','Vl Aquisicao','Vl_Aquisicao','valor_aquisicao'],0)),'codigo':str(col(r,['Codigo','Código','Cod Bem','Cod_Bem','codigo'],''))}
def label(r):
    a=ativo_info(r); return f"{a['codigo']} | {a['equipamento'][:65]} | {moeda(a['valor'])}"

st.sidebar.markdown('## FIRST MEDICAL\n### Precificação de Locação\n---')
menu=st.sidebar.radio('Menu',['Visão Geral','1 - Locação de Novos','2 - Locação de Usados','3 - Ativos','4 - Histórico','5 - Parâmetros'])

if menu=='Visão Geral':
    st.markdown('<div class="hero"><h1>Precificação de Locação</h1><p>Equipamentos novos e usados em fluxos independentes.</p></div>',unsafe_allow_html=True)
    h=hist(); cols=st.columns(4)
    vals=[('Precificações',len(h),'Registros salvos'),('Novos',int((h.tipo=='Novo').sum()) if not h.empty else 0,'Equipamentos novos'),('Usados',int((h.tipo=='Usado').sum()) if not h.empty else 0,'Equipamentos usados'),('Margem média',perc(h.margem.mean()) if not h.empty else '0,00%','Histórico')]
    for c,x in zip(cols,vals):
        with c: card(*x)
    if not h.empty:
        st.bar_chart(h.head(20)[['equipamento','margem']].set_index('equipamento'))
        v=h[['data_hora','tipo','cliente','equipamento','prazo','aluguel','lucro','margem']].head(15).copy(); v['aluguel']=v.aluguel.map(moeda); v['lucro']=v.lucro.map(moeda); v['margem']=v.margem.map(perc); st.dataframe(v,use_container_width=True,hide_index=True)

elif menu=='1 - Locação de Novos':
    st.markdown('<div class="hero"><h1>Locação de Equipamentos Novos</h1><p>FOB em dólar, nacionalização, financiamento, impostos e comissão.</p></div>',unsafe_allow_html=True)
    try: dolar0,dt=ptax(); st.success(f'Dólar PTAX de venda: R$ {dolar0:.4f} em {dt}')
    except: dolar0=5.50; st.warning('Não foi possível consultar a PTAX. Informe a cotação manualmente.')
    with st.form('novos'):
        c1,c2,c3=st.columns(3); cliente=c1.text_input('Cliente'); equipamento=c2.text_input('Equipamento'); fabricante=c3.text_input('Fabricante / linha')
        c1,c2,c3=st.columns(3); resp=c1.text_input('Vendedor / representante'); prazo=c2.number_input('Prazo (meses)',1,120,24); c3.date_input('Data',date.today(),format='DD/MM/YYYY')
        st.markdown('<div class="section-title">Importação e nacionalização</div>',unsafe_allow_html=True)
        c1,c2,c3=st.columns(3); fob=c1.number_input('Valor FOB (US$)',0.0,step=100.0,format='%.2f'); dolar=c2.number_input('Dólar utilizado (R$)',0.01,value=float(dolar0),step=0.01,format='%.4f'); nac=c3.number_input('Nacionalização (%)',0.0,value=NAC,step=1.0)
        fob_brl=fob*dolar; custo_nac=fob_brl*nac/100; investimento=fob_brl+custo_nac; st.info(f'FOB convertido: {moeda(fob_brl)} | Nacionalização: {moeda(custo_nac)} | Investimento: {moeda(investimento)}')
        st.markdown('<div class="section-title">Origem do investimento</div>',unsafe_allow_html=True)
        origem=st.radio('Origem',['Capital próprio','Financiamento bancário'],horizontal=True)
        custo_fin=0; entrada=0; financiado=0; taxa=TAXA_FIN; prazo_fin=PRAZO_FIN; parcela=0
        if origem=='Financiamento bancário':
            c1,c2,c3=st.columns(3)
            with c1: entrada=input_rs('Entrada',0,'n_ent')
            with c2: financiado=input_rs('Valor financiado',max(investimento-entrada,0),'n_fin')
            prazo_fin=c3.number_input('Prazo financiamento',1,120,PRAZO_FIN)
            c1,c2=st.columns(2); taxa=c1.number_input('Taxa mensal (%)',0.0,value=TAXA_FIN,step=0.1); parcela=price(financiado,taxa,prazo_fin); custo_fin=max(parcela*prazo_fin-financiado,0); c2.metric('Parcela estimada',moeda(parcela)); st.info(f'Custo financeiro total: {moeda(custo_fin)}')
        st.markdown('<div class="section-title">Comissão</div>',unsafe_allow_html=True)
        tipo=st.radio('Modelo',['Vendedor + gerente','Representante','Sem comissão'],horizontal=True); c1,c2,c3=st.columns(3); cv=c1.number_input('Vendedor (%)',0.0,value=CV,step=0.25,disabled=tipo!='Vendedor + gerente'); cg=c2.number_input('Gerente (%)',0.0,value=CG,step=0.25,disabled=tipo!='Vendedor + gerente'); cr=c3.number_input('Representante (%)',0.0,value=CR,step=0.5,disabled=tipo!='Representante'); cp=com_pct(tipo,cv,cg,cr)
        c1,c2,c3=st.columns(3)
        with c1: aluguel=input_rs('Aluguel mensal',0,'n_alug')
        with c2: despesas=input_rs('Despesas adicionais totais',0,'n_desp')
        margem=c3.number_input('Margem desejada (%)',0.0,value=MARGEM,step=1.0)
        st.number_input('Impostos sobre locação (%)',value=IMP,disabled=True)
        ok=st.form_submit_button('Calcular precificação',use_container_width=True)
    if ok:
        r=calc(investimento,int(prazo),aluguel,despesas,IMP,cp,margem,custo_fin); cols=st.columns(4); dados=[('Investimento',moeda(investimento),'FOB + nacionalização'),('Aluguel mínimo',moeda(r['minimo']),f'Margem {perc(margem)}'),('Lucro',moeda(r['lucro']),'Com aluguel informado'),('Margem',perc(r['margem']),'Lucro sobre receita')]
        for c,x in zip(cols,dados):
            with c: card(*x)
        cols=st.columns(4); dados=[('Receita total',moeda(r['receita']),f'{prazo} meses'),('Impostos',moeda(r['impostos']),'14,30%'),('Comissão',moeda(r['comissao']),perc(cp)),('Custo financeiro',moeda(custo_fin),origem)]
        for c,x in zip(cols,dados):
            with c: card(*x)
        if st.button('Salvar precificação de novo',use_container_width=True):
            salvar(dict(data_hora=datetime.now().strftime('%d/%m/%Y %H:%M:%S'),tipo='Novo',cliente=cliente,equipamento=equipamento,fabricante=fabricante,responsavel=resp,prazo=int(prazo),investimento=investimento,aluguel=aluguel,receita=r['receita'],custos=r['custos'],impostos=r['impostos'],comissao=r['comissao'],lucro=r['lucro'],margem=r['margem'],aluguel_minimo=r['minimo'],origem=origem,detalhes=json.dumps({'fob_usd':fob,'dolar':dolar,'nacionalizacao':nac,'modelo_comissao':tipo,'comissao_pct':cp,'parcela':parcela},ensure_ascii=False))); st.success('Precificação salva.')

elif menu=='2 - Locação de Usados':
    st.markdown('<div class="hero"><h1>Locação de Equipamentos Usados</h1><p>Manutenção, peças, horas técnicas, impostos e comissão.</p></div>',unsafe_allow_html=True)
    a=ativos(); info={}
    if not a.empty:
        busca=st.text_input('Buscar ativo'); f=a.copy()
        if busca: f=f[f.astype(str).apply(lambda x:x.str.contains(busca,case=False,na=False)).any(axis=1)]
        opts=['Não selecionar']+[label(r) for _,r in f.head(300).iterrows()]; sel=st.selectbox('Selecionar ativo',opts)
        if sel!='Não selecionar': info=ativo_info(f.iloc[opts.index(sel)-1]); st.success(f"Ativo: {info['equipamento']} | Aquisição: {moeda(info['valor'])}")
    with st.form('usados'):
        c1,c2,c3=st.columns(3); cliente=c1.text_input('Cliente'); equipamento=c2.text_input('Equipamento',value=info.get('equipamento','')); fabricante=c3.text_input('Fabricante / linha',value=info.get('fabricante',''))
        c1,c2,c3=st.columns(3); resp=c1.text_input('Vendedor / representante'); prazo=c2.number_input('Prazo (meses)',1,120,24); c3.date_input('Data',date.today(),format='DD/MM/YYYY')
        st.markdown('<div class="section-title">Custos para manter funcionando</div>',unsafe_allow_html=True)
        c1,c2,c3=st.columns(3)
        with c1: manut=input_rs('Manutenção mensal',0,'u_man')
        with c2: pecas=input_rs('Peças / consumíveis mensais',0,'u_pec')
        with c3: seguro=input_rs('Seguro mensal',0,'u_seg')
        c1,c2,c3=st.columns(3); horas=c1.number_input('Horas técnicas por mês',0.0,step=1.0)
        with c2: vh=input_rs('Valor da hora técnica',0,'u_hora')
        with c3: desloc=input_rs('Deslocamento mensal',0,'u_desl')
        c1,c2,c3=st.columns(3)
        with c1: revisao=input_rs('Revisão inicial / recuperação',0,'u_rev')
        with c2: outros=input_rs('Outros custos mensais',0,'u_out')
        recuperar=c3.checkbox('Recuperar valor contábil no contrato',False)
        valor_ativo=info.get('valor',0.0)
        if recuperar: valor_ativo=input_rs('Valor-base do ativo',valor_ativo,'u_valor')
        st.markdown('<div class="section-title">Comissão</div>',unsafe_allow_html=True)
        tipo=st.radio('Modelo',['Vendedor + gerente','Representante','Sem comissão'],horizontal=True,key='u_tipo'); c1,c2,c3=st.columns(3); cv=c1.number_input('Vendedor (%)',0.0,value=CV,step=0.25,disabled=tipo!='Vendedor + gerente',key='u_cv'); cg=c2.number_input('Gerente (%)',0.0,value=CG,step=0.25,disabled=tipo!='Vendedor + gerente',key='u_cg'); cr=c3.number_input('Representante (%)',0.0,value=CR,step=0.5,disabled=tipo!='Representante',key='u_cr'); cp=com_pct(tipo,cv,cg,cr)
        c1,c2=st.columns(2)
        with c1: aluguel=input_rs('Aluguel mensal',0,'u_alug')
        margem=c2.number_input('Margem desejada (%)',0.0,value=MARGEM,step=1.0)
        st.number_input('Impostos sobre locação (%)',value=IMP,disabled=True,key='u_imp'); ok=st.form_submit_button('Calcular precificação',use_container_width=True)
    if ok:
        tecnico=horas*vh; mensal=manut+pecas+seguro+tecnico+desloc+outros; contrato=mensal*prazo+revisao; investimento=valor_ativo if recuperar else 0; r=calc(investimento,int(prazo),aluguel,contrato,IMP,cp,margem,0)
        cols=st.columns(4); dados=[('Custo operacional mensal',moeda(mensal),'Manutenção + técnico'),('Aluguel mínimo',moeda(r['minimo']),f'Margem {perc(margem)}'),('Lucro',moeda(r['lucro']),'Com aluguel informado'),('Margem',perc(r['margem']),'Lucro sobre receita')]
        for c,x in zip(cols,dados):
            with c: card(*x)
        cols=st.columns(4); dados=[('Horas técnicas',f'{horas:.1f} h/mês',moeda(tecnico)),('Custos no contrato',moeda(contrato),f'{prazo} meses'),('Impostos',moeda(r['impostos']),'14,30%'),('Comissão',moeda(r['comissao']),perc(cp))]
        for c,x in zip(cols,dados):
            with c: card(*x)
        if st.button('Salvar precificação de usado',use_container_width=True):
            salvar(dict(data_hora=datetime.now().strftime('%d/%m/%Y %H:%M:%S'),tipo='Usado',cliente=cliente,equipamento=equipamento,fabricante=fabricante,responsavel=resp,prazo=int(prazo),investimento=investimento,aluguel=aluguel,receita=r['receita'],custos=r['custos'],impostos=r['impostos'],comissao=r['comissao'],lucro=r['lucro'],margem=r['margem'],aluguel_minimo=r['minimo'],origem='Ativo próprio',detalhes=json.dumps({'manutencao_mensal':manut,'pecas_mensais':pecas,'horas_tecnico':horas,'valor_hora':vh,'custo_tecnico':tecnico,'modelo_comissao':tipo,'comissao_pct':cp},ensure_ascii=False))); st.success('Precificação salva.')

elif menu=='3 - Ativos':
    st.markdown('<div class="hero"><h1>Ativos</h1><p>Consulta da base pré-cadastrada.</p></div>',unsafe_allow_html=True); a=ativos()
    if a.empty: st.warning('Arquivo ativos_pre_cadastro.csv não encontrado ou vazio.')
    else:
        busca=st.text_input('Buscar'); v=a.copy()
        if busca:v=v[v.astype(str).apply(lambda x:x.str.contains(busca,case=False,na=False)).any(axis=1)]
        st.dataframe(v,use_container_width=True,hide_index=True)

elif menu=='4 - Histórico':
    st.markdown('<div class="hero"><h1>Histórico de Precificação</h1><p>Lista de novos e usados já precificados.</p></div>',unsafe_allow_html=True); h=hist()
    if h.empty: st.info('Nenhuma precificação salva.')
    else:
        c1,c2,c3=st.columns(3); tipos=c1.multiselect('Tipo',['Novo','Usado'],default=['Novo','Usado']); cli=c2.text_input('Cliente'); eq=c3.text_input('Equipamento'); v=h.copy()
        if tipos:v=v[v.tipo.isin(tipos)]
        if cli:v=v[v.cliente.str.contains(cli,case=False,na=False)]
        if eq:v=v[v.equipamento.str.contains(eq,case=False,na=False)]
        view=v[['id','data_hora','tipo','cliente','equipamento','fabricante','responsavel','prazo','investimento','aluguel','aluguel_minimo','lucro','margem','origem']].copy()
        for c in ['investimento','aluguel','aluguel_minimo','lucro']:view[c]=view[c].map(moeda)
        view['margem']=view.margem.map(perc); st.dataframe(view,use_container_width=True,hide_index=True)
        st.download_button('Exportar histórico',data=v.to_csv(index=False).encode('utf-8-sig'),file_name='historico_precificacao.csv',mime='text/csv',use_container_width=True)

else:
    st.markdown('<div class="hero"><h1>Parâmetros</h1><p>Premissas padrão usadas no app.</p></div>',unsafe_allow_html=True)
    st.dataframe(pd.DataFrame([['Impostos sobre locação','14,30%'],['Nacionalização de novos','65,00% — editável'],['Dólar','PTAX de venda do Banco Central'],['Comissão vendedor','5,00%'],['Comissão gerente','0,50%'],['Comissão representante','14,00% — editável'],['Margem desejada','25,00%'],['Financiamento','Tabela Price; 1,60% a.m.'],['Usados','Manutenção + peças + horas técnicas + demais custos']],columns=['Parâmetro','Valor']),use_container_width=True,hide_index=True)
