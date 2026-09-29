# BizzyFrontend

AWS deployment documentation is maintained in [BizzyBackend/docs/deployment](https://github.com/BizzyBeeAI/BizzyBackend/tree/main/docs/deployment). The pending delivery changes add Cognito PKCE login and owner-only approval controls; production builds fail closed without Cognito configuration. Use `.env.example` for public configuration only. `npm run test:contract` verifies the checked-in backend OpenAPI snapshot.

Frontend scaffolding for **BizzyBee AI** MVP UI.

## Run locally

```bash
npm install
npm run dev
```

The dev server proxies `/api` to the backend at `http://localhost:8000`, so start [BizzyBackend](https://github.com/BizzyBeeAI/BizzyBackend) first (`uvicorn backend.main:app --reload`). To call a deployed backend instead, set `VITE_API_BASE_URL` (for example `https://<host>/api/v1`) in `.env.local`.

## Build and lint

```bash
npm run lint
npm run build
```

## Scope in this scaffold

- Business health summary cards; health score (`GET /api/v1/business-health`), sales trend and out-of-stock count are live
- Priority alerts (`GET /api/v1/sales-inventory/alerts`): critical, warning and info alerts with the suggested next step and whether it needs approval
- Sales Bee panel (`GET /api/v1/sales/summary`): revenue for the last 7 days vs the 7 days before, each product's share of the decline, volume vs price/mix effect, revenue by channel and the suggested next step
- Inventory Bee panel (`GET /api/v1/inventory/status`): stock risk counts, the out-of-stock product with unfulfilled demand, lost sales and next delivery, and a watch list of products that may run out before restock with suggested order quantities. Quantities are marked provisional when an incoming delivery has no confirmed quantity
- Both panels read the standard `AgentResponse` (`summary`, `evidence`, `recommended_actions`); a `failed` response shows the agent's own explanation
- Multilingual query input (English, Tamil, Mandarin, Bahasa Melayu, Hindi). The selected language is sent as a code (`en`, `ta`, `zh-CN`, `ms`, `hi`) to `/query` and both Bee panels; the backend currently localises summaries for English and Chinese only
- Hive activity panel for Queen/Specialist/Governance agents
- Evidence and recommendation panels with GREEN/AMBER/RED cues
- Approval action controls and an audit timeline built from the stored record (`GET /api/v1/audit/{workflow_id}`)
- Typed API route placeholders aligned to planned backend endpoints under `/api/v1`
