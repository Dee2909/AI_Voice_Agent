import os
import shutil

dirs = [
    "personal-ai-call-agent/backend/app/api",
    "personal-ai-call-agent/backend/app/core",
    "personal-ai-call-agent/backend/app/models",
    "personal-ai-call-agent/backend/app/schemas",
    "personal-ai-call-agent/backend/app/services",
    "personal-ai-call-agent/backend/app/tools",
    "personal-ai-call-agent/backend/app/agents",
    "personal-ai-call-agent/backend/app/policies",
    "personal-ai-call-agent/backend/app/memory",
    "personal-ai-call-agent/backend/app/contacts",
    "personal-ai-call-agent/backend/app/delegation",
    "personal-ai-call-agent/backend/app/calls",
    "personal-ai-call-agent/backend/app/notifications",
    "personal-ai-call-agent/backend/app/security",
    "personal-ai-call-agent/backend/tests",
    "personal-ai-call-agent/backend/alembic",
    "personal-ai-call-agent/android/PersonalCallAgent",
    "personal-ai-call-agent/ai/ollama",
    "personal-ai-call-agent/ai/stt",
    "personal-ai-call-agent/ai/tts",
    "personal-ai-call-agent/ai/vad",
    "personal-ai-call-agent/telephony/asterisk",
    "personal-ai-call-agent/telephony/configs",
    "personal-ai-call-agent/infra/docker",
    "personal-ai-call-agent/infra/monitoring",
    "personal-ai-call-agent/infra/security",
    "personal-ai-call-agent/scripts",
    "personal-ai-call-agent/docs",
]

for d in dirs:
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "__init__.py"), 'w').close() if "backend/app" in d or "backend/tests" in d else None

