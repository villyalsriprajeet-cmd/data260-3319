# HW6 settings: personal config values and the MongoDB connection, overridable with environment variables
import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env")  
SID4 = 3319  
PORT_BASE = 8000 + SID4 % 900  # 8619
PREFIX = f"s{SID4}"
SEED = SID4
VERIFY_SEED = 260000 + SID4
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")  
MONGODB_DB = f"{PREFIX}_doc"  
FIXTURES_COLLECTION = "fixtures" 
STATUS_VALUES = ["Scheduled", "Live", "Completed", "Postponed"]  
CATEGORY_VALUES = ["League", "Cup", "Friendly", "Tournament"]  
MESSAGES_COLLECTION = "messages"  # Part 2 collections in the same database
SUMMARIES_COLLECTION = "summaries"
EPISODES_COLLECTION = "episodes"
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")  # local Ollama server
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:3b")  # same model as HW1 to HW5
LLM_NUM_CTX = int(os.getenv("LLM_NUM_CTX", "4096")) 
LLM_NUM_PREDICT = int(os.getenv("LLM_NUM_PREDICT", "150"))  # cap on tokens per model reply
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"  # same embedder as HW4, 384 numbers per text
SHORT_TERM_N = int(os.getenv("SHORT_TERM_N", "12"))  # last N messages sent to the model
SUMMARIZE_EVERY_USER_MSGS = int(os.getenv("SUMMARIZE_EVERY_USER_MSGS", "5"))  # M: session summary every M user messages
LIFETIME_EVERY_SUMMARIES = int(os.getenv("LIFETIME_EVERY_SUMMARIES", "3"))  # condense after every 3 session summaries
EPISODIC_TOP_K = int(os.getenv("EPISODIC_TOP_K", "3"))  # k facts retrieved per turn
MAX_FACTS_PER_MESSAGE = 3  # facts extracted from one user message
METRICS_LOG = Path(__file__).resolve().parents[2] / "reports" / "hw06" / "raw" / "chat_metrics.csv"  # one row per /api/chat request
