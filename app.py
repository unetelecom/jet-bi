"""
═══════════════════════════════════════════════════════════════════════════════
  JET BI — Plataforma de BI Financeiro · Grupo JET
═══════════════════════════════════════════════════════════════════════════════

Plataforma web que processa relatórios do HubSoft + extratos bancários
e gera dashboards de conciliação, inadimplência, fluxo de caixa, etc.

Como rodar local:
  pip install -r requirements.txt
  streamlit run app.py

Como hospedar (Streamlit Cloud):
  1. Push para GitHub
  2. Conectar em share.streamlit.io
  3. Configurar secrets (usuários/senhas) no painel
"""

import streamlit as st
import streamlit_authenticator as stauth
import pandas as pd
import numpy as np
import re
import io
from pathlib import Path
from datetime import datetime, timedelta
from itertools import combinations
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURAÇÃO E TEMA
# ═══════════════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="JET BI · Grupo JET",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

BRAND_ORANGE = "#FF5A00"
BRAND_LIGHT = "#FFA366"
BRAND_DARK = "#CC4800"
GRAY = "#6B6B6B"

# Custom CSS
st.markdown(f"""
<style>
    /* Hide Streamlit footer */
    footer {{visibility: hidden;}}
    #MainMenu {{visibility: hidden;}}

    /* Headers brand color */
    h1, h2, h3 {{
        color: {BRAND_ORANGE};
        font-weight: 600;
    }}

    /* Sidebar */
    [data-testid="stSidebar"] {{
        background-color: #1a1a1a;
    }}
    [data-testid="stSidebar"] * {{
        color: #ffffff !important;
    }}
    [data-testid="stSidebar"] .stRadio > label {{
        color: #ffffff !important;
    }}

    /* Buttons */
    .stButton > button {{
        background-color: {BRAND_ORANGE};
        color: white;
        border: none;
        border-radius: 4px;
        font-weight: 500;
    }}
    .stButton > button:hover {{
        background-color: {BRAND_DARK};
        color: white;
    }}

    /* Metric cards */
    [data-testid="stMetricValue"] {{
        color: {BRAND_ORANGE};
        font-weight: 700;
    }}

    /* Dataframe */
    [data-testid="stDataFrame"] {{
        border: 1px solid #e0e0e0;
        border-radius: 4px;
    }}
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# AUTENTICAÇÃO
# ═══════════════════════════════════════════════════════════════════════════════

def get_auth_config():
    """Lê configuração de usuários do secrets.toml (Streamlit Cloud) ou padrão."""
    try:
        # Em produção (Streamlit Cloud), usar st.secrets
        users_dict = {}
        for user_key in st.secrets["users"]:
            users_dict[user_key] = {
                "name": st.secrets["users"][user_key]["name"],
                "password": st.secrets["users"][user_key]["password"],
            }
        return {
            "credentials": {"usernames": users_dict},
            "cookie": {
                "name": st.secrets["cookie"]["name"],
                "key": st.secrets["cookie"]["key"],
                "expiry_days": int(st.secrets["cookie"]["expiry_days"]),
            },
        }
    except (KeyError, FileNotFoundError, Exception):
        # Fallback local: usuário admin com senha "jet2026"
        return {
            "credentials": {
                "usernames": {
                    "admin": {
                        "name": "Administrador",
                        "password": "$2b$12$qM/0czZH9ipLwQVCkKO0c.4t4QnqcZjE7du/rlquO3lRixJZQv30q",
                    }
                }
            },
            "cookie": {
                "name": "jet_bi_auth",
                "key": "trocar-essa-chave-em-producao-32-caracteres-no-minimo",
                "expiry_days": 7,
            },
        }


def login():
    """Renderiza tela de login e retorna status."""
    config = get_auth_config()
    authenticator = stauth.Authenticate(
        config["credentials"],
        config["cookie"]["name"],
        config["cookie"]["key"],
        config["cookie"]["expiry_days"],
    )

    # Logo / título antes do login
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown(f"<h1 style='text-align: center; color: {BRAND_ORANGE};'>JET BI</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #888;'>Plataforma de BI Financeiro · Grupo JET</p>", unsafe_allow_html=True)

    # API 0.3.2: login() retorna tuple (name, auth_status, username)
    try:
        name, auth_status, username = authenticator.login(location="main")
    except TypeError:
        # Fallback para versões mais antigas que usam posicional
        name, auth_status, username = authenticator.login("Login", "main")

    if auth_status is False:
        st.error("Usuário ou senha inválidos.")
    elif auth_status is None:
        st.info("Faça login para continuar.")

    return authenticator, auth_status, name


# ═══════════════════════════════════════════════════════════════════════════════
# PARSERS DE ARQUIVOS
# ═══════════════════════════════════════════════════════════════════════════════

def parse_hubsoft_xlsx(file) -> pd.DataFrame:
    """Lê o relatório de faturas do HubSoft (xlsx)."""
    df = pd.read_excel(file)
    # Remove linha de total (HubSoft adiciona no final)
    df = df[df['codigo_cliente'].astype(str) != '-'].copy()

    # Converte valores
    for col in ['valor', 'valor_pago']:
        if col in df.columns:
            df[col] = df[col].astype(str).str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    # Converte datas
    for col in ['data_vencimento', 'data_pagamento']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], format='%d/%m/%Y', errors='coerce')

    return df


def parse_ofx(file) -> pd.DataFrame:
    """Lê extrato bancário OFX. Detecta banco automaticamente."""
    text = file.read().decode('latin-1', errors='ignore')

    # Detectar banco pelo BANKID (código do banco — mais confiável que ORG)
    # 001=BB, 033=Santander, 104=Caixa, 208=BTG, 237=Bradesco, 260=NuBank, 336=C6, 341=Itaú, 748=Sicredi
    BANK_CODES = {
        '001': 'Banco do Brasil',
        '033': 'Santander',
        '104': 'Caixa Econômica',
        '208': 'BTG Pactual',
        '237': 'Bradesco',
        '260': 'Nubank',
        '336': 'C6 Bank',
        '341': 'Itaú',
        '748': 'Sicredi',
        '756': 'Sicoob',
    }
    bankid_match = re.search(r'<BANKID>([^\r\n<]+)', text)
    bankid = bankid_match.group(1).strip().lstrip('0') if bankid_match else None
    bankid_padded = bankid.zfill(3) if bankid else None

    banco = None
    if bankid_padded and bankid_padded in BANK_CODES:
        banco = BANK_CODES[bankid_padded]

    # Fallback: pelo ORG/FID (caso BANKID não esteja claro)
    if not banco:
        org_match = re.search(r'<ORG>([^\r\n<]+)', text)
        org = org_match.group(1).strip().upper() if org_match else ""
        if "C6" in org: banco = "C6 Bank"
        elif "SICREDI" in org or "CCPI" in org: banco = "Sicredi"
        elif "CAIXA" in org: banco = "Caixa Econômica"
        elif "BTG" in org: banco = "BTG Pactual"
        elif "BRADESCO" in org: banco = "Bradesco"
        elif "ITAU" in org or "ITAÚ" in org: banco = "Itaú"
        elif "SANTANDER" in org: banco = "Santander"
        elif "BANCO DO BRASIL" in org: banco = "Banco do Brasil"
        else: banco = org or "Desconhecido"

    # Parse transações
    blocks = re.findall(r'<STMTTRN>(.*?)</STMTTRN>', text, re.DOTALL)
    if not blocks:
        blocks = re.findall(r'<STMTTRN>(.*?)(?=<STMTTRN>|</BANKTRANLIST>)', text, re.DOTALL)

    rows = []
    for b in blocks:
        def get(tag):
            m = re.search(f'<{tag}>([^\r\n<]+)', b)
            return m.group(1).strip() if m else None
        tipo = get('TRNTYPE')
        if tipo != 'CREDIT':
            continue
        rows.append({
            'Data': get('DTPOSTED'),
            'Valor': float(get('TRNAMT') or 0),
            'memo': get('MEMO') or '',
            'banco': banco,
        })

    df = pd.DataFrame(rows)
    if len(df) == 0:
        return df
    df['Data'] = pd.to_datetime(df['Data'].str[:8], format='%Y%m%d', errors='coerce')
    df = df.dropna(subset=['Data'])
    return df


def parse_btg_csv(file) -> pd.DataFrame:
    """Lê extrato BTG Pactual em CSV."""
    df = pd.read_csv(file)
    df['Data'] = pd.to_datetime(df['Data'], format='%d/%m/%Y')
    df['Valor'] = df['Valor'].astype(str).str.replace('.', '', regex=False).str.replace(',', '.', regex=False).astype(float)
    df = df[df['Valor'] > 0].copy()
    df = df.rename(columns={'Descricao': 'memo'})
    df['banco'] = 'BTG Pactual'
    return df[['Data', 'Valor', 'memo', 'banco']]


# ═══════════════════════════════════════════════════════════════════════════════
# INTEGRAÇÃO API HUBSOFT
# ═══════════════════════════════════════════════════════════════════════════════

def hubsoft_authenticate(url: str, client_id: str, client_secret: str,
                         username: str, password: str) -> str:
    """Faz OAuth2 password grant e retorna access_token."""
    import requests
    base = url.rstrip('/')
    resp = requests.post(
        f"{base}/oauth/token",
        json={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "password",
            "username": username,
            "password": password,
        },
        timeout=30,
        headers={"Accept": "application/json"},
    )
    resp.raise_for_status()
    data = resp.json()
    if "access_token" not in data:
        raise ValueError(f"Resposta sem access_token: {data}")
    return data["access_token"]


def hubsoft_get_invoices(url: str, token: str, progress_cb=None,
                          data_inicio: str = None, data_fim: str = None) -> list:
    """Baixa todas as faturas paginadas. Retorna lista de dicts.

    Endpoint oficial: /api/v1/integracao/financeiro/fatura
    Documentação: https://wiki.hubsoft.com.br
    """
    import requests
    base = url.rstrip('/')
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    endpoint = "/api/v1/integracao/financeiro/fatura"

    all_invoices = []
    pagina = 1
    erros_endpoint = []

    while True:
        params = {"itens_por_pagina": 100, "pagina": pagina}
        if data_inicio:
            params["data_inicio"] = data_inicio
        if data_fim:
            params["data_fim"] = data_fim

        try:
            resp = requests.get(
                f"{base}{endpoint}",
                headers=headers,
                params=params,
                timeout=120,
            )
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"Falha de rede: {e}")

        if resp.status_code == 401:
            raise PermissionError("Token expirou ou credenciais inválidas.")
        if resp.status_code == 404:
            # Tentar endpoint legado como fallback
            endpoint_alt = "/api/v1/integracao/cliente/financeiro"
            erros_endpoint.append(f"{endpoint} → 404")
            try:
                resp = requests.get(
                    f"{base}{endpoint_alt}",
                    headers=headers, params=params, timeout=120,
                )
                if resp.status_code == 200:
                    endpoint = endpoint_alt
                else:
                    erros_endpoint.append(f"{endpoint_alt} → {resp.status_code}")
                    raise ValueError(
                        f"Endpoints de faturas retornaram erro:\n" +
                        "\n".join(f"  - {e}" for e in erros_endpoint) +
                        f"\n\nResposta: {resp.text[:300]}"
                    )
            except requests.exceptions.RequestException as e:
                raise ConnectionError(f"Falha de rede: {e}")

        if resp.status_code != 200:
            raise ValueError(f"API retornou HTTP {resp.status_code}: {resp.text[:500]}")

        try:
            data = resp.json()
        except Exception:
            raise ValueError(f"Resposta da API não é JSON válido: {resp.text[:300]}")

        # API HubSoft retorna geralmente: {"status": "success", "faturas": [...], "paginacao": {...}}
        if isinstance(data, dict):
            invoices = (data.get("faturas") or data.get("data") or
                       data.get("results") or data.get("itens") or [])
            # Pegar info de paginação se disponível
            pag_info = data.get("paginacao", {})
            total_paginas = pag_info.get("total_de_paginas") or pag_info.get("total_paginas")
        else:
            invoices = data
            total_paginas = None

        if not invoices:
            break
        all_invoices.extend(invoices)
        if progress_cb:
            progress_cb(len(all_invoices))

        # Critério de parada
        if total_paginas and pagina >= total_paginas:
            break
        if len(invoices) < 100:
            break
        pagina += 1
        if pagina > 200:  # safety limit (20.000 faturas)
            break

    return all_invoices


def flatten_hubsoft_invoices(invoices: list) -> pd.DataFrame:
    """Converte lista de dicts da API em DataFrame no mesmo formato do XLSX."""
    rows = []
    for inv in invoices:
        # API pode estruturar de jeito ligeiramente diferente — tentamos várias chaves
        cli = inv.get("cliente", {}) if isinstance(inv.get("cliente"), dict) else {}
        endereco = cli.get("endereco_principal", {}) if isinstance(cli.get("endereco_principal"), dict) else {}

        rows.append({
            "codigo_cliente": inv.get("codigo_cliente") or cli.get("codigo_cliente"),
            "nome_razaosocial": (inv.get("nome_razaosocial") or cli.get("nome_razaosocial")
                                  or cli.get("nome") or inv.get("nome")),
            "numero_plano": inv.get("numero_plano") or inv.get("plano"),
            "servico": inv.get("servico") or inv.get("descricao_servico"),
            "servico_status": inv.get("servico_status") or inv.get("status_servico"),
            "nosso_numero": inv.get("nosso_numero") or inv.get("numero_documento"),
            "valor": float(str(inv.get("valor", 0)).replace(",", ".") or 0),
            "valor_pago": float(str(inv.get("valor_pago", 0)).replace(",", ".") or 0),
            "valor_descontos": inv.get("valor_descontos"),
            "data_vencimento": inv.get("data_vencimento") or inv.get("vencimento"),
            "data_pagamento": inv.get("data_pagamento") or inv.get("pagamento"),
            "forma_cobranca": inv.get("forma_cobranca") or inv.get("forma_pagamento"),
            "cpf_cnpj": (inv.get("cpf_cnpj") or cli.get("cpf_cnpj") or "").replace(".", "").replace("-", "").replace("/", ""),
            "status_pagamento": inv.get("status_pagamento") or inv.get("status"),
            "telefone_primario": cli.get("telefone_celular") or cli.get("telefone_primario") or inv.get("telefone"),
        })
    df = pd.DataFrame(rows)
    # Datas
    for col in ['data_vencimento', 'data_pagamento']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')
    # Valores
    for col in ['valor', 'valor_pago']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    return df


def filter_intercompany_and_judicial(df_ext: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Filtra transações que não são receita de cliente (intercompany, judicial, devoluções)."""
    if len(df_ext) == 0:
        return df_ext, {}

    stats = {}
    memo_lower = df_ext['memo'].fillna('').str.lower()

    mask_inter = memo_lower.str.contains(r'rdmi|rrd', na=False, regex=True)
    mask_jud = memo_lower.str.contains(r'desbloq|dblq|reversão.*bloqueio|reversao.*bloqueio|bloqueia.*judicial', na=False, regex=True)
    mask_devol = memo_lower.str.contains(r'devolu[çc][ãa]o', na=False, regex=True)
    mask_prot = df_ext['memo'].fillna('').str.match(r'^PROTOCOLO', na=False)

    stats['intercompany'] = {'qtd': mask_inter.sum(), 'valor': df_ext[mask_inter]['Valor'].sum()}
    stats['judicial'] = {'qtd': mask_jud.sum(), 'valor': df_ext[mask_jud]['Valor'].sum()}
    stats['devolucao'] = {'qtd': mask_devol.sum(), 'valor': df_ext[mask_devol]['Valor'].sum()}
    stats['protocolo'] = {'qtd': mask_prot.sum(), 'valor': df_ext[mask_prot]['Valor'].sum()}

    df_clean = df_ext[~(mask_inter | mask_jud | mask_devol | mask_prot)].copy()
    return df_clean, stats


# ═══════════════════════════════════════════════════════════════════════════════
# CLASSIFICAÇÃO DE CLIENTES
# ═══════════════════════════════════════════════════════════════════════════════

GOV_KEYWORDS = [
    'secretaria', 'ministerio', 'prefeitura', 'governo do estado', 'estado de goias',
    'tribunal', 'ministerio publico', 'mp recursos', 'tesouro ', 'fundo municipal',
    'fundo estadual', 'fundo nacional', 'fms ', 'fma ', 'fmas ', 'fundeb', 'fnde',
    'sus ', 'policia', 'polícia', 'anatel', 'anvisa', 'anac', 'incra', 'inss',
    'ibge', 'ibama', 'abin', 'agencia brasileira', 'fundesp', 'instituto federal',
    'instituto nacional', 'autarquia', 'casa civil', 'controladoria', 'procuradoria',
    'camara municipal', 'senado', 'assembleia legislativa', 'sgg', 'secretaria geral',
    'conselho federal', 'conselho regional', 'agencia nacional', 'fundacao publica',
    'departamento de', 'cda - on line', 'divida ativa', 'receita federal', 'sefaz',
    'detran', 'dnit', 'goinfra', 'agehab', 'agetop', 'tribunal de justica', 'ceasa',
    'centrais de abastecimento', 'município de', 'municipio de', 'crea-go', 'cfa',
    'cft', 'crt', 'centrais elet', 'companhia energe', 'agencia reguladora',
]
PJ_KEYWORDS = [
    ' ltda', ' s/a', ' s.a.', ' sa ', ' s a ', ' eireli', ' me ', ' epp', ' mei',
    '& cia', 'soluc', 'soluç', 'tecnologia', 'telecom', 'tecnologias', 'comercio',
    'comércio', 'industria', 'indústria', 'servicos', 'serviços', 'consultoria',
    'construcoes', 'construções', 'associacao', 'associação', 'cooperativa',
    'sociedade', 'empresa ', 'telecomunicacoes', 'telecomunicações', 'spe ',
    'concessionaria', ' & ', 'incorporadora', 'engenharia', 'comercial ',
    'distribuidora', 'logistica', 'corretora', 'imobiliaria', 'transportes',
    'farmacia', 'farmácia', 'restaurante', 'lanchonete', 'hotel ', 'pousada',
    'clinica', 'clínica', 'laboratorio', 'laboratório', 'escola ', 'colegio',
    'colégio', 'centro educacional', 'igreja', 'paroquia', 'fundacao ', 'fundação ',
    'instituto ', 'idtech', 'sindicato', 'condominio', 'condomínio', ' ltd',
    'eletro', 'eletrica', 'elétrica', 'senac', 'senai', 'senat', 'sebrae', 'sesc',
    'sesi', 'sest', 'senar', 'rede nacional', ' rnp', 'cianet', 'cartorio',
    'livraria', 'movimento ', 'conectar', 'perboni', 'banco do brasil',
]


def classify_client(nome: str) -> str:
    n = (nome or '').lower().strip()
    if any(k in n for k in GOV_KEYWORDS):
        return 'Governo'
    if re.search(r'\bs\.?\s?a\.?\s*$', n):
        return 'Empresa'
    if any(k in n for k in PJ_KEYWORDS):
        return 'Empresa'
    if len(n.split()) == 1 and len(n) >= 4:
        return 'Empresa'
    if re.search(r'\d{3,}', n):
        return 'Empresa'
    palavras = re.sub(r'\s*-\s*qrcode\s*-?\s*', '', n).strip().split()
    if 2 <= len(palavras) <= 6 and not re.search(r'\d', n):
        return 'Pessoa Física'
    return 'Empresa'


# ═══════════════════════════════════════════════════════════════════════════════
# MATCHING / CONCILIAÇÃO
# ═══════════════════════════════════════════════════════════════════════════════

def clean_name(s: str) -> str:
    if pd.isna(s) or not s:
        return ''
    s = str(s).lower()
    s = re.sub(r'\b(ltda|s/?a|s\.a\.|me|epp|eireli|mei)\b', '', s)
    s = re.sub(r'[^\w\s]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def run_match(fat: pd.DataFrame, ext: pd.DataFrame, date_start: str, date_end: str) -> tuple:
    """Roda conciliação em 3 passes. Retorna (fat_match, ext_used)."""
    fat_match = fat[
        (fat['status_pagamento'].isin(['Paga', 'Pago - Desconto'])) &
        (fat['data_pagamento'] >= date_start) &
        (fat['data_pagamento'] <= date_end)
    ].copy()
    fat_match['matched_ext_id'] = None
    fat_match['ext_data'] = pd.NaT
    fat_match['ext_desc'] = None
    fat_match['ext_banco'] = None
    fat_match['nome_clean'] = fat_match['nome_razaosocial'].apply(clean_name)

    ext = ext.copy()
    ext['used'] = False
    ext['id_ext'] = ext.index
    ext['desc_clean'] = ext['memo'].apply(clean_name)

    # Pass 1: exato
    for idx, fat_row in fat_match.iterrows():
        valor, data = fat_row['valor_pago'], fat_row['data_pagamento']
        cand = ext[(~ext['used']) & (ext['Valor'].round(2) == round(valor, 2)) &
                   ((ext['Data'] - data).abs() <= pd.Timedelta(days=3))]
        if len(cand) > 0:
            cand = cand.copy(); cand['diff'] = (cand['Data'] - data).abs()
            best = cand.sort_values('diff').iloc[0]
            fat_match.at[idx, 'matched_ext_id'] = int(best['id_ext'])
            fat_match.at[idx, 'ext_data'] = best['Data']
            fat_match.at[idx, 'ext_desc'] = best['memo']
            fat_match.at[idx, 'ext_banco'] = best['banco']
            ext.at[int(best['id_ext']), 'used'] = True

    # Pass 2: relaxado
    for idx, fat_row in fat_match[fat_match['matched_ext_id'].isna()].iterrows():
        valor, data, nome = fat_row['valor_pago'], fat_row['data_pagamento'], fat_row['nome_clean']
        tol = max(5.0, valor * 0.02)
        cand = ext[(~ext['used']) & ((ext['Valor'] - valor).abs() <= tol) &
                   ((ext['Data'] - data).abs() <= pd.Timedelta(days=7))].copy()
        if len(cand) == 0:
            continue
        cand['score_nome'] = cand['desc_clean'].apply(
            lambda x: any(w in x for w in nome.split() if len(w) > 3) if nome else False)
        cand['diff_valor'] = (cand['Valor'] - valor).abs()
        cand['diff_dias'] = (cand['Data'] - data).abs()
        cand = cand.sort_values(['score_nome', 'diff_valor', 'diff_dias'], ascending=[False, True, True])
        best = cand.iloc[0]
        if best['score_nome'] or (best['diff_valor'] <= 2.0 and best['diff_dias'] <= pd.Timedelta(days=3)):
            fat_match.at[idx, 'matched_ext_id'] = int(best['id_ext'])
            fat_match.at[idx, 'ext_data'] = best['Data']
            fat_match.at[idx, 'ext_desc'] = best['memo']
            fat_match.at[idx, 'ext_banco'] = best['banco']
            ext.at[int(best['id_ext']), 'used'] = True

    # Pass 3: agrupado N:1
    for ext_idx, ext_row in ext[~ext['used']].iterrows():
        valor_ext, data_ext, banco = ext_row['Valor'], ext_row['Data'], ext_row['banco']
        if banco == 'Caixa Econômica':
            cand_fat = fat_match[(fat_match['matched_ext_id'].isna()) &
                                  (fat_match['forma_cobranca'] == 'Cobrança Local - RD') &
                                  ((fat_match['data_pagamento'] - data_ext).abs() <= pd.Timedelta(days=10))]
        else:
            nome_ext = re.sub(r'\b(pix recebido de|ted recebida de|doc recebido de|boleto pago por)\b', '',
                             (ext_row['memo'] or '').lower())
            nome_ext = re.sub(r'[^\w\s]', ' ', nome_ext).strip()
            tokens = [w for w in nome_ext.split() if len(w) >= 4]
            if not tokens:
                continue
            cand_fat = fat_match[(fat_match['matched_ext_id'].isna()) &
                                  (fat_match['nome_razaosocial'].str.lower().str.contains(tokens[0], regex=False, na=False)) &
                                  ((fat_match['data_pagamento'] - data_ext).abs() <= pd.Timedelta(days=10))]
        if len(cand_fat) == 0:
            continue
        if len(cand_fat) > 10:
            cand_fat = cand_fat.nlargest(10, 'valor_pago')
        fat_list = list(cand_fat.iterrows())
        best_combo = None
        for size in range(1, min(len(fat_list) + 1, 6)):
            for combo in combinations(fat_list, size):
                soma = sum(r['valor_pago'] for _, r in combo)
                if abs(soma - valor_ext) <= max(10.0, valor_ext * 0.03):
                    best_combo = combo
                    break
            if best_combo:
                break
        if best_combo:
            for idx, _ in best_combo:
                fat_match.at[idx, 'matched_ext_id'] = int(ext_idx)
                fat_match.at[idx, 'ext_data'] = data_ext
                fat_match.at[idx, 'ext_desc'] = f'{ext_row["memo"]} (agrup {len(best_combo)}x)'
                fat_match.at[idx, 'ext_banco'] = banco
            ext.at[ext_idx, 'used'] = True

    return fat_match, ext


# ═══════════════════════════════════════════════════════════════════════════════
# PÁGINAS DO APP
# ═══════════════════════════════════════════════════════════════════════════════

def page_hubsoft_api():
    st.title("🔌 Importar do HubSoft")
    st.markdown("Sincroniza diretamente com a API do HubSoft — sem precisar exportar XLSX.")

    # Verificar se há credenciais em secrets
    has_secrets = False
    secret_url = secret_cid = secret_csec = secret_user = secret_pwd = None
    try:
        secret_url = st.secrets["hubsoft"]["url"]
        secret_cid = st.secrets["hubsoft"]["client_id"]
        secret_csec = st.secrets["hubsoft"]["client_secret"]
        secret_user = st.secrets["hubsoft"]["username"]
        secret_pwd = st.secrets["hubsoft"]["password"]
        has_secrets = True
    except Exception:
        has_secrets = False

    if has_secrets:
        st.success("✅ Credenciais HubSoft configuradas no servidor (Secrets).")
        st.caption(f"URL: `{secret_url}` · Usuário: `{secret_user}`")
        usar_secrets = st.checkbox("Usar credenciais salvas", value=True)
    else:
        st.warning("⚠️ Credenciais HubSoft não estão no Secrets do app. "
                   "Você pode preencher abaixo (só pra esta sessão) ou configurar permanentemente.")
        usar_secrets = False

    if not usar_secrets:
        with st.form("hubsoft_creds"):
            st.markdown("**Credenciais HubSoft:**")
            url = st.text_input("URL da API", value=secret_url or "https://api.SEU-PROVEDOR.hubsoft.com.br",
                                help="Ex: https://api.jettelecom.hubsoft.com.br")
            c1, c2 = st.columns(2)
            client_id = c1.text_input("client_id", value=secret_cid or "")
            client_secret = c2.text_input("client_secret", type="password", value=secret_csec or "")
            c3, c4 = st.columns(2)
            username = c3.text_input("usuário (e-mail)", value=secret_user or "")
            password = c4.text_input("senha", type="password", value=secret_pwd or "")
            submit = st.form_submit_button("🔄 Sincronizar Faturas", type="primary", use_container_width=True)
    else:
        url, client_id, client_secret, username, password = secret_url, secret_cid, secret_csec, secret_user, secret_pwd
        submit = st.button("🔄 Sincronizar Faturas Agora", type="primary", use_container_width=True)

    # Filtro de período (opcional)
    with st.expander("📅 Filtro por período (opcional)"):
        st.caption("Se vazio, baixa todas as faturas. Recomendado limitar pra os últimos 6-12 meses.")
        c1, c2 = st.columns(2)
        data_inicio = c1.date_input("De", value=None, key="hs_de")
        data_fim = c2.date_input("Até", value=None, key="hs_ate")
        data_inicio_str = data_inicio.strftime("%Y-%m-%d") if data_inicio else None
        data_fim_str = data_fim.strftime("%Y-%m-%d") if data_fim else None

    if submit:
        if not (url and client_id and client_secret and username and password):
            st.error("Preencha todos os campos.")
            return

        progress = st.empty()
        status = st.empty()
        try:
            status.info("🔐 Autenticando no HubSoft...")
            token = hubsoft_authenticate(url, client_id, client_secret, username, password)
            status.success("✅ Autenticado!")

            status.info("📥 Baixando faturas (pode levar alguns minutos)...")
            def cb(count):
                progress.text(f"  → {count} faturas baixadas...")
            invoices_raw = hubsoft_get_invoices(url, token, cb,
                                                 data_inicio=data_inicio_str,
                                                 data_fim=data_fim_str)
            status.success(f"✅ {len(invoices_raw)} faturas baixadas da API.")

            status.info("🔄 Convertendo dados...")
            df = flatten_hubsoft_invoices(invoices_raw)
            st.session_state['fat'] = df
            st.session_state['hubsoft_sync_time'] = datetime.now()

            status.success(f"✅ Pronto! {len(df)} faturas importadas · R$ {df['valor'].sum():,.2f} faturado.")
            st.balloons()

            # Mostra preview
            st.subheader("Preview dos dados importados")
            st.dataframe(df.head(10), use_container_width=True)
            st.info("👉 Vá para **Resumo**, **Inadimplência**, **Clientes** etc. para ver os dashboards. "
                    "Para conciliar com banco, ainda precisa subir os extratos pela página **Upload**.")

        except PermissionError as e:
            st.error(f"🔒 Erro de autenticação: {e}")
            st.markdown("**Verifique:**\n"
                        "- O client_id e client_secret estão corretos?\n"
                        "- A senha do usuário API foi renovada recentemente?\n"
                        "- O usuário tem permissão de acesso à API?")
        except ValueError as e:
            st.error(f"⚠️ {e}")
        except Exception as e:
            st.error(f"❌ Erro: {type(e).__name__}: {e}")
            st.markdown("**Possíveis causas:**\n"
                        "- URL da API errada (confira `https://api.SEU-PROVEDOR.hubsoft.com.br`)\n"
                        "- Sem internet no servidor (raro)\n"
                        "- API do HubSoft fora do ar momentaneamente")

    # Status da última sincronização
    if 'hubsoft_sync_time' in st.session_state:
        st.divider()
        st.caption(f"Última sincronização: {st.session_state['hubsoft_sync_time']:%d/%m/%Y %H:%M:%S}")

    # Instruções
    with st.expander("ℹ️ Como configurar credenciais permanentemente"):
        st.markdown("""
Para evitar digitar as credenciais toda vez, configure no **Secrets** do Streamlit Cloud:

1. No painel do app, **Manage app** → **⚙️ Settings** → **Secrets**
2. Adicione no final do arquivo:

```toml
[hubsoft]
url = "https://api.SEU-PROVEDOR.hubsoft.com.br"
client_id = "SEU_CLIENT_ID"
client_secret = "SEU_CLIENT_SECRET"
username = "api@SEU-PROVEDOR.com.br"
password = "SUA_SENHA"
```

3. Save → Reboot app

Depois, basta clicar em **"Sincronizar Faturas Agora"** sem precisar digitar nada.

> **Segurança:** o conteúdo do Secrets nunca aparece no GitHub público — fica só no servidor do Streamlit Cloud.
        """)


def page_upload():
    st.title("📥 Upload de Dados")
    st.markdown("Arraste os arquivos abaixo. O sistema identifica o tipo automaticamente.")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Relatório de Faturas HubSoft")
        hubsoft_file = st.file_uploader(
            "XLSX exportado do HubSoft", type=['xlsx', 'xls'],
            key="hubsoft", help="Vá em HubSoft → Relatórios → Faturas → Exportar XLSX"
        )

    with col2:
        st.subheader("Extratos Bancários")
        ext_files = st.file_uploader(
            "OFX (Sicredi/Caixa/C6) ou CSV (BTG) — múltiplos arquivos",
            type=['ofx', 'csv'], accept_multiple_files=True, key="ext",
        )

    if st.button("🔄 Processar Tudo", type="primary", use_container_width=True):
        if not hubsoft_file:
            st.error("Você precisa fazer upload do relatório HubSoft.")
            return
        if not ext_files:
            st.error("Você precisa fazer upload de pelo menos 1 extrato bancário.")
            return

        with st.spinner("Processando arquivos..."):
            # HubSoft
            fat = parse_hubsoft_xlsx(hubsoft_file)
            st.session_state['fat'] = fat
            st.success(f"✓ HubSoft: {len(fat)} faturas · R$ {fat['valor'].sum():,.2f} faturado")

            # Extratos
            all_ext = []
            for ext_file in ext_files:
                fname = ext_file.name.lower()
                ext_file.seek(0)
                if fname.endswith('.csv'):
                    df_e = parse_btg_csv(ext_file)
                else:
                    df_e = parse_ofx(ext_file)
                if len(df_e) > 0:
                    all_ext.append(df_e)
                    st.info(f"✓ {ext_file.name}: {len(df_e)} créditos de {df_e['banco'].iloc[0]}")

            if not all_ext:
                st.error("Nenhuma transação encontrada nos extratos.")
                return

            ext_raw = pd.concat(all_ext, ignore_index=True)
            ext_clean, filter_stats = filter_intercompany_and_judicial(ext_raw)
            st.session_state['ext'] = ext_clean
            st.session_state['ext_raw'] = ext_raw
            st.session_state['filter_stats'] = filter_stats

            # Roda conciliação
            min_date = ext_clean['Data'].min().strftime('%Y-%m-%d')
            max_date = ext_clean['Data'].max().strftime('%Y-%m-%d')
            fat_match, ext_after = run_match(fat, ext_clean, min_date, max_date)
            st.session_state['fat_match'] = fat_match
            st.session_state['ext_after'] = ext_after

            st.success("✓ Processamento completo! Navegue pelas páginas no menu lateral.")

    # Mostrar estado atual
    if 'fat' in st.session_state:
        st.divider()
        st.subheader("📊 Dados Atualmente Carregados")
        c1, c2, c3 = st.columns(3)
        c1.metric("Faturas", f"{len(st.session_state['fat']):,}")
        c2.metric("Faturado", f"R$ {st.session_state['fat']['valor'].sum():,.0f}")
        if 'ext' in st.session_state:
            c3.metric("Transações Banco", f"{len(st.session_state['ext']):,}")


def page_resumo():
    st.title("📊 Resumo Executivo")

    if 'fat' not in st.session_state:
        st.warning("Você precisa fazer upload dos dados primeiro (página Upload).")
        return

    fat = st.session_state['fat']
    ext = st.session_state.get('ext', pd.DataFrame())
    fat_match = st.session_state.get('fat_match', pd.DataFrame())
    HOJE = pd.Timestamp(datetime.now().date())

    # KPIs
    em_aberto = fat[fat['status_pagamento'] == 'Em Aberto']
    vencidas = em_aberto[em_aberto['data_vencimento'] < HOJE]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Faturado", f"R$ {fat['valor'].sum():,.0f}", f"{len(fat)} faturas")
    col2.metric("Pago (HubSoft)", f"R$ {fat['valor_pago'].sum():,.0f}", f"{fat['valor_pago'].sum()/fat['valor'].sum()*100:.1f}% cobrado")
    col3.metric("Vencido", f"R$ {vencidas['valor'].sum():,.0f}", f"{len(vencidas)} faturas", delta_color="inverse")
    if len(ext) > 0:
        col4.metric("Recebido nos Bancos", f"R$ {ext['Valor'].sum():,.0f}", f"{len(ext)} transações")

    # Conciliação
    if len(fat_match) > 0:
        st.divider()
        st.subheader("Conciliação Bancária")
        matched = fat_match[fat_match['matched_ext_id'].notna()]
        pct = len(matched) / len(fat_match) * 100
        c1, c2, c3 = st.columns(3)
        c1.metric("Taxa de Conciliação", f"{pct:.1f}%", f"{len(matched)}/{len(fat_match)}")
        c2.metric("Valor Conciliado", f"R$ {matched['valor_pago'].sum():,.0f}")
        c3.metric("Pendente Investigação", f"R$ {fat_match[fat_match['matched_ext_id'].isna()]['valor_pago'].sum():,.0f}")

    # Gráfico mensal
    st.divider()
    st.subheader("Fluxo Mensal")
    mes_fat = fat.groupby(fat['data_vencimento'].dt.to_period('M').astype(str))['valor'].sum()
    mes_pag = fat[fat['data_pagamento'].notna()].groupby(
        fat['data_pagamento'].dt.to_period('M').astype(str))['valor_pago'].sum()

    df_plot = pd.DataFrame({'Faturado': mes_fat, 'Pago HubSoft': mes_pag}).fillna(0).reset_index()
    df_plot.columns = ['Mês', 'Faturado', 'Pago HubSoft']

    if len(ext) > 0:
        mes_ext = ext.groupby(ext['Data'].dt.to_period('M').astype(str))['Valor'].sum()
        df_plot['Recebido Banco'] = df_plot['Mês'].map(mes_ext).fillna(0)

    fig = go.Figure()
    fig.add_trace(go.Bar(name='Faturado', x=df_plot['Mês'], y=df_plot['Faturado'], marker_color=GRAY))
    fig.add_trace(go.Bar(name='Pago HubSoft', x=df_plot['Mês'], y=df_plot['Pago HubSoft'], marker_color=BRAND_LIGHT))
    if 'Recebido Banco' in df_plot.columns:
        fig.add_trace(go.Bar(name='Recebido Banco', x=df_plot['Mês'], y=df_plot['Recebido Banco'], marker_color=BRAND_ORANGE))
    fig.update_layout(
        barmode='group', height=400, hovermode='x unified',
        yaxis_tickformat='R$ ,.0f', yaxis_title='R$',
    )
    st.plotly_chart(fig, use_container_width=True)


def page_conciliacao():
    st.title("🔍 Conciliação Bancária")
    if 'fat_match' not in st.session_state:
        st.warning("Faça upload dos dados primeiro.")
        return

    fat_match = st.session_state['fat_match']
    ext = st.session_state.get('ext_after', pd.DataFrame())

    matched = fat_match[fat_match['matched_ext_id'].notna()]
    unmatched = fat_match[fat_match['matched_ext_id'].isna()]
    ext_unused = ext[~ext['used']] if 'used' in ext.columns else pd.DataFrame()

    c1, c2, c3 = st.columns(3)
    c1.metric("Conciliadas", f"{len(matched)}", f"R$ {matched['valor_pago'].sum():,.0f}")
    c2.metric("Sem Match Banco", f"{len(unmatched)}", f"R$ {unmatched['valor_pago'].sum():,.0f}", delta_color="inverse")
    c3.metric("Banco s/ Fatura", f"{len(ext_unused)}", f"R$ {ext_unused['Valor'].sum() if len(ext_unused)>0 else 0:,.0f}", delta_color="inverse")

    tab1, tab2, tab3 = st.tabs(["✅ Conciliadas", "🔴 Faturas s/ Match", "❓ Banco s/ Fatura"])

    with tab1:
        st.dataframe(
            matched[['codigo_cliente', 'nome_razaosocial', 'nosso_numero', 'valor_pago',
                     'data_pagamento', 'ext_banco', 'ext_data', 'ext_desc']]
            .rename(columns={'codigo_cliente': 'Cód', 'nome_razaosocial': 'Cliente',
                             'nosso_numero': 'Nosso Nº', 'valor_pago': 'Pago',
                             'data_pagamento': 'Data Pgto', 'ext_banco': 'Banco',
                             'ext_data': 'Data Banco', 'ext_desc': 'Descrição'})
            .sort_values('Pago', ascending=False),
            use_container_width=True, height=500
        )

    with tab2:
        st.markdown(f"**{len(unmatched)} faturas marcadas como pagas no HubSoft mas sem comprovante bancário.**")
        st.dataframe(
            unmatched[['codigo_cliente', 'nome_razaosocial', 'nosso_numero', 'valor_pago',
                       'data_pagamento', 'forma_cobranca']]
            .rename(columns={'codigo_cliente': 'Cód', 'nome_razaosocial': 'Cliente',
                             'nosso_numero': 'Nosso Nº', 'valor_pago': 'Pago',
                             'data_pagamento': 'Data Pgto', 'forma_cobranca': 'Forma'})
            .sort_values('Pago', ascending=False),
            use_container_width=True, height=500
        )

    with tab3:
        if len(ext_unused) > 0:
            st.markdown(f"**{len(ext_unused)} créditos no banco que não acharam fatura correspondente.**")
            st.dataframe(
                ext_unused[['banco', 'Data', 'Valor', 'memo']]
                .rename(columns={'memo': 'Descrição'})
                .sort_values('Valor', ascending=False),
                use_container_width=True, height=500
            )


def page_inadimplencia():
    st.title("🚨 Inadimplência")
    if 'fat' not in st.session_state:
        st.warning("Faça upload dos dados primeiro.")
        return

    fat = st.session_state['fat']
    HOJE = pd.Timestamp(datetime.now().date())

    # Validações defensivas
    if 'status_pagamento' not in fat.columns or 'data_vencimento' not in fat.columns:
        st.error("Os dados carregados não têm as colunas necessárias (status_pagamento, data_vencimento). "
                 "Use a página Upload ou re-sincronize pela HubSoft API.")
        return

    em_aberto = fat[fat['status_pagamento'] == 'Em Aberto'].copy()
    if len(em_aberto) == 0:
        st.success("🎉 Nenhuma fatura em aberto na base atual!")
        st.info("Se isso parece errado, verifique se a base está completa. "
                "Pela API HubSoft, use o filtro de período para baixar histórico maior.")
        return

    vencidas = em_aberto[em_aberto['data_vencimento'] < HOJE].copy()
    vencidas['dias_atraso'] = (HOJE - vencidas['data_vencimento']).dt.days

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Vencido", f"R$ {vencidas['valor'].sum():,.0f}", f"{len(vencidas)} faturas")
    c2.metric("Clientes Inadimplentes", f"{vencidas['codigo_cliente'].nunique() if len(vencidas) > 0 else 0}")
    over_90 = vencidas[vencidas['dias_atraso'] > 90] if len(vencidas) > 0 else pd.DataFrame()
    c3.metric("Acima de 90 dias", f"R$ {over_90['valor'].sum() if len(over_90) > 0 else 0:,.0f}",
              f"{len(over_90)} faturas (jurídico)", delta_color="inverse")

    if len(vencidas) == 0:
        st.success("🎉 Nenhuma fatura vencida! Toda a carteira está em dia.")
        st.info(f"Carteira a vencer: {len(em_aberto)} faturas · R$ {em_aberto['valor'].sum():,.2f}")
        return

    # Aging
    st.subheader("Aging — Distribuição por Faixa de Atraso")
    faixas = [(0, 7, '0-7d'), (8, 15, '8-15d'), (16, 30, '16-30d'),
              (31, 60, '31-60d'), (61, 90, '61-90d'), (91, 9999, '>90d')]
    aging_data = []
    for ini, fim, nome in faixas:
        sub = vencidas[(vencidas['dias_atraso'] >= ini) & (vencidas['dias_atraso'] <= fim)]
        if len(sub) > 0:
            aging_data.append({'Faixa': nome, 'Qtd': len(sub), 'Valor': sub['valor'].sum(),
                               'Clientes': sub['codigo_cliente'].nunique()})
    aging_df = pd.DataFrame(aging_data)

    if len(aging_df) > 0:
        fig = px.bar(aging_df, x='Faixa', y='Valor', text='Valor',
                     color='Faixa',
                     color_discrete_sequence=['#FFEB9C', '#FFD966', '#FFCC99', '#FF9966', '#FF6666', '#CC0000'])
        fig.update_traces(texttemplate='R$ %{text:,.0f}', textposition='outside')
        fig.update_layout(height=400, showlegend=False, yaxis_tickformat='R$ ,.0f')
        st.plotly_chart(fig, use_container_width=True)

    # Top inadimplentes
    st.subheader("Top Inadimplentes")
    cols_disp = [c for c in ['codigo_cliente', 'nome_razaosocial', 'cpf_cnpj', 'telefone_primario']
                 if c in vencidas.columns]
    top = vencidas.groupby(cols_disp).agg(
        Faturas=('valor', 'count'),
        Valor=('valor', 'sum'),
        Atraso_Max=('dias_atraso', 'max'),
    ).reset_index().sort_values('Valor', ascending=False)
    st.dataframe(top, use_container_width=True, height=500)


def page_clientes():
    st.title("👥 Clientes")
    if 'fat' not in st.session_state:
        st.warning("Faça upload dos dados primeiro.")
        return

    fat = st.session_state['fat']
    HOJE = pd.Timestamp(datetime.now().date())

    # Agregar
    cli = fat.groupby(['codigo_cliente', 'nome_razaosocial', 'cpf_cnpj']).agg(
        Faturas=('valor', 'count'),
        Faturado=('valor', 'sum'),
        Pago=('valor_pago', 'sum'),
    ).reset_index()
    cli['Em_Aberto'] = cli['Faturado'] - cli['Pago']
    cli['% Pago'] = cli['Pago'] / cli['Faturado'] * 100
    cli['Categoria'] = cli['nome_razaosocial'].apply(classify_client)
    cli = cli.sort_values('Faturado', ascending=False).reset_index(drop=True)

    # Filtros
    c1, c2, c3 = st.columns([2, 2, 1])
    search = c1.text_input("🔍 Buscar cliente", placeholder="Nome, CNPJ ou código...")
    cat_filter = c2.multiselect("Categoria", ['Empresa', 'Governo', 'Pessoa Física'])
    only_inad = c3.checkbox("Só inadimplentes")

    df = cli.copy()
    if search:
        s = search.lower()
        df = df[df.apply(lambda r: s in str(r['nome_razaosocial']).lower()
                         or s in str(r['cpf_cnpj']).lower()
                         or s in str(r['codigo_cliente']).lower(), axis=1)]
    if cat_filter:
        df = df[df['Categoria'].isin(cat_filter)]
    if only_inad:
        df = df[df['Em_Aberto'] > 0]

    st.markdown(f"**{len(df)} clientes · R$ {df['Faturado'].sum():,.2f} faturado**")

    # Cards summary
    c1, c2, c3 = st.columns(3)
    for col, cat, color in [(c1, 'Empresa', '#9FC5E8'), (c2, 'Governo', '#FFD966'), (c3, 'Pessoa Física', '#B6D7A8')]:
        sub = df[df['Categoria'] == cat]
        col.markdown(f"<div style='padding:1rem;background:{color}22;border-left:4px solid {color};border-radius:4px'>"
                     f"<div style='font-size:11px;color:#666'>{cat.upper()}</div>"
                     f"<div style='font-size:22px;font-weight:600'>{len(sub)} clientes</div>"
                     f"<div style='font-size:13px;color:#444'>R$ {sub['Faturado'].sum():,.0f}</div>"
                     f"</div>", unsafe_allow_html=True)

    st.dataframe(
        df[['codigo_cliente', 'nome_razaosocial', 'cpf_cnpj', 'Categoria',
            'Faturas', 'Faturado', 'Pago', '% Pago', 'Em_Aberto']]
        .rename(columns={'codigo_cliente': 'Cód', 'nome_razaosocial': 'Cliente',
                         'cpf_cnpj': 'CPF/CNPJ', 'Em_Aberto': 'Em Aberto'}),
        use_container_width=True, height=600
    )


def page_top_clientes():
    st.title("🏆 Top Clientes")
    if 'fat' not in st.session_state:
        st.warning("Faça upload dos dados primeiro.")
        return

    fat = st.session_state['fat']
    top_n = st.slider("Quantos mostrar?", 5, 30, 15)

    top = fat.groupby('nome_razaosocial').agg(
        Pago=('valor_pago', 'sum'),
        Faturas=('valor', 'count'),
    ).sort_values('Pago', ascending=False).head(top_n).reset_index()

    fig = px.bar(top, y='nome_razaosocial', x='Pago', orientation='h',
                 text='Pago', color_discrete_sequence=[BRAND_ORANGE])
    fig.update_traces(texttemplate='R$ %{text:,.0f}', textposition='outside')
    fig.update_layout(height=max(500, top_n * 30), showlegend=False,
                      xaxis_tickformat='R$ ,.0f', yaxis_title=None,
                      yaxis={'categoryorder': 'total ascending'})
    st.plotly_chart(fig, use_container_width=True)

    total_top = top['Pago'].sum()
    total_geral = fat['valor_pago'].sum()
    st.info(f"**Top {top_n}** = R$ {total_top:,.2f} · {total_top/total_geral*100:.1f}% da receita total")


def page_exportar():
    st.title("💾 Exportar Relatórios")
    if 'fat' not in st.session_state:
        st.warning("Faça upload dos dados primeiro.")
        return

    fat = st.session_state['fat']
    fat_match = st.session_state.get('fat_match', pd.DataFrame())

    st.markdown("Baixe os relatórios em XLSX.")

    if st.button("📊 Gerar Planilha Consolidada", type="primary"):
        with st.spinner("Gerando..."):
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine='openpyxl') as writer:
                # Resumo
                resumo = pd.DataFrame({
                    'Indicador': ['Total faturas', 'Total faturado', 'Total pago HubSoft', 'Em aberto'],
                    'Valor': [len(fat), fat['valor'].sum(), fat['valor_pago'].sum(),
                              fat['valor'].sum() - fat['valor_pago'].sum()]
                })
                resumo.to_excel(writer, sheet_name='Resumo', index=False)
                fat.to_excel(writer, sheet_name='Faturas HubSoft', index=False)
                if len(fat_match) > 0:
                    matched = fat_match[fat_match['matched_ext_id'].notna()]
                    unmatched = fat_match[fat_match['matched_ext_id'].isna()]
                    matched.to_excel(writer, sheet_name='Conciliadas', index=False)
                    unmatched.to_excel(writer, sheet_name='Sem Match', index=False)

            st.download_button(
                label="⬇️ Baixar XLSX",
                data=buf.getvalue(),
                file_name=f"jet-bi-relatorio-{datetime.now():%Y%m%d}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    authenticator, auth_status, name = login()

    if not auth_status:
        return

    # Sidebar
    with st.sidebar:
        st.markdown(f"<h2 style='color: {BRAND_ORANGE}'>JET BI</h2>", unsafe_allow_html=True)
        st.markdown(f"<small>Logado: <b>{name}</b></small>", unsafe_allow_html=True)
        st.divider()

        pagina = st.radio(
            "Menu",
            ["📥 Upload", "🔌 HubSoft API", "📊 Resumo", "🔍 Conciliação",
             "🚨 Inadimplência", "👥 Clientes", "🏆 Top Clientes", "💾 Exportar"],
            label_visibility="collapsed",
        )

        st.divider()
        try:
            authenticator.logout(location="sidebar")
        except TypeError:
            authenticator.logout("Logout", "sidebar")

    # Router
    if pagina == "📥 Upload": page_upload()
    elif pagina == "🔌 HubSoft API": page_hubsoft_api()
    elif pagina == "📊 Resumo": page_resumo()
    elif pagina == "🔍 Conciliação": page_conciliacao()
    elif pagina == "🚨 Inadimplência": page_inadimplencia()
    elif pagina == "👥 Clientes": page_clientes()
    elif pagina == "🏆 Top Clientes": page_top_clientes()
    elif pagina == "💾 Exportar": page_exportar()


if __name__ == "__main__":
    main()
