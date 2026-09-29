import datetime
import uuid
from typing import Optional, List, Any
from pydantic import BaseModel, ConfigDict, Field
from app.models.policy import UserStatusType, StatusSource, PolicyDecision, DelegationSource
from app.models.contact import RelationshipType

class UserStatusBase(BaseModel):
    status: UserStatusType
    source: StatusSource
    starts_at: Optional[datetime.datetime] = None
    expires_at: Optional[datetime.datetime] = None

class UserStatusOut(UserStatusBase):
    id: uuid.UUID
    user_id: str
    created_at: datetime.datetime
    updated_at: datetime.datetime
    model_config = ConfigDict(from_attributes=True)

class DelegationRuleBase(BaseModel):
    relationship_type: RelationshipType
    action: PolicyDecision

class DelegationRuleOut(DelegationRuleBase):
    id: uuid.UUID
    delegation_id: uuid.UUID
    model_config = ConfigDict(from_attributes=True)

class DelegationBase(BaseModel):
    mode: UserStatusType
    active: bool = True
    starts_at: Optional[datetime.datetime] = None
    expires_at: Optional[datetime.datetime] = None
    source: DelegationSource

class DelegationCreate(DelegationBase):
    rules: List[DelegationRuleBase] = []

class DelegationOut(DelegationBase):
    id: uuid.UUID
    user_id: str
    rules: List[DelegationRuleOut] = []
    created_at: datetime.datetime
    updated_at: datetime.datetime
    model_config = ConfigDict(from_attributes=True)

class UserPreferenceBase(BaseModel):
    allow_family_answer: bool = True
    allow_friend_screening: bool = True
    allow_unknown_screening: bool = True
    allow_work_screening: bool = True
    allow_human_handoff: bool = True
    allow_urgent_notifications: bool = True

class UserPreferenceOut(UserPreferenceBase):
    id: uuid.UUID
    user_id: str
    model_config = ConfigDict(from_attributes=True)

class ContactPolicyRuleBase(BaseModel):
    contact_id: uuid.UUID
    action: PolicyDecision
    conditions: Optional[Any] = None

class ContactPolicyRuleOut(ContactPolicyRuleBase):
    id: uuid.UUID
    user_id: str
    model_config = ConfigDict(from_attributes=True)

class PolicyEvaluationRequest(BaseModel):
    contact_id: Optional[uuid.UUID] = None
    relationship: str
    relationship_status: str
    urgency: str = "NORMAL"
    call_id: str

class PolicyEvaluationResponse(BaseModel):
    decision: PolicyDecision
    reason: str
    policy_source: str
    requires_notification: bool = False
