# Deployment and Data-Localisation Guide

The same codebase and Docker images support every deployment mode below. Only `.env` changes.

## 1. Deployment modes

| Mode | Where it runs | LLM | Best for |
|---|---|---|---|
| **A. On-premise** | Client's server room / your office server | Ollama or vLLM on a local GPU | Banks, NBFCs, large corporates, strict clients |
| **B. Desktop/offline** | Laptop of a CA/finance user | Ollama on the laptop (3–8B model) | CA firms, SMEs, demos |
| **C. Global cloud, India region** | AWS Mumbai/Hyderabad, Azure Central/South/West India, GCP Mumbai/Delhi, OCI Mumbai/Hyderabad | vLLM on a GPU VM in the **same** region, or a managed AI service **verified** to process in-region | SaaS |
| **D. Indian / sovereign cloud** | Yotta, E2E Networks, CtrlS, Sify, NxtGen, Tata Communications, MeitY-empanelled clouds, NIC | vLLM on Indian GPU cloud; Indian LLM providers | Government/PSU, sovereignty-sensitive clients |
| **E. Hybrid** (recommended) | App + DB in an India region; enterprise clients get on-prem | Self-hosted, per deployment | Growing SaaS business |

## 2. Reference production layout (India region)

```
                Internet (HTTPS only, WAF)
                        │
             ┌──────────▼──────────┐
             │  Load balancer / TLS │  (India region)
             └──────────┬──────────┘
      ┌─────────────────┼──────────────────┐
      │ Private subnet  │                  │
 ┌────▼────┐      ┌─────▼─────┐      ┌─────▼──────┐
 │ UI      │      │ API       │      │ Scheduler  │
 │Streamlit│      │ FastAPI   │      │ cron/Celery│
 └────┬────┘      └─────┬─────┘      └─────┬──────┘
      └─────────┬───────┴──────────────────┘
       ┌────────▼────────┐   ┌──────────────────┐   ┌──────────────────┐
       │ PostgreSQL      │   │ Object storage    │   │ GPU VM: vLLM     │
       │ (encrypted)     │   │ (reports, files)  │   │ NO internet egress│
       └─────────────────┘   └──────────────────┘   └──────────────────┘
  Backups + DR: second India region (e.g. Mumbai → Hyderabad). Logs stay in-region.
```

Network controls:
- Security groups / NSGs should **deny all egress** except OS-patch mirrors and approved in-region services.
- The GPU VM has no public IP. Copy model weights in once from an internal artifact store.
- Set `ALLOWED_LLM_HOSTS` to the private DNS name of the GPU VM only.

## 3. What to verify with cloud AI services (if not self-hosting)

- [ ] The model is deployed in an India region (not "global" or "data zone" routing outside India)
- [ ] Prompts and outputs are **not stored or used for training**
- [ ] Abuse-monitoring and log storage location (some services keep prompts for review in other regions)
- [ ] A written DPA / contract clause confirming in-country processing

## 4. Regulatory checklist (confirm with your legal or CA advisor)

| Area | Action |
|---|---|
| DPDP Act 2023 + Rules | Notice/consent for personal data, purpose limitation, breach reporting, processor contracts |
| RBI (if payment data) | Payment system data stored only in India |
| SEBI (if regulated clients) | Follow the cloud framework for regulated entities |
| CERT-In | Report incidents on time; keep logs for 180 days in India; sync clocks to NTP |
| Companies Act | Books of account and backups must remain accessible in India |
| Security | VAPT by a CERT-In empanelled auditor; ISO 27001 / SOC 2 as you scale |

## 5. Go-live checklist

- [ ] Every resource (DB, storage, backups, logs, LLM, email relay) is in the approved region or on-prem
- [ ] `BLOCK_OUTBOUND_NETWORK=true`, `MASK_PII_BEFORE_LLM=true`, strong `COPILOT_API_KEYS`
- [ ] TLS 1.2+ in front of UI/API, plus disk/DB encryption at rest
- [ ] SSO/MFA (Keycloak) and role-based access before multi-user rollout
- [ ] Audit log shipped to in-region, write-once storage and retained 180+ days
- [ ] Backup/restore drill done, DR in a second India region
- [ ] Parallel run: AI MIS vs manual MIS for 2–3 month-ends, with signed-off variances
