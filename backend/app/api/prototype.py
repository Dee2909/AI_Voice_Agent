"""
Prototype API: Interactive dashboard, demo data seeder, and natural-language delegation parser.
Provides a complete, live-interactive UI for the Personal AI Call Agent.
"""

import datetime
import re
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.core.utils import normalize_phone_number
from app.models.call import (
    Call,
)
from app.models.contact import (
    AliasSource,
    Contact,
    ContactRelationship,
    NamingConvention,
    RelationshipSuggestion,
    RelationshipType,
    SuggestionStatus,
)
from app.models.memory import ConversationMemory
from app.models.notification import Notification
from app.models.policy import (
    DelegationSource,
    StatusSource,
    UserPreference,
    UserStatusType,
)
from app.services.policy import DelegationService, UserStatusService

router = APIRouter(tags=["prototype"])


class NLDelegationRequest(BaseModel):
    text: str = Field(..., description="Natural language delegation command")


@router.post("/api/v1/prototype/seed")
def seed_demo_data(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Pre-populates sample contacts, naming conventions, preferences, and status for instant testing."""
    # 1. User Preference
    pref = db.scalars(select(UserPreference).where(UserPreference.user_id == user_id)).first()
    if not pref:
        pref = UserPreference(
            user_id=user_id,
            allow_family_answer=True,
            allow_friend_screening=True,
            allow_unknown_screening=True,
            allow_work_screening=True,
            allow_human_handoff=True,
            allow_urgent_notifications=True,
        )
        db.add(pref)

    # 2. Default Status: MEETING
    status_svc = UserStatusService(db, user_id)
    status_svc.clear_status()
    status_svc.set_status(
        status=UserStatusType.MEETING,
        source=StatusSource.MANUAL,
        expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=2),
    )

    # 3. Naming Conventions (e.g. 'natpu' -> FRIEND)
    existing_nc = db.scalars(
        select(NamingConvention).where(NamingConvention.user_id == user_id, NamingConvention.token == "natpu")
    ).first()
    if not existing_nc:
        nc = NamingConvention(
            user_id=user_id,
            token="natpu",
            meaning=RelationshipType.FRIEND,
            scope="CONTACT_NAME",
            created_by=AliasSource.USER,
            status=SuggestionStatus.CONFIRMED,
        )
        db.add(nc)

    # 4. Sample Contacts
    contacts_data = [
        {
            "name": "Amma",
            "phone": "+919876543210",
            "rel": RelationshipType.MOTHER,
            "status": SuggestionStatus.CONFIRMED,
        },
        {
            "name": "Arun Natpu",
            "phone": "+918888888888",
            "rel": RelationshipType.FRIEND,
            "status": SuggestionStatus.CONFIRMED,
        },
        {
            "name": "Ravi Manager",
            "phone": "+917777777777",
            "rel": RelationshipType.MANAGER,
            "status": SuggestionStatus.CONFIRMED,
        },
    ]

    for cdata in contacts_data:
        normalized = normalize_phone_number(cdata["phone"])
        contact = db.scalars(
            select(Contact).where(Contact.user_id == user_id, Contact.phone_number == normalized)
        ).first()
        if not contact:
            contact = Contact(
                user_id=user_id,
                phone_number=normalized,
                saved_name=cdata["name"],
                status="ACTIVE",
            )
            db.add(contact)
            db.flush()

            rel = ContactRelationship(
                contact_id=contact.id,
                relationship_type=cdata["rel"],
                status=cdata["status"],
                confidence=1.0,
                source=AliasSource.USER,
            )
            db.add(rel)

    # 5. Delegation
    del_svc = DelegationService(db, user_id)
    rules = [
        {"relationship_type": "FRIEND", "action": "SCREEN"},
        {"relationship_type": "WORK", "action": "SCREEN"},
        {"relationship_type": "UNKNOWN", "action": "SCREEN"},
        {"relationship_type": "MOTHER", "action": "ANSWER"},
        {"relationship_type": "FAMILY", "action": "ANSWER"},
    ]
    del_svc.create_delegation(
        mode=UserStatusType.MEETING,
        source=DelegationSource.USER,
        expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=2),
        rules=rules,
    )

    db.commit()
    return {"status": "seeded", "message": "Demo contacts, preferences, status (MEETING) and delegation created."}


@router.get("/api/v1/prototype/state")
def get_prototype_state(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Returns aggregated live state of the agent for the UI."""
    status_svc = UserStatusService(db, user_id)
    cur_status = status_svc.get_current_status()

    del_svc = DelegationService(db, user_id)
    active_del = del_svc.get_active_delegation()

    contacts = db.scalars(select(Contact).where(Contact.user_id == user_id)).all()
    notifications = db.scalars(
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
        .limit(10)
    ).all()
    unread_count = db.query(Notification).filter(Notification.user_id == user_id, Notification.is_read == False).count()

    recent_calls = db.scalars(
        select(Call).where(Call.user_id == user_id).order_by(Call.started_at.desc()).limit(5)
    ).all()

    suggestions = db.scalars(
        select(RelationshipSuggestion)
        .join(Contact)
        .where(Contact.user_id == user_id, RelationshipSuggestion.status == SuggestionStatus.SUGGESTED)
    ).all()

    memories = db.scalars(
        select(ConversationMemory).where(ConversationMemory.user_id == user_id).order_by(ConversationMemory.created_at.desc()).limit(10)
    ).all()

    return {
        "user_id": user_id,
        "status": cur_status.status.value if cur_status else "AVAILABLE",
        "status_source": cur_status.source.value if cur_status else "DEFAULT",
        "status_expires_at": cur_status.expires_at.isoformat() if cur_status and cur_status.expires_at else None,
        "delegation": {
            "active": active_del is not None,
            "mode": active_del.mode.value if active_del else None,
            "expires_at": active_del.expires_at.isoformat() if active_del and active_del.expires_at else None,
        },
        "contacts_count": len(contacts),
        "contacts": [
            {
                "id": str(c.id),
                "name": c.saved_name or c.real_name or "Unknown",
                "phone": c.phone_number,
            }
            for c in contacts
        ],
        "unread_notifications": unread_count,
        "notifications": [
            {
                "id": str(n.id),
                "title": n.title,
                "body": n.body,
                "urgency": n.urgency.value,
                "type": n.notification_type.value,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in notifications
        ],
        "recent_calls": [
            {
                "id": str(c.id),
                "phone": c.caller_phone,
                "status": c.status.value,
                "started_at": c.started_at.isoformat() if c.started_at else None,
                "duration": c.duration_seconds,
            }
            for c in recent_calls
        ],
        "suggestions": [
            {
                "id": str(s.id),
                "name": s.suggested_name,
                "relationship": s.suggested_relationship.value,
                "reason": s.reason,
            }
            for s in suggestions
        ],
        "memories": [
            {
                "id": str(m.id),
                "category": m.fact_key,
                "content": m.fact_value,
                "confidence": m.confidence,
            }
            for m in memories
        ],
    }


@router.post("/api/v1/prototype/parse-delegation")
def parse_natural_language_delegation(
    req: NLDelegationRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """
    Parses natural language delegation in Tamil/Tanglish/English:
    e.g. 'Naan meeting-la irukken. 6 mani varaikum en calls pathuko'
    e.g. 'Don't disturb me for 2 hours'
    e.g. 'Driving mode, handle my calls'
    """
    text = req.text.lower()
    mode = UserStatusType.MEETING
    expires_at = None
    now = datetime.datetime.now(datetime.UTC)

    # 1. Determine Status Mode
    if any(k in text for k in ("meeting", "conference", "discussion")):
        mode = UserStatusType.MEETING
    elif any(k in text for k in ("driving", "drive", "travel", "vandi")):
        mode = UserStatusType.DRIVING
    elif any(k in text for k in ("sleep", "sleeping", "thoonga", "rest")):
        mode = UserStatusType.SLEEPING
    elif any(k in text for k in ("dnd", "disturb", "busy", "disturb pannadha")):
        mode = UserStatusType.DND
    elif any(k in text for k in ("away", "out", "veliya")):
        mode = UserStatusType.AWAY

    # 2. Extract Duration / Expiration
    hours_match = re.search(r"(\d+)\s*(?:hours|hour|hr|hrs|mani neram)", text)
    time_match = re.search(r"(\d+)\s*(?:pm|am|mani)", text)
    until_match = re.search(r"until\s*(\d+)", text)

    if hours_match:
        hrs = int(hours_match.group(1))
        expires_at = now + datetime.timedelta(hours=hrs)
    elif time_match:
        target_hour = int(time_match.group(1))
        if "pm" in text or target_hour <= 12:
            target_hour = target_hour if target_hour > 12 else target_hour + 12
        expires_at = now.replace(hour=min(23, target_hour), minute=0, second=0)
        if expires_at <= now:
            expires_at += datetime.timedelta(days=1)
    elif until_match:
        target_hour = int(until_match.group(1))
        expires_at = now + datetime.timedelta(hours=target_hour)
    else:
        # Default 2 hours if not specified
        expires_at = now + datetime.timedelta(hours=2)

    # 3. Create Delegation & Status
    del_svc = DelegationService(db, user_id)
    rules = [
        {"relationship_type": "FRIEND", "action": "SCREEN"},
        {"relationship_type": "WORK", "action": "SCREEN"},
        {"relationship_type": "UNKNOWN", "action": "SCREEN"},
        {"relationship_type": "MOTHER", "action": "ANSWER"},
        {"relationship_type": "FAMILY", "action": "ANSWER"},
    ]
    delegation = del_svc.create_delegation(
        mode=mode,
        source=DelegationSource.USER,
        expires_at=expires_at,
        rules=rules,
    )

    return {
        "status": "applied",
        "mode": mode.value,
        "expires_at": expires_at.isoformat(),
        "parsed_command": req.text,
        "delegation_id": str(delegation.id),
        "message": f"Delegation activated: Mode={mode.value} until {expires_at.strftime('%I:%M %p')}",
    }


@router.get("/", response_class=HTMLResponse)
@router.get("/prototype", response_class=HTMLResponse)
def get_prototype_ui() -> str:
    """Returns the single-page interactive prototype UI dashboard."""
    return """<!DOCTYPE html>
<html lang="en" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Personal AI Call Agent — Live Prototype</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <script>
        tailwind.config = {
            darkMode: 'class',
            theme: {
                extend: {
                    colors: {
                        brand: { 50: '#f0fdf4', 500: '#22c55e', 600: '#16a34a', 700: '#15803d' },
                        surface: { 800: '#1e293b', 900: '#0f172a', 950: '#020617' }
                    }
                }
            }
        }
    </script>
    <style>
        .pulse-live { animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: .5; } }
        .custom-scroll::-webkit-scrollbar { width: 6px; height: 6px; }
        .custom-scroll::-webkit-scrollbar-thumb { background: #334155; border-radius: 4px; }
    </style>
</head>
<body class="bg-surface-950 text-slate-100 font-sans min-h-screen flex flex-col">

    <!-- Top Header -->
    <header class="border-b border-slate-800 bg-surface-900/90 backdrop-blur sticky top-0 z-50 px-6 py-3 flex items-center justify-between">
        <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-emerald-500 to-cyan-500 flex items-center justify-center shadow-lg shadow-emerald-500/20">
                <i class="fa-solid fa-headset text-white text-lg"></i>
            </div>
            <div>
                <h1 class="font-bold text-lg leading-tight flex items-center gap-2">
                    Personal AI Call Agent
                    <span class="text-xs px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 font-semibold">Live Prototype</span>
                </h1>
                <p class="text-xs text-slate-400">Tamil · Tanglish · English Multilingual Voice Orchestrator</p>
            </div>
        </div>

        <div class="flex items-center gap-4">
            <!-- User Status Indicator -->
            <div class="flex items-center gap-2 bg-surface-800 border border-slate-700 px-3 py-1.5 rounded-lg">
                <span id="header-status-dot" class="w-2.5 h-2.5 rounded-full bg-amber-400"></span>
                <span class="text-xs text-slate-400">Status:</span>
                <span id="header-status-text" class="text-xs font-bold text-amber-400 uppercase">MEETING</span>
            </div>

            <!-- Seed Demo Data Button -->
            <button onclick="seedDemoData()" class="text-xs bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 px-3 py-1.5 rounded-lg flex items-center gap-1.5 transition">
                <i class="fa-solid fa-database text-emerald-400"></i> Seed Demo Data
            </button>

            <!-- Notification Bell -->
            <button onclick="toggleNotifications()" class="relative p-2 bg-surface-800 hover:bg-surface-700 rounded-lg border border-slate-700 text-slate-300">
                <i class="fa-solid fa-bell"></i>
                <span id="notif-badge" class="hidden absolute -top-1 -right-1 bg-red-500 text-white text-[10px] w-4 h-4 rounded-full flex items-center justify-center font-bold">0</span>
            </button>
        </div>
    </header>

    <!-- Main Workspace Grid -->
    <main class="flex-1 p-6 grid grid-cols-1 lg:grid-cols-12 gap-6 max-w-7xl mx-auto w-full">

        <!-- LEFT COLUMN: Live Call Phone Simulator (5 Cols) -->
        <div class="lg:col-span-5 flex flex-col gap-6">

            <!-- Virtual Smartphone Dial & Call Simulator -->
            <div class="bg-surface-900 border border-slate-800 rounded-2xl p-5 shadow-2xl flex flex-col justify-between relative overflow-hidden">
                <div class="absolute -right-20 -top-20 w-48 h-48 bg-emerald-500/10 rounded-full blur-3xl pointer-events-none"></div>

                <div>
                    <div class="flex items-center justify-between mb-4">
                        <h2 class="font-bold text-sm text-slate-300 flex items-center gap-2">
                            <i class="fa-solid fa-mobile-screen text-emerald-400"></i> Incoming Call Simulator
                        </h2>
                        <span id="call-state-pill" class="text-xs px-2.5 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700 font-medium">Idle</span>
                    </div>

                    <!-- Preset Callers -->
                    <div class="mb-4">
                        <label class="text-xs text-slate-400 font-medium block mb-2">Simulate Caller Presets:</label>
                        <div class="grid grid-cols-2 gap-2">
                            <button onclick="selectCaller('Amma', '+919876543210', 'MOTHER')" class="text-left p-2.5 rounded-xl bg-surface-800 hover:bg-slate-700/60 border border-slate-700 text-xs transition">
                                <div class="font-bold text-emerald-400">👩 Amma</div>
                                <div class="text-[11px] text-slate-400">+91 98765 43210 (Family)</div>
                            </button>
                            <button onclick="selectCaller('Arun Natpu', '+918888888888', 'FRIEND')" class="text-left p-2.5 rounded-xl bg-surface-800 hover:bg-slate-700/60 border border-slate-700 text-xs transition">
                                <div class="font-bold text-cyan-400">🤝 Arun Natpu</div>
                                <div class="text-[11px] text-slate-400">+91 88888 88888 (Friend)</div>
                            </button>
                            <button onclick="selectCaller('Ravi Manager', '+917777777777', 'MANAGER')" class="text-left p-2.5 rounded-xl bg-surface-800 hover:bg-slate-700/60 border border-slate-700 text-xs transition">
                                <div class="font-bold text-purple-400">💼 Ravi Manager</div>
                                <div class="text-[11px] text-slate-400">+91 77777 77777 (Work)</div>
                            </button>
                            <button onclick="selectCaller('Unknown Caller', '+919123456789', 'UNKNOWN')" class="text-left p-2.5 rounded-xl bg-surface-800 hover:bg-slate-700/60 border border-slate-700 text-xs transition">
                                <div class="font-bold text-amber-400">❓ Unknown Caller</div>
                                <div class="text-[11px] text-slate-400">+91 91234 56789 (Stranger)</div>
                            </button>
                        </div>
                    </div>

                    <!-- Phone Input & Dial -->
                    <div class="flex gap-2 mb-4">
                        <input id="caller-input" type="text" value="+918888888888" placeholder="+91..." class="flex-1 bg-surface-950 border border-slate-700 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500 font-mono" />
                        <button id="btn-dial" onclick="startCall()" class="bg-emerald-600 hover:bg-emerald-500 text-white font-bold px-4 py-2 rounded-xl text-xs flex items-center gap-1.5 shadow-lg shadow-emerald-600/30 transition">
                            <i class="fa-solid fa-phone"></i> Dial Call
                        </button>
                    </div>

                    <!-- Active Call Card -->
                    <div id="active-call-panel" class="hidden border border-slate-700 rounded-xl p-4 bg-surface-950/80 mb-4">
                        <div class="flex items-center justify-between mb-3">
                            <div class="flex items-center gap-2.5">
                                <div class="w-8 h-8 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center justify-center text-xs font-bold">
                                    <i class="fa-solid fa-phone-volume"></i>
                                </div>
                                <div>
                                    <div id="active-caller-name" class="text-xs font-bold text-white">Caller Name</div>
                                    <div id="active-caller-phone" class="text-[10px] text-slate-400 font-mono">+91...</div>
                                </div>
                            </div>
                            <span id="active-policy-decision" class="text-[11px] px-2 py-0.5 rounded font-bold uppercase bg-cyan-500/20 text-cyan-400 border border-cyan-500/30">SCREEN</span>
                        </div>

                        <!-- Policy Reason Note -->
                        <div class="bg-slate-900 p-2 rounded text-[11px] text-slate-300 mb-3 border border-slate-800 flex items-start gap-1.5">
                            <i class="fa-solid fa-shield-halved text-emerald-400 mt-0.5"></i>
                            <span id="policy-reason-text">Policy evaluated.</span>
                        </div>

                        <!-- Live Action Controls during Call -->
                        <div class="flex gap-2">
                            <button id="btn-takeover" onclick="humanTakeover()" class="flex-1 bg-amber-600/20 hover:bg-amber-600/30 text-amber-400 border border-amber-500/40 text-xs font-bold py-2 rounded-lg flex items-center justify-center gap-1.5 transition">
                                <i class="fa-solid fa-hand"></i> Take Over Call
                            </button>
                            <button onclick="endCall()" class="flex-1 bg-red-600 hover:bg-red-500 text-white text-xs font-bold py-2 rounded-lg flex items-center justify-center gap-1.5 shadow-lg shadow-red-600/30 transition">
                                <i class="fa-solid fa-phone-slash"></i> End Call
                            </button>
                        </div>
                    </div>
                </div>

                <!-- Live Transcript Stream Area -->
                <div class="flex flex-col h-64 border border-slate-800 bg-surface-950 rounded-xl overflow-hidden">
                    <div class="bg-slate-900/80 px-3 py-2 border-b border-slate-800 text-[11px] font-bold text-slate-400 flex items-center justify-between">
                        <span><i class="fa-solid fa-comment-dots text-emerald-400 mr-1.5"></i> Live Conversation Transcript</span>
                        <span id="tts-indicator" class="hidden text-xs text-emerald-400 flex items-center gap-1"><i class="fa-solid fa-volume-high pulse-live"></i> Speaking</span>
                    </div>

                    <div id="transcript-list" class="flex-1 p-3 overflow-y-auto custom-scroll flex flex-col gap-2.5 text-xs">
                        <div class="text-center text-slate-500 my-auto text-[11px]">No active call. Dial a preset above to begin.</div>
                    </div>

                    <!-- Caller Speech Input Box (Mic + Text) -->
                    <div class="p-2 border-t border-slate-800 bg-surface-900 flex items-center gap-2">
                        <button id="btn-mic" onclick="toggleVoiceRecognition()" class="w-9 h-9 rounded-lg bg-surface-800 hover:bg-slate-700 text-slate-300 flex items-center justify-center border border-slate-700 transition" title="Hold/Click to Speak">
                            <i class="fa-solid fa-microphone"></i>
                        </button>
                        <input id="caller-msg-input" type="text" placeholder="Type caller speech or use mic..." onkeydown="if(event.key==='Enter') sendCallerTurn()" class="flex-1 bg-surface-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:border-emerald-500" />
                        <button onclick="sendCallerTurn()" class="bg-emerald-600 hover:bg-emerald-500 text-white text-xs px-3 py-1.5 rounded-lg font-bold transition">
                            <i class="fa-solid fa-paper-plane"></i>
                        </button>
                    </div>
                </div>

                <!-- Quick Tanglish & Tamil Caller Speech Prompts -->
                <div class="mt-3 flex flex-wrap gap-1.5">
                    <span class="text-[10px] text-slate-500 self-center">Quick speech:</span>
                    <button onclick="insertAndSend('Deenan irukkana? Naan meeting pathi pesa vandhen.')" class="text-[10px] bg-surface-800 hover:bg-slate-700 border border-slate-700 px-2 py-1 rounded text-slate-300">
                        "Deenan irukkana?"
                    </button>
                    <button onclick="insertAndSend('Production server down! Urgent-ah call panna sollunga!')" class="text-[10px] bg-red-950/40 hover:bg-red-900/40 border border-red-800/40 px-2 py-1 rounded text-red-300">
                        🚨 "Production issue!"
                    </button>
                    <button onclick="insertAndSend('Free aana thirumba call panna sollunga.')" class="text-[10px] bg-surface-800 hover:bg-slate-700 border border-slate-700 px-2 py-1 rounded text-slate-300">
                        "Call back later"
                    </button>
                    <button onclick="insertAndSend('Naan Karthik pesuren, avaroda friend.')" class="text-[10px] bg-surface-800 hover:bg-slate-700 border border-slate-700 px-2 py-1 rounded text-slate-300">
                        "Naan Karthik pesuren"
                    </button>
                </div>
            </div>

            <!-- Status & Natural Language Delegation Box -->
            <div class="bg-surface-900 border border-slate-800 rounded-2xl p-5 shadow-xl">
                <h2 class="font-bold text-sm text-slate-300 mb-3 flex items-center gap-2">
                    <i class="fa-solid fa-wand-magic-sparkles text-cyan-400"></i> Natural Language Delegation
                </h2>
                <p class="text-xs text-slate-400 mb-3">Speak or type your status in Tanglish/English (e.g. <i>"Naan meeting-la irukken. 6 mani varaikum calls pathuko"</i>):</p>
                <div class="flex gap-2 mb-3">
                    <input id="nl-delegation-input" type="text" placeholder="e.g. Naan meeting-la irukken, 2 hours disturb pannadha" class="flex-1 bg-surface-950 border border-slate-700 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-cyan-500" />
                    <button onclick="applyNLDelegation()" class="bg-cyan-600 hover:bg-cyan-500 text-white font-bold px-3 py-2 rounded-xl text-xs flex items-center gap-1 transition">
                        <i class="fa-solid fa-arrow-right"></i> Apply
                    </button>
                </div>

                <!-- Quick Status Switcher Chips -->
                <div class="flex flex-wrap gap-1.5">
                    <button onclick="setStatus('AVAILABLE')" class="text-xs px-2.5 py-1 rounded-lg bg-emerald-950/50 hover:bg-emerald-900/50 border border-emerald-800 text-emerald-400 font-medium">AVAILABLE</button>
                    <button onclick="setStatus('MEETING')" class="text-xs px-2.5 py-1 rounded-lg bg-amber-950/50 hover:bg-amber-900/50 border border-amber-800 text-amber-400 font-medium">MEETING</button>
                    <button onclick="setStatus('DRIVING')" class="text-xs px-2.5 py-1 rounded-lg bg-blue-950/50 hover:bg-blue-900/50 border border-blue-800 text-blue-400 font-medium">DRIVING</button>
                    <button onclick="setStatus('SLEEPING')" class="text-xs px-2.5 py-1 rounded-lg bg-purple-950/50 hover:bg-purple-900/50 border border-purple-800 text-purple-400 font-medium">SLEEPING</button>
                    <button onclick="setStatus('DND')" class="text-xs px-2.5 py-1 rounded-lg bg-red-950/50 hover:bg-red-900/50 border border-red-800 text-red-400 font-medium">DND</button>
                </div>
            </div>
        </div>

        <!-- RIGHT COLUMN: Post-Call Intelligence & System Intelligence (7 Cols) -->
        <div class="lg:col-span-7 flex flex-col gap-6">

            <!-- Post-Call Intelligence Card -->
            <div id="post-call-card" class="bg-surface-900 border border-slate-800 rounded-2xl p-5 shadow-2xl">
                <div class="flex items-center justify-between mb-4">
                    <h2 class="font-bold text-sm text-slate-300 flex items-center gap-2">
                        <i class="fa-solid fa-brain text-purple-400"></i> Post-Call Intelligence
                    </h2>
                    <span id="summary-urgency-badge" class="text-xs px-2 py-0.5 rounded font-bold uppercase bg-slate-800 text-slate-400">Awaiting Call</span>
                </div>

                <div id="summary-content" class="text-xs text-slate-400 bg-surface-950 p-4 rounded-xl border border-slate-800 flex flex-col gap-3">
                    <div class="text-slate-500 italic">No call ended recently. Complete a simulated call on the left to see instant extraction.</div>
                </div>
            </div>

            <!-- Tabs: Contacts & Naming Conventions / Memories / Notifications -->
            <div class="bg-surface-900 border border-slate-800 rounded-2xl p-5 shadow-2xl flex-1 flex flex-col">
                <div class="flex border-b border-slate-800 gap-4 mb-4 pb-2">
                    <button onclick="switchTab('contacts')" id="tab-btn-contacts" class="text-xs font-bold text-emerald-400 border-b-2 border-emerald-400 pb-2">Contacts & Aliases</button>
                    <button onclick="switchTab('suggestions')" id="tab-btn-suggestions" class="text-xs font-bold text-slate-400 hover:text-slate-200 pb-2 flex items-center gap-1.5">
                        Relationship Suggestions <span id="sugg-badge" class="text-[10px] bg-cyan-500/20 text-cyan-400 px-1.5 rounded-full">0</span>
                    </button>
                    <button onclick="switchTab('memories')" id="tab-btn-memories" class="text-xs font-bold text-slate-400 hover:text-slate-200 pb-2">Long-term Memories</button>
                    <button onclick="switchTab('notifications')" id="tab-btn-notifications" class="text-xs font-bold text-slate-400 hover:text-slate-200 pb-2">Notifications</button>
                </div>

                <!-- Tab 1: Contacts -->
                <div id="tab-contacts" class="flex-1 overflow-y-auto custom-scroll max-h-72">
                    <div class="flex justify-between items-center mb-3">
                        <span class="text-xs text-slate-400 font-medium">Saved Contacts Directory</span>
                    </div>
                    <div id="contacts-list" class="flex flex-col gap-2">
                        <div class="text-xs text-slate-500">Loading contacts...</div>
                    </div>
                </div>

                <!-- Tab 2: Suggestions -->
                <div id="tab-suggestions" class="hidden flex-1 overflow-y-auto custom-scroll max-h-72">
                    <p class="text-xs text-slate-400 mb-3">AI extracted potential caller names/relationships during calls. Review and confirm:</p>
                    <div id="suggestions-list" class="flex flex-col gap-2">
                        <div class="text-xs text-slate-500">No unconfirmed suggestions.</div>
                    </div>
                </div>

                <!-- Tab 3: Memories -->
                <div id="tab-memories" class="hidden flex-1 overflow-y-auto custom-scroll max-h-72">
                    <p class="text-xs text-slate-400 mb-3">Persistent facts & context extracted across past conversations:</p>
                    <div id="memories-list" class="flex flex-col gap-2">
                        <div class="text-xs text-slate-500">No memories stored yet.</div>
                    </div>
                </div>

                <!-- Tab 4: Notifications -->
                <div id="tab-notifications" class="hidden flex-1 overflow-y-auto custom-scroll max-h-72">
                    <div id="notifications-list" class="flex flex-col gap-2">
                        <div class="text-xs text-slate-500">No notifications.</div>
                    </div>
                </div>
            </div>

        </div>
    </main>

    <!-- Footer -->
    <footer class="border-t border-slate-800/80 px-6 py-3 text-center text-xs text-slate-500 bg-surface-900/50">
        Personal AI Call Agent — Production Architecture · LLM is never authority · Policy Engine & Privacy Firewall Protected
    </footer>

    <!-- Prototype Logic Script -->
    <script>
        let currentCallId = null;
        let isListening = false;
        let recognition = null;
        let synth = window.speechSynthesis;

        // Initialize Speech Recognition if supported
        if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
            const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
            recognition = new SpeechRec();
            recognition.continuous = false;
            recognition.interimResults = false;
            recognition.lang = 'en-IN'; // Works well with Indian English & Tanglish

            recognition.onresult = (event) => {
                const text = event.results[0][0].transcript;
                document.getElementById('caller-msg-input').value = text;
                sendCallerTurn();
            };
            recognition.onend = () => {
                isListening = false;
                document.getElementById('btn-mic').classList.remove('bg-red-600', 'text-white');
            };
        }

        function toggleVoiceRecognition() {
            if (!recognition) {
                alert('Speech recognition not supported in this browser. Please type in the text box.');
                return;
            }
            if (isListening) {
                recognition.stop();
                isListening = false;
                document.getElementById('btn-mic').classList.remove('bg-red-600', 'text-white');
            } else {
                recognition.start();
                isListening = true;
                document.getElementById('btn-mic').classList.add('bg-red-600', 'text-white');
            }
        }

        function speakText(text) {
            if (!synth || !text) return;
            synth.cancel();
            const utter = new SpeechSynthesisUtterance(text);
            utter.rate = 1.0;
            const ind = document.getElementById('tts-indicator');
            ind.classList.remove('hidden');
            utter.onend = () => ind.classList.add('hidden');
            synth.speak(utter);
        }

        async function fetchState() {
            try {
                const res = await fetch('/api/v1/prototype/state');
                const data = await res.json();

                // Status Update
                const statusDot = document.getElementById('header-status-dot');
                const statusText = document.getElementById('header-status-text');
                statusText.innerText = data.status;
                if (data.status === 'AVAILABLE') {
                    statusDot.className = 'w-2.5 h-2.5 rounded-full bg-emerald-400';
                    statusText.className = 'text-xs font-bold text-emerald-400 uppercase';
                } else if (data.status === 'MEETING') {
                    statusDot.className = 'w-2.5 h-2.5 rounded-full bg-amber-400';
                    statusText.className = 'text-xs font-bold text-amber-400 uppercase';
                } else {
                    statusDot.className = 'w-2.5 h-2.5 rounded-full bg-blue-400';
                    statusText.className = 'text-xs font-bold text-blue-400 uppercase';
                }

                // Notification badge
                const badge = document.getElementById('notif-badge');
                if (data.unread_notifications > 0) {
                    badge.innerText = data.unread_notifications;
                    badge.classList.remove('hidden');
                } else {
                    badge.classList.add('hidden');
                }

                // Contacts list
                const cl = document.getElementById('contacts-list');
                if (data.contacts.length === 0) {
                    cl.innerHTML = '<div class="text-xs text-slate-500">No contacts. Click "Seed Demo Data" above.</div>';
                } else {
                    cl.innerHTML = data.contacts.map(c => `
                        <div class="flex items-center justify-between p-2.5 bg-surface-950 rounded-xl border border-slate-800">
                            <div>
                                <div class="font-bold text-xs text-slate-200">${c.name}</div>
                                <div class="text-[10px] text-slate-400 font-mono">${c.phone}</div>
                            </div>
                            <button onclick="selectCaller('${c.name}', '${c.phone}', 'FRIEND')" class="text-[10px] bg-slate-800 hover:bg-slate-700 text-slate-300 px-2 py-1 rounded border border-slate-700">Dial</button>
                        </div>
                    `).join('');
                }

                // Suggestions
                const suggBadge = document.getElementById('sugg-badge');
                suggBadge.innerText = data.suggestions.length;
                const sl = document.getElementById('suggestions-list');
                if (data.suggestions.length === 0) {
                    sl.innerHTML = '<div class="text-xs text-slate-500">No pending suggestions.</div>';
                } else {
                    sl.innerHTML = data.suggestions.map(s => `
                        <div class="p-3 bg-surface-950 rounded-xl border border-cyan-800/40 flex justify-between items-center">
                            <div>
                                <div class="font-bold text-xs text-cyan-300">${s.name} (${s.relationship})</div>
                                <div class="text-[10px] text-slate-400">${s.reason}</div>
                            </div>
                            <div class="flex gap-1.5">
                                <button onclick="confirmSuggestion('${s.id}')" class="text-[10px] bg-emerald-600 hover:bg-emerald-500 text-white px-2 py-1 rounded font-bold">Confirm</button>
                                <button onclick="rejectSuggestion('${s.id}')" class="text-[10px] bg-slate-800 hover:bg-slate-700 text-slate-300 px-2 py-1 rounded">Reject</button>
                            </div>
                        </div>
                    `).join('');
                }

                // Memories
                const ml = document.getElementById('memories-list');
                if (data.memories.length === 0) {
                    ml.innerHTML = '<div class="text-xs text-slate-500">No memories recorded yet.</div>';
                } else {
                    ml.innerHTML = data.memories.map(m => `
                        <div class="p-2.5 bg-surface-950 rounded-xl border border-slate-800">
                            <div class="flex justify-between items-center mb-1">
                                <span class="text-[10px] uppercase font-bold text-purple-400">${m.category}</span>
                                <span class="text-[10px] text-slate-500">${Math.round(m.confidence * 100)}% conf</span>
                            </div>
                            <div class="text-xs text-slate-300">${m.content}</div>
                        </div>
                    `).join('');
                }

                // Notifications
                const nl = document.getElementById('notifications-list');
                if (data.notifications.length === 0) {
                    nl.innerHTML = '<div class="text-xs text-slate-500">No notifications.</div>';
                } else {
                    nl.innerHTML = data.notifications.map(n => `
                        <div class="p-2.5 bg-surface-950 rounded-xl border ${n.urgency === 'EMERGENCY_CLAIM' ? 'border-red-500/50 bg-red-950/20' : 'border-slate-800'}">
                            <div class="font-bold text-xs text-slate-200">${n.title}</div>
                            <div class="text-[11px] text-slate-400">${n.body}</div>
                        </div>
                    `).join('');
                }

            } catch (err) {
                console.error('Failed to fetch state', err);
            }
        }

        function selectCaller(name, phone, rel) {
            document.getElementById('caller-input').value = phone;
        }

        async function seedDemoData() {
            const res = await fetch('/api/v1/prototype/seed', { method: 'POST' });
            const data = await res.json();
            alert('🎉 ' + data.message);
            fetchState();
        }

        async function setStatus(st) {
            await fetch('/api/v1/status', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status: st, source: 'MANUAL' })
            });
            fetchState();
        }

        async function applyNLDelegation() {
            const input = document.getElementById('nl-delegation-input');
            const text = input.value.trim();
            if (!text) return;
            const res = await fetch('/api/v1/prototype/parse-delegation', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text })
            });
            const data = await res.json();
            alert('⚡ ' + data.message);
            input.value = '';
            fetchState();
        }

        async function startCall() {
            const phone = document.getElementById('caller-input').value.trim();
            if (!phone) return;

            const res = await fetch('/api/v1/calls/incoming', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ caller_phone: phone, direction: 'INBOUND' })
            });
            const data = await res.json();
            currentCallId = data.call_id;

            document.getElementById('active-call-panel').classList.remove('hidden');
            document.getElementById('call-state-pill').innerText = 'Active Call (' + data.status + ')';
            document.getElementById('call-state-pill').className = 'text-xs px-2.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 font-bold';
            document.getElementById('active-caller-name').innerText = data.caller_name + ' (' + data.relationship + ')';
            document.getElementById('active-caller-phone').innerText = phone;
            document.getElementById('active-policy-decision').innerText = data.policy_decision;
            document.getElementById('policy-reason-text').innerText = data.reason;

            // Clear transcript
            const tl = document.getElementById('transcript-list');
            tl.innerHTML = '';
            appendTranscript('SYSTEM', 'Call connected. Policy Engine evaluated: ' + data.policy_decision);

            // Initial AI screening opening turn if screened
            if (data.policy_decision === 'SCREEN') {
                const initialGreeting = "Hi, I'm Deenan's AI call assistant. Deenan is currently in a meeting. Who is calling and how can I help you?";
                appendTranscript('AI_AGENT', initialGreeting);
                speakText(initialGreeting);
            }
        }

        function appendTranscript(speaker, text) {
            const tl = document.getElementById('transcript-list');
            const isCaller = speaker === 'CALLER';
            const isAI = speaker === 'AI_AGENT' || speaker === 'ASSISTANT';
            const isSystem = speaker === 'SYSTEM';

            let bubble = '';
            if (isCaller) {
                bubble = `
                    <div class="flex flex-col items-start">
                        <span class="text-[10px] text-cyan-400 font-bold mb-0.5">Caller</span>
                        <div class="bg-cyan-950/60 border border-cyan-800/40 text-cyan-100 p-2.5 rounded-xl rounded-tl-none max-w-[85%]">${text}</div>
                    </div>`;
            } else if (isAI) {
                bubble = `
                    <div class="flex flex-col items-end">
                        <span class="text-[10px] text-emerald-400 font-bold mb-0.5">AI Voice Assistant</span>
                        <div class="bg-emerald-950/60 border border-emerald-800/40 text-emerald-100 p-2.5 rounded-xl rounded-tr-none max-w-[85%]">${text}</div>
                    </div>`;
            } else {
                bubble = `
                    <div class="text-center my-1">
                        <span class="text-[10px] bg-slate-800 text-slate-400 px-2 py-0.5 rounded border border-slate-700">${text}</span>
                    </div>`;
            }
            tl.insertAdjacentHTML('beforeend', bubble);
            tl.scrollTop = tl.scrollHeight;
        }

        async function sendCallerTurn() {
            const input = document.getElementById('caller-msg-input');
            const text = input.value.trim();
            if (!text || !currentCallId) return;

            appendTranscript('CALLER', text);
            input.value = '';

            const res = await fetch(`/api/v1/calls/${currentCallId}/turn`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: text, speaker: 'CALLER', language: 'en' })
            });
            const data = await res.json();

            if (data.assistant_response) {
                appendTranscript('AI_AGENT', data.assistant_response);
                speakText(data.assistant_response);
            }
        }

        function insertAndSend(text) {
            document.getElementById('caller-msg-input').value = text;
            sendCallerTurn();
        }

        async function humanTakeover() {
            if (!currentCallId) return;
            const res = await fetch(`/api/v1/calls/${currentCallId}/takeover`, { method: 'POST' });
            const data = await res.json();
            appendTranscript('SYSTEM', '🚨 ' + data.message);
            document.getElementById('btn-takeover').classList.add('bg-amber-500', 'text-white');
            document.getElementById('btn-takeover').innerText = 'Takeover Active';
            fetchState();
        }

        async function endCall() {
            if (!currentCallId) return;
            const res = await fetch(`/api/v1/calls/${currentCallId}/end`, { method: 'POST' });
            const data = await res.json();
            appendTranscript('SYSTEM', 'Call ended. Post-call intelligence generated.');

            document.getElementById('call-state-pill').innerText = 'Completed';
            document.getElementById('call-state-pill').className = 'text-xs px-2.5 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700 font-medium';
            document.getElementById('active-call-panel').classList.add('hidden');

            // Render Post-Call Intelligence card
            renderSummary(data);
            currentCallId = null;
            fetchState();
        }

        function renderSummary(data) {
            const card = document.getElementById('summary-content');
            const badge = document.getElementById('summary-urgency-badge');

            badge.innerText = data.urgency;
            if (data.urgency === 'EMERGENCY_CLAIM' || data.urgency === 'POTENTIALLY_URGENT') {
                badge.className = 'text-xs px-2 py-0.5 rounded font-bold uppercase bg-red-500/20 text-red-400 border border-red-500/30';
            } else {
                badge.className = 'text-xs px-2 py-0.5 rounded font-bold uppercase bg-emerald-500/20 text-emerald-400 border border-emerald-500/30';
            }

            card.innerHTML = `
                <div class="border-b border-slate-800 pb-2">
                    <div class="text-[10px] text-slate-500 uppercase font-bold">Call Summary</div>
                    <div class="text-slate-200 font-medium text-xs mt-0.5">${data.summary}</div>
                </div>
                <div class="grid grid-cols-2 gap-3 border-b border-slate-800 pb-2">
                    <div>
                        <div class="text-[10px] text-slate-500 uppercase font-bold">Detected Intent</div>
                        <div class="text-cyan-400 text-xs font-semibold">${data.intent}</div>
                    </div>
                    <div>
                        <div class="text-[10px] text-slate-500 uppercase font-bold">Primary Reason</div>
                        <div class="text-slate-300 text-xs">${data.reason}</div>
                    </div>
                </div>
                <div class="flex items-center justify-between pt-1">
                    <span class="text-[11px] text-slate-400">Extracted Actions / Callbacks: <strong class="text-white">${data.actions_count}</strong></span>
                    ${data.suggestion_created ? '<span class="text-[11px] text-cyan-400 font-bold">✨ Caller identity suggested</span>' : ''}
                </div>
            `;
        }

        async function confirmSuggestion(id) {
            await fetch(`/api/v1/relationships/${id}/confirm`, { method: 'POST' });
            fetchState();
        }

        async function rejectSuggestion(id) {
            await fetch(`/api/v1/relationships/${id}/reject`, { method: 'POST' });
            fetchState();
        }

        function switchTab(tab) {
            ['contacts', 'suggestions', 'memories', 'notifications'].forEach(t => {
                document.getElementById('tab-' + t).classList.add('hidden');
                document.getElementById('tab-btn-' + t).className = 'text-xs font-bold text-slate-400 hover:text-slate-200 pb-2';
            });
            document.getElementById('tab-' + tab).classList.remove('hidden');
            document.getElementById('tab-btn-' + tab).className = 'text-xs font-bold text-emerald-400 border-b-2 border-emerald-400 pb-2';
        }

        function toggleNotifications() {
            switchTab('notifications');
        }

        // Auto poll state every 10s
        fetchState();
        setInterval(fetchState, 10000);
    </script>
</body>
</html>"""
