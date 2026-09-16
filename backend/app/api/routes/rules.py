from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import require_any_role
from app.database import get_db
from app.models import Rule
from app.schemas import RuleOut

router = APIRouter(prefix="/api/rules", tags=["rules"])


@router.get("", response_model=list[RuleOut])
def list_rules(db: Session = Depends(get_db), _: object = Depends(require_any_role)):
    return db.query(Rule).order_by(Rule.id).all()
