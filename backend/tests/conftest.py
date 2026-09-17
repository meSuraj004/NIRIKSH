import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app

TestEngine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(bind=TestEngine, autoflush=False, expire_on_commit=False)
Base.metadata.create_all(bind=TestEngine)


def override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def signup_and_login(email: str) -> dict:
    client.post(
        "/api/auth/signup",
        json={"email": email, "full_name": "Test User", "password": "secure-pass-123"},
    )
    res = client.post("/api/auth/login", json={"email": email, "password": "secure-pass-123"})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}
