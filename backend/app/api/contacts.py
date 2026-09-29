import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.contact import Contact
from app.schemas.contact import ContactBase, ContactIdentityResponse, ContactOut
from app.services.contact import ContactIdentityService

router = APIRouter(prefix="/contacts", tags=["contacts"])

def get_current_user_id() -> str:
    # Dummy authentication for now, returning a static user UUID
    return "user_123"

@router.get("", response_model=list[ContactOut])
def list_contacts(db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)) -> list[Contact]:
    return db.query(Contact).filter(Contact.user_id == user_id).all()

@router.post("", response_model=ContactOut)
def create_contact(contact_in: ContactBase, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)) -> Contact:
    from app.core.utils import normalize_phone_number
    normalized = normalize_phone_number(contact_in.phone_number)
    
    # Check for duplicates
    existing = db.query(Contact).filter(Contact.user_id == user_id, Contact.phone_number == normalized).first()
    if existing:
        raise HTTPException(status_code=400, detail="Contact with this phone number already exists.")
        
    contact = Contact(
        user_id=user_id,
        phone_number=normalized,
        saved_name=contact_in.saved_name,
        real_name=contact_in.real_name,
        status=contact_in.status
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact

@router.get("/{id}", response_model=ContactOut)
def get_contact(id: str, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)) -> Contact:
    svc = ContactIdentityService(db, user_id)
    contact = svc.get_contact(uuid.UUID(id))
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    return contact

@router.get("/{id}/identity", response_model=ContactIdentityResponse)
def get_contact_identity(id: str, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)) -> ContactIdentityResponse:
    svc = ContactIdentityService(db, user_id)
    contact = svc.get_contact(uuid.UUID(id))
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    return svc.resolve_identity(str(contact.phone_number))
