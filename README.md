# Contratly 📋
### Sistema de Gestão de Contratos com Alertas Automáticos

> **Problema resolvido:** O jurídico de empresas médias perde dinheiro todo mês por esquecer prazos contratuais. ContratosPy automatiza alertas de vencimento, renovação e marcos — nunca mais uma multa por prazo esquecido.

---

## ⚡ Engine de alertas

O APScheduler roda **a cada hora** dentro do próprio processo Gunicorn e verifica todos os contratos ativos. Alertas são disparados automaticamente em:

`90d → 60d → 30d → 15d → 7d → 1d`

Cada marco gera: registro no banco + e-mail para o responsável (se configurado) + notificação no painel.

---
