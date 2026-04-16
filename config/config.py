import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-3.5-turbo")
    MAX_TOKENS = int(os.getenv("MAX_TOKENS", 1000))
    TEMPERATURE = float(os.getenv("TEMPERATURE", 0.7))
    
    ALLOWED_EXTENSIONS = ['.xlsx', '.xls']
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "data/uploads")
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", 16 * 1024 * 1024))  # 16 MB
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_USE_LLM = os.getenv("TELEGRAM_USE_LLM", "true").lower() in {"1", "true", "yes", "on"}
    TELEGRAM_WEIGHT_PRICE = float(os.getenv("TELEGRAM_WEIGHT_PRICE", 0.4))
    TELEGRAM_WEIGHT_DELIVERY = float(os.getenv("TELEGRAM_WEIGHT_DELIVERY", 0.3))
    TELEGRAM_WEIGHT_RELIABILITY = float(os.getenv("TELEGRAM_WEIGHT_RELIABILITY", 0.3))