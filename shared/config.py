import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load .env file before Config class is evaluated
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)


class Config:
    OCR_TIER1_ENABLED: bool = os.getenv("OCR_TIER1_ENABLED", "true").lower() == "true"
    OCR_TIER2_ENABLED: bool = os.getenv("OCR_TIER2_ENABLED", "true").lower() == "true"
    OCR_TIER3_ENABLED: bool = os.getenv("OCR_TIER3_ENABLED", "false").lower() == "true"
    OCR_CONFIDENCE_THRESHOLD: float = float(os.getenv("OCR_CONFIDENCE_THRESHOLD", "60"))
    
    CLASSIFICATION_CONFIDENCE_THRESHOLD: float = float(
        os.getenv("CLASSIFICATION_CONFIDENCE_THRESHOLD", "0.75")
    )
    
    MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
    MAX_FILE_SIZE_BYTES: int = MAX_FILE_SIZE_MB * 1024 * 1024
    PROCESSING_TIMEOUT_SEC: int = int(os.getenv("PROCESSING_TIMEOUT_SEC", "60"))
    
    VIRUS_SCAN_ENABLED: bool = os.getenv("VIRUS_SCAN_ENABLED", "true").lower() == "true"
    CLAMAV_HOST: str = os.getenv("CLAMAV_HOST", "localhost")
    CLAMAV_PORT: int = int(os.getenv("CLAMAV_PORT", "3310"))
    
    TIER3_PROVIDER: str = os.getenv("TIER3_PROVIDER", "gemini").lower()
    
    GEMINI_API_KEY: Optional[str] = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    
    GOOGLE_DRIVE_CREDENTIALS: Optional[str] = os.getenv("GOOGLE_DRIVE_CREDENTIALS")
    GOOGLE_DRIVE_USE_SERVICE_ACCOUNT: bool = os.getenv("GOOGLE_DRIVE_USE_SERVICE_ACCOUNT", "true").lower() == "true"
    
    MISTRAL_API_KEY: Optional[str] = os.getenv("MISTRAL_API_KEY")
    MISTRAL_MODEL: str = os.getenv("MISTRAL_MODEL", "pixtral-12b-2409")
    
    OCR_TIER1_TIMEOUT_MS: int = 100
    OCR_TIER2_TIMEOUT_MS: int = 3000
    OCR_TIER3_TIMEOUT_MS: int = 5000
    
    GEMINI_COST_PER_PAGE: float = 0.0001
    MISTRAL_COST_PER_PAGE: float = 0.0002
    
    DEDUP_CACHE_TTL_DAYS: int = 90
    
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    ELIGIBLE_TO_INVOICE_SANITY_MULTIPLIER: float = float(os.getenv("ELIGIBLE_TO_INVOICE_SANITY_MULTIPLIER", "1.5"))
    INVOICE_TO_CLAIM_SANITY_MULTIPLIER: float = float(os.getenv("INVOICE_TO_CLAIM_SANITY_MULTIPLIER", "1.5"))
    
    DATABASE_URL: Optional[str] = os.getenv("DATABASE_URL")
    
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    TEMP_DIR: Path = Path(os.getenv("TEMP_DIR", "/tmp/app_documents"))
    
    # Concurrency & Queue Configuration
    MAX_CONCURRENT_WORKERS: int = int(os.getenv("MAX_CONCURRENT_WORKERS", "10"))
    MAX_QUEUE_DEPTH: int = int(os.getenv("MAX_QUEUE_DEPTH", "1000"))
    QUEUE_WARNING_THRESHOLD: int = int(os.getenv("QUEUE_WARNING_THRESHOLD", "800"))
    RATE_LIMIT_PER_CLAIM: int = int(os.getenv("RATE_LIMIT_PER_CLAIM", "10"))
    RATE_LIMIT_PER_USER: int = int(os.getenv("RATE_LIMIT_PER_USER", "100"))
    
    # SLA Configuration
    SLA_TARGET_AVG_MS: int = int(os.getenv("SLA_TARGET_AVG_MS", "5000"))
    SLA_TARGET_P95_MS: int = int(os.getenv("SLA_TARGET_P95_MS", "15000"))
    SLA_TARGET_P99_MS: int = int(os.getenv("SLA_TARGET_P99_MS", "30000"))
    SLA_TARGET_MAX_MS: int = int(os.getenv("SLA_TARGET_MAX_MS", "60000"))
    SLA_ALERT_THRESHOLD: float = float(os.getenv("SLA_ALERT_THRESHOLD", "0.05"))
    
    # PII Detection Configuration
    PII_DETECTION_ENABLED: bool = os.getenv("PII_DETECTION_ENABLED", "true").lower() == "true"
    PII_REDACTION_MODE: str = os.getenv("PII_REDACTION_MODE", "REDACT")
    PII_USE_ML_MODEL: bool = os.getenv("PII_USE_ML_MODEL", "false").lower() == "true"
    
    # Error Budget Configuration
    OCR_ERROR_BUDGET_PERCENTAGE: float = float(os.getenv("OCR_ERROR_BUDGET_PERCENTAGE", "0.05"))
    OCR_LOW_CONFIDENCE_THRESHOLD: float = float(os.getenv("OCR_LOW_CONFIDENCE_THRESHOLD", "50.0"))
    ERROR_BUDGET_WINDOW_HOURS: int = int(os.getenv("ERROR_BUDGET_WINDOW_HOURS", "24"))
    ERROR_BUDGET_ALERT_THRESHOLD: float = float(os.getenv("ERROR_BUDGET_ALERT_THRESHOLD", "0.80"))
    
    # Language Detection Configuration
    LANGUAGE_DETECTION_ENABLED: bool = os.getenv("LANGUAGE_DETECTION_ENABLED", "true").lower() == "true"
    RTL_LANGUAGE_SUPPORT: bool = os.getenv("RTL_LANGUAGE_SUPPORT", "true").lower() == "true"
    
    # Tesseract configuration (Tier2 OCR)
    TESSERACT_CMD: Optional[str] = os.getenv("TESSERACT_CMD")
    TESSDATA_PREFIX: Optional[str] = os.getenv("TESSDATA_PREFIX")
    
    @classmethod
    def ensure_temp_dir(cls) -> None:
        cls.TEMP_DIR.mkdir(parents=True, exist_ok=True)
