import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_user_id
from app.schemas.policy import UserPreferenceBase, UserPreferenceOut, ContactPolicyRuleBase, ContactPolicyRuleOut
from app.services.policy import PolicyEngine

router = APIRouter(tags=["Preferences"])

@router.get("/api/v1/preferences", response_model=UserPreferenceOut)
def get_preferences(db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    engine = PolicyEngine(db, user_id)
    return engine.get_preferences()

@router.post("/api/v1/preferences", response_model=UserPreferenceOut)
def update_preferences(pref_in: UserPreferenceBase, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    engine = PolicyEngine(db, user_id)
    pref = engine.get_preferences()
    for k, v in pref_in.model_dump().items():
        setattr(pref, k, v)
    db.commit()
    db.refresh(pref)
    return pref

@router.post("/api/v1/policies/evaluate")
def evaluate_policy(request: dict, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    from app.schemas.policy import PolicyEvaluationRequest
    engine = PolicyEngine(db, user_id)
    req = PolicyEvaluationRequest(**request)
    return engine.evaluate_call(req)

@router.post("/api/v1/policies/contact", response_model=ContactPolicyRuleOut)
def create_contact_policy(rule_in: ContactPolicyRuleBase, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    from app.models.policy import ContactPolicyRule
    rule = ContactPolicyRule(user_id=user_id, **rule_in.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule

