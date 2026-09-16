import os
import sys
from unittest.mock import patch

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import User, UserRole


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


def _signup_and_login(email: str) -> dict:
    client.post(
        "/api/auth/signup",
        json={"email": email, "full_name": "Test Officer", "password": "secure-pass-123"},
    )
    res = client.post("/api/auth/login", json={"email": email, "password": "secure-pass-123"})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


class TestAuth:
    def test_signup_hashes_password(self):
        res = client.post(
            "/api/auth/signup",
            json={"email": "hash-test@example.com", "full_name": "H", "password": "secure-pass-123"},
        )
        assert res.status_code == 201
        db = TestSession()
        user = db.query(User).filter(User.email == "hash-test@example.com").first()
        assert user.hashed_password != "secure-pass-123"
        assert user.hashed_password.startswith("$2")
        db.close()

    def test_first_user_is_admin(self):
        res = client.post(
            "/api/auth/signup",
            json={"email": "admin-test@example.com", "full_name": "A", "password": "secure-pass-123"},
        )
        db = TestSession()
        user = db.query(User).filter(User.email == "admin-test@example.com").first()
        expected = UserRole.ADMIN if user.id == 1 else UserRole.OFFICER
        assert user.role == expected
        db.close()

    def test_login_rejects_wrong_password(self):
        res = client.post(
            "/api/auth/login",
            json={"email": "hash-test@example.com", "password": "wrong-password"},
        )
        assert res.status_code == 401

    def test_me_requires_token(self):
        assert client.get("/api/auth/me").status_code == 401

    def test_me_returns_user_without_hash(self):
        headers = _signup_and_login("me-test@example.com")
        res = client.get("/api/auth/me", headers=headers)
        assert res.status_code == 200
        body = res.json()
        assert body["email"] == "me-test@example.com"
        assert "hashed_password" not in body
        assert "password" not in body


class TestApiKeyHandling:
    def test_no_groq_key_configured_means_empty_pool(self):
        with patch.dict(os.environ, {"GROQ_API_KEYS": ""}, clear=False):
            from app.ai.ocr.key_manager import GroqKeyManager

            manager = GroqKeyManager()
            assert manager.keys == []

    def test_keys_loaded_from_settings(self):
        from app.ai.ocr.key_manager import GroqKeyManager
        from app.config import settings

        with patch.object(settings, "groq_api_keys", ["gsk_test_key_1234567890abcdefghijklmn"]):
            manager = GroqKeyManager()
            assert manager.keys == ["gsk_test_key_1234567890abcdefghijklmn"]

    def test_source_tree_contains_no_api_keys(self):
        root = os.path.dirname(BASE_DIR)
        offenders = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__", "node_modules", ".venv", "venv")]
            for name in filenames:
                if not name.endswith(".py"):
                    continue
                path = os.path.join(dirpath, name)
                content = open(path, encoding="utf-8", errors="ignore").read()
                if "gsk_" in content and "GROQ_API_KEYS" not in content:
                    offenders.append(path)
        assert offenders == [], f"Hard-coded Groq keys found in: {offenders}"


class TestDeclarationIntegrity:
    def test_missing_fields_stay_not_detected(self):
        from app.ai.pipeline.extraction import build_declarations

        aggregated = {
            "product_identity": {"brand_name": "Acme", "product_name": None},
            "pricing_and_quantity": {"mrp": None, "net_quantity": "500 ml"},
        }
        evidence = [{"view_index": 0, "text": "Acme product
Net Quantity 500 ml"}]
        rows = {r["field_name"]: r for r in build_declarations(aggregated, evidence)}

        assert rows["product_identity.brand_name"]["value"] == "Acme"
        assert rows["product_identity.brand_name"]["status"] == "DETECTED"
        assert rows["product_identity.brand_name"]["source_view"] == 0
        assert rows["product_identity.product_name"]["value"] is None
        assert rows["product_identity.product_name"]["status"] == "NOT_DETECTED"
        assert rows["pricing_and_quantity.mrp"]["value"] is None
        assert rows["pricing_and_quantity.mrp"]["status"] == "NOT_DETECTED"

    def test_undetected_mandatory_value_maps_to_review(self):
        from app.compliance.engine import RuleEngine
        from app.compliance.models import ComplianceStatus

        report = RuleEngine().evaluate({
            "session_id": "session_integrity_test",
            "product_identity": {"category": "Snacks"},
            "pricing_and_quantity": {"mrp": None},
            "dates_and_batch": {"mfg_date": None, "exp_date": None},
        })

        mrp = report.parameter_results["mrp"]
        assert mrp.status == ComplianceStatus.REVIEW
        assert mrp.extracted_raw_value is None
        assert report.summary.review_parameters >= 1


class TestInspectionFlow:
    def test_inspection_requires_auth(self):
        assert client.post("/api/inspections", json={}).status_code == 401

    def test_inspection_without_images_cannot_process(self):
        headers = _signup_and_login("process-test@example.com")
        res = client.post("/api/inspections", json={}, headers=headers)
        inspection_id = res.json()["id"]
        res = client.post(f"/api/inspections/{inspection_id}/process", headers=headers)
        assert res.status_code == 400

    def test_results_blocked_until_completed(self):
        headers = _signup_and_login("results-test@example.com")
        res = client.post("/api/inspections", json={}, headers=headers)
        inspection_id = res.json()["id"]
        res = client.get(f"/api/inspections/{inspection_id}/results", headers=headers)
        assert res.status_code == 409
