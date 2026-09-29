import uuid

from pydantic import BaseModel, ConfigDict

from app.models.contact import (
    AliasSource,
    ContactStatus,
    RelationshipType,
    SuggestionStatus,
)


class NamingConventionBase(BaseModel):
    token: str
    meaning: RelationshipType
    scope: str
    status: SuggestionStatus = SuggestionStatus.SUGGESTED
    created_by: AliasSource

class NamingConventionOut(NamingConventionBase):
    id: uuid.UUID
    user_id: str
    model_config = ConfigDict(from_attributes=True)

class RelationshipSuggestionBase(BaseModel):
    suggested_name: str | None = None
    suggested_relationship: RelationshipType
    confidence: float
    reason: str | None = None

class RelationshipSuggestionOut(RelationshipSuggestionBase):
    id: uuid.UUID
    contact_id: str
    status: SuggestionStatus
    actions: list[str] = ["CONFIRMED", "REJECTED", "UNKNOWN", "REMIND_LATER"]
    model_config = ConfigDict(from_attributes=True)

class ContactRelationshipBase(BaseModel):
    relationship_type: RelationshipType
    status: SuggestionStatus = SuggestionStatus.UNCONFIRMED
    confidence: float = 1.0
    source: AliasSource

class ContactRelationshipOut(ContactRelationshipBase):
    id: uuid.UUID
    contact_id: str
    model_config = ConfigDict(from_attributes=True)

class ContactAliasBase(BaseModel):
    alias: str
    alias_type: str
    source: AliasSource
    status: SuggestionStatus = SuggestionStatus.SUGGESTED

class ContactAliasOut(ContactAliasBase):
    id: uuid.UUID
    contact_id: str
    model_config = ConfigDict(from_attributes=True)

class ContactBase(BaseModel):
    phone_number: str
    saved_name: str | None = None
    real_name: str | None = None
    status: ContactStatus = ContactStatus.ACTIVE

class ContactOut(ContactBase):
    id: uuid.UUID
    user_id: str
    model_config = ConfigDict(from_attributes=True)

class ContactIdentityResponse(BaseModel):
    contact_id: str | None
    saved_name: str | None
    real_name: str | None
    aliases: list[str]
    relationship: str
    relationship_status: str
    confidence: float
    permissions: list[str] = []
