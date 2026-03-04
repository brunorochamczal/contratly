-- ═══════════════════════════════════════════════════════════
--  ContratosPy — Schema PostgreSQL
--  Execute: psql -U postgres -d contratospy -f schema.sql
-- ═══════════════════════════════════════════════════════════

-- Criar banco (executar como superuser)
-- CREATE DATABASE contratospy;

-- ─────────────────────────────────────────────
-- USERS
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id              VARCHAR(36) PRIMARY KEY,
    name            VARCHAR(200) NOT NULL,
    email           VARCHAR(200) UNIQUE NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    role            VARCHAR(20) DEFAULT 'viewer'
                    CHECK (role IN ('admin','legal','manager','viewer')),
    department      VARCHAR(100),
    phone           VARCHAR(20),
    is_active       BOOLEAN DEFAULT true,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

-- ─────────────────────────────────────────────
-- CONTRACTS
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS contracts (
    id                  VARCHAR(36) PRIMARY KEY,
    code                VARCHAR(50) UNIQUE NOT NULL,
    title               VARCHAR(300) NOT NULL,
    contract_type       VARCHAR(30) DEFAULT 'service'
                        CHECK (contract_type IN ('service','supply','lease','nda','sla','partnership','other')),
    status              VARCHAR(20) DEFAULT 'active'
                        CHECK (status IN ('draft','active','expiring','expired','cancelled','renewed')),
    counterparty_name   VARCHAR(200) NOT NULL,
    counterparty_doc    VARCHAR(30),
    counterparty_email  VARCHAR(200),
    start_date          DATE NOT NULL,
    end_date            DATE,
    renewal_type        VARCHAR(20) DEFAULT 'manual'
                        CHECK (renewal_type IN ('manual','automatic','none')),
    renewal_notice_days INTEGER DEFAULT 30,
    auto_renewal_months INTEGER,
    value_total         NUMERIC(15,2),
    value_monthly       NUMERIC(15,2),
    currency            CHAR(3) DEFAULT 'BRL',
    description         TEXT,
    internal_notes      TEXT,
    responsible_id      VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    department          VARCHAR(100),
    is_confidential     BOOLEAN DEFAULT false,
    created_by          VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    created_at          TIMESTAMP DEFAULT NOW(),
    updated_at          TIMESTAMP DEFAULT NOW()
);

-- Índices para performance
CREATE INDEX IF NOT EXISTS idx_contracts_status ON contracts(status);
CREATE INDEX IF NOT EXISTS idx_contracts_end_date ON contracts(end_date);
CREATE INDEX IF NOT EXISTS idx_contracts_responsible ON contracts(responsible_id);
CREATE INDEX IF NOT EXISTS idx_contracts_type ON contracts(contract_type);

-- ─────────────────────────────────────────────
-- ALERTS
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS alerts (
    id              VARCHAR(36) PRIMARY KEY,
    contract_id     VARCHAR(36) NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    alert_type      VARCHAR(20) DEFAULT 'expiration'
                    CHECK (alert_type IN ('expiration','renewal','clause','custom')),
    days_before     INTEGER NOT NULL,
    trigger_date    DATE NOT NULL,
    event_date      DATE NOT NULL,
    title           VARCHAR(200),
    message         TEXT,
    status          VARCHAR(20) DEFAULT 'pending'
                    CHECK (status IN ('pending','sent','acknowledged','snoozed','dismissed')),
    priority        VARCHAR(10) DEFAULT 'medium'
                    CHECK (priority IN ('low','medium','high','critical')),
    sent_at         TIMESTAMP,
    acknowledged_at TIMESTAMP,
    acknowledged_by VARCHAR(36) REFERENCES users(id),
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alerts_contract ON alerts(contract_id);
CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status);
CREATE INDEX IF NOT EXISTS idx_alerts_trigger_date ON alerts(trigger_date);
CREATE INDEX IF NOT EXISTS idx_alerts_priority ON alerts(priority);

-- ─────────────────────────────────────────────
-- RENEWALS
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS renewals (
    id                      VARCHAR(36) PRIMARY KEY,
    original_contract_id    VARCHAR(36) REFERENCES contracts(id) ON DELETE SET NULL,
    new_contract_id         VARCHAR(36) REFERENCES contracts(id) ON DELETE SET NULL,
    renewal_number          INTEGER DEFAULT 1,
    decision                VARCHAR(20) DEFAULT 'renew'
                            CHECK (decision IN ('renew','renegotiate','terminate','replace')),
    decision_date           DATE,
    decision_by             VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    new_start_date          DATE,
    new_end_date            DATE,
    new_value               NUMERIC(15,2),
    notes                   TEXT,
    approved_by             VARCHAR(36) REFERENCES users(id),
    approved_at             TIMESTAMP,
    created_at              TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_renewals_original ON renewals(original_contract_id);

-- ─────────────────────────────────────────────
-- DOCUMENTS
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS documents (
    id              VARCHAR(36) PRIMARY KEY,
    contract_id     VARCHAR(36) REFERENCES contracts(id) ON DELETE CASCADE,
    filename        VARCHAR(300) NOT NULL,
    file_path       VARCHAR(500) NOT NULL,
    file_size       INTEGER,
    mime_type       VARCHAR(100),
    version         INTEGER DEFAULT 1,
    is_current      BOOLEAN DEFAULT true,
    uploaded_by     VARCHAR(36) REFERENCES users(id),
    uploaded_at     TIMESTAMP DEFAULT NOW(),
    description     VARCHAR(500)
);

-- ─────────────────────────────────────────────
-- TAGS
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tags (
    id      VARCHAR(36) PRIMARY KEY,
    name    VARCHAR(50) UNIQUE NOT NULL,
    color   CHAR(7) DEFAULT '#6366f1'
);

CREATE TABLE IF NOT EXISTS contract_tags (
    contract_id VARCHAR(36) REFERENCES contracts(id) ON DELETE CASCADE,
    tag_id      VARCHAR(36) REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (contract_id, tag_id)
);

-- ─────────────────────────────────────────────
-- AUDIT LOGS
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_logs (
    id          VARCHAR(36) PRIMARY KEY,
    user_id     VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    action      VARCHAR(100) NOT NULL,
    entity_type VARCHAR(50),
    entity_id   VARCHAR(36),
    old_values  JSONB,
    new_values  JSONB,
    ip_address  VARCHAR(50),
    user_agent  TEXT,
    created_at  TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_logs(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at DESC);

-- ─────────────────────────────────────────────
-- UPDATE TRIGGER
-- ─────────────────────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_contracts_updated_at ON contracts;
CREATE TRIGGER trigger_contracts_updated_at
    BEFORE UPDATE ON contracts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ─────────────────────────────────────────────
-- VIEW: DASHBOARD SUMMARY
-- ─────────────────────────────────────────────
CREATE OR REPLACE VIEW v_contract_summary AS
SELECT
    c.id, c.code, c.title, c.status, c.contract_type,
    c.counterparty_name, c.end_date,
    c.end_date - CURRENT_DATE AS days_until_expiry,
    c.value_total, c.value_monthly,
    u.name AS responsible_name,
    CASE
        WHEN c.end_date IS NULL THEN 'none'
        WHEN c.end_date < CURRENT_DATE THEN 'expired'
        WHEN c.end_date <= CURRENT_DATE + 7 THEN 'critical'
        WHEN c.end_date <= CURRENT_DATE + 30 THEN 'high'
        WHEN c.end_date <= CURRENT_DATE + 60 THEN 'medium'
        WHEN c.end_date <= CURRENT_DATE + 90 THEN 'low'
        ELSE 'ok'
    END AS urgency_level,
    (SELECT COUNT(*) FROM alerts a WHERE a.contract_id = c.id AND a.status IN ('pending','sent')) AS pending_alerts
FROM contracts c
LEFT JOIN users u ON c.responsible_id = u.id
WHERE c.status != 'cancelled';

-- Mensagem de sucesso
DO $$ BEGIN
    RAISE NOTICE '✅ Schema ContratosPy criado com sucesso!';
    RAISE NOTICE '   Tabelas: users, contracts, alerts, renewals, documents, tags, audit_logs';
    RAISE NOTICE '   Views: v_contract_summary';
END $$;
