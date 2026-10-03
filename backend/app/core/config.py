from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Personal AI Call Agent"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "dev"

    DATABASE_URL: str | None = None
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: str = "5432"
    POSTGRES_DB: str = "call_agent"

    REDIS_URL: str = "redis://localhost:6379/0"

    LOG_LEVEL: str = "INFO"

    # Ollama settings
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3"
    OLLAMA_TIMEOUT_SECONDS: int = 30
    OLLAMA_MAX_RETRIES: int = 3
    OLLAMA_TEMPERATURE: float = 0.0

    MOCK_LLM_ENABLED: bool = False
    MAX_TOOL_CALLS_PER_TURN: int = 5
    AGENT_SYSTEM_PROMPT_VERSION: int = 2

    # Telephony & Asterisk ARI settings
    ASTERISK_HOST: str = "localhost"
    ASTERISK_PORT: int = 5038
    ASTERISK_ARI_URL: str = "http://localhost:8088/ari"
    ASTERISK_ARI_WS_URL: str = "ws://localhost:8088/ari/events"
    ASTERISK_ARI_USERNAME: str = "asterisk"
    ASTERISK_ARI_PASSWORD: str = "asterisk"
    ASTERISK_APP_NAME: str = "ai_call_agent"

    SIP_PROVIDER: str = "local"
    SIP_USERNAME: str | None = None
    SIP_PASSWORD: str | None = None

    # Voice pipeline settings
    STT_PROVIDER: str = "faster-whisper"
    STT_MODEL: str = "base"
    STT_DEVICE: str = "cpu"
    STT_TIMEOUT_SECONDS: int = 10

    TTS_PROVIDER: str = "indic-tts"
    TTS_LANGUAGE: str = "ta"
    TTS_TIMEOUT_SECONDS: int = 10

    VAD_THRESHOLD: float = 0.5
    AUDIO_SAMPLE_RATE: int = 16000
    CALL_MAX_DURATION_SECONDS: int = 600

    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
