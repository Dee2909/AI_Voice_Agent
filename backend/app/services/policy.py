import datetime
import uuid
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, or_

from app.models.policy import (
    UserStatus, UserStatusType, StatusSource,
    Delegation, DelegationRule, DelegationSource,
    UserPreference, ContactPolicyRule, PolicyDecision,
    PolicyAuditLog
)
from app.models.contact import RelationshipType
from app.schemas.policy import PolicyEvaluationRequest, PolicyEvaluationResponse

def now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)

class UserStatusService:
    def __init__(self, db: Session, user_id: str):
        self.db = db
        self.user_id = user_id

    def get_current_status(self) -> Optional[UserStatus]:
        now = now_utc()
        # Find active statuses that haven't expired
        statuses = self.db.scalars(
            select(UserStatus).where(
                and_(
                    UserStatus.user_id == self.user_id,
                    or_(UserStatus.expires_at == None, UserStatus.expires_at > now),
                    or_(UserStatus.starts_at == None, UserStatus.starts_at <= now)
                )
            ).order_by(
                # Priority mapping: EXPLICIT/MANUAL > DELEGATION > DEVICE > CALENDAR > INFERRED
                UserStatus.source
            )
        ).all()
        
        if not statuses:
            return None
            
        # Priority mapping
        priority = {
            StatusSource.MANUAL: 1,
            StatusSource.DELEGATION: 2,
            StatusSource.DEVICE: 3,
            StatusSource.CALENDAR: 4,
            StatusSource.INFERRED: 5,
            StatusSource.SYSTEM: 6,
        }
        
        return min(statuses, key=lambda s: priority.get(s.source, 99))

    def set_status(self, status: UserStatusType, source: StatusSource, expires_at: Optional[datetime.datetime] = None) -> UserStatus:
        # Clear existing manual if this is manual
        if source == StatusSource.MANUAL:
            self.clear_status(StatusSource.MANUAL)
            
        us = UserStatus(user_id=self.user_id, status=status, source=source, expires_at=expires_at)
        self.db.add(us)
        self.db.commit()
        self.db.refresh(us)
        return us

    def clear_status(self, source: Optional[StatusSource] = None) -> None:
        query = select(UserStatus).where(UserStatus.user_id == self.user_id)
        if source:
            query = query.where(UserStatus.source == source)
        for s in self.db.scalars(query).all():
            self.db.delete(s)
        self.db.commit()

class DelegationService:
    def __init__(self, db: Session, user_id: str):
        self.db = db
        self.user_id = user_id

    def get_active_delegation(self) -> Optional[Delegation]:
        now = now_utc()
        delegation = self.db.scalars(
            select(Delegation).where(
                and_(
                    Delegation.user_id == self.user_id,
                    Delegation.active == True,
                    or_(Delegation.expires_at == None, Delegation.expires_at > now),
                    or_(Delegation.starts_at == None, Delegation.starts_at <= now)
                )
            )
        ).first()
        return delegation

    def create_delegation(
        self, mode: UserStatusType, source: DelegationSource, expires_at: Optional[datetime.datetime], rules: List[Dict[str, Any]]
    ) -> Delegation:
        # Deactivate current active ones
        existing = self.db.scalars(select(Delegation).where(Delegation.user_id == self.user_id, Delegation.active == True)).all()
        for e in existing:
            e.active = False
        
        d = Delegation(user_id=self.user_id, mode=mode, source=source, expires_at=expires_at, active=True)
        self.db.add(d)
        self.db.flush()
        
        for r in rules:
            rule = DelegationRule(
                delegation_id=d.id,
                relationship_type=RelationshipType(r["relationship_type"]),
                action=PolicyDecision(r["action"])
            )
            self.db.add(rule)
            
        self.db.commit()
        self.db.refresh(d)
        
        # Also sync UserStatus
        status_svc = UserStatusService(self.db, self.user_id)
        status_svc.set_status(status=mode, source=StatusSource.DELEGATION, expires_at=expires_at)
        
        return d

    def cancel_delegation(self, delegation_id: uuid.UUID) -> bool:
        d = self.db.get(Delegation, delegation_id)
        if not d or d.user_id != self.user_id:
            return False
        d.active = False
        self.db.commit()
        
        # Clear delegation status
        status_svc = UserStatusService(self.db, self.user_id)
        status_svc.clear_status(StatusSource.DELEGATION)
        return True

class PolicyEngine:
    def __init__(self, db: Session, user_id: str):
        self.db = db
        self.user_id = user_id

    def get_preferences(self) -> UserPreference:
        pref = self.db.scalars(select(UserPreference).where(UserPreference.user_id == self.user_id)).first()
        if not pref:
            pref = UserPreference(user_id=self.user_id)
            self.db.add(pref)
            self.db.commit()
            self.db.refresh(pref)
        return pref

    def evaluate_call(self, request: PolicyEvaluationRequest) -> PolicyEvaluationResponse:
        status_svc = UserStatusService(self.db, self.user_id)
        delegation_svc = DelegationService(self.db, self.user_id)
        
        current_status_obj = status_svc.get_current_status()
        current_status = current_status_obj.status.value if current_status_obj else "AVAILABLE"
        
        active_delegation = delegation_svc.get_active_delegation()
        preferences = self.get_preferences()
        
        decision = PolicyDecision.SCREEN
        reason = "Default fallback"
        policy_source = "DEFAULT"
        
        # Priority 1: Emergency/Safety (hardcoded for now if URGENT flag is EMERGENCY)
        if request.urgency == "EMERGENCY":
            decision = PolicyDecision.NOTIFY
            reason = "Emergency override"
            policy_source = "SAFETY_CRITICAL"
            return self._log_and_return(request, current_status, decision, reason, policy_source)
        
        # Priority 2: Explicit contact rule
        if request.contact_id:
            contact_rule = self.db.scalars(
                select(ContactPolicyRule).where(
                    ContactPolicyRule.user_id == self.user_id,
                    ContactPolicyRule.contact_id == request.contact_id
                )
            ).first()
            
            if contact_rule:
                # check conditions
                conditions = contact_rule.conditions or {}
                status_condition = conditions.get("user_status", [])
                if not status_condition or current_status in status_condition:
                    return self._log_and_return(request, current_status, contact_rule.action, "Explicit user contact rule matched", "CONTACT_RULE")
                    
        # Priority 3: Active delegation rule
        if active_delegation:
            for rule in active_delegation.rules:
                if rule.relationship_type.value == request.relationship:
                    return self._log_and_return(request, current_status, rule.action, "Delegation rule matched", "DELEGATION_RULE")
                    
        # Priority 4: Global Preferences mapped to default behaviors based on Status
        rel = request.relationship
        
        if current_status == "AVAILABLE":
            if rel in ["MOTHER", "FATHER", "PARENT", "BROTHER", "SISTER", "FAMILY", "CLOSE_FRIEND", "FRIEND", "COLLEAGUE", "MANAGER", "CLIENT"]:
                decision = PolicyDecision.ANSWER
                reason = "User is available and relationship is known"
                policy_source = "DEFAULT_POLICY"
            else:
                decision = PolicyDecision.SCREEN if preferences.allow_unknown_screening else PolicyDecision.REJECT
                reason = "Unknown caller policy"
                policy_source = "GLOBAL_PREFERENCE"
                
        elif current_status in ["MEETING", "BUSY", "DRIVING", "DND"]:
            if rel in ["FAMILY", "MOTHER", "FATHER", "PARENT", "BROTHER", "SISTER"] and preferences.allow_family_answer:
                decision = PolicyDecision.ANSWER
                reason = "User allows family during busy statuses"
                policy_source = "GLOBAL_PREFERENCE"
            else:
                decision = PolicyDecision.SCREEN
                reason = f"User is {current_status}"
                policy_source = "DEFAULT_POLICY"
                
        else: # SLEEPING, AWAY
            if rel in ["FAMILY", "MOTHER", "FATHER", "PARENT", "BROTHER", "SISTER"] and preferences.allow_family_answer:
                decision = PolicyDecision.NOTIFY
                reason = "User allows family notifications when asleep/away"
                policy_source = "GLOBAL_PREFERENCE"
            else:
                decision = PolicyDecision.SCREEN
                reason = f"User is {current_status}"
                policy_source = "DEFAULT_POLICY"
                
        # Unknown Caller override
        if rel == "UNKNOWN":
            decision = PolicyDecision.SCREEN if preferences.allow_unknown_screening else PolicyDecision.REJECT
            reason = "Caller is unknown"
            policy_source = "GLOBAL_PREFERENCE"

        return self._log_and_return(request, current_status, decision, reason, policy_source)
        
    def _log_and_return(
        self, request: PolicyEvaluationRequest, status: str, decision: PolicyDecision, reason: str, source: str
    ) -> PolicyEvaluationResponse:
        log = PolicyAuditLog(
            event="CALL_POLICY_DECISION",
            call_id=request.call_id,
            user_id=self.user_id,
            contact_id=str(request.contact_id) if request.contact_id else None,
            relationship=request.relationship,
            user_status=status,
            decision=decision.value,
            policy_source=source
        )
        self.db.add(log)
        self.db.commit()
        
        return PolicyEvaluationResponse(
            decision=decision,
            reason=reason,
            policy_source=source,
            requires_notification=(decision == PolicyDecision.NOTIFY)
        )

