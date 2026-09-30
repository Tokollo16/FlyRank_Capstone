import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import jwt
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from openai import OpenAI
from pydantic import BaseModel, Field
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from app.database import Base, CostLog, Project, Report, SessionLocal, Task, User, get_db, hash_password, verify_password

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-me")
REPORT_DIR = Path("reports")
REPORT_DIR.mkdir(exist_ok=True)

project_summary_cache: dict[str, tuple[datetime, dict[str, Any]]] = {}


def create_app() -> FastAPI:
    app = FastAPI(title="FocusFlow AI", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    return app


app = create_app()


class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=6)
    name: str = Field(..., min_length=2)


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=6)


class CreateProjectRequest(BaseModel):
    name: str = Field(..., min_length=2)
    objective: str = Field(..., min_length=10)
    status: str = "active"


class CreateTaskRequest(BaseModel):
    project_id: int
    title: str = Field(..., min_length=2)
    status: str = "todo"
    due_date: str | None = None
    notes: str = ""


class SummaryRequest(BaseModel):
    text: str = Field(..., min_length=20)
    project_id: int | None = None


class WeeklyReportRequest(BaseModel):
    project_id: int
    title: str = "Weekly Focus Summary"


def create_token(user: User) -> str:
    payload = {"sub": user.email, "user_id": user.id, "exp": datetime.utcnow() + timedelta(hours=8)}
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def get_current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    user = db.query(User).filter(User.id == int(payload["user_id"])).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown user")
    return user


def add_cost_log(db: Session, user_id: int, operation: str, cost_usd: float, prompt_tokens: int = 0, completion_tokens: int = 0) -> None:
    log = CostLog(
        user_id=user_id,
        operation=operation,
        cost_usd=cost_usd,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
    db.add(log)
    db.commit()


def build_fallback_summary(text: str) -> str:
    sentences = [part.strip() for part in text.split(".") if part.strip()]
    top_points = "\n".join(f"- {sentence[:90]}" for sentence in sentences[:3])
    return (
        "Priority summary:\n"
        f"{top_points}\n\n"
        "Recommended action: break the work into the next three moves, finish the highest-impact task first, and review the blocker before the next check-in."
    )


def generate_ai_summary(text: str, user: User, db: Session) -> tuple[str, float, int, int]:
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        try:
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a concise project coach. Summarize the provided notes into 3 bullet points and one recommended next action."},
                    {"role": "user", "content": text},
                ],
                temperature=0.2,
            )
            summary = response.choices[0].message.content or "No summary generated"
            prompt_tokens = getattr(response.usage, "prompt_tokens", 0) or 0
            completion_tokens = getattr(response.usage, "completion_tokens", 0) or 0
            cost_usd = round((prompt_tokens * 0.00015) + (completion_tokens * 0.0006), 6)
            add_cost_log(db, user.id, "llm_summary", cost_usd, prompt_tokens, completion_tokens)
            return summary, cost_usd, prompt_tokens, completion_tokens
        except Exception:
            pass

    summary = build_fallback_summary(text)
    add_cost_log(db, user.id, "llm_summary_fallback", 0.0, 0, 0)
    return summary, 0.0, 0, 0


def get_project_summary(db: Session, project_id: int) -> dict[str, Any]:
    cache_key = f"project:{project_id}:summary"
    now = datetime.utcnow()
    cached = project_summary_cache.get(cache_key)
    if cached and now - cached[0] < timedelta(minutes=5):
        return cached[1]

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    tasks = db.query(Task).filter(Task.project_id == project_id).all()
    completed = sum(1 for task in tasks if task.status.lower() == "done")
    active = sum(1 for task in tasks if task.status.lower() in {"in_progress", "todo"})
    summary = {
        "project_name": project.name,
        "objective": project.objective,
        "status": project.status,
        "total_tasks": len(tasks),
        "completed": completed,
        "active": active,
        "next_steps": [task.title for task in tasks[:3]],
    }
    project_summary_cache[cache_key] = (now, summary)
    return summary


def generate_pdf_report(db: Session, user: User, project_id: int, title: str) -> Report:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    tasks = db.query(Task).filter(Task.project_id == project_id).all()
    summary_text = "\n".join(f"- {task.title} ({task.status})" for task in tasks) or "- No tasks recorded"
    filename = f"report_{project_id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.pdf"
    path = REPORT_DIR / filename

    doc = SimpleDocTemplate(str(path), pagesize=letter, title=title)
    story = []
    story.append(Paragraph(title, style={"fontName": "Helvetica-Bold", "fontSize": 18}))
    story.append(Spacer(1, 12))
    story.append(Paragraph(f"Project: {project.name}", style={"fontName": "Helvetica", "fontSize": 12}))
    story.append(Paragraph(f"Objective: {project.objective}", style={"fontName": "Helvetica", "fontSize": 12}))
    story.append(Spacer(1, 12))
    table_data = [["Task", "Status"], *[(task.title, task.status) for task in tasks]]
    table = Table(table_data)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f7a7a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 1, colors.grey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.beige]),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 12))
    story.append(Paragraph("Summary", style={"fontName": "Helvetica-Bold", "fontSize": 14}))
    story.append(Paragraph(summary_text, style={"fontName": "Helvetica", "fontSize": 10}))
    doc.build(story)

    record = Report(
        user_id=user.id,
        title=title,
        summary=summary_text,
        file_name=filename,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def maybe_seed_demo_data() -> None:
    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            user = User(
                email="demo@focusflow.dev",
                name="Demo User",
                password_hash=hash_password("demo123"),
            )
            db.add(user)
            db.commit()
            db.refresh(user)

            project = Project(
                name="Launch Sprint",
                objective="Ship the first version of the product and validate the onboarding flow.",
                status="active",
                user_id=user.id,
            )
            db.add(project)
            db.commit()
            db.refresh(project)

            tasks = [
                Task(project_id=project.id, title="Draft onboarding flow", status="done", notes="Three-step checklist completed."),
                Task(project_id=project.id, title="Prepare analytics dashboard", status="in_progress", notes="Review metrics needed for launch."),
                Task(project_id=project.id, title="Create launch email", status="todo", notes="Reach out to early testers."),
            ]
            db.add_all(tasks)
            db.commit()
    finally:
        db.close()


scheduler = BackgroundScheduler(daemon=True)


def scheduled_digest() -> None:
    print(f"[background] Running digest at {datetime.utcnow().isoformat()} - project health check")


@app.on_event("startup")
def startup_event() -> None:
    Base.metadata.create_all(bind=SessionLocal.kw["bind"])  # type: ignore[attr-defined]
    maybe_seed_demo_data()
    scheduler.add_job(scheduled_digest, "interval", minutes=60)
    scheduler.start()


@app.on_event("shutdown")
def shutdown_event() -> None:
    scheduler.shutdown()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/auth/register")
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    if db.query(User).filter(User.email == payload.email.lower()).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already exists")

    user = User(email=payload.email.lower(), name=payload.name, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"token": create_token(user), "user": {"id": user.id, "email": user.email, "name": user.name}}


@app.post("/api/auth/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    return {"token": create_token(user), "user": {"id": user.id, "email": user.email, "name": user.name}}


@app.get("/api/projects")
def list_projects(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    projects = db.query(Project).filter(Project.user_id == current_user.id).order_by(Project.created_at.desc()).all()
    return [{"id": project.id, "name": project.name, "objective": project.objective, "status": project.status} for project in projects]


@app.post("/api/projects")
def create_project(payload: CreateProjectRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    project = Project(name=payload.name, objective=payload.objective, status=payload.status, user_id=current_user.id)
    db.add(project)
    db.commit()
    db.refresh(project)
    return {"id": project.id, "name": project.name, "objective": project.objective, "status": project.status}


@app.post("/api/tasks")
def create_task(payload: CreateTaskRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    project = db.query(Project).filter(Project.id == payload.project_id, Project.user_id == current_user.id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    task = Task(
        project_id=payload.project_id,
        title=payload.title,
        status=payload.status,
        due_date=payload.due_date,
        notes=payload.notes,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return {"id": task.id, "project_id": task.project_id, "title": task.title, "status": task.status, "due_date": task.due_date, "notes": task.notes}


@app.get("/api/projects/{project_id}/summary")
def fetch_project_summary(project_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == current_user.id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return get_project_summary(db, project_id)


@app.post("/api/insights/summary")
def insight_summary(payload: SummaryRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    if payload.project_id is not None:
        project = db.query(Project).filter(Project.id == payload.project_id, Project.user_id == current_user.id).first()
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    summary, cost_usd, prompt_tokens, completion_tokens = generate_ai_summary(payload.text, current_user, db)
    return {
        "summary": summary,
        "cost_usd": cost_usd,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
    }


@app.post("/api/reports/weekly")
def create_weekly_report(payload: WeeklyReportRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    report = generate_pdf_report(db, current_user, payload.project_id, payload.title)
    return {"report_id": report.id, "file_name": report.file_name, "title": report.title}


@app.get("/api/reports/{report_id}/download")
def download_report(report_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> FileResponse:
    report = db.query(Report).filter(Report.id == report_id, Report.user_id == current_user.id).first()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

    path = REPORT_DIR / report.file_name
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report file not found")

    return FileResponse(path, media_type="application/pdf", filename=report.file_name)
