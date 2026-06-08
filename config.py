"""Central settings, loaded from .env (see .env.example)."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- Paths / browser-grab (desktop app) ---
PROJECT_ROOT = Path(__file__).resolve().parent
CACHE_DIR = PROJECT_ROOT / "cache"
DOWNLOAD_DIR = CACHE_DIR / "downloads"
CHROME_PROFILE_DIR = CACHE_DIR / "chrome_profile"

# Where the user's meeting recordings/transcripts live (their OneDrive for Business).
MEETINGS_URL = os.getenv("MEETINGS_URL", "https://shiandms-my.sharepoint.com/meetings").strip()

for _d in (CACHE_DIR, DOWNLOAD_DIR, CHROME_PROFILE_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# --- SHI ATLAS vault layout (durable user knowledge base) ---
USER_NAME = os.getenv("ATLAS_USER", "Manuel")
# How many independent Copilot Chrome instances run in parallel (the job pool).
POOL_SIZE = int(os.getenv("ATLAS_POOL_SIZE", "7"))   # up to 7 concurrent Copilot Chrome instances
VAULT_DIR = PROJECT_ROOT / "vault"
INBOX_DIR = VAULT_DIR / "inbox"            # ⇐ drop files here to ingest
INBOX_PROCESSED = INBOX_DIR / "_processed"
ACCOUNTS_DIR = VAULT_DIR / "accounts"      # per-customer folders
CUSTOMERS_DIR = VAULT_DIR / "customers"    # Customer Vault (ATP) — persistent customer repos
DAILY_DIR = VAULT_DIR / "daily"            # daily briefings by date
EXPORTS_DIR = VAULT_DIR / "exports"        # emails/decks/shareables
RECYCLEBIN_DIR = VAULT_DIR / "recyclebin"  # soft-deleted folders — moved here, never auto-purged
CRON_PATH = VAULT_DIR / "cron.json"        # scheduled instructions (the Cron Jobs tab)
RUNS_DIR = CACHE_DIR / "runs"              # raw Copilot answers (audit)
TEMPLATES_DIR = PROJECT_ROOT / "templates"

# --- People Resources (the SHI resource-alignment directory) ---
# Lives in the skill's own folder (where the user drops the source file), CSV = source of truth.
PEOPLE_DIR = PROJECT_ROOT / "atlas" / "skills" / "peopleresources"
PEOPLE_CSV = PEOPLE_DIR / "resources.csv"          # the permanent, editable source of truth
PEOPLE_ARCHIVE_DIR = PEOPLE_DIR / "archive"        # superseded CSVs on import (never deleted)
PEOPLE_IMPORT_DIR = PEOPLE_DIR / "import"          # drop a new CSV here, then Import in-app

for _d in (VAULT_DIR, INBOX_DIR, INBOX_PROCESSED, ACCOUNTS_DIR, CUSTOMERS_DIR, DAILY_DIR,
           EXPORTS_DIR, RECYCLEBIN_DIR, RUNS_DIR, TEMPLATES_DIR,
           PEOPLE_DIR, PEOPLE_ARCHIVE_DIR, PEOPLE_IMPORT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# --- LLM ---
# Default engine = "copilot": drive Microsoft 365 Copilot in the browser (no API key,
# no tokens). Set to "anthropic" or "azure_openai" to use those APIs instead.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "copilot").strip().lower()
COPILOT_URL = os.getenv("COPILOT_URL", "https://m365.cloud.microsoft/chat/").strip()

AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o").strip()
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21").strip()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6").strip()

# --- Entra ID / Microsoft Graph (M1: OneDrive pull) ---
AZURE_TENANT_ID = os.getenv("AZURE_TENANT_ID", "").strip()
AZURE_CLIENT_ID = os.getenv("AZURE_CLIENT_ID", "").strip()
AZURE_CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET", "").strip()
AZURE_REDIRECT_URI = os.getenv("AZURE_REDIRECT_URI", "http://localhost:8501").strip()

# Delegated scopes this app uses (all no-admin-consent).
GRAPH_SCOPES = ["User.Read", "Files.Read.All"]
AUTHORITY = f"https://login.microsoftonline.com/{AZURE_TENANT_ID}" if AZURE_TENANT_ID else None


def llm_configured() -> bool:
    return bool((AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT) or ANTHROPIC_API_KEY)


def graph_configured() -> bool:
    return bool(AZURE_TENANT_ID and AZURE_CLIENT_ID and AZURE_CLIENT_SECRET)
