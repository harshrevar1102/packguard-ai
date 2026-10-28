import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root or backend folder
env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))

# Ensure data directory exists
DATA_DIR.mkdir(parents=True, exist_ok=True)
(DATA_DIR / "products").mkdir(parents=True, exist_ok=True)
(DATA_DIR / "uploads").mkdir(parents=True, exist_ok=True)

# AI Configuration (Environment variables, safe defaults)
AI_PROVIDER = os.getenv("AI_PROVIDER", "auto")  # 'auto', 'openai', 'gemini', 'anthropic', or 'none'
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022")

# Server host & port
SERVER_HOST = os.getenv("SERVER_HOST", "127.0.0.1")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


class Settings:
    max_sheet_mb: int = _int("PACKGUARD_MAX_SHEET_MB", 10)
    max_pdf_mb: int = _int("PACKGUARD_MAX_PDF_MB", 50)
    max_pdf_pages: int = _int("PACKGUARD_MAX_PDF_PAGES", 20)
    min_text_chars: int = _int("PACKGUARD_MIN_TEXT_CHARS", 40)
    ocr_min_confidence: float = float(os.getenv("PACKGUARD_OCR_MIN_CONFIDENCE", "70"))
    ocr_timeout_s: int = _int("PACKGUARD_OCR_TIMEOUT_S", 90)
    cors_origins: list = [
        o.strip()
        for o in os.getenv("PACKGUARD_CORS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
        if o.strip()
    ]


settings = Settings()
