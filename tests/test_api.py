import os

os.environ["DATABASE_URL"] = "sqlite:///./test_capstone.db"

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_register_and_login() -> None:
    register = client.post(
        "/api/auth/register",
        json={"email": "user@example.com", "password": "password123", "name": "Test User"},
    )
    assert register.status_code == 200
    token = register.json()["token"]
    assert token

    login = client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "password123"},
    )
    assert login.status_code == 200
    assert login.json()["user"]["email"] == "user@example.com"


def test_project_and_summary_flow() -> None:
    token = client.post(
        "/api/auth/register",
        json={"email": "project@example.com", "password": "password123", "name": "Project User"},
    ).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    project = client.post(
        "/api/projects",
        json={"name": "Sprint Plan", "objective": "Build a prototype and validate the onboarding flow."},
        headers=headers,
    )
    assert project.status_code == 200
    project_id = project.json()["id"]

    task = client.post(
        "/api/tasks",
        json={"project_id": project_id, "title": "Finalize prototype", "status": "todo", "notes": "Test the first user flow."},
        headers=headers,
    )
    assert task.status_code == 200

    summary = client.get(f"/api/projects/{project_id}/summary", headers=headers)
    assert summary.status_code == 200
    assert summary.json()["project_name"] == "Sprint Plan"

    ai = client.post(
        "/api/insights/summary",
        json={"text": "We need to validate onboarding, reduce funnel friction, and move the launch plan forward with a stable demo path.", "project_id": project_id},
        headers=headers,
    )
    assert ai.status_code == 200
    assert "summary" in ai.json()
