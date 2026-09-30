# My 10x Solution - Alex Morgan

## 1. Problem
Small teams often lose time when they have a stream of notes, tasks, and updates but no fast way to turn that information into a weekly summary, priority list, and downloadable report. A founder can spend hours rewriting project status by hand, which slows down product decisions and creates friction before the next sprint.

## 2. Solution
FocusFlow AI gives a team a simple backend where they can register, create projects, track tasks, fetch a cached project summary, generate an AI insight from notes, and export a PDF report. The app is designed to shorten the process of converting messy project signals into a clear, useable plan.

### Implemented concepts
- API endpoints: implemented in `app/main.py` for auth, projects, reports, and summaries.
- Database: SQLite persistence in `app/database.py` keeps users, projects, tasks, cost logs, and reports after a restart.
- Authentication: login and protected project endpoints use bearer-token auth.
- Background jobs: a scheduler runs a daily digest task in the background.
- Reporting: generates a PDF report file for a weekly summary.
- Caching logic: project summary results are cached for a short TTL to avoid recomputing expensive summaries.
- LLM integration: `POST /api/insights/summary` sends a narrow AI summary request with validation and cost logging.

### Swaps
- No swap used; all implemented concepts come from the first table in the brief.

## 3. How to run
1. Create a venv and install dependencies.
2. Copy `.env.example` to `.env` and set a secret key if desired.
3. Run `python scripts/seed_demo.py` to populate demo data.
4. Start the app with `uvicorn app.main:app --reload`.
5. Open the Swagger docs at `http://localhost:8000/docs`.

This solution is intentionally focused and can be built within a small timebox while still demonstrating the required backend concepts from the capstone brief.
