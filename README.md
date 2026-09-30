# FocusFlow AI

FocusFlow AI is a backend service for small teams that need to turn scattered notes and project updates into a clean weekly plan, AI-generated insights, and downloadable PDF summaries.

## 10x claim
A founder or team lead can turn a rough pile of project notes into a usable weekly summary in minutes instead of hours.

## Concepts implemented

| Concept | Where it lives |
| --- | --- |
| API endpoints | `app/main.py` |
| Database | `app/database.py` |
| Authentication | `app/main.py` (`/api/auth/*`) |
| Background jobs | `app/main.py` (`start_scheduler`) |
| Reporting (PDF) | `app/main.py` (`generate_pdf_report`) |
| Caching logic | `app/main.py` (`project_summary_cache`) |
| LLM integration | `app/main.py` (`/api/insights/summary`) |

## Run it locally

1. Create a virtual environment and install dependencies:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Optional: copy the env template and set your secret:

   ```bash
   cp .env.example .env
   ```

3. Seed demo data:

   ```bash
   python scripts/seed_demo.py
   ```

4. Start the API:

   ```bash
   uvicorn app.main:app --reload
   ```

5. Open:
   - Swagger UI: http://localhost:8000/docs
   - Health check: http://localhost:8000/health

## 5-minute demo path

1. Register a user via `POST /api/auth/register` with an email and password.
2. Create a project via `POST /api/projects`.
3. Add a few tasks via `POST /api/tasks`.
4. Fetch the project summary via `GET /api/projects/{project_id}/summary`.
5. Trigger an AI summary with `POST /api/insights/summary`.
6. Generate a report with `POST /api/reports/weekly` and download the PDF from `GET /api/reports/{report_id}/download`.

## Demo account

A seeded demo account is created automatically when the database is empty:

- Email: `demo@focusflow.dev`
- Password: `demo123`

## Notes

- The app uses SQLite for persistence and stores the database in `capstone.db`.
- AI responses work without an API key using a local fallback; set `OPENAI_API_KEY` in `.env` to enable live model calls.
- No secrets are committed to Git.

## Future ideas

- Add drag-and-drop task boards.
- Connect email delivery for generated reports.
- Support multiple workspaces and team members.
# FlyRank_Capstone
