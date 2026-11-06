# AI Prospecting SaaS

Self-serve B2B prospecting: describe your business, define an Ideal Customer
Profile (ICP), run a batch, and review researched prospects with a business
problem, a "why it fits" explanation, qualification scoring, and evidence.

The Prospecting module is separate from the Outreach workflow. This repository
does **not** generate or send emails; it exports leads for Outreach via CSV
(and an optional, untested Google Sheets push).

## Stack

- **Backend:** FastAPI, Pydantic v2, SQLAlchemy 2, SQLite, Python 3.12
- **Frontend:** Next.js (App Router), React 19, TypeScript, Tailwind CSS
- **Providers:** deterministic synthetic demo provider (default) and an optional OpenAI analysis provider

## Running locally

### Backend

```bash
cd backend
python -m pip install -e ".[dev]"
python scripts/seed_demo.py          # creates backend/data/prospecting.db + demo workspace
python -m uvicorn app.main:app --reload --port 8000
```

The API runs at `http://localhost:8000`; interactive docs at `/docs`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Create `frontend/.env.local` with:

```
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

Open `http://localhost:3000`. All pages use the `demo` workspace slug.

## Environment variables (backend)

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./data/prospecting.db` | Database connection |
| `DEMO_MODE` | `true` | Demo mode flag |
| `AI_PROVIDER` | `demo` | `demo` or `openai` |
| `OPENAI_API_KEY` | empty | Required only for `AI_PROVIDER=openai` |
| `FRONTEND_URL` | `http://localhost:3000` | CORS origin |
| `GOOGLE_SHEETS_ENABLED` | `false` | Enables Google Sheets export |
| `GOOGLE_CREDENTIALS_PATH` | empty | Service-account JSON path |
| `GOOGLE_SHEET_ID` | empty | Target spreadsheet ID |
| `GOOGLE_SHEET_TAB_NAME` | `Leads` | Target tab |

Never commit `.env` files or service-account JSON. See `.gitignore`.

## API

| Method | Path |
| --- | --- |
| GET | `/health` |
| GET/POST | `/api/v1/business-profile/` |
| GET/PUT/DELETE | `/api/v1/business-profile/{id}` |
| GET/POST | `/api/v1/icp/` |
| GET/PUT/DELETE | `/api/v1/icp/{id}` |
| POST | `/api/v1/batches/` |
| GET | `/api/v1/batches/?workspace_slug=demo` |
| GET | `/api/v1/batches/{id}?workspace_slug=demo` |
| GET | `/api/v1/prospects/?workspace_slug=demo` |
| GET | `/api/v1/prospects/{id}?workspace_slug=demo` |
| GET | `/api/v1/exports/csv/{batch_id}?workspace_slug=demo` |
| GET | `/api/v1/exports/preview/{batch_id}?workspace_slug=demo` |
| POST | `/api/v1/exports/google-sheets/{batch_id}?workspace_slug=demo` |

All data access is scoped by `workspace_slug`; cross-workspace IDs return 404.

### Batch lifecycle

`pending → running → completed | failed`, with stage transitions:
`configured → discovering_companies → researching_companies →
discovering_decision_makers → enriching_contacts → identifying_problems →
matching_solutions → qualifying → completed`.

## Outreach CSV contract

The export is designed for the existing n8n Leads sheet. Column order is fixed:

```
lead_id, first_name, last_name, email, company, website, role, client_id, status, draft_date, notes
```

- `lead_id`: `PROSPECT-{uuid}` (stable, unique)
- `status`: always `new` for generated prospects
- `draft_date`: always empty
- `client_id`: workspace UUID
- `notes`: `Problem: … | Fit: … | Research: … | Missing: …`
- Missing values (for example an unavailable email) are left blank; they are never fabricated.

By default only prospects marked ready for outreach are exported. Pass
`include_all=true` to export every prospect in the batch.

## Data honesty

The demo provider produces **synthetic** companies, decision-makers, and
research. These records are labelled synthetic in the UI and in the generated
notes/confidence fields. No real emails are invented: unavailable addresses are
left blank and listed under missing information. Do not treat demo output as
verified company research.

## Tests and checks

```bash
cd backend && python -m pytest tests -q
cd frontend && npx tsc --noEmit
cd frontend && npx eslint .
cd frontend && npm run build
```

## Known limitations

- Google Sheets export is implemented against the official API but has **not**
  been tested against a live sheet or credentials.
- There is no authentication; workspace isolation is enforced by slug only.
- The OpenAI provider is optional and untested against a live key.
- Synthetic demo data is illustrative, not verified research.
