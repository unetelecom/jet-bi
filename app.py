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


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS DE FORMATAÇÃO BRASILEIRA (R$ 1.234.567,89)
# ═══════════════════════════════════════════════════════════════════════════════

def fmt_brl(valor, decimais=2) -> str:
    """Formata número como moeda Real BR: R$ 1.234.567,89"""
    if valor is None or pd.isna(valor):
        return "—"
    try:
        v = float(valor)
        s = f"{v:,.{decimais}f}"
        # US (1,234,567.89) → BR (1.234.567,89)
        s = s.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {s}"
    except (ValueError, TypeError):
        return "—"


def fmt_num(valor) -> str:
    """Formata inteiro com separador BR: 1.234.567"""
    if valor is None or pd.isna(valor):
        return "—"
    try:
        return f"{int(valor):,}".replace(",", ".")
    except (ValueError, TypeError):
        return "—"

def format_df_brl(df, money_cols=None, num_cols=None, pct_cols=None):
    """Retorna cópia do DataFrame com colunas monetárias/numéricas formatadas em pt-BR.

    money_cols: lista de colunas de moeda (R$ 1.234,56)
    num_cols: lista de colunas inteiras (1.234)
    pct_cols: lista de colunas percentuais (12,3%)
    """
    if len(df) == 0:
        return df
    df = df.copy()
    for col in (money_cols or []):
        if col in df.columns:
            df[col] = df[col].apply(lambda v: fmt_brl(v, 2) if pd.notna(v) else "—")
    for col in (num_cols or []):
        if col in df.columns:
            df[col] = df[col].apply(lambda v: fmt_num(v) if pd.notna(v) else "—")
    for col in (pct_cols or []):
        if col in df.columns:
            df[col] = df[col].apply(lambda v: f"{v:.1f}%".replace(".", ",") if pd.notna(v) else "—")
    return df




# Logo Grupo JET (embutido em base64)
LOGO_B64 = "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"
LOGO_HTML = f'<img src="data:image/png;base64,{LOGO_B64}" />'


# CSS corporativo (compatível com dark/light mode)
st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"]  {{
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }}

    /* Esconder Streamlit defaults */
    footer {{visibility: hidden;}}
    #MainMenu {{visibility: hidden;}}
    header[data-testid="stHeader"] {{background: transparent;}}

    /* Container principal */
    .main .block-container {{
        padding-top: 2rem;
        padding-bottom: 3rem;
        max-width: 1400px;
    }}

    /* Headings — usa cor padrão do tema, não força preto/branco */
    h1 {{
        font-weight: 700;
        font-size: 1.875rem;
        letter-spacing: -0.025em;
        margin-bottom: 0.25rem !important;
        padding-bottom: 0 !important;
    }}
    h2 {{
        font-weight: 600;
        font-size: 1.25rem;
        letter-spacing: -0.015em;
        border-bottom: 2px solid rgba(128,128,128,0.15);
        padding-bottom: 0.5rem;
        margin-top: 2rem;
    }}
    h3 {{
        font-weight: 600;
        font-size: 1rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        opacity: 0.75;
    }}

    /* SIDEBAR — sempre escura, independente do tema */
    [data-testid="stSidebar"] {{
        background: linear-gradient(180deg, #0a0a0a 0%, #1a1a1a 100%);
        border-right: 1px solid #333;
    }}
    [data-testid="stSidebar"] * {{
        color: #f0f0f0 !important;
    }}
    [data-testid="stSidebar"] .sidebar-logo {{
        padding: 1rem 0.5rem 0.75rem 0.5rem;
        border-bottom: 1px solid #333;
        margin-bottom: 1rem;
    }}
    [data-testid="stSidebar"] .sidebar-logo img {{
        width: 100%;
        max-width: 160px;
        height: auto;
        display: block;
        margin: 0 auto 0.5rem auto;
    }}
    [data-testid="stSidebar"] .sidebar-subtitle {{
        font-size: 0.65rem;
        color: #888 !important;
        text-transform: uppercase;
        letter-spacing: 0.15em;
        text-align: center;
        font-weight: 600;
    }}
    [data-testid="stSidebar"] .sidebar-user {{
        padding: 0.75rem 1rem;
        background: rgba(255,90,0,0.1);
        border-left: 3px solid {BRAND_ORANGE};
        border-radius: 4px;
        margin-bottom: 1rem;
        font-size: 0.85rem;
    }}
    [data-testid="stSidebar"] .stRadio > label {{
        color: #f0f0f0 !important;
        font-weight: 500;
    }}

    /* Botões — laranja Grupo JET */
    .stButton > button {{
        background-color: {BRAND_ORANGE};
        color: white !important;
        border: none;
        border-radius: 6px;
        font-weight: 600;
        padding: 0.5rem 1.5rem;
        transition: all 0.2s;
    }}
    .stButton > button:hover {{
        background-color: {BRAND_DARK};
        color: white !important;
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(255,90,0,0.25);
    }}

    /* KPI Cards (st.metric) — visual elegante em qualquer tema */
    [data-testid="stMetric"] {{
        background: rgba(128,128,128,0.04);
        border: 1px solid rgba(128,128,128,0.15);
        border-radius: 8px;
        padding: 1rem 1.25rem;
    }}
    [data-testid="stMetricLabel"] {{
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        font-weight: 600;
        opacity: 0.7;
    }}
    [data-testid="stMetricValue"] {{
        font-weight: 700;
        font-size: 1.5rem;
        letter-spacing: -0.025em;
        color: {BRAND_ORANGE};
    }}
    [data-testid="stMetricDelta"] {{
        font-size: 0.8rem;
        font-weight: 500;
    }}

    /* DataFrame */
    [data-testid="stDataFrame"] {{
        border: 1px solid rgba(128,128,128,0.2);
        border-radius: 6px;
    }}

    /* Tabs */
    .stTabs [data-baseweb="tab"] {{
        font-weight: 500;
        padding: 0.5rem 1.25rem;
    }}
    .stTabs [aria-selected="true"] {{
        color: {BRAND_ORANGE} !important;
        border-bottom-color: {BRAND_ORANGE} !important;
    }}

    /* Alerts */
    .stAlert {{
        border-radius: 6px;
        border-left-width: 4px;
    }}

    /* Login screen — bloco isolado central */
    .login-container {{
        max-width: 380px;
        margin: 3rem auto 1rem auto;
        padding: 1.5rem;
        background: rgba(128,128,128,0.04);
        border-radius: 12px;
        border: 1px solid rgba(128,128,128,0.15);
    }}
    .login-logo {{
        background: linear-gradient(135deg, #0a0a0a 0%, #2a2a2a 100%);
        padding: 1.5rem;
        border-radius: 8px;
        margin-bottom: 1rem;
        text-align: center;
    }}
    .login-logo img {{
        max-width: 200px;
        width: 80%;
        height: auto;
    }}
    .login-tagline {{
        text-align: center;
        font-size: 0.7rem;
        letter-spacing: 0.15em;
        opacity: 0.6;
        font-weight: 600;
    }}

    /* Page header */
    .page-header {{
        border-bottom: 1px solid rgba(128,128,128,0.15);
        padding-bottom: 1rem;
        margin-bottom: 1.5rem;
    }}
    .page-eyebrow {{
        font-size: 0.7rem;
        color: {BRAND_ORANGE};
        text-transform: uppercase;
        letter-spacing: 0.12em;
        font-weight: 700;
        margin-bottom: 0.25rem;
    }}
    .page-subtitle {{
        font-size: 0.9rem;
        opacity: 0.7;
        margin-top: 0.25rem;
    }}

    /* Divider */
    hr {{
        border-color: rgba(128,128,128,0.15);
        margin: 1.5rem 0;
    }}
</style>
""", unsafe_allow_html=True)


def page_header(eyebrow: str, title: str, subtitle: str = ""):
    """Renderiza um cabeçalho corporativo padronizado para cada página."""
    sub_html = f'<div class="page-subtitle">{subtitle}</div>' if subtitle else ''
    st.markdown(f"""
    <div class="page-header">
        <div class="page-eyebrow">{eyebrow}</div>
        <h1 style="margin:0;">{title}</h1>
        {sub_html}
    </div>
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

    # Verificar se já está autenticado (evita renderizar tela de login depois de logado)
    already_authenticated = st.session_state.get("authentication_status") is True

    # Só mostra o card de logo na tela de login se NÃO estiver autenticado
    login_container = st.empty()
    if not already_authenticated:
        login_container.markdown(f"""
        <div class="login-container">
            <div class="login-logo">
                {LOGO_HTML}
            </div>
            <div class="login-tagline">PLATAFORMA DE BI FINANCEIRO</div>
        </div>
        """, unsafe_allow_html=True)

    # API 0.3.2: login() retorna tuple (name, auth_status, username)
    try:
        name, auth_status, username = authenticator.login(location="main")
    except TypeError:
        name, auth_status, username = authenticator.login("Login", "main")

    # Se autenticou agora, limpa o card de logo
    if auth_status is True:
        login_container.empty()
    elif auth_status is False:
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

        # API HubSoft retorna: {"status": "success", "faturas": [...], "paginacao": {...}}
        if isinstance(data, dict):
            invoices = (data.get("faturas") or data.get("data") or
                       data.get("results") or data.get("itens") or [])
            # Pegar info de paginação se disponível
            pag_info = data.get("paginacao") or {}
            if isinstance(pag_info, dict):
                total_paginas = (pag_info.get("total_de_paginas") or
                                 pag_info.get("total_paginas") or
                                 pag_info.get("total"))
                pagina_atual = (pag_info.get("pagina_atual") or
                               pag_info.get("pagina") or pagina)
            else:
                total_paginas = None
                pagina_atual = pagina
        else:
            invoices = data
            total_paginas = None
            pagina_atual = pagina

        if not invoices:
            break
        all_invoices.extend(invoices)
        if progress_cb:
            extra = f" (página {pagina_atual}/{total_paginas})" if total_paginas else f" (página {pagina_atual})"
            progress_cb(len(all_invoices))

        # Critério de parada
        if total_paginas and pagina_atual >= int(total_paginas):
            break
        if len(invoices) < 100 and not total_paginas:
            # Sem info de paginação, e veio menos de 100 → última página
            break
        pagina += 1
        if pagina > 500:  # safety limit (50.000 faturas)
            break

    return all_invoices


def flatten_hubsoft_invoices(invoices: list) -> pd.DataFrame:
    """Converte resposta da API HubSoft em DataFrame.

    Estrutura real da API (confirmada via debug):
    - cliente, servico, forma_cobranca são objetos aninhados
    - Datas em formato YYYY-MM-DD
    - Valores são números (não strings)
    - NÃO tem 'status_pagamento' direto — derivar de data_pagamento
    """
    rows = []
    for inv in invoices:
        cliente = inv.get("cliente") or {}
        servico = inv.get("servico") or {}
        forma = inv.get("forma_cobranca") or {}
        if not isinstance(cliente, dict): cliente = {}
        if not isinstance(servico, dict): servico = {}
        if not isinstance(forma, dict): forma = {}

        data_pag = inv.get("data_pagamento")
        data_venc = inv.get("data_vencimento")
        valor_desc = float(inv.get("valor_desconto") or 0)
        fatura_ativa = inv.get("fatura_ativa", True)

        # Deriva status_pagamento (a API não fornece direto)
        if data_pag and str(data_pag).strip() not in ("", "None", "null"):
            status = "Pago - Desconto" if valor_desc > 0 else "Paga"
        elif fatura_ativa is False:
            status = "Cancelada"
        else:
            status = "Em Aberto"

        rows.append({
            "codigo_cliente": cliente.get("codigo_cliente"),
            "nome_razaosocial": cliente.get("nome_razaosocial") or cliente.get("nome_fantasia"),
            "numero_plano": servico.get("numero_plano"),
            "servico": servico.get("descricao"),
            "servico_status": servico.get("servico_status"),
            "nosso_numero": inv.get("nosso_numero"),
            "valor": float(inv.get("valor") or 0),
            "valor_pago": float(inv.get("valor_pago") or 0),
            "valor_descontos": valor_desc,
            "data_vencimento": data_venc,
            "data_pagamento": data_pag,
            "forma_cobranca": forma.get("descricao"),
            "cpf_cnpj": (cliente.get("cpf_cnpj") or "").replace(".", "").replace("-", "").replace("/", ""),
            "status_pagamento": status,
            "telefone_primario": cliente.get("telefone_primario"),
            # Campos extras que podem ser úteis depois
            "tipo_cobranca": inv.get("tipo_cobranca"),
            "grupos_cliente": cliente.get("grupos_cliente"),
            "id_fatura": inv.get("id_fatura"),
        })

    df = pd.DataFrame(rows)
    # Converter datas (formato ISO YYYY-MM-DD)
    for col in ['data_vencimento', 'data_pagamento']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')
    # Garantir valores numéricos
    for col in ['valor', 'valor_pago', 'valor_descontos']:
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
    page_header("INTEGRAÇÃO API", "Importar do HubSoft", "Sincroniza diretamente com a API do HubSoft — sem precisar exportar XLSX")

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

    # Modo debug
    debug_mode = st.checkbox("🔬 Modo debug (mostra resposta crua da API)",
                              help="Útil pra diagnosticar problemas. Mostra o JSON da 1ª fatura.")

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

            # DEBUG: mostrar JSON cru da 1ª fatura
            if debug_mode and len(invoices_raw) > 0:
                st.divider()
                st.subheader("🔬 Debug: JSON cru da 1ª fatura (da API)")
                st.markdown("**Copia este JSON e mande pro suporte para mapear os campos corretamente:**")
                st.json(invoices_raw[0])
                st.markdown("**Lista de chaves do 1º registro:**")
                st.code(", ".join(invoices_raw[0].keys()) if isinstance(invoices_raw[0], dict) else "(não é dict)")

            status.info("🔄 Convertendo dados...")
            df = flatten_hubsoft_invoices(invoices_raw)
            st.session_state['fat'] = df
            st.session_state['hubsoft_sync_time'] = datetime.now()

            status.success(f"✅ Pronto! {len(df)} faturas importadas · {fmt_brl(df['valor'].sum(), 2)} faturado.")
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
    page_header("UPLOAD", "Upload de Dados", "Arraste os arquivos abaixo — o sistema identifica o tipo automaticamente")

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
            st.success(f"✓ HubSoft: {len(fat)} faturas · {fmt_brl(fat['valor'].sum(), 2)} faturado")

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
        c2.metric("Faturado", f"{fmt_brl(st.session_state['fat']['valor'].sum(), 0)}")
        if 'ext' in st.session_state:
            c3.metric("Transações Banco", f"{len(st.session_state['ext']):,}")


def page_resumo():
    page_header("VISÃO GERAL", "Resumo Executivo", "Indicadores-chave do financeiro consolidado")

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
    col1.metric("Faturado", f"{fmt_brl(fat['valor'].sum(), 0)}", f"{len(fat)} faturas")
    col2.metric("Pago (HubSoft)", f"{fmt_brl(fat['valor_pago'].sum(), 0)}", f"{fat['valor_pago'].sum()/fat['valor'].sum()*100:.1f}% cobrado")
    col3.metric("Vencido", f"{fmt_brl(vencidas['valor'].sum(), 0)}", f"{len(vencidas)} faturas", delta_color="inverse")
    if len(ext) > 0:
        col4.metric("Recebido nos Bancos", f"{fmt_brl(ext['Valor'].sum(), 0)}", f"{len(ext)} transações")

    # Conciliação
    if len(fat_match) > 0:
        st.divider()
        st.subheader("Conciliação Bancária")
        matched = fat_match[fat_match['matched_ext_id'].notna()]
        pct = len(matched) / len(fat_match) * 100
        c1, c2, c3 = st.columns(3)
        c1.metric("Taxa de Conciliação", f"{pct:.1f}%", f"{len(matched)}/{len(fat_match)}")
        c2.metric("Valor Conciliado", f"{fmt_brl(matched['valor_pago'].sum(), 0)}")
        c3.metric("Pendente Investigação", f"{fmt_brl(fat_match[fat_match['matched_ext_id'].isna()]['valor_pago'].sum(), 0)}")

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
        yaxis_tickformat=',.0f', yaxis_title='R$', separators=',.',
    )
    st.plotly_chart(fig, use_container_width=True)


def page_conciliacao():
    page_header("CONCILIAÇÃO", "Conciliação Bancária", "Cruzamento entre faturas pagas no HubSoft × créditos efetivos nos bancos")
    if 'fat_match' not in st.session_state:
        st.warning("Faça upload dos dados primeiro.")
        return

    fat_match = st.session_state['fat_match']
    ext = st.session_state.get('ext_after', pd.DataFrame())

    matched = fat_match[fat_match['matched_ext_id'].notna()]
    unmatched = fat_match[fat_match['matched_ext_id'].isna()]
    ext_unused = ext[~ext['used']] if 'used' in ext.columns else pd.DataFrame()

    c1, c2, c3 = st.columns(3)
    c1.metric("Conciliadas", f"{len(matched)}", f"{fmt_brl(matched['valor_pago'].sum(), 0)}")
    c2.metric("Sem Match Banco", f"{len(unmatched)}", f"{fmt_brl(unmatched['valor_pago'].sum(), 0)}", delta_color="inverse")
    c3.metric("Banco s/ Fatura", f"{len(ext_unused)}", f"{fmt_brl(ext_unused['Valor'].sum() if len(ext_unused)>0 else 0, 0)}", delta_color="inverse")

    tab1, tab2, tab3 = st.tabs(["✅ Conciliadas", "🔴 Faturas s/ Match", "❓ Banco s/ Fatura"])

    with tab1:
        df_disp = (matched[['codigo_cliente', 'nome_razaosocial', 'nosso_numero', 'valor_pago',
                            'data_pagamento', 'ext_banco', 'ext_data', 'ext_desc']]
                   .rename(columns={'codigo_cliente': 'Cód', 'nome_razaosocial': 'Cliente',
                                    'nosso_numero': 'Nosso Nº', 'valor_pago': 'Pago',
                                    'data_pagamento': 'Data Pgto', 'ext_banco': 'Banco',
                                    'ext_data': 'Data Banco', 'ext_desc': 'Descrição'})
                   .sort_values('Pago', ascending=False))
        st.dataframe(format_df_brl(df_disp, money_cols=['Pago']),
                     use_container_width=True, height=500)

    with tab2:
        st.markdown(f"**{len(unmatched)} faturas marcadas como pagas no HubSoft mas sem comprovante bancário.**")
        df_disp = (unmatched[['codigo_cliente', 'nome_razaosocial', 'nosso_numero', 'valor_pago',
                              'data_pagamento', 'forma_cobranca']]
                   .rename(columns={'codigo_cliente': 'Cód', 'nome_razaosocial': 'Cliente',
                                    'nosso_numero': 'Nosso Nº', 'valor_pago': 'Pago',
                                    'data_pagamento': 'Data Pgto', 'forma_cobranca': 'Forma'})
                   .sort_values('Pago', ascending=False))
        st.dataframe(format_df_brl(df_disp, money_cols=['Pago']),
                     use_container_width=True, height=500)

    with tab3:
        if len(ext_unused) > 0:
            st.markdown(f"**{len(ext_unused)} créditos no banco que não acharam fatura correspondente.**")
            df_disp = (ext_unused[['banco', 'Data', 'Valor', 'memo']]
                       .rename(columns={'memo': 'Descrição'})
                       .sort_values('Valor', ascending=False))
            st.dataframe(format_df_brl(df_disp, money_cols=['Valor']),
                         use_container_width=True, height=500)


def page_inadimplencia():
    page_header("COBRANÇA", "Inadimplência", "Faturas vencidas — aging, valores e priorização por cliente")
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
    c1.metric("Total Vencido", f"{fmt_brl(vencidas['valor'].sum(), 0)}", f"{len(vencidas)} faturas")
    c2.metric("Clientes Inadimplentes", f"{vencidas['codigo_cliente'].nunique() if len(vencidas) > 0 else 0}")
    over_90 = vencidas[vencidas['dias_atraso'] > 90] if len(vencidas) > 0 else pd.DataFrame()
    c3.metric("Acima de 90 dias", f"{fmt_brl(over_90['valor'].sum() if len(over_90) > 0 else 0, 0)}",
              f"{len(over_90)} faturas (jurídico)", delta_color="inverse")

    if len(vencidas) == 0:
        st.success("🎉 Nenhuma fatura vencida! Toda a carteira está em dia.")
        st.info(f"Carteira a vencer: {len(em_aberto)} faturas · {fmt_brl(em_aberto['valor'].sum(), 2)}")
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
        fig.update_layout(height=400, showlegend=False, yaxis_tickformat=',.0f', separators=',.')
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
    st.dataframe(format_df_brl(top, money_cols=['Valor']),
                 use_container_width=True, height=500)


def page_clientes():
    page_header("CARTEIRA", "Clientes", "Base completa de clientes com classificação Empresa / Governo / Pessoa Física")
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

    st.markdown(f"**{len(df)} clientes · {fmt_brl(df['Faturado'].sum(), 2)} faturado**")

    # Cards summary
    c1, c2, c3 = st.columns(3)
    for col, cat, color in [(c1, 'Empresa', '#9FC5E8'), (c2, 'Governo', '#FFD966'), (c3, 'Pessoa Física', '#B6D7A8')]:
        sub = df[df['Categoria'] == cat]
        col.markdown(f"<div style='padding:1rem;background:{color}22;border-left:4px solid {color};border-radius:4px'>"
                     f"<div style='font-size:11px;color:#666'>{cat.upper()}</div>"
                     f"<div style='font-size:22px;font-weight:600'>{len(sub)} clientes</div>"
                     f"<div style='font-size:13px;color:#444'>{fmt_brl(sub['Faturado'].sum(), 0)}</div>"
                     f"</div>", unsafe_allow_html=True)

    df_disp = (df[['codigo_cliente', 'nome_razaosocial', 'cpf_cnpj', 'Categoria',
                   'Faturas', 'Faturado', 'Pago', '% Pago', 'Em_Aberto']]
               .rename(columns={'codigo_cliente': 'Cód', 'nome_razaosocial': 'Cliente',
                                'cpf_cnpj': 'CPF/CNPJ', 'Em_Aberto': 'Em Aberto'}))
    st.dataframe(
        format_df_brl(df_disp, money_cols=['Faturado', 'Pago', 'Em Aberto'], pct_cols=['% Pago']),
        use_container_width=True, height=600
    )


def page_top_clientes():
    page_header("RANKING", "Top Clientes", "Maiores pagantes acumulados no período carregado")
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
                      xaxis_tickformat=',.0f', yaxis_title=None, separators=',.',
                      yaxis={'categoryorder': 'total ascending'})
    st.plotly_chart(fig, use_container_width=True)

    total_top = top['Pago'].sum()
    total_geral = fat['valor_pago'].sum()
    st.info(f"**Top {top_n}** = {fmt_brl(total_top, 2)} · {total_top/total_geral*100:.1f}% da receita total")


def page_exportar():
    page_header("EXPORTAÇÃO", "Relatórios", "Gere planilhas consolidadas em XLSX para distribuir")
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

    # Sidebar com logo
    with st.sidebar:
        st.markdown(f"""
        <div class="sidebar-logo">
            {LOGO_HTML}
            <div class="sidebar-subtitle">JET BI</div>
        </div>
        <div class="sidebar-user">
            <div style="font-size:0.7rem;color:#888;text-transform:uppercase;letter-spacing:0.05em;">Logado como</div>
            <div style="font-weight:600;color:#fff;">{name}</div>
        </div>
        """, unsafe_allow_html=True)

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
