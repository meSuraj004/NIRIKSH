from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.api.routes import auth, inspections, products, reports, rules


def seed_rules() -> None:
    from app.compliance.repository import JSONRuleRepository
    from app.models import Rule

    db = SessionLocal()
    try:
        rulebook = JSONRuleRepository().load_rulebook()
        for definition in rulebook.rules:
            existing = db.query(Rule).filter(Rule.rule_id == definition.rule_id).first()
            if existing:
                continue
            db.add(Rule(
                rule_id=definition.rule_id,
                title=definition.rule_title,
                section_reference=definition.section_reference,
                parameter=definition.parameter,
                description=definition.description,
                mandatory=definition.mandatory,
                rulebook_version=rulebook.version,
                definition=definition.model_dump(),
            ))
        db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    seed_rules()
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth.router)
app.include_router(inspections.router)
app.include_router(products.router)
app.include_router(rules.router)
app.include_router(reports.router)


@app.get("/api/health", tags=["system"])
def health():
    return {"status": "ok", "environment": settings.app_env}
