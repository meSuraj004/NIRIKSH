from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import require_any_role
from app.database import get_db
from app.models import Product
from app.schemas import ProductOut

router = APIRouter(prefix="/api/products", tags=["products"])


@router.get("", response_model=list[ProductOut])
def list_products(db: Session = Depends(get_db), _: object = Depends(require_any_role)):
    return db.query(Product).order_by(Product.created_at.desc()).limit(200).all()


@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db), _: object = Depends(require_any_role)):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product
