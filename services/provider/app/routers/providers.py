from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from ..db import get_db
from .. import models, schemas

router = APIRouter(prefix="/providers", tags=["providers"])

@router.get("", response_model=List[schemas.ProviderOut])
def list_providers(db: Session = Depends(get_db)):
    rows = db.query(models.Provider).order_by(models.Provider.id.desc()).limit(50).all()
    return rows

@router.post("", response_model=schemas.ProviderOut, status_code=201)
def create_provider(payload: schemas.ProviderCreate, db: Session = Depends(get_db)):
    obj = models.Provider(**payload.dict())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj
