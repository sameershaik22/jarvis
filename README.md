# YoursBuddy AI — Jarvis-Like Autonomous Browser Research Agent

Browser-based AI research agent for discovering real estate podcasts on LinkedIn, evaluating video quality, identifying podcast hosts (excluding guests), verifying host companies, discovering business contact details (LinkedIn -> YouTube About -> Official Website -> Apollo fallback), storing evidence in Neon PostgreSQL, and exporting formatted Excel/CSV reports.

## Workspace Layout

```text
javis/
├── .env
├── backend/
│   ├── alembic/                 # Database migrations (Neon PostgreSQL compatible)
│   ├── app/
│   │   ├── api/v1/              # FastAPI REST & SSE endpoints
│   │   ├── db/                  # SQLAlchemy models & session management
│   │   ├── schemas/             # Pydantic request/response schemas
│   │   └── services/            # Playwright browser, OpenAI planner, research modules, Excel/CSV export
│   └── tests/                   # End-to-end & Playwright tests
├── frontend/                    # Next.js 15 + TypeScript + Tailwind CSS 8-page dashboard
└── scripts/                     # Startup helpers
```

## Setup

1. Open `.env` in `javis/` and fill in:
   - `DATABASE_URL` (your Neon PostgreSQL connection string, e.g. `postgresql://user:pass@ep-xxx.neon.tech/neondb?sslmode=require`)
   - `OPENAI_API_KEY`
   - `APOLLO_API_KEY` (optional fallback)
2. Run database migrations against Neon PostgreSQL:
   ```powershell
   cd backend
   python -m alembic upgrade head
   ```
3. Start the FastAPI backend:
   ```powershell
   .\scripts\start_backend.ps1
   ```
4. Install frontend packages and start the Next.js dashboard:
   ```powershell
   cd frontend
   npm install
   npm run dev
   ```
5. Open `http://localhost:3000`.

