import enum

from sqlalchemy import Column, Float, ForeignKey, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class ContactStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    BLOCKED = "BLOCKED"

class AliasSource(str, enum.Enum):
    USER = "USER"
    CONTACT_SYNC = "CONTACT_SYNC"
    CALLER_IDENTIFICATION = "CALLER_IDENTIFICATION"
    CONVERSATION = "CONVERSATION"
    SYSTEM = "SYSTEM"

class SuggestionStatus(str, enum.Enum):
    CONFIRMED = "CONFIRMED"
    SUGGESTED = "SUGGESTED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"
    UNCONFIRMED = "UNCONFIRMED"

class RelationshipType(str, enum.Enum):
    MOTHER = "MOTHER"
    FATHER = "FATHER"
    PARENT = "PARENT"
    BROTHER = "BROTHER"
    SISTER = "SISTER"
    FAMILY = "FAMILY"
    RELATIVE = "RELATIVE"
    CLOSE_FRIEND = "CLOSE_FRIEND"
    FRIEND = "FRIEND"
    COLLEAGUE = "COLLEAGUE"
    MANAGER = "MANAGER"
    CLIENT = "CLIENT"
    RECRUITER = "RECRUITER"
    WORK = "WORK"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"

class Contact(BaseModel): 
    __tablename__ = "contacts"
    
    user_id = Column(String, index=True, nullable=False)
    phone_number = Column(String, index=True, nullable=False)
    saved_name = Column(String, nullable=True)
    real_name = Column(String, nullable=True)
    status = Column(SQLEnum(ContactStatus), default=ContactStatus.ACTIVE, nullable=False)
    
    aliases = relationship ("ContactAlias", back_populates="contact", cascade="all, delete-orphan")
    relationship_record = relationship ("ContactRelationship", uselist=False, back_populates="contact", cascade="all, delete-orphan")
    suggestions = relationship ("RelationshipSuggestion", back_populates="contact", cascade="all, delete-orphan")

class ContactAlias(BaseModel): 
    __tablename__ = "contact_aliases"
    
    contact_id = Column(ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False)
    alias = Column(String, nullable=False)
    alias_type = Column(String, nullable=False)
    source = Column(SQLEnum(AliasSource), nullable=False)
    status = Column(SQLEnum(SuggestionStatus), default=SuggestionStatus.SUGGESTED, nullable=False)
    
    contact = relationship ("Contact", back_populates="aliases")

class ContactRelationship(BaseModel): 
    __tablename__ = "contact_relationships"
    
    contact_id = Column(ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, unique=True)
    relationship_type = Column(SQLEnum(RelationshipType), nullable=False)
    status = Column(SQLEnum(SuggestionStatus), default=SuggestionStatus.UNCONFIRMED, nullable=False)
    confidence = Column(Float, default=1.0)
    source = Column(SQLEnum(AliasSource), nullable=False)
    
    contact = relationship ("Contact", back_populates="relationship_record")

class RelationshipSuggestion(BaseModel): 
    __tablename__ = "relationship_suggestions"
    
    contact_id = Column(ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False)
    suggested_name = Column(String, nullable=True)
    suggested_relationship = Column(SQLEnum(RelationshipType), nullable=False)
    confidence = Column(Float, default=0.0)
    reason = Column(String, nullable=True)
    status = Column(SQLEnum(SuggestionStatus), default=SuggestionStatus.SUGGESTED, nullable=False)
    
    contact = relationship ("Contact", back_populates="suggestions")

class NamingConvention(BaseModel): 
    __tablename__ = "naming_conventions"
    
    user_id = Column(String, index=True, nullable=False)
    token = Column(String, nullable=False)
    meaning = Column(SQLEnum(RelationshipType), nullable=False)
    scope = Column(String, nullable=False)
    status = Column(SQLEnum(SuggestionStatus), default=SuggestionStatus.SUGGESTED, nullable=False)
    created_by = Column(SQLEnum(AliasSource), nullable=False)
