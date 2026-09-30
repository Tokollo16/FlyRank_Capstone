from app.database import SessionLocal, User, Project, Task, hash_password


def seed() -> None:
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
            print("Demo data created for demo@focusflow.dev / demo123")
        else:
            print("Demo data already exists.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
