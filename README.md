# Personal AI Call Agent — Working Prototype

A production-oriented, multilingual (**English · Tamil · Tanglish**) Personal AI Telephone Assistant that screens and answers incoming calls on behalf of the user when unavailable, resolves contact identities and relationships, enforces deterministic policy rules, protects privacy with a firewall, and extracts post-call structured intelligence.

---

## 🚀 Quick Start (Working Prototype)

### 1. Launch Prototype in One Command
```bash
./run_prototype.sh
```
Or with make:
```bash
make prototype
```

Then open your browser at: **`http://localhost:8000`**

### 2. Manual Startup
```bash
cd backend
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:api_app --host 0.0.0.0 --port 8000 --reload
```

---

## 🌟 Key Prototype Capabilities

1. **Interactive Web Dashboard & Call Simulator (`http://localhost:8000`)**:
   - **Preset Dials**: Quick test calls from **Amma** (Mother/Family), **Arun Natpu** (Friend/Natpu convention), **Ravi Manager** (Work), and **Unknown Number**.
   - **Live Audio & Speech (STT + TTS)**: Microphone voice input and instant voice audio response playback.
   - **Live Policy Decision Visualizer**: Real-time breakdown of Caller ID ➔ Relationship Resolution ➔ User Status ➔ Active Delegation ➔ Policy Decision (`ANSWER` vs `SCREEN` vs `NOTIFY`).
   - **Live One-Tap Human Takeover**: Instantly mutes the AI and transfers the call to human handling.
   - **Instant Post-Call Intelligence**: Automatically generates summary, detected intent, urgency level (`NORMAL`, `POTENTIALLY_URGENT`, `EMERGENCY_CLAIM`), action items, callback requests, and relationship suggestions upon call termination.

2. **Natural Language Delegation**:
   - Parse spoken or typed commands in Tamil/Tanglish/English (e.g. *"Naan meeting-la irukken. 6 mani varaikum en calls pathuko"* or *"Don't disturb me for 2 hours"*).
   - Backend enforces strict expiration timestamps.

3. **Deterministic Privacy Firewall**:
   - Automatically sanitizes context before LLM processing: redacts passwords, tokens, API keys, credentials, and credit card numbers.
   - Blocks unauthorized disclosure of user GPS location and calendar schedules to unconfirmed callers.

4. **Modular Audio Pipeline**:
   - **VAD**: Silero VAD + Energy VAD fallback.
   - **STT**: `faster-whisper` + simulated fallback.
   - **TTS**: AI4Bharat Indic-TTS adapter + PCM WAV tone synthesizer.

5. **Telephony & Asterisk ARI Integration**:
   - Telephony adapter interface supporting Asterisk ARI (REST & WebSockets) and in-memory simulated telephony.

---

## 🛠 Ollama Configuration

To connect a local Ollama instance:
```bash
# Pull your preferred model (e.g., llama3 or mistral)
ollama run llama3

# Set in .env or environment
export OLLAMA_BASE_URL=http://localhost:11434
export OLLAMA_MODEL=llama3
export MOCK_LLM_ENABLED=false
```

When offline or in automated CI tests, `MOCK_LLM_ENABLED=true` provides deterministic tool calling and response handling.

---

## 🧪 Testing & Verification

Run the full automated test suite (69 tests covering unit, security, and Scenarios A through J):
```bash
make test
```
Run linter & type checking:
```bash
make lint
make typecheck
```

### Verified Test Scenarios:
- **Scenario A**: Known family caller (Amma) ➔ Resolved relationship, Policy `ANSWER`, Summary generated.
- **Scenario B**: Unknown caller asking for private schedule ➔ Policy `SCREEN`, Privacy firewall blocks disclosure, Caller leaves message.
- **Scenario C**: Meeting delegation with expiry ➔ Contact rules applied, Time-based expiry enforced.
- **Scenario D**: Callback request ➔ Persisted without automated outbound dialing.
- **Scenario E**: Action item extraction ➔ Validated without invented dates or facts.
- **Scenario F**: Prompt injection attack ➔ Blocked and redacted by Privacy Firewall.
- **Scenario G**: Ollama unavailable / fallback ➔ Safe fallback response, call remains valid, post-call retriable.
- **Scenario H**: Duplicate processing idempotency ➔ Repeated post-call executions produce no duplicate records.
- **Scenario I**: Multilingual voice pipeline ➔ Tamil / Tanglish / English audio processing.
- **Scenario J**: Cross-user isolation ➔ Strict user ID scoping preventing IDOR.

---

## 🐳 Docker Deployment

```bash
# Start backend, postgres, redis, and ollama
docker compose up -d

# Stop services
docker compose down
```

---

## 🔒 Security Principles
- **LLM is NEVER the final authority**: Permissions, relationship confirmation, status changes, and policy evaluations are strictly executed by deterministic backend code.
- **Zero-Trust Input**: All caller transcripts and speech inputs are treated as untrusted data.
