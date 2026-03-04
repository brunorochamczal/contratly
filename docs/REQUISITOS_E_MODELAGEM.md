# ContratosPy — Sistema de Gestão de Contratos
## Requisitos & Modelagem

---

## 1. CONTEXTO E DOR DO CLIENTE

**Problema central:** Departamentos jurídicos de empresas médias perdem dinheiro mensalmente por
esquecimento de prazos contratuais — renovações automáticas indesejadas, multas por rescisão fora
do prazo, perda de janelas de negociação e inadimplência por falta de cobrança.

**Impacto financeiro típico:**
- Renovação automática indesejada de contratos desfavoráveis
- Multas contratuais por descumprimento de prazos de notificação
- Perda de cláusulas de reajuste não exercidas no prazo
- Contratos de fornecedores renovados sem renegociação

---

## 2. OBJETIVOS DO SISTEMA

1. Centralizar todos os contratos da empresa em um único repositório
2. Automatizar alertas de vencimento, renovação e marcos contratuais
3. Fornecer dashboard executivo com visão de risco e exposição financeira
4. Rastrear todo o histórico de alterações e renovações
5. Gerar relatórios para auditoria e compliance

---

## 3. REQUISITOS FUNCIONAIS

### RF-01 — Gestão de Contratos
- RF-01.1: Cadastrar contrato com todas as partes envolvidas
- RF-01.2: Definir tipo: prestação de serviços, fornecimento, locação, NDA, SLA, etc.
- RF-01.3: Registrar valor total, valor mensal e moeda
- RF-01.4: Definir data de início, término e tipo de renovação
- RF-01.5: Upload e versionamento de documentos (.pdf, .docx)
- RF-01.6: Registrar responsável interno (gestor do contrato)
- RF-01.7: Associar tags e categorias livres
- RF-01.8: Registrar cláusulas especiais com datas próprias

### RF-02 — Alertas e Notificações
- RF-02.1: Configurar múltiplos alertas por contrato (ex.: 90, 60, 30, 15 dias antes)
- RF-02.2: Enviar notificações por e-mail
- RF-02.3: Exibir alertas no dashboard em tempo real
- RF-02.4: Escalonar alertas não respondidos para gestores superiores
- RF-02.5: Alertas para cláusulas específicas (reajuste, auditoria, entrega)
- RF-02.6: Histórico completo de alertas enviados e recebidos

### RF-03 — Dashboard Executivo
- RF-03.1: Total de contratos ativos, a vencer e vencidos
- RF-03.2: Exposição financeira total por categoria
- RF-03.3: Contratos críticos (vencendo em < 30 dias)
- RF-03.4: Linha do tempo de vencimentos (próximos 12 meses)
- RF-03.5: Distribuição por tipo e status
- RF-03.6: KPIs de saúde do portfólio contratual

### RF-04 — Fluxo de Renovação
- RF-04.1: Iniciar processo de renovação a partir de alerta
- RF-04.2: Registrar decisão: renovar, renegociar, encerrar, substituir
- RF-04.3: Criar nova versão do contrato vinculada ao original
- RF-04.4: Registrar histórico de todas as renovações
- RF-04.5: Workflow de aprovação multi-nível (solicitante → jurídico → diretoria)

### RF-05 — Relatórios e Auditoria
- RF-05.1: Relatório de contratos por período
- RF-05.2: Relatório de vencimentos (30/60/90 dias)
- RF-05.3: Histórico de alterações com autor e timestamp
- RF-05.4: Exportação para PDF e Excel

### RF-06 — Segurança e Controle de Acesso
- RF-06.1: Autenticação com usuário e senha (JWT)
- RF-06.2: Perfis: Administrador, Jurídico, Gestor, Visualizador
- RF-06.3: Controle de acesso por contrato (visibilidade restrita)
- RF-06.4: Log de auditoria de todas as ações do sistema

---

## 4. REQUISITOS NÃO FUNCIONAIS

| ID     | Requisito                                              | Critério                        |
|--------|--------------------------------------------------------|---------------------------------|
| RNF-01 | Performance                                            | Resposta < 2s para 100 usuários |
| RNF-02 | Disponibilidade                                        | 99,5% uptime                    |
| RNF-03 | Segurança                                              | LGPD-compliant, dados criptografados |
| RNF-04 | Escalabilidade                                         | Suporte a 10.000+ contratos     |
| RNF-05 | Usabilidade                                            | Interface responsiva (mobile-first) |
| RNF-06 | Rastreabilidade                                        | 100% das ações logadas          |

---

## 5. MODELAGEM DO BANCO DE DADOS

### Diagrama Entidade-Relacionamento (textual)

```
USERS ──< CONTRACT_USERS >── CONTRACTS
  │                               │
  │                          ┌────┴────────────┐
  └──< AUDIT_LOGS         ALERTS          RENEWALS
                              │                 │
                         ALERT_HISTORY    DOCUMENTS
                                          CLAUSES
                                          CONTRACT_TAGS >── TAGS
```

### Tabelas Detalhadas

#### `users`
```sql
id              UUID PRIMARY KEY
name            VARCHAR(200) NOT NULL
email           VARCHAR(200) UNIQUE NOT NULL
password_hash   VARCHAR(255) NOT NULL
role            ENUM('admin','legal','manager','viewer')
department      VARCHAR(100)
phone           VARCHAR(20)
is_active       BOOLEAN DEFAULT true
created_at      TIMESTAMP DEFAULT NOW()
updated_at      TIMESTAMP DEFAULT NOW()
```

#### `contracts`
```sql
id                  UUID PRIMARY KEY
code                VARCHAR(50) UNIQUE NOT NULL  -- ex: CTR-2024-0001
title               VARCHAR(300) NOT NULL
contract_type       ENUM('service','supply','lease','nda','sla','partnership','other')
status              ENUM('draft','active','expiring','expired','cancelled','renewed')
counterparty_name   VARCHAR(200) NOT NULL
counterparty_doc    VARCHAR(30)  -- CNPJ/CPF
counterparty_email  VARCHAR(200)
start_date          DATE NOT NULL
end_date            DATE
renewal_type        ENUM('manual','automatic','none')
renewal_notice_days INT DEFAULT 30  -- dias de antecedência para notificar
auto_renewal_months INT             -- meses de renovação automática
value_total         NUMERIC(15,2)
value_monthly       NUMERIC(15,2)
currency            CHAR(3) DEFAULT 'BRL'
description         TEXT
internal_notes      TEXT
responsible_id      UUID REFERENCES users(id)
department          VARCHAR(100)
is_confidential     BOOLEAN DEFAULT false
created_by          UUID REFERENCES users(id)
created_at          TIMESTAMP DEFAULT NOW()
updated_at          TIMESTAMP DEFAULT NOW()
```

#### `alerts`
```sql
id              UUID PRIMARY KEY
contract_id     UUID REFERENCES contracts(id) ON DELETE CASCADE
alert_type      ENUM('expiration','renewal','clause','custom')
days_before     INT NOT NULL  -- quantos dias antes do evento
trigger_date    DATE NOT NULL  -- data calculada do alerta
event_date      DATE NOT NULL  -- data do evento alvo
title           VARCHAR(200)
message         TEXT
status          ENUM('pending','sent','acknowledged','snoozed','dismissed')
priority        ENUM('low','medium','high','critical')
notify_users    UUID[]  -- array de user IDs
sent_at         TIMESTAMP
acknowledged_at TIMESTAMP
acknowledged_by UUID REFERENCES users(id)
created_at      TIMESTAMP DEFAULT NOW()
```

#### `alert_history`
```sql
id          UUID PRIMARY KEY
alert_id    UUID REFERENCES alerts(id)
action      ENUM('created','sent','resent','acknowledged','snoozed','dismissed','escalated')
performed_by UUID REFERENCES users(id)
channel     ENUM('email','system','sms')
details     JSONB
created_at  TIMESTAMP DEFAULT NOW()
```

#### `renewals`
```sql
id                  UUID PRIMARY KEY
original_contract_id UUID REFERENCES contracts(id)
new_contract_id      UUID REFERENCES contracts(id)
renewal_number       INT  -- 1ª renovação, 2ª renovação...
decision            ENUM('renew','renegotiate','terminate','replace')
decision_date       DATE
decision_by         UUID REFERENCES users(id)
new_start_date      DATE
new_end_date        DATE
new_value           NUMERIC(15,2)
notes               TEXT
approved_by         UUID REFERENCES users(id)
approved_at         TIMESTAMP
created_at          TIMESTAMP DEFAULT NOW()
```

#### `documents`
```sql
id              UUID PRIMARY KEY
contract_id     UUID REFERENCES contracts(id) ON DELETE CASCADE
filename        VARCHAR(300) NOT NULL
file_path       VARCHAR(500) NOT NULL
file_size       INT
mime_type       VARCHAR(100)
version         INT DEFAULT 1
is_current      BOOLEAN DEFAULT true
uploaded_by     UUID REFERENCES users(id)
uploaded_at     TIMESTAMP DEFAULT NOW()
description     VARCHAR(500)
```

#### `clauses`
```sql
id              UUID PRIMARY KEY
contract_id     UUID REFERENCES contracts(id) ON DELETE CASCADE
title           VARCHAR(200) NOT NULL
description     TEXT
due_date        DATE
alert_days      INT DEFAULT 30
is_recurring    BOOLEAN DEFAULT false
recurrence_rule VARCHAR(100)  -- RRULE format
status          ENUM('pending','completed','missed')
created_at      TIMESTAMP DEFAULT NOW()
```

#### `tags`
```sql
id      UUID PRIMARY KEY
name    VARCHAR(50) UNIQUE NOT NULL
color   CHAR(7)  -- hex color
```

#### `contract_tags`
```sql
contract_id UUID REFERENCES contracts(id) ON DELETE CASCADE
tag_id      UUID REFERENCES tags(id) ON DELETE CASCADE
PRIMARY KEY (contract_id, tag_id)
```

#### `audit_logs`
```sql
id          UUID PRIMARY KEY
user_id     UUID REFERENCES users(id)
action      VARCHAR(100) NOT NULL
entity_type VARCHAR(50)  -- 'contract', 'alert', 'user', etc.
entity_id   UUID
old_values  JSONB
new_values  JSONB
ip_address  INET
user_agent  TEXT
created_at  TIMESTAMP DEFAULT NOW()
```

---

## 6. ARQUITETURA DO SISTEMA

```
┌─────────────────────────────────────────────────────────┐
│                    FRONTEND (HTML/CSS/JS)                 │
│  Dashboard │ Contratos │ Alertas │ Relatórios │ Config   │
└─────────────────────┬───────────────────────────────────-┘
                      │ REST API (JSON)
┌─────────────────────▼────────────────────────────────────┐
│                  BACKEND (Python / Flask)                  │
│                                                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
│  │  Auth    │  │Contracts │  │ Alerts   │  │ Reports  │ │
│  │  JWT     │  │   CRUD   │  │ Engine   │  │  Export  │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘ │
│                                                            │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  SCHEDULER (APScheduler) — roda a cada hora        │  │
│  │  → Verifica contratos a vencer                     │  │
│  │  → Dispara alertas por e-mail                      │  │
│  │  → Atualiza status automaticamente                 │  │
│  └─────────────────────────────────────────────────────┘  │
└─────────────────────┬────────────────────────────────────-┘
                      │ SQLAlchemy ORM
┌─────────────────────▼────────────────────────────────────┐
│                    PostgreSQL                              │
│   contracts │ alerts │ users │ renewals │ audit_logs     │
└──────────────────────────────────────────────────────────┘
```

---

## 7. FLUXO DE ALERTAS

```
Scheduler (hourly)
    │
    ▼
Para cada contrato ATIVO:
    │
    ├─ Calcular dias_restantes = end_date - today
    │
    ├─ Para cada regra de alerta (90d, 60d, 30d, 15d, 7d, 1d):
    │       │
    │       ├─ Alerta já foi enviado hoje? → SKIP
    │       │
    │       └─ dias_restantes <= dias_alerta? → CRIAR ALERTA
    │                                              │
    │                                              ├─ Salvar no BD
    │                                              ├─ Enviar e-mail
    │                                              └─ Notificar dashboard
    │
    └─ dias_restantes <= 0 → Atualizar status para 'expired'
```

---

## 8. PERFIS DE USUÁRIO E PERMISSÕES

| Ação                        | Admin | Jurídico | Gestor | Visualizador |
|-----------------------------|-------|----------|--------|--------------|
| Criar contrato              | ✅    | ✅       | ✅     | ❌           |
| Editar contrato             | ✅    | ✅       | ✅*    | ❌           |
| Excluir contrato            | ✅    | ❌       | ❌     | ❌           |
| Ver contratos confidenciais | ✅    | ✅       | ❌     | ❌           |
| Gerenciar alertas           | ✅    | ✅       | ✅*    | ❌           |
| Aprovar renovações          | ✅    | ✅       | ❌     | ❌           |
| Gerenciar usuários          | ✅    | ❌       | ❌     | ❌           |
| Ver relatórios              | ✅    | ✅       | ✅     | ✅           |
| Configurar sistema          | ✅    | ❌       | ❌     | ❌           |

*apenas nos contratos sob sua responsabilidade

---

## 9. STACK TECNOLÓGICA

| Camada      | Tecnologia                          | Justificativa                    |
|-------------|-------------------------------------|----------------------------------|
| Frontend    | HTML5 + CSS3 + Vanilla JS           | Zero dependências, máxima perf   |
| Charts      | Chart.js                            | Leve, bonito, sem build step     |
| Backend     | Python 3.11 + Flask                 | Rápido de desenvolver, produtivo |
| ORM         | SQLAlchemy 2.0                      | Abstração segura do BD           |
| Banco       | PostgreSQL 15                       | ACID, JSON nativo, performático  |
| Scheduler   | APScheduler                         | Agendamento de tarefas em Python |
| Auth        | JWT (PyJWT + bcrypt)                | Stateless, seguro                |
| Email       | Flask-Mail / SMTP                   | Envio de alertas                 |
| PDF Export  | ReportLab / WeasyPrint              | Relatórios profissionais         |

---

## 10. ESTIMATIVA DE ESFORÇO

| Módulo                  | Complexidade | Horas estimadas |
|-------------------------|--------------|-----------------|
| Setup BD + Modelos      | Média        | 8h              |
| Auth + Usuários         | Média        | 8h              |
| CRUD Contratos          | Alta         | 16h             |
| Engine de Alertas       | Alta         | 12h             |
| Dashboard + Charts      | Alta         | 16h             |
| Renovações + Workflow   | Alta         | 12h             |
| Relatórios + Export     | Média        | 8h              |
| Frontend completo       | Alta         | 24h             |
| Testes + Deploy         | Média        | 8h              |
| **TOTAL**               |              | **~112h**       |
