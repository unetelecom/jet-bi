# 🚀 Tutorial Visual de Deploy — Passo a Passo

Tempo total: ~15 minutos · Custo: R$ 0,00

## ✅ Pré-requisitos

- Conta no GitHub (criar em https://github.com — gratuito, leva 2 min)
- Os arquivos do projeto: `app.py`, `requirements.txt`, `.gitignore`, `README.md`

---

## Etapa 1 — Subir o código no GitHub

### Opção A: Pelo navegador (mais fácil)

1. Acesse https://github.com/new
2. Nome do repositório: `jet-bi`
3. Visibilidade: **Public** (necessário para o plano free do Streamlit)
4. Marque **"Add a README file"**
5. Clique em **"Create repository"**

6. No repositório criado, clique em **"Add file" → "Upload files"**
7. Arraste os 4 arquivos do projeto:
   - `app.py`
   - `requirements.txt`
   - `.gitignore`
   - (substitua o README pelo que está aqui)
8. Clique em **"Commit changes"**

✅ Pronto! Seu código está no GitHub.

---

## Etapa 2 — Hospedar no Streamlit Cloud

1. Acesse https://share.streamlit.io
2. Clique em **"Sign in with GitHub"**
3. Autorize o acesso
4. Clique em **"Create app"** → **"Deploy a public app from GitHub"**

Preencha:
- **Repository:** `SEU-USUARIO/jet-bi`
- **Branch:** `main`
- **Main file path:** `app.py`
- **App URL:** escolha um nome (ex: `jet-bi`)

5. Clique em **"Deploy"**

⏱️ Aguarde 2-3 minutos. O Streamlit vai instalar as dependências e iniciar o app.

✅ Quando aparecer "App is live!", clique em **"Manage app"** → "Open app".

Você verá a tela de login. Use o usuário/senha padrão (`admin` / `jet2026`) — mas SÓ TEMPORARIAMENTE.

---

## Etapa 3 — Configurar usuários reais

⚠️ **OBRIGATÓRIO antes de usar com dados reais.**

### 3.1 — Gerar hash da senha

No seu computador, abra um terminal e rode:

```bash
pip install streamlit-authenticator
```

Depois:

```bash
python -c "import streamlit_authenticator as stauth; print(stauth.Hasher().hash('MINHA_SENHA_FORTE'))"
```

Saída exemplo:
```
$2b$12$Xy9pK8...
```

Guarde esse hash. Faça uma vez para cada usuário do time.

### 3.2 — Configurar no Streamlit Cloud

1. No painel do app, clique em **"⚙️ Settings"** (canto inferior direito)
2. Vá em **"Secrets"**
3. Cole o conteúdo abaixo, **substituindo os valores**:

```toml
[cookie]
name = "jet_bi_auth"
key = "uma-string-aleatoria-bem-longa-de-pelo-menos-32-caracteres-aqui"
expiry_days = 7

[users.ruan]
name = "Ruan Carlos"
password = "$2b$12$SEU_HASH_AQUI"

[users.financeiro]
name = "Equipe Financeira"
password = "$2b$12$OUTRO_HASH_AQUI"
```

4. Clique em **"Save"**

O app reinicia automaticamente em ~30 segundos com os novos usuários.

---

## Etapa 4 — Compartilhar com o time

A URL é fixa: `https://SEU-USUARIO-jet-bi.streamlit.app`

Compartilhe com o time + os usuários/senhas que você criou.

Pode salvar na tela inicial do celular como atalho.

---

## 💡 Dicas

- **App "dormiu"?** No plano free, o app dorme após ~20 min sem uso. Quando alguém acessa, ele acorda em 30s. Não tem perda de dados — eles já foram processados em memória e descartados a cada sessão.
- **Erro ao processar arquivo?** Conferir se o formato bate: HubSoft em XLSX, BTG em CSV, demais em OFX.
- **Quer adicionar mais funcionalidades?** Edite `app.py` no GitHub. O Streamlit Cloud detecta a mudança e re-deploya automaticamente em ~1 minuto.

---

## 🐛 Algo deu errado?

Erros comuns:

| Problema | Solução |
|---|---|
| "ModuleNotFoundError" | Adicionar o módulo no `requirements.txt` e fazer commit |
| Login dá erro de cookie | Garantir que `cookie.key` no secrets tem 32+ caracteres |
| App não atualiza | Em "Manage app" → "Reboot app" |
| Senha não funciona | Re-gerar hash, copiar exato (cuidado com aspas extras) |
