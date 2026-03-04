# ContratosPy 📋
### Sistema de Gestão de Contratos com Alertas Automáticos

> **Problema resolvido:** O jurídico de empresas médias perde dinheiro todo mês por esquecer prazos contratuais. ContratosPy automatiza alertas de vencimento, renovação e marcos — nunca mais uma multa por prazo esquecido.

---

## 🚀 Deploy no Render (passo a passo)

### 1. Suba o repositório no GitHub
```bash
git init
git add .
git commit -m "first commit"
git remote add origin https://github.com/seu-usuario/contratospy.git
git push -u origin main
```

### 2. Crie o serviço no Render

**Opção A — Blueprint automático (recomendado)**
1. Acesse [render.com/dashboard](https://dashboard.render.com)
2. Clique em **New → Blueprint**
3. Conecte o repositório GitHub
4. O Render lê o `render.yaml` e cria automaticamente:
   - Web Service (Python/Flask + Gunicorn)
   - Banco PostgreSQL gratuito
   - Variável `SECRET_KEY` gerada automaticamente
   - `DATABASE_URL` injetada no serviço

**Opção B — Manual**
1. **New → PostgreSQL** — nome: `contratospy-db`
2. **New → Web Service** — conecte o repositório
   - Runtime: **Python 3**
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app --workers 2 --bind 0.0.0.0:$PORT --timeout 120`
3. Em **Environment Variables**, adicione:
   | Variável | Valor |
   |---|---|
   | `DATABASE_URL` | (copiar do PostgreSQL criado) |
   | `SECRET_KEY` | (gerar: `python -c "import secrets; print(secrets.token_hex(32))"`) |

### 3. Primeiro acesso
Após o deploy (~3 minutos), acesse a URL gerada pelo Render.

O sistema cria automaticamente os dados demo no primeiro boot:

| Perfil | E-mail | Senha |
|---|---|---|
| Administrador | `admin@empresa.com` | `admin123` |
| Jurídico | `marina@empresa.com` | `legal123` |
| Gestor | `carlos@empresa.com` | `manager123` |

> ⚠️ **Troque as senhas imediatamente após o primeiro login.**

### 4. Configurar e-mail (opcional)
No dashboard do Render → seu serviço → **Environment**:

| Variável | Valor |
|---|---|
| `MAIL_USERNAME` | seu@gmail.com |
| `MAIL_PASSWORD` | senha-de-app-gmail |
| `MAIL_FROM` | contratos@suaempresa.com |

Para gerar a senha de app: [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)

---

## 🗂️ Estrutura do repositório

```
contratospy/
├── app.py                        # Backend Flask completo
├── requirements.txt              # Dependências Python
├── render.yaml                   # Blueprint de deploy automático
├── .env.example                  # Template de variáveis de ambiente
├── .gitignore
│
├── frontend/
│   ├── index.html                # SPA — estrutura HTML
│   └── static/
│       ├── css/app.css           # Design system (603 linhas)
│       └── js/app.js             # Lógica da SPA (894 linhas)
│
├── scripts/
│   └── schema.sql                # Schema PostgreSQL (referência)
│
└── docs/
    └── REQUISITOS_E_MODELAGEM.md # Requisitos, DER, arquitetura
```

---

## 🏗️ Arquitetura

```
GitHub ──push──▶ Render (auto-deploy)
                      │
              ┌───────┴────────┐
              │   Flask/Gunicorn│  ← Web Service
              │   app.py        │
              │   /api/*  ─────────▶ REST API (JSON)
              │   /*      ─────────▶ frontend/index.html
              └───────┬────────┘
                      │ SQLAlchemy
              ┌───────▼────────┐
              │   PostgreSQL    │  ← Render Managed DB
              └────────────────┘
```

O Flask serve o frontend estático (`/frontend`) diretamente — sem Nginx, sem CDN. Simples e funcional para o plano gratuito do Render.

---

## ⚡ Engine de alertas

O APScheduler roda **a cada hora** dentro do próprio processo Gunicorn e verifica todos os contratos ativos. Alertas são disparados automaticamente em:

`90d → 60d → 30d → 15d → 7d → 1d`

Cada marco gera: registro no banco + e-mail para o responsável (se configurado) + notificação no painel.

---

## 🔑 Variáveis de ambiente

| Variável | Obrigatória | Descrição |
|---|---|---|
| `DATABASE_URL` | ✅ | URL do PostgreSQL (Render injeta automaticamente) |
| `SECRET_KEY` | ✅ | Chave JWT (Render pode gerar automaticamente) |
| `MAIL_USERNAME` | ❌ | E-mail remetente dos alertas |
| `MAIL_PASSWORD` | ❌ | Senha de app Gmail |
| `MAIL_FROM` | ❌ | Endereço "De:" dos e-mails |
| `MAIL_SERVER` | ❌ | Servidor SMTP (padrão: smtp.gmail.com) |
| `MAIL_PORT` | ❌ | Porta SMTP (padrão: 587) |

---

## 👥 Perfis de acesso

| Perfil | Permissões |
|---|---|
| **Admin** | Total: usuários, exclusão, auditoria, engine de alertas |
| **Jurídico** | Contratos + aprovação de renovações + auditoria |
| **Gestor** | Seus próprios contratos |
| **Visualizador** | Somente leitura |

---

## 🛠️ Desenvolvimento local

```bash
# 1. Clonar
git clone https://github.com/seu-usuario/contratospy.git
cd contratospy

# 2. Ambiente Python
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Banco local (PostgreSQL precisa estar rodando)
createdb contratospy

# 4. Variáveis de ambiente
cp .env.example .env
# edite o .env com suas configs locais

# 5. Rodar
python app.py
# Acesse: http://localhost:5000
```
