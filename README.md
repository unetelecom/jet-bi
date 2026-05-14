# JET BI — Plataforma de BI Financeiro

Plataforma web que processa relatórios do HubSoft + extratos bancários e gera dashboards de conciliação, inadimplência, fluxo de caixa e análise de clientes — automaticamente.

## 📦 O que faz

Você arrasta:
- 📊 **Relatório de faturas do HubSoft** (XLSX exportado do painel)
- 🏦 **Extratos bancários** (BTG em CSV, Sicredi/Caixa/C6 em OFX) — múltiplos arquivos

E recebe:
- ✅ **Resumo executivo** com KPIs principais
- 🔍 **Conciliação bancária automática** (3 passes de match, ~85% de taxa)
- 🚨 **Inadimplência** com aging e priorização
- 👥 **Lista de clientes** pesquisável (categorizados em Empresa/Governo/PF)
- 🏆 **Ranking dos top pagantes**
- 📈 **Fluxo mensal** comparando faturado × pago × recebido
- 💾 **Exportação** de relatórios em XLSX

Tudo processado em memória — **nenhum dado fica salvo** após você fechar a sessão.

---

## 🚀 Como Hospedar (Streamlit Cloud — gratuito)

### Passo 1 — Criar repositório no GitHub

1. Acesse https://github.com e crie uma conta (se ainda não tiver).
2. Crie um novo repositório chamado `jet-bi` (público).
3. Faça upload dos arquivos deste projeto:
   - `app.py`
   - `requirements.txt`
   - `README.md`
   - `.gitignore`
   - **NÃO** envie `secrets.toml.example` se ele contiver senhas reais.

### Passo 2 — Conectar ao Streamlit Cloud

1. Acesse https://share.streamlit.io
2. Faça login com sua conta GitHub
3. Clique em **"New app"**
4. Selecione o repositório `jet-bi`, branch `main`, arquivo `app.py`
5. Clique em **"Deploy"**

Em ~3 minutos sua plataforma estará no ar em `https://SEU-USUARIO-jet-bi.streamlit.app`

### Passo 3 — Configurar usuários e senhas

1. No painel do app no Streamlit Cloud → clique em **"⋮"** → **"Settings"** → **"Secrets"**
2. Cole o conteúdo do arquivo `secrets.toml.example` (depois de personalizar com seus usuários)
3. Para gerar uma nova senha, rode no seu computador:

```bash
pip install streamlit-authenticator
python -c "import streamlit_authenticator as stauth; print(stauth.Hasher().hash('SUA_SENHA_AQUI'))"
```

Cole o hash gerado no campo `password` do usuário.

4. Salve. O app reinicia automaticamente.

---

## 🖥️ Como Rodar Localmente

Útil para testes e desenvolvimento.

### Passo 1 — Instalar Python (se ainda não tiver)

Baixe em https://python.org (versão 3.10 ou superior).

### Passo 2 — Instalar dependências

Abra o terminal/prompt no diretório do projeto:

```bash
pip install -r requirements.txt
```

### Passo 3 — Configurar autenticação local (opcional)

Crie o diretório `.streamlit` e dentro dele um arquivo `secrets.toml` com o conteúdo do `secrets.toml.example`.

Se não configurar, o sistema usa um usuário padrão:
- **Usuário:** `admin`
- **Senha:** `jet2026`

⚠️ Troque essa senha em produção!

### Passo 4 — Rodar

```bash
streamlit run app.py
```

Abre no navegador em http://localhost:8501

---

## 🔐 Segurança

- ✅ Código no GitHub público é normal — senhas ficam em `secrets`, não no código
- ✅ Dados processados em memória, descartados ao fechar sessão
- ✅ Login com hash bcrypt das senhas
- ⚠️ **NUNCA commite** o arquivo `secrets.toml` (já está no `.gitignore`)
- ⚠️ **NUNCA commite** arquivos `.csv`, `.ofx`, `.xlsx` com dados reais

---

## 🔄 Uso Mensal

1. No início de cada mês, exporte do HubSoft o relatório atualizado de faturas
2. Exporte os 4 extratos bancários do mês anterior (BTG, Sicredi, Caixa, C6)
3. Abra a plataforma (URL do Streamlit Cloud)
4. Arraste tudo na página **Upload** e clique em **Processar**
5. Navegue pelas páginas — todo o BI é gerado automaticamente
6. Exporte planilhas/relatórios na página **Exportar** se precisar

---

## 🛠️ Customização

O arquivo `app.py` é único — toda a lógica está lá. Para customizar:

- **Cores da marca:** altere `BRAND_ORANGE`, `BRAND_LIGHT` no topo do arquivo
- **Filtros de exclusão (intercompany, judicial, etc.):** função `filter_intercompany_and_judicial()`
- **Classificação de clientes (Governo/Empresa/PF):** listas `GOV_KEYWORDS` e `PJ_KEYWORDS`
- **Algoritmo de match:** função `run_match()` — 3 passes (exato / relaxado / agrupado N:1)

---

## 📞 Suporte

Plataforma desenvolvida para a Grupo JET (telecomunicações, Goiânia/GO).

Estrutura inicial das análises foi prototipada via Claude (Anthropic). Códigos baseados em padrões reais de uso do HubSoft + BTG Pactual + Sicredi + Caixa Econômica + C6 Bank.
