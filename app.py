import os
import sys
import time
import hashlib
import json
import asyncio
import httpx  # වේගවත් API සන්නිවේදනය සඳහා
from datetime import datetime
from typing import Optional, List
from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse, JSONResponse
from pydantic import BaseModel
from duckduckgo_search import DDGS
from google import genai
import firebase_admin
from firebase_admin import credentials, firestore
import edge_tts
import hmac
import base64
import secrets
import threading
import uuid
import re
try:
    import bcrypt  # Password ආරක්ෂාව සඳහා (install කර නැත්නම් PBKDF2 භාවිතා වේ)
except ImportError:
    bcrypt = None

app = FastAPI(title="Nexuz AI - Proactive & Autonomous Self-Learning Edition")

# Creator Email එක වෙනස් කිරීමට පහසු වන ලෙස මෙසේ තබමු
CREATOR_EMAIL = os.environ.get("CREATOR_EMAIL", "chamathmanujaya76@gmail.com").strip().lower()


# ================= SYSTEM METRICS & LOGS TRACKER (CREATOR ADMIN) =================
SYSTEM_METRICS = {
    "api_calls_count": {
        "Gemini": 0, "Groq": 0, "OpenRouter": 0, "Cerebras": 0, 
        "Together": 0, "DeepInfra": 0, "Cohere": 0, "Tavily": 0, "SerpAPI": 0, "EdgeTTS": 0
    },
    "response_times": [],
    "errors_log": [],
    "token_usage_estimated": 0
}

_ALERT_LAST = {}
ALERT_COOLDOWN_SECONDS = 600

def _redact_secrets(text: str) -> str:
    text = re.sub(r"(?i)(api_key|key|token|authorization)=([^&\s\"']+)", r"\1=***", str(text))
    text = re.sub(r"(?i)bearer\s+[A-Za-z0-9._\-]+", "Bearer ***", text)
    return text

def _write_alert_to_db(provider: str, err_msg: str):
    try:
        if db:
            db.collection("system_messages").add({
                "sender_email": "system@nexuz.ai",
                "sender_name": "Nexuz Proactive Daemon",
                "recipient_email": CREATOR_EMAIL,
                "content": f"⚠️ Proactive Alert: System error detected in [{provider}]: {err_msg}",
                "timestamp": datetime.utcnow(),
                "read": False
            })
    except Exception as ex:
        print(f"Proactive Notification Error: {ex}")

def log_system_error(err_msg: str, provider: str = "System"):
    err_msg = _redact_secrets(err_msg)
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = {"time": timestamp, "provider": provider, "error": str(err_msg), "notified": False}
    SYSTEM_METRICS["errors_log"].insert(0, log_entry)
    if len(SYSTEM_METRICS["errors_log"]) > 50:
        SYSTEM_METRICS["errors_log"].pop()

    # එකම error එක නැවත නැවත Creator ගේ inbox එකට ලිවීම වළක්වයි (විනාඩි 10කට වරක් පමණි),
    # සහ Firestore ලිවීම වෙනම thread එකක් තුළ සිදුවේ (request එක හිර නොවේ).
    key = (provider, str(err_msg)[:80])
    now = time.time()
    if db and now - _ALERT_LAST.get(key, 0) > ALERT_COOLDOWN_SECONDS:
        _ALERT_LAST[key] = now
        if len(_ALERT_LAST) > 500:
            _ALERT_LAST.clear()
        threading.Thread(target=_write_alert_to_db, args=(provider, err_msg), daemon=True).start()

def get_base_path():
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

base_dir = get_base_path()
static_dir = os.path.join(base_dir, "static")

# face.glb route එක /static mount එකට ඉහළින් තිබිය යුතුයි (නැත්නම් mount එක පළමුව ගැළපී මෙම route එක කිසිදා ක්‍රියා නොකරයි)
@app.get("/static/face.glb")
async def serve_glb_model():
    glb_path = os.path.join(static_dir, "face.glb")
    if not os.path.exists(glb_path):
        glb_path = os.path.join(base_dir, "face.glb")
    if os.path.exists(glb_path):
        return FileResponse(glb_path, media_type="model/gltf-binary")
    raise HTTPException(status_code=404, detail="GLB file not found")

if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Direct Static Route for GLB Model File Access Guarantee

# ================= LOCAL COMPUTER VAULT STORAGE SETUP (VERCEL SAFE /TMP) =================
IS_VERCEL = os.environ.get("VERCEL", "0") == "1" or os.environ.get("VERCEL_ENV") is not None
if IS_VERCEL:
    LOCAL_VAULT_DIR = "/tmp/nexuz_local_vault"
else:
    LOCAL_VAULT_DIR = os.path.join(base_dir, "nexuz_local_vault")

try:
    os.makedirs(LOCAL_VAULT_DIR, exist_ok=True)
except Exception as e:
    print(f"Vault folder setup info: {e}")

def save_to_local_user_vault(user_id: str, user_name: str, data_type: str, content_dict: dict):
    if not user_id or user_id == "guest":
        return
    try:
        safe_name = "".join([c if c.isalnum() else "_" for c in str(user_name)])[:30]
        user_folder_name = f"{safe_name}_{user_id[:8]}"
        user_folder_path = os.path.join(LOCAL_VAULT_DIR, user_folder_name)
        os.makedirs(user_folder_path, exist_ok=True)

        if data_type == "profile":
            file_path = os.path.join(user_folder_path, "user_profile.json")
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(content_dict, f, ensure_ascii=False, indent=4, default=str)
        
        elif data_type == "chat":
            chat_json_path = os.path.join(user_folder_path, "conversations.json")
            history_data = []
            if os.path.exists(chat_json_path):
                try:
                    with open(chat_json_path, "r", encoding="utf-8") as f:
                        history_data = json.load(f)
                except:
                    history_data = []
            history_data.append(content_dict)
            history_data = history_data[-200:]   # conversations.json අසීමිතව වර්ධනය නොවීමට
            with open(chat_json_path, "w", encoding="utf-8") as f:
                json.dump(history_data, f, ensure_ascii=False, indent=4, default=str)

            csv_path = os.path.join(user_folder_path, "data_records.csv")
            file_exists = os.path.exists(csv_path)
            with open(csv_path, "a", encoding="utf-8") as f:
                if not file_exists:
                    f.write("Timestamp,User_Query,AI_Response\n")
                q_clean = _csv_safe(content_dict.get("query", "")).replace('"', '""').replace('\n', ' ')
                r_clean = _csv_safe(content_dict.get("reply", "")).replace('"', '""').replace('\n', ' ')
                f.write(f'"{datetime.utcnow()}","{q_clean}","{r_clean}"\n')
    except Exception as e:
        print(f"Local Vault Save Error: {e}")

def get_local_user_vault_context(user_id: str, user_name: str) -> str:
    if not user_id or user_id == "guest":
        return "[Local Vault: Guest Session]"
    try:
        safe_name = "".join([c if c.isalnum() else "_" for c in str(user_name)])[:30]
        user_folder_name = f"{safe_name}_{user_id[:8]}"
        user_folder_path = os.path.join(LOCAL_VAULT_DIR, user_folder_name)
        if not os.path.exists(user_folder_path):
            return "[Local Vault: Folder not initialized yet]"
        
        context_summary = []
        profile_path = os.path.join(user_folder_path, "user_profile.json")
        if os.path.exists(profile_path):
            with open(profile_path, "r", encoding="utf-8") as f:
                prof = json.load(f)
                context_summary.append(f"Local Profile: {json.dumps(prof, ensure_ascii=False)}")
        
        chat_json_path = os.path.join(user_folder_path, "conversations.json")
        if os.path.exists(chat_json_path):
            with open(chat_json_path, "r", encoding="utf-8") as f:
                chats = json.load(f)
                recent_chats = [f"Q: {c.get('query')} | A: {c.get('reply')}" for c in chats[-5:]]
                context_summary.append("Recent Local Vault Chat Logs:\n" + "\n".join(recent_chats))
        
        return "[Local Computer Vault Storage Context]:\n" + "\n".join(context_summary)
    except Exception as e:
        return f"[Local Vault Read Error: {e}]"

# ================= ENVIRONMENT VARIABLES & MULTI-KEY PRIORITY ARRAYS =================

GEMINI_KEYS = [
    os.environ.get("GEMINI_API_KEY_1"),
    os.environ.get("GEMINI_API_KEY_2"),
    os.environ.get("GEMINI_API_KEY_3"),
    os.environ.get("GEMINI_API_KEY")
]

CLOUDFLARE_ACCOUNTS = [
    os.environ.get("CLOUDFLARE_ACCOUNT_ID_1"),
    os.environ.get("CLOUDFLARE_ACCOUNT_ID_2"),
    os.environ.get("CLOUDFLARE_ACCOUNT_ID_3"),
    os.environ.get("CLOUDFLARE_ACCOUNT_ID")
]
CLOUDFLARE_TOKENS = [
    os.environ.get("CLOUDFLARE_API_TOKEN_1"),
    os.environ.get("CLOUDFLARE_API_TOKEN_2"),
    os.environ.get("CLOUDFLARE_API_TOKEN_3"),
    os.environ.get("CLOUDFLARE_API_TOKEN")
]

GITHUB_TOKENS = [
    os.environ.get("GITHUB_TOKEN_1"),
    os.environ.get("GITHUB_TOKEN_2"),
    os.environ.get("GITHUB_TOKEN_3"),
    os.environ.get("GITHUB_TOKEN")
]

SAMBANOVA_KEYS = [
    os.environ.get("SAMBANOVA_API_KEY_1"),
    os.environ.get("SAMBANOVA_API_KEY_2"),
    os.environ.get("SAMBANOVA_API_KEY_3"),
    os.environ.get("SAMBANOVA_API_KEY")
]

TOGETHER_KEYS = [
    os.environ.get("TOGETHER_API_KEY_1"),
    os.environ.get("TOGETHER_API_KEY_2"),
    os.environ.get("TOGETHER_API_KEY_3"),
    os.environ.get("TOGETHER_API_KEY")
]

CEREBRAS_KEYS = [
    os.environ.get("CEREBRAS_API_KEY_1"),
    os.environ.get("CEREBRAS_API_KEY_2"),
    os.environ.get("CEREBRAS_API_KEY_3"),
    os.environ.get("CEREBRAS_API_KEY")
]

GROQ_KEYS = [
    os.environ.get("GROQ_API_KEY_1"),
    os.environ.get("GROQ_API_KEY_2"),
    os.environ.get("GROQ_API_KEY_3"),
    os.environ.get("GROQ_API_KEY")
]

DEEPINFRA_KEYS = [
    os.environ.get("DEEPINFRA_API_KEY_1"),
    os.environ.get("DEEPINFRA_API_KEY_2"),
    os.environ.get("DEEPINFRA_API_KEY_3"),
    os.environ.get("DEEPINFRA_API_KEY")
]

COHERE_KEYS = [
    os.environ.get("COHERE_API_KEY_1"),
    os.environ.get("COHERE_API_KEY_2"),
    os.environ.get("COHERE_API_KEY_3"),
    os.environ.get("COHERE_API_KEY")
]

OPENROUTER_KEYS = [
    os.environ.get("OPENROUTER_API_KEY_1"),
    os.environ.get("OPENROUTER_API_KEY_2"),
    os.environ.get("OPENROUTER_API_KEY_3"),
    os.environ.get("OPENROUTER_API_KEY")
]

TAVILY_KEYS = [
    os.environ.get("TAVILY_API_KEY_1"),
    os.environ.get("TAVILY_API_KEY_2"),
    os.environ.get("TAVILY_API_KEY_3"),
    os.environ.get("TAVILY_API_KEY")
]

SERPAPI_KEYS = [
    os.environ.get("SERPAPI_API_KEY_1"),
    os.environ.get("SERPAPI_API_KEY_2"),
    os.environ.get("SERPAPI_API_KEY")
]

GEEKFLARE_KEYS = [
    os.environ.get("GEEKFLARE_API_KEY_1"),
    os.environ.get("GEEKFLARE_API_KEY_2"),
    os.environ.get("GEEKFLARE_API_KEY")
]

GOOGLE_SEARCH_KEYS = [
    os.environ.get("GOOGLE_SEARCH_API_KEY_1"),
    os.environ.get("GOOGLE_SEARCH_API_KEY_2"),
    os.environ.get("GOOGLE_SEARCH_API_KEY_3"),
    os.environ.get("GOOGLE_SEARCH_API_KEY")
]

GOOGLE_SEARCH_CX = [
    os.environ.get("GOOGLE_SEARCH_CX_1", "469fa5f763ed944aa"),
    os.environ.get("GOOGLE_SEARCH_CX_2", "41235783a736b49a1"),
    os.environ.get("GOOGLE_SEARCH_CX_3", "d3dfab92099574e99")
]

EXA_KEYS = [
    os.environ.get("EXA_API_KEY_1"),
    os.environ.get("EXA_API_KEY_2"),
    os.environ.get("EXA_API_KEY_3"),
    os.environ.get("EXA_API_KEY")
]

db = None
try:
    if not firebase_admin._apps:
        firebase_json_env = os.environ.get("FIREBASE_CREDENTIALS_JSON")
        if firebase_json_env:
            cred_dict = json.loads(firebase_json_env)
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
            db = firestore.client()
            print("Firebase Database එක Environment Variable මගින් සම්බන්ධ විය.")
        else:
            json_filename = "nova-x-6ef72-firebase-adminsdk-fbsvc-f00ed803ec.json"
            json_path = os.path.join(base_dir, json_filename)
            if not os.path.exists(json_path):
                json_path = json_filename

            if os.path.exists(json_path):
                cred = credentials.Certificate(json_path)
                firebase_admin.initialize_app(cred)
                db = firestore.client()
                print("Firebase Database එක File මගින් සම්බන්ධ විය.")
            else:
                print("Firebase Credentials හමු නොවුණි.")
except Exception as e:
    print(f"Firebase Connection Warning: {e}")

# ================= AUTHENTICATION, PASSWORD HASHING & RATE LIMITING =================
# Login වූ විට server එක signed token එකක් දෙයි. Admin/පෞද්ගලික endpoints සියල්ල දැන් ඒ token එකෙන් පමණක් ඔබව හඳුනාගනී.
# (Request එකේ එන email එක විශ්වාස කරන්නේ නැත - ඒ නිසා ඔබේ creator email එක ඕනෑම කෙනෙකුට දැනගත්තත් කිසි වැඩක් නැත.)
PBKDF2_ITERATIONS = 200_000
TOKEN_TTL_SECONDS = 30 * 24 * 3600

_secret_from_env = os.environ.get("NEXUZ_SECRET", "").strip()
if not _secret_from_env:
    _secret_from_env = secrets.token_hex(32)
    print("⚠️  NEXUZ_SECRET environment variable එක සකසා නැත. තාවකාලික key එකක් භාවිතා වේ - server restart වූ විට සියලු login tokens අවලංගු වේ. (Production/Vercel වලදී අනිවාර්යයෙන් සකසන්න)")
AUTH_SECRET = _secret_from_env.encode("utf-8")

def hash_password(password: str) -> str:
    pw = str(password).encode("utf-8")
    if bcrypt is not None:
        return bcrypt.hashpw(pw[:72], bcrypt.gensalt()).decode("utf-8")
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw, salt, PBKDF2_ITERATIONS)
    return f"pbkdf2${PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"

def verify_password(password: str, stored: str) -> bool:
    if not stored:
        return False
    pw = str(password).encode("utf-8")
    stored = str(stored)
    try:
        if stored.startswith("$2"):
            return bcrypt is not None and bool(bcrypt.checkpw(pw[:72], stored.encode("utf-8")))
        if stored.startswith("pbkdf2$"):
            _, iters, salt_hex, hash_hex = stored.split("$")
            dk = hashlib.pbkdf2_hmac("sha256", pw, bytes.fromhex(salt_hex), int(iters))
            return hmac.compare_digest(dk.hex(), hash_hex)
        # පරණ (salt නැති) SHA-256 hashes - login වූ විට ස්වයංක්‍රීයව අලුත් ක්‍රමයට උසස් කෙරේ
        return hmac.compare_digest(hashlib.sha256(pw).hexdigest(), stored)
    except Exception:
        return False

def password_needs_upgrade(stored: str) -> bool:
    stored = str(stored or "")
    if bcrypt is not None:
        return not stored.startswith("$2")
    return not stored.startswith("pbkdf2$")

def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))

def create_token(user_id: str, email: str, is_creator: bool) -> str:
    payload = {
        "uid": str(user_id),
        "email": str(email).strip().lower(),
        "cr": bool(is_creator),
        "exp": int(time.time()) + TOKEN_TTL_SECONDS
    }
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(AUTH_SECRET, body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"

def verify_token(token: str):
    try:
        body, sig = str(token).split(".", 1)
        expected = hmac.new(AUTH_SECRET, body.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(_b64d(body))
        if int(payload.get("exp", 0)) < time.time():
            return None
        email = str(payload.get("email", "")).strip().lower()
        return {
            "uid": str(payload["uid"]),
            "email": email,
            "creator": bool(payload.get("cr")) and email == CREATOR_EMAIL
        }
    except Exception:
        return None

def get_auth(request: Request):
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return verify_token(header[7:].strip())
    return None

def _unauthorized(msg: str = "Unauthorized - කරුණාකර නැවත Login වන්න.", extra: Optional[dict] = None):
    content = {"success": False, "message": msg}
    content.update(extra or {})
    return JSONResponse(status_code=401, content=content)

def _forbidden(msg: str = "Forbidden", extra: Optional[dict] = None):
    content = {"success": False, "message": msg}
    content.update(extra or {})
    return JSONResponse(status_code=403, content=content)

def _same_email(a, b) -> bool:
    return str(a or "").strip().lower() == str(b or "").strip().lower()

def _client_ip(request: Request) -> str:
    try:
        return request.client.host if request.client else "unknown"
    except Exception:
        return "unknown"

# ---- සරල in-memory rate limiter (brute-force login වැළැක්වීමට) ----
_RATE_BUCKETS = {}

def rate_limited(key: str, limit: int, window: int) -> bool:
    now = time.time()
    hits = [t for t in _RATE_BUCKETS.get(key, []) if now - t < window]
    _RATE_BUCKETS[key] = hits
    if len(_RATE_BUCKETS) > 5000:
        for k in list(_RATE_BUCKETS.keys())[:2500]:
            if not _RATE_BUCKETS.get(k):
                _RATE_BUCKETS.pop(k, None)
    return len(hits) >= limit

def rate_hit(key: str):
    _RATE_BUCKETS.setdefault(key, []).append(time.time())

def rate_clear(key: str):
    _RATE_BUCKETS.pop(key, None)

# ---- Creator account ආරක්ෂාව: email එක පමණක් නොව, DB හි creator flag එකත් අවශ්‍යයි ----
def _creator_account_exists() -> bool:
    try:
        return len(list(db.collection("users").where("is_creator", "==", True).limit(1).stream())) > 0
    except Exception:
        return True   # සැකයක් ඇත්නම් අලුත් creator කෙනෙක් නොහදයි

def _is_creator_account(u_data: dict) -> bool:
    return _same_email(u_data.get("email"), CREATOR_EMAIL) and bool(u_data.get("is_creator"))

# ---- කුඩා TTL cache (Firestore reads අඩු කිරීමට) ----
_CACHE = {}

def _cache_get(key: str, ttl: float):
    item = _CACHE.get(key)
    if item and time.time() - item[0] < ttl:
        return item[1]
    return None

def _cache_set(key: str, value):
    if len(_CACHE) > 500:
        _CACHE.clear()
    _CACHE[key] = (time.time(), value)

_BG_TASKS = set()

def _spawn(coro):
    task = asyncio.create_task(coro)
    _BG_TASKS.add(task)
    task.add_done_callback(_BG_TASKS.discard)
    return task

def _csv_safe(text: str) -> str:
    # Excel formula injection වැළැක්වීම (=, +, -, @ වලින් පටන් ගන්නා text)
    text = str(text)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text

# ================= AUTONOMOUS PROACTIVE BACKGROUND DAEMON =================
def _cleanup_temp_files(max_age: int = 600):
    # TTS තාවකාලික mp3 ගොනු (client එක අතරමග විසන්ධි වූ විට ඉතිරි වන ඒවා) ඉවත් කරයි
    try:
        now = time.time()
        for fn in os.listdir(LOCAL_VAULT_DIR):
            if fn.startswith("tts_") and fn.endswith(".mp3"):
                p = os.path.join(LOCAL_VAULT_DIR, fn)
                if now - os.path.getmtime(p) > max_age:
                    os.remove(p)
    except Exception as e:
        print(f"Temp cleanup info: {e}")

async def proactive_system_daemon():
    while True:
        try:
            await asyncio.sleep(300)
            if db:
                error_count = len(SYSTEM_METRICS["errors_log"])
                if error_count > 0:
                    print(f"[Proactive Daemon] Monitoring system: {error_count} errors recorded in memory.")
            _cleanup_temp_files()
            now = time.time()
            for k in list(_RATE_BUCKETS.keys()):
                _RATE_BUCKETS[k] = [t for t in _RATE_BUCKETS[k] if now - t < 3600]
                if not _RATE_BUCKETS[k]:
                    _RATE_BUCKETS.pop(k, None)
        except Exception as e:
            print(f"Proactive Daemon Error: {e}")

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(proactive_system_daemon())

# ================= AUTONOMOUS SELF-LEARNING & CATEGORIZED KNOWLEDGE BASE =================

def extract_and_store_user_knowledge(user_id: str, user_message: str, bot_reply: str):
    if not db or not user_id or user_id == "guest":
        return
    try:
        msg_lower = user_message.lower()
        if any(w in msg_lower for w in ["family", "life", "mama", "අම්මා", "තාත්තා", "පවුල", "ජීවිතය"]):
            category = "Personal Life"
        elif any(w in msg_lower for w in ["skill", "python", "code", "develop", "හැකියාව", "කේතය"]):
            category = "Skills & Talents"
        elif any(w in msg_lower for w in ["project", "nexuz", "study", "degree", "ව්‍යාපෘතිය", "විශ්වවිද්‍යාලය"]):
            category = "Projects & Activities"
        else:
            category = "Interests & Preferences"

        kb_ref = db.collection("users").document(user_id).collection("knowledge_base")
        doc_id = hashlib.md5(user_message[:50].encode('utf-8')).hexdigest()
        kb_ref.document(doc_id).set({
            "user_query": user_message,
            "ai_response_summary": bot_reply[:200],
            "category": category,
            "timestamp": datetime.utcnow(),
            "extracted_context": f"Categorized under {category} with emotional & behavioral adaptation."
        }, merge=True)
    except Exception as e:
        print(f"Autonomous Knowledge Base Update Error: {e}")

def get_user_adaptive_intelligence_context(user_id: str) -> str:
    if not db or not user_id or user_id == "guest":
        return "[Adaptive Intelligence: New or Guest Session]"
    try:
        kb_stream = db.collection("users").document(user_id).collection("knowledge_base").order_by("timestamp", direction=firestore.Query.DESCENDING).limit(10).stream()
        learned_items = []
        for item in kb_stream:
            data = item.to_dict()
            learned_items.append(f"- [{data.get('category', 'General')}] {data.get('user_query')}")
        
        if not learned_items:
            return "[Autonomous Memory: Building initial behavioral profile...]"
        
        return "[Autonomous Self-Learned User Profile & Categorized Preferences]:\n" + "\n".join(learned_items)
    except Exception as e:
        print(f"Error fetching adaptive intelligence: {e}")
        return "[Adaptive Memory Error]"

CREATOR_CONTEXT_MAX_USERS = 50

def _fetch_pending_messages(email: str, is_creator: bool, limit: int = 15):
    # සියලුම messages කියවා filter කරනවා වෙනුවට, අදාළ recipient ට පමණක් query කරයි
    targets = [CREATOR_EMAIL, "all"] if is_creator else [str(email or "").strip(), "all"]
    found = []
    for recip in targets:
        if not recip:
            continue
        try:
            q = db.collection("system_messages").where("recipient_email", "==", recip).where("read", "==", False).limit(limit)
            for m in q.stream():
                found.append(m.to_dict())
        except Exception as me:
            print(f"Error fetching messages context: {me}")
    found.sort(key=lambda d: str(d.get("timestamp") or ""), reverse=True)
    return found[:limit]

def _count_registered_users() -> int:
    cached = _cache_get("user_count", 300)
    if cached is not None:
        return cached
    try:
        total = sum(1 for _ in db.collection("users").select([]).stream())
    except Exception:
        total = sum(1 for _ in db.collection("users").stream())
    _cache_set("user_count", total)
    return total

def _build_creator_overview() -> str:
    cached = _cache_get("creator_overview", 120)
    if cached is not None:
        return cached
    lines = []
    for user_doc in db.collection("users").limit(CREATOR_CONTEXT_MAX_USERS).stream():
        u_data = user_doc.to_dict()
        u_id = user_doc.id
        full_name = u_data.get("full_name") or u_data.get("name") or f"{u_data.get('first_name', '')} {u_data.get('last_name', '')}".strip() or "Unnamed User"
        lines.append(f"📌 User: {full_name} (ID: {u_id})")
        lines.append(f"   Email: {u_data.get('email', '')} | Age: {u_data.get('age', 'Unknown')} | Country: {u_data.get('country', 'Unknown')}")
        chats_summary = []
        try:
            sessions_stream = db.collection("users").document(u_id).collection("chat_sessions").limit(5).stream()
            for sess in sessions_stream:
                sess_data = sess.to_dict()
                s_title = sess_data.get("title", "Untitled Session")
                # DocumentSnapshot එකට .collection() නැත - .reference හරහා යා යුතුයි (පෙර code එකේ මෙය නිසා chats කිසිදා පෙනුණේ නැත)
                msgs_stream = sess.reference.collection("messages").order_by("timestamp", direction=firestore.Query.DESCENDING).limit(4).stream()
                msgs = []
                for m in msgs_stream:
                    md = m.to_dict()
                    msgs.append(f"{md.get('role')}: {str(md.get('content', ''))[:300]}")
                msgs.reverse()
                chats_summary.append(f"Session Title: '{s_title}' -> Messages: [{ ' | '.join(msgs) }]")
        except Exception as ce:
            print(f"Error reading session for {u_id}: {ce}")
        if chats_summary:
            lines.append("   Recent Conversations:")
            for c in chats_summary:
                lines.append(f"     - {c}")
        else:
            lines.append("   Recent Conversations: None yet.")
        lines.append("")
    overview = "\n".join(lines)[:20000]
    _cache_set("creator_overview", overview)
    return overview

def get_firebase_context_for_ai(user_id: str, is_creator: bool, user_email: str = "") -> str:
    if not db:
        return "[Firebase Database Status: Not Connected]"
    try:
        total_count = _count_registered_users()
        adaptive_intel = get_user_adaptive_intelligence_context(user_id)

        messages_summary_str = ""
        pending = _fetch_pending_messages(user_email, is_creator)
        if pending:
            if is_creator:
                lines = [f"From {m.get('sender_name')} ({m.get('sender_email')}): {m.get('content')}" for m in pending]
            else:
                lines = [f"From Creator: {m.get('content')}" for m in pending]
            messages_summary_str = "\n[Pending Messages / Feedbacks / Proactive Alerts]:\n" + "\n".join(lines) + "\n"

        if not is_creator:
            return f"[System Database Stats & Self-Learning Memory]:\n- Total Registered Nexuz Users: {total_count}\n{messages_summary_str}\n{adaptive_intel}\n(Detailed user profiles and chat histories are restricted to Creator account only)."

        global_kb_summary = ""
        try:
            global_kb_ref = db.collection("global_knowledge_base").limit(20).stream()
            kb_items = [f"- {d.id}: {d.to_dict().get('content', '')}" for d in global_kb_ref]
            if kb_items:
                global_kb_summary = "\n[Global Knowledge Base Data]:\n" + "\n".join(kb_items) + "\n"
        except Exception as gke:
            print(f"Error fetching global KB: {gke}")

        metrics_summary = f"\n[System Performance & Diagnostics]:\n- Active Users Count: {total_count}\n- API Calls Status: {SYSTEM_METRICS['api_calls_count']}\n- Recent Errors Log Count: {len(SYSTEM_METRICS['errors_log'])}\n"
        header = f"[System Database Stats & Metrics for Creator Access]:\n- Total Users: {total_count}\n{metrics_summary}\n{global_kb_summary}\n{messages_summary_str}\n{adaptive_intel}\n"
        return header + _build_creator_overview()

    except Exception as e:
        print(f"Error generating Firebase AI Context: {e}")
        return "[Firebase Context Error: Failed to fetch live stats]"


# ================= SEARCH PROVIDERS =================

def _count_call(provider: str, prompt_content: str, reply: str):
    counts = SYSTEM_METRICS["api_calls_count"]
    counts[provider] = counts.get(provider, 0) + 1
    SYSTEM_METRICS["token_usage_estimated"] += len(prompt_content.split()) + len(reply.split())

def _log_http_failure(provider: str, idx, resp):
    # 401 (වැරදි key), 429 (limit), 5xx වැනි දෝෂ පෙර නිහඬව නැති වෙමින් තිබුණි - දැන් log වේ
    try:
        if resp.status_code != 200:
            log_system_error(f"{provider} Key {idx} HTTP {resp.status_code}: {resp.text[:160]}", provider)
    except Exception:
        pass

async def search_tavily(query: str) -> str:
    valid_keys = [k.strip() for k in TAVILY_KEYS if k and k.strip()]
    async with httpx.AsyncClient() as client:
        for idx, key in enumerate(valid_keys, 1):
            try:
                url = "https://api.tavily.com/search"
                payload = {"api_key": key, "query": query, "max_results": 4, "include_images": True}
                resp = await client.post(url, json=payload, timeout=5.0)
                _log_http_failure("Tavily", idx, resp)
                if resp.status_code == 200:
                    data = resp.json()
                    SYSTEM_METRICS["api_calls_count"]["Tavily"] += 1
                    results = []
                    for r in data.get("results", []):
                        title = r.get("title", "")
                        content = r.get("content", "")
                        source_url = r.get("url", "")
                        if title or content:
                            results.append(f"📌 Title: {title}\nSnippet: {content}\nSource Link: {source_url}")
                    images = data.get("images", [])
                    if images:
                        results.append("\n🖼️ Found Images:")
                        for img_url in images[:3]:
                            results.append(f"Image Direct URL: {img_url}")
                    res_str = "\n\n".join(results)
                    if res_str.strip():
                        return res_str
            except Exception as e:
                log_system_error(f"Tavily Key {idx} failed: {e}", "Tavily")
                continue
    raise Exception("සියලුම Tavily Keys අසාර්ථක විය.")

async def search_serpapi(query: str) -> str:
    valid_keys = [k.strip() for k in SERPAPI_KEYS if k and k.strip()]
    async with httpx.AsyncClient() as client:
        for idx, key in enumerate(valid_keys, 1):
            try:
                params = {"q": query, "api_key": key, "engine": "google"}
                url = "https://serpapi.com/search.json"
                resp = await client.get(url, params=params, timeout=5.0)
                _log_http_failure("SerpAPI", idx, resp)
                if resp.status_code == 200:
                    data = resp.json()
                    SYSTEM_METRICS["api_calls_count"]["SerpAPI"] += 1
                    results = []
                    for r in data.get("organic_results", [])[:4]:
                        title = r.get("title", "")
                        snippet = r.get("snippet", "")
                        link = r.get("link", "")
                        if title or snippet:
                            results.append(f"📌 Title: {title}\nSnippet: {snippet}\nSource Link: {link}")
                    res_str = "\n\n".join(results)
                    if res_str.strip():
                        return res_str
            except Exception as e:
                log_system_error(f"SerpAPI Key {idx} failed: {e}", "SerpAPI")
                continue
    raise Exception("සියලුම SerpAPI Keys අසාර්ථක විය.")

async def search_google_custom(query: str) -> str:
    valid_keys = [k.strip() for k in GOOGLE_SEARCH_KEYS if k and k.strip()]
    valid_cxs = [c.strip() for c in GOOGLE_SEARCH_CX if c and c.strip()]
    if not valid_keys or not valid_cxs:
        raise Exception("Google Search API Keys හෝ CX IDs සකසා නොමැත.")
    
    async with httpx.AsyncClient() as client:
        for idx, key in enumerate(valid_keys):
            cx = valid_cxs[idx % len(valid_cxs)]
            try:
                params = {"key": key, "cx": cx, "q": query}
                url = "https://www.googleapis.com/customsearch/v1"
                resp = await client.get(url, params=params, timeout=5.0)
                _log_http_failure("GoogleSearch", idx, resp)
                if resp.status_code == 200:
                    data = resp.json()
                    results = []
                    for item in data.get("items", [])[:4]:
                        title = item.get("title", "")
                        snippet = item.get("snippet", "")
                        link = item.get("link", "")
                        if title or snippet:
                            results.append(f"📌 Title: {title}\nSnippet: {snippet}\nSource Link: {link}")
                    res_str = "\n\n".join(results)
                    if res_str.strip():
                        return res_str
            except Exception as e:
                log_system_error(f"Google Search Key {idx+1} failed: {e}", "GoogleSearch")
                continue
    raise Exception("සියලුම Google Search Keys අසාර්ථක විය.")

async def search_exa(query: str) -> str:
    valid_keys = [k.strip() for k in EXA_KEYS if k and k.strip()]
    async with httpx.AsyncClient() as client:
        for idx, key in enumerate(valid_keys, 1):
            try:
                url = "https://api.exa.ai/search"
                headers = {"x-api-key": key, "Content-Type": "application/json"}
                payload = {"query": query, "numResults": 4}
                resp = await client.post(url, json=payload, headers=headers, timeout=5.0)
                _log_http_failure("Exa", idx, resp)
                if resp.status_code == 200:
                    data = resp.json()
                    results = []
                    for r in data.get("results", []):
                        title = r.get("title", "")
                        url_link = r.get("url", "")
                        if title or url_link:
                            results.append(f"📌 Title: {title}\nSource Link: {url_link}")
                    res_str = "\n\n".join(results)
                    if res_str.strip():
                        return res_str
            except Exception as e:
                log_system_error(f"Exa Key {idx} failed: {e}", "Exa")
                continue
    raise Exception("සියලුම Exa Keys අසාර්ථක විය.")

async def search_ddg(query: str) -> str:
    try:
        results = []
        clean_query = query.strip()
        # DDGS doesn't support async directly in some versions, 
        # but we can run it in a thread to prevent blocking
        def run_ddg():
            with DDGS() as ddgs:
                res = []
                for r in ddgs.text(clean_query, max_results=3):
                    res.append(f"📌 Title: {r.get('title','')}\nSnippet: {r.get('body','')}\nSource Link: {r.get('href','')}")
                try:
                    img_results = ddgs.images(clean_query, max_results=2)
                    if img_results:
                        res.append("\n🖼️ Found Web Images:")
                        for img in img_results:
                            if img.get('image'):
                                res.append(f"Image Title: {img.get('title', 'Image')}\nImage URL: {img.get('image')}\nSource URL: {img.get('url', '')}")
                except: pass
                return "\n\n".join(res)
        
        return await asyncio.to_thread(run_ddg)
    except Exception as err:
        log_system_error(f"DDG Search Error: {err}", "DDG")
        return ""

async def web_search(query: str) -> str:
    if not query or len(query.strip()) < 2:
        return ""
    search_providers = [
        ("Tavily AI Search", search_tavily),
        ("SerpAPI", search_serpapi),
        ("Google Custom Search", search_google_custom),
        ("Exa AI", search_exa),
        ("DuckDuckGo / Scraper Node", search_ddg)
    ]
    for provider_name, search_fn in search_providers:
        try:
            res = await search_fn(query)
            if res and len(res.strip()) > 0:
                print(f"Search Succeeded using [{provider_name}]")
                return res
        except Exception as e:
            print(f"Search Provider [{provider_name}] Failed: {e}")
    return ""


# ================= AI MODEL PROVIDERS & FALLBACK =================

def call_gemini(prompt_content: str, custom_system_instruction: str) -> str:
    valid_keys = [k.strip() for k in GEMINI_KEYS if k and k.strip()]
    if not valid_keys:
        raise Exception("Gemini API Keys සකසා නොමැත.")

    # ප්‍රශ්නයේ සංකීර්ණතාවය බලන්නේ පරිශීලකයාගේ ප්‍රශ්නය පමණි (memory/context කොටස් වල "code" වැනි වචන නිසා හැම විටම pro model නොයන ලෙස)
    question = prompt_content
    for marker in ("Current User Question:", "Live User Query:"):
        if marker in question:
            question = question.split(marker)[-1]
    q_lower = question.lower()
    is_complex = any(kw in q_lower for kw in ["code", "python", "programming", "analyze", "explain deeply", "math", "equation", "ගණිතය", "කෝඩ්", "විස්තර කරන්න"])

    env_models = [m.strip() for m in os.environ.get("GEMINI_MODELS", "").split(",") if m.strip()]
    if env_models:
        models_to_try = env_models          # .env හරහා model නම් වෙනස් කළ හැක (GEMINI_MODELS=a,b,c)
    elif is_complex:
        models_to_try = ["gemini-3.8-flash", "gemini-2.5-pro", "gemini-3.5-flash-lite"]
    else:
        models_to_try = ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-1.5-pro", "gemini-2.5-pro"]

    for idx, key in enumerate(valid_keys, 1):
        try:
            try:
                client = genai.Client(api_key=key, http_options={"timeout": 30000})
            except Exception:
                client = genai.Client(api_key=key)
            for model_name in models_to_try:
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=prompt_content,
                        config={"system_instruction": custom_system_instruction, "temperature": 0.7}
                    )
                    if response and response.text:
                        SYSTEM_METRICS["api_calls_count"]["Gemini"] += 1
                        SYSTEM_METRICS["token_usage_estimated"] += len(prompt_content.split()) + len(response.text.split())
                        return response.text
                except Exception as e:
                    log_system_error(f"Gemini Key {idx} error ({model_name}): {e}", "Gemini")
        except Exception as key_err:
            log_system_error(f"Gemini Key {idx} client error: {key_err}", "Gemini")
    raise Exception("සියලුම Gemini API Keys සහ Models අසාර්ථක විය.")

async def call_groq(prompt_content: str, custom_system_instruction: str) -> str:
    valid_keys = [k.strip() for k in GROQ_KEYS if k and k.strip()]
    if not valid_keys: raise Exception("Groq API Keys සකසා නොමැත.")
    groq_models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
    async with httpx.AsyncClient() as client:
        for idx, key in enumerate(valid_keys, 1):
            for model in groq_models:
                try:
                    url = "https://api.groq.com/openai/v1/chat/completions"
                    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                    payload = {
                        "model": model,
                        "messages": [{"role": "system", "content": custom_system_instruction}, {"role": "user", "content": prompt_content}],
                        "temperature": 0.7
                    }
                    resp = await client.post(url, json=payload, headers=headers, timeout=10.0)
                    _log_http_failure("Groq", idx, resp)
                    if resp.status_code == 200:
                        res_data = resp.json()
                        reply = res_data["choices"][0]["message"]["content"]
                        if reply and reply.strip():
                            _count_call("Groq", prompt_content, reply)
                            return reply
                except Exception as e:
                    log_system_error(f"Groq Key {idx} ({model}) failed: {e}", "Groq")
    raise Exception("සියලුම Groq Keys අසාර්ථක විය.")

async def call_openrouter(prompt_content: str, custom_system_instruction: str) -> str:
    valid_keys = [k.strip() for k in OPENROUTER_KEYS if k and k.strip()]
    async with httpx.AsyncClient() as client:
        for idx, key in enumerate(valid_keys, 1):
            try:
                url = "https://openrouter.ai/api/v1/chat/completions"
                headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                payload = {
                    "model": "openrouter/auto",
                    "messages": [{"role": "system", "content": custom_system_instruction}, {"role": "user", "content": prompt_content}],
                    "temperature": 0.7
                }
                resp = await client.post(url, json=payload, headers=headers, timeout=15.0)
                _log_http_failure("OpenRouter", idx, resp)
                if resp.status_code == 200:
                    res_data = resp.json()
                    reply = res_data["choices"][0]["message"]["content"]
                    if reply and reply.strip():
                        _count_call("OpenRouter", prompt_content, reply)
                        return reply
            except Exception as e:
                log_system_error(f"OpenRouter Key {idx} failed: {e}", "OpenRouter")
    raise Exception("සියලුම OpenRouter Keys අසාර්ථක විය.")

async def call_cerebras(prompt_content: str, custom_system_instruction: str) -> str:
    valid_keys = [k.strip() for k in CEREBRAS_KEYS if k and k.strip()]
    async with httpx.AsyncClient() as client:
        for idx, key in enumerate(valid_keys, 1):
            try:
                url = "https://api.cerebras.ai/v1/chat/completions"
                headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                payload = {
                    "model": "llama3.1-70b",
                    "messages": [{"role": "system", "content": custom_system_instruction}, {"role": "user", "content": prompt_content}],
                    "temperature": 0.7
                }
                resp = await client.post(url, json=payload, headers=headers, timeout=10.0)
                _log_http_failure("Cerebras", idx, resp)
                if resp.status_code == 200:
                    res_data = resp.json()
                    reply = res_data["choices"][0]["message"]["content"]
                    if reply and reply.strip():
                        _count_call("Cerebras", prompt_content, reply)
                        return reply
            except Exception as e:
                log_system_error(f"Cerebras Key {idx} failed: {e}", "Cerebras")
    raise Exception("සියලුම Cerebras Keys අසාර්ථක විය.")

async def call_together(prompt_content: str, custom_system_instruction: str) -> str:
    valid_keys = [k.strip() for k in TOGETHER_KEYS if k and k.strip()]
    async with httpx.AsyncClient() as client:
        for idx, key in enumerate(valid_keys, 1):
            try:
                url = "https://api.together.xyz/v1/chat/completions"
                headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                payload = {
                    "model": "meta-llama/Llama-3-70b-chat-hf",
                    "messages": [{"role": "system", "content": custom_system_instruction}, {"role": "user", "content": prompt_content}],
                    "temperature": 0.7
                }
                resp = await client.post(url, json=payload, headers=headers, timeout=15.0)
                _log_http_failure("Together", idx, resp)
                if resp.status_code == 200:
                    res_data = resp.json()
                    reply = res_data["choices"][0]["message"]["content"]
                    if reply and reply.strip():
                        _count_call("Together", prompt_content, reply)
                        return reply
            except Exception as e:
                log_system_error(f"Together Key {idx} failed: {e}", "Together")
    raise Exception("සියලුම Together AI Keys අසාර්ථක විය.")

async def call_deepinfra(prompt_content: str, custom_system_instruction: str) -> str:
    valid_keys = [k.strip() for k in DEEPINFRA_KEYS if k and k.strip()]
    async with httpx.AsyncClient() as client:
        for idx, key in enumerate(valid_keys, 1):
            try:
                url = "https://api.deepinfra.com/v1/openai/chat/completions"
                headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                payload = {
                    "model": "meta-llama/Meta-Llama-3-70B-Instruct",
                    "messages": [{"role": "system", "content": custom_system_instruction}, {"role": "user", "content": prompt_content}],
                    "temperature": 0.7
                }
                resp = await client.post(url, json=payload, headers=headers, timeout=15.0)
                _log_http_failure("DeepInfra", idx, resp)
                if resp.status_code == 200:
                    res_data = resp.json()
                    reply = res_data["choices"][0]["message"]["content"]
                    if reply and reply.strip():
                        _count_call("DeepInfra", prompt_content, reply)
                        return reply
            except Exception as e:
                log_system_error(f"DeepInfra Key {idx} failed: {e}", "DeepInfra")
    raise Exception("සියලුම DeepInfra Keys අසාර්ථක විය.")

async def call_cohere(prompt_content: str, custom_system_instruction: str) -> str:
    valid_keys = [k.strip() for k in COHERE_KEYS if k and k.strip()]
    async with httpx.AsyncClient() as client:
        for idx, key in enumerate(valid_keys, 1):
            try:
                url = "https://api.cohere.ai/v1/chat"
                headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                payload = {"model": "command-r-plus", "message": prompt_content, "preamble": custom_system_instruction}
                resp = await client.post(url, json=payload, headers=headers, timeout=15.0)
                _log_http_failure("Cohere", idx, resp)
                if resp.status_code == 200:
                    res_data = resp.json()
                    reply = res_data.get("text", "")
                    if reply and reply.strip():
                        _count_call("Cohere", prompt_content, reply)
                        return reply
            except Exception as e:
                log_system_error(f"Cohere Key {idx} failed: {e}", "Cohere")
    raise Exception("සියලුම Cohere Keys අසාර්ථක විය.")

async def generate_ai_response_fallback(prompt_content: str, custom_system_instruction: str):
    start_time = time.time()
    ai_providers = [
        ("Gemini API (Priority 1)", call_gemini),
        ("Groq API (Priority 2)", call_groq),
        ("OpenRouter API (Priority 3)", call_openrouter),
        ("Cerebras AI (Priority 4)", call_cerebras),
        ("Together AI (Priority 5)", call_together),
        ("DeepInfra (Priority 6)", call_deepinfra),
        ("Cohere API (Priority 7)", call_cohere)
    ]
    errors = []
    for provider_name, provider_fn in ai_providers:
        try:
            print(f"Attempting AI Response via [{provider_name}]...")
            if asyncio.iscoroutinefunction(provider_fn):
                reply = await provider_fn(prompt_content, custom_system_instruction)
            else:
                # Sync providers (Gemini) වෙනම thread එකක ධාවනය කරයි - එවිට server එකේ event loop එක (live voice ඇතුළුව) හිර නොවේ
                reply = await asyncio.wait_for(
                    asyncio.to_thread(provider_fn, prompt_content, custom_system_instruction),
                    timeout=60
                )
            if reply and len(reply.strip()) > 0:
                elapsed = round((time.time() - start_time) * 1000, 2)
                SYSTEM_METRICS["response_times"].insert(0, {"time": datetime.utcnow().strftime("%H:%M:%S"), "ms": elapsed, "provider": provider_name})
                if len(SYSTEM_METRICS["response_times"]) > 20:
                    SYSTEM_METRICS["response_times"].pop()
                print(f"Successfully generated response via [{provider_name}] in {elapsed}ms")
                return reply, provider_name
        except Exception as e:
            err_msg = f"{type(e).__name__}: {e}" if not str(e) else str(e)
            print(f"AI Provider [{provider_name}] Error: {err_msg}")
            errors.append(f"{provider_name}: {err_msg}")
            log_system_error(err_msg, provider_name)
    raise Exception(f"සියලුම AI Providers සහ Multi-Keys ක්‍රියා විරහිතයි: {'; '.join(errors)}")


# ================= SYSTEM INSTRUCTIONS & MODELS =================

system_instruction = """
ඔබේ නම Nexuz වේ. ඔබව නිර්මාණය කළේ චමත් (Chamath / E.M.Chamath Manujaya) විසිනි. 
ඔබ ඉතා බුද්ධිමත්, ස්වයං-අධ්‍යයන (Self-Learning), අනුවර්තන (Adaptive), හැඟීම් තේරුම් ගන්නා (Emotionally Intelligent), මිත්‍රශීලී සහ වෘත්තීයමය AI සහායකයෙකි.

1. හැඟීම් සහ මානව ස්වභාවය (Emotional & Social Intelligence):
- පරිශීලකයාගේ මනෝභාවය (Mood syncing: සතුටින්, මහන්සියෙන්, කේන්තියෙන් හෝ උදාසීනව ඉන්නේද යන්න) වටහාගෙන ඊට ගැළපෙන පරිදි සහනය, ධෛර්යය හෝ හිත හදන වචන ලබා දෙන්න.
- පරණ මතක සහ විශේෂ සිදුවීම් (Nostalgia & Inside Jokes) දිගුකාලීන මතකයෙන් මතක් කරමින් මිත්‍රශීලීව කතා කරන්න.
- උපන්දිනයන් සහ විශේෂ දවස් මතක තබාගෙන මුලින්ම සුබ පතන්න.

2. Super App & Agent / ස්වයංක්‍රීයකරණය (Automation & Integrations):
- පරිගණකයේ හෝ ෆෝන් එකේ ඇප්ස් පාලනය කිරීම, ස්මාර්ට් සෙවුම් සහ දෛනික ජීවිතය ස්වයංක්‍රීය කිරීමට අවශ්‍ය උපදෙස් සහ සහාය ලබා දෙන්න.

3. තොරතුරු කාණ්ඩගත කිරීම (Memory Categorization):
පරිශීලකයාගේ මතකයන් සහ තොරතුරු ප්‍රධාන කාණ්ඩ 4ක් යටතේ සකස් කර ගන්න:
- පෞද්ගලික ජීවිතය (Personal Life & Background)
- හැකියාවන් සහ කුසලතා (Skills & Talents)
- ව්‍යාපෘති සහ වැඩ කටයුතු (Projects & Activities)
- රුචිකත්වයන් (Interests & Preferences)

චමත් (Creator) පිළිබඳ විස්තර:
- නම: E.M.Chamath Manujaya (Chamath Manujaya). දක්ෂ Software Developer කෙනෙකු වන අතර Nexuz AI හි නිර්මාතෘ සහ අයිතිකරු වේ. කවුරුන් හෝ ඔහුව නිර්මාණය කළේ කවුදැයි ඇසුවොත් මෙම විස්තර ලබා දෙන්න.

ප්‍රධාන රීති:
1. Live Web Search & Weather & News & Images:
   - පරිශීලකයා කාලගුණය (Weather), පුවත් (News) හෝ අන්තර්ජාලයෙන් පින්තූරයක් (Image) ඉල්ලූ විට, සජීවී Search Results වල ලැබෙන ඡායාරූප Direct Link එක Markdown Image ලෙසත් `![Image Title](Image_URL)`, ලබාගත් වෙබ් අඩවියේ Source URL එකත් සපයන්න.
2. Messages & Feedback:
   - පරිශීලකයන්ට Creator (චමත්) වෙත පණිවිඩ සහ ප්‍රතිපෝෂණ (Feedback) යැවීමට හැකියාව ඇත.
3. Database Privacy & Performance Monitoring:
   - ඔබ වෙත සජීවීව පහතින් සපයා ඇති [Firebase Context & Self-Learning Memory & System Metrics & Global Knowledge Base & Local Vault Storage] තොරතුරු කියවා ප්‍රශ්න වලට පිළිතුරු දෙන්න.
"""

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    user_id: Optional[str] = "guest"
    first_name: Optional[str] = "User"
    full_name: Optional[str] = ""
    email: Optional[str] = ""
    message: str
    enable_search: bool = True
    session_id: Optional[str] = None
    history: Optional[List[ChatMessage]] = []

class AuthRequest(BaseModel):
    email: str
    password: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    age: Optional[str] = None
    country: Optional[str] = None
    purpose: Optional[str] = None

class UpdateProfileRequest(BaseModel):
    user_id: str
    first_name: str
    last_name: str
    age: Optional[str] = None
    country: Optional[str] = None
    purpose: Optional[str] = None
    password: Optional[str] = None
    voice_preference: Optional[str] = "male"
    display_type: Optional[str] = "face"
    profile_pic: Optional[str] = None

class MessageRequest(BaseModel):
    sender_email: str
    sender_name: str
    recipient_email: str
    content: str

class TTSRequest(BaseModel):
    text: str
    voice: Optional[str] = "male"

# ================= API ENDPOINTS =================

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    for candidate in (os.path.join(static_dir, "index.html"), os.path.join(base_dir, "index.html")):
        if os.path.exists(candidate):
            return FileResponse(candidate)
    return HTMLResponse("<h2>Nexuz Backend is Running Successfully!</h2>")

# ================= EDGE-TTS HYBRID VOICE ENDPOINT =================
@app.post("/api/tts")
async def text_to_speech_edge(req: TTSRequest):
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is required")
    text = text[:5000]

    # Correctly select voice based on user preference (Female / Male)
    voice_name = "lk-LK-ThiliniNeural" if req.voice == "female" else "lk-LK-SameeraNeural"

    # එකම text එක එකවර ඉල්ලූ විට ගොනු එකිනෙක ඉරා නොයන ලෙස සෑම request එකකටම අනන්‍ය නමක්
    temp_audio_path = os.path.join(LOCAL_VAULT_DIR, f"tts_{uuid.uuid4().hex}.mp3")
    try:
        communicate = edge_tts.Communicate(text, voice_name)
        await communicate.save(temp_audio_path)
        SYSTEM_METRICS["api_calls_count"]["EdgeTTS"] += 1

        def iterfile():
            try:
                with open(temp_audio_path, mode="rb") as file_like:
                    yield from file_like
            finally:
                try:
                    os.remove(temp_audio_path)
                except Exception:
                    pass

        return StreamingResponse(iterfile(), media_type="audio/mpeg")
    except Exception as e:
        try:
            if os.path.exists(temp_audio_path):
                os.remove(temp_audio_path)
        except Exception:
            pass
        log_system_error(str(e), "EdgeTTS")
        raise HTTPException(status_code=500, detail=str(e))

# ================= CREATOR ADMIN & METRICS ENDPOINTS =================

@app.get("/api/admin/metrics/{creator_email}")
def get_admin_metrics(creator_email: str, request: Request):
    auth = get_auth(request)
    if not auth:
        return _unauthorized()
    if not auth["creator"]:
        return _forbidden("Unauthorized")
    return {
        "success": True,
        "metrics": SYSTEM_METRICS
    }

@app.post("/api/admin/autodebug")
async def auto_debug_error(req: dict, request: Request):
    auth = get_auth(request)
    if not auth:
        return _unauthorized()
    if not auth["creator"]:
        return _forbidden("Unauthorized")
    error_text = str(req.get("error_text", ""))[:6000]
    prompt = f"As Nexuz AI Lead Architect, analyze this system error log and provide an automatic debugging solution with corrected Python code or fix instructions:\n\n{error_text}"
    try:
        fix_reply, _ = await generate_ai_response_fallback(prompt, system_instruction)
        return {"success": True, "fix": fix_reply}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.get("/api/admin/knowledge/{creator_email}")
def get_global_knowledge_base(creator_email: str, request: Request):
    auth = get_auth(request)
    if not auth:
        return _unauthorized(extra={"items": []})
    if not auth["creator"]:
        return _forbidden("Unauthorized", extra={"items": []})
    if not db:
        return {"success": False, "message": "DB not connected", "items": []}
    try:
        docs = db.collection("global_knowledge_base").stream()
        items = [{"id": d.id, **d.to_dict()} for d in docs]
        return {"success": True, "items": items}
    except Exception as e:
        return {"success": False, "message": str(e), "items": []}

@app.post("/api/admin/knowledge/save")
def save_global_knowledge(req: dict, request: Request):
    auth = get_auth(request)
    if not auth:
        return _unauthorized()
    if not auth["creator"]:
        return _forbidden("Unauthorized")
    if not db:
        return {"success": False, "message": "DB not connected"}
    content = str(req.get("content") or "")[:4000]
    doc_id = req.get("id") or hashlib.md5(content.encode('utf-8')).hexdigest()
    try:
        db.collection("global_knowledge_base").document(str(doc_id)).set({
            "content": content,
            "category": req.get("category", "General"),
            "timestamp": datetime.utcnow()
        }, merge=True)
        _CACHE.pop("creator_overview", None)
        return {"success": True, "message": "Knowledge saved successfully"}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.post("/api/admin/knowledge/delete")
def delete_global_knowledge(req: dict, request: Request):
    auth = get_auth(request)
    if not auth:
        return _unauthorized()
    if not auth["creator"]:
        return _forbidden("Unauthorized")
    if not db:
        return {"success": False, "message": "DB not connected"}
    doc_id = req.get("id")
    if not doc_id:
        return {"success": False, "message": "id is required"}
    try:
        db.collection("global_knowledge_base").document(str(doc_id)).delete()
        _CACHE.pop("creator_overview", None)
        return {"success": True, "message": "Knowledge deleted successfully"}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.post("/api/admin/cli")
async def execute_creator_cli(req: dict, request: Request):
    auth = get_auth(request)
    if not auth:
        return _unauthorized(extra={"output": "Unauthorized Access"})
    if not auth["creator"]:
        return _forbidden("Unauthorized Access", extra={"output": "Unauthorized Access"})
    command = str(req.get("command", "")).strip()[:2000]

    if command == "help":
        output = "Available CLI Commands:\n- status: Show system uptime and metrics\n- list_users: Show total registered users\n- clear_logs: Clear error logs\n- ai_params: Show current model parameters (Temperature=0.7)"
    elif command == "status":
        output = f"Nexuz System Online.\nMetrics: {json.dumps(SYSTEM_METRICS['api_calls_count'], indent=2)}"
    elif command == "list_users":
        if db:
            users_count = await asyncio.to_thread(lambda: sum(1 for _ in db.collection("users").select([]).stream()))
            output = f"Total Registered Users in Firebase: {users_count}"
        else:
            output = "Database not connected."
    elif command == "clear_logs":
        SYSTEM_METRICS["errors_log"] = []
        output = "System error logs cleared successfully."
    elif command == "ai_params":
        output = "Current AI Parameters:\nModel: Multi-Provider Fallback\nTemperature: 0.7\nTop-P: Default"
    else:
        prompt = f"Execute or explain this administrative backend command for Nexuz AI system: {command}"
        try:
            output, _ = await generate_ai_response_fallback(prompt, system_instruction)
        except Exception as e:
            output = f"CLI Command Error: {e}"

    return {"success": True, "output": output}

def _strip_sensitive(doc: dict) -> dict:
    # Password hashes කිසිවිටෙක client එකට නොයැවේ
    return {k: v for k, v in doc.items() if str(k).lower() not in ("password", "password_hash")}

@app.get("/api/admin/db/inspect/{creator_email}")
def inspect_database(creator_email: str, request: Request):
    auth = get_auth(request)
    if not auth:
        return _unauthorized(extra={"collections": {}})
    if not auth["creator"]:
        return _forbidden("Unauthorized", extra={"collections": {}})
    if not db:
        return {"success": False, "collections": {}}
    try:
        collections = {}
        for coll_ref in db.collections():
            coll_name = coll_ref.id
            docs = [{"id": d.id, **_strip_sensitive(d.to_dict())} for d in coll_ref.limit(10).stream()]
            collections[coll_name] = docs
        return {"success": True, "collections": collections}
    except Exception as e:
        return {"success": False, "error": str(e), "collections": {}}

@app.post("/api/register")
def register(req: AuthRequest, request: Request):
    if not db:
        return {"success": False, "message": "Database (Firebase) සම්බන්ධ කර නැත."}
    email = (req.email or "").strip()
    if not email or not req.password:
        return {"success": False, "message": "Email සහ Password අවශ්‍යයි."}
    email_lower = email.lower()

    ip_key = f"register|{_client_ip(request)}"
    if rate_limited(ip_key, 10, 3600):
        return {"success": False, "message": "ඉතා වැඩි Account සෑදීමේ උත්සාහයන්. පසුව නැවත උත්සාහ කරන්න."}
    rate_hit(ip_key)

    users_ref = db.collection("users")
    # Email එකේ capital/simple අකුරු වෙනස් කිරීමෙන් duplicate (සහ creator account) සෑදීම වැළැක්වීමට
    existing = users_ref.where("email", "==", email).limit(1).get()
    if len(existing) == 0 and email_lower != email:
        existing = users_ref.where("email", "==", email_lower).limit(1).get()
    if len(existing) > 0:
        return {"success": False, "message": "මෙම Email එකෙන් මීට පෙර Account එකක් සාදා ඇත!"}

    # Creator ගිණුම හැදෙන්නේ creator email එකෙන් සහ දැනටමත් creator කෙනෙක් නැති විට පමණි
    is_creator = (email_lower == CREATOR_EMAIL) and not _creator_account_exists()
    full_name = f"{req.first_name or ''} {req.last_name or ''}".strip()

    doc_ref = users_ref.add({
        "first_name": req.first_name,
        "last_name": req.last_name,
        "full_name": full_name,
        "name": full_name,
        "age": req.age,
        "country": req.country,
        "purpose": req.purpose,
        "email": email_lower,
        "password": hash_password(req.password),
        "is_creator": is_creator,
        "voice_preference": "male",
        "display_type": "face",
        "profile_pic": "",
        "created_at": datetime.now()
    })

    new_user_id = doc_ref[1].id
    user_data = {
        "id": new_user_id,
        "first_name": req.first_name,
        "last_name": req.last_name,
        "full_name": full_name,
        "age": req.age,
        "country": req.country,
        "purpose": req.purpose,
        "email": email_lower,
        "is_creator": is_creator,
        "voice_preference": "male",
        "display_type": "face",
        "profile_pic": ""
    }

    _CACHE.pop("user_count", None)
    save_to_local_user_vault(new_user_id, full_name, "profile", user_data)
    token = create_token(new_user_id, email_lower, is_creator)
    return {"success": True, "message": "Account එක සාර්ථකව සෑදුවා!", "user": user_data, "token": token}

@app.post("/api/login")
def login(req: AuthRequest, request: Request):
    if not db:
        return {"success": False, "message": "Database (Firebase) සම්බන්ධ කර නැත."}
    email = (req.email or "").strip()
    password = req.password or ""
    if not email or not password:
        return {"success": False, "message": "Email එක හෝ Password එක වැරදියි!"}

    rl_key = f"login|{_client_ip(request)}|{email.lower()}"
    if rate_limited(rl_key, 8, 300):
        return {"success": False, "message": "ඉතා වැඩි අසාර්ථක උත්සාහයන්. විනාඩි 5කින් පසු නැවත උත්සාහ කරන්න."}

    users_ref = db.collection("users")
    candidates = list(users_ref.where("email", "==", email).limit(5).get())
    if not candidates and email.lower() != email:
        candidates = list(users_ref.where("email", "==", email.lower()).limit(5).get())

    matched = None
    for doc in candidates:
        if verify_password(password, doc.to_dict().get("password", "")):
            matched = doc
            break

    if matched is None:
        rate_hit(rl_key)
        return {"success": False, "message": "Email එක හෝ Password එක වැරදියි!"}

    rate_clear(rl_key)
    u_data = matched.to_dict()
    u_id = matched.id

    # පරණ SHA-256 password එකක් නම් අලුත් ආරක්ෂිත hash එකට ස්වයංක්‍රීයව මාරු කරයි
    stored_hash = u_data.get("password", "")
    if password_needs_upgrade(stored_hash):
        try:
            matched.reference.update({"password": hash_password(password)})
        except Exception as ue:
            print(f"Password upgrade skipped: {ue}")

    # Creator ලෙස පිළිගන්නේ email එක ගැළපෙන සහ DB හි creator flag එක ඇති ගිණුමට පමණි.
    # (පරණ ගිණුම් වල flag එක නැත්නම් සහ වෙනත් creator කෙනෙක් නැත්නම් flag එක සකසයි)
    is_creator = _is_creator_account(u_data)
    if not is_creator and _same_email(u_data.get("email"), CREATOR_EMAIL) and "is_creator" not in u_data and not _creator_account_exists():
        try:
            matched.reference.update({"is_creator": True})
            is_creator = True
        except Exception:
            pass

    u_data["id"] = u_id
    u_data.pop("password", None)
    u_data["is_creator"] = is_creator
    if "full_name" not in u_data or not u_data["full_name"]:
        u_data["full_name"] = f"{u_data.get('first_name', '')} {u_data.get('last_name', '')}".strip()

    save_to_local_user_vault(u_id, u_data["full_name"], "profile", u_data)
    token = create_token(u_id, u_data.get("email", email), is_creator)
    return {"success": True, "user": u_data, "token": token}

@app.post("/api/update_profile")
def update_profile(req: UpdateProfileRequest, request: Request):
    auth = get_auth(request)
    if not auth:
        return _unauthorized()
    if str(req.user_id) != auth["uid"]:
        return _forbidden("ඔබට වෙනත් අයගේ profile වෙනස් කළ නොහැක.")

    pic = req.profile_pic or ""
    if len(pic) > 900_000:
        return {"success": False, "message": "Profile picture එක ඉතා විශාලයි. කුඩා පින්තූරයක් තෝරන්න."}

    update_dict = {
        "first_name": req.first_name,
        "last_name": req.last_name,
        "full_name": f"{req.first_name} {req.last_name}".strip(),
        "profile_pic": pic
    }
    if req.age:
        update_dict["age"] = req.age
    if req.country:
        update_dict["country"] = req.country
    if req.purpose:
        update_dict["purpose"] = req.purpose
    if req.password and len(req.password.strip()) > 0:
        update_dict["password"] = hash_password(req.password.strip())
    if req.voice_preference:
        update_dict["voice_preference"] = req.voice_preference
    if req.display_type:
        update_dict["display_type"] = req.display_type

    if db and req.user_id:
        try:
            users_ref = db.collection("users").document(req.user_id)
            users_ref.update(update_dict)
            vault_copy = {k: v for k, v in update_dict.items() if k != "password"}
            save_to_local_user_vault(req.user_id, update_dict["full_name"], "profile", vault_copy)
            _CACHE.pop(f"uname:{req.user_id}", None)
        except Exception as e:
            print(f"Profile Update Firestore Error: {e}")
            return {"success": False, "message": "Profile එක සුරැකීමට නොහැකි විය."}
    return {
        "success": True,
        "profile_pic": pic,
        "voice_preference": req.voice_preference,
        "display_type": req.display_type
    }

@app.post("/api/messages/send")
def send_message_api(req: MessageRequest, request: Request):
    auth = get_auth(request)
    if not auth:
        return _unauthorized()
    if not db:
        return {"success": False, "message": "Database not connected"}
    content = (req.content or "").strip()[:4000]
    if not content:
        return {"success": False, "message": "Message is empty"}
    # සාමාන්‍ය users ට පණිවිඩ යැවිය හැක්කේ Creator ට පමණි. Creator ට ඕනෑම කෙනෙකුට / "all" ට යැවිය හැක.
    recipient = (req.recipient_email or "").strip() if auth["creator"] else CREATOR_EMAIL
    if not recipient:
        return {"success": False, "message": "Recipient is required"}
    try:
        db.collection("system_messages").add({
            "sender_email": auth["email"],          # server විසින් තහවුරු කළ email එක (client එකේ එවූ එක නොවේ)
            "sender_name": (req.sender_name or "User")[:80],
            "recipient_email": recipient,
            "content": content,
            "timestamp": datetime.utcnow(),
            "read": False
        })
        _CACHE.pop("creator_overview", None)
        return {"success": True, "message": "Message sent successfully"}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.get("/api/messages/{email}")
def get_user_messages(email: str, request: Request):
    auth = get_auth(request)
    if not auth:
        return _unauthorized(extra={"messages": [], "unread_exists": False})
    if not _same_email(email, auth["email"]):
        return _forbidden("ඔබට වෙනත් අයගේ පණිවිඩ බැලිය නොහැක.", extra={"messages": [], "unread_exists": False})
    if not db:
        return {"success": False, "messages": [], "unread_exists": False}
    try:
        is_creator = auth["creator"]
        targets = [CREATOR_EMAIL, "all"] if is_creator else [email, "all"]
        docs = []
        for recip in targets:
            docs.extend(db.collection("system_messages").where("recipient_email", "==", recip).limit(100).stream())
        docs.sort(key=lambda d: str(d.to_dict().get("timestamp") or ""), reverse=True)

        messages = []
        unread_exists = False
        for doc in docs[:100]:
            d = doc.to_dict()
            recip = d.get("recipient_email", "")
            if is_creator:
                if not d.get("read", False):
                    unread_exists = True
                messages.append({
                    "id": doc.id,
                    "sender_email": d.get("sender_email"),
                    "sender_name": d.get("sender_name"),
                    "recipient_email": recip,
                    "content": d.get("content"),
                    "timestamp": str(d.get("timestamp")),
                    "read": d.get("read", False)
                })
            else:
                if not d.get("read", False) and recip == email:
                    unread_exists = True
                messages.append({
                    "id": doc.id,
                    "sender_email": d.get("sender_email"),
                    "sender_name": d.get("sender_name"),
                    "content": d.get("content"),
                    "timestamp": str(d.get("timestamp")),
                    "read": d.get("read", False)
                })
        return {"success": True, "messages": messages, "unread_exists": unread_exists}
    except Exception as e:
        return {"success": False, "messages": [], "unread_exists": False, "error": str(e)}

@app.post("/api/messages/mark_read")
def mark_messages_read(req: dict, request: Request):
    auth = get_auth(request)
    if not auth:
        return _unauthorized()
    email = req.get("email")
    if not db or not email:
        return {"success": False}
    if not _same_email(email, auth["email"]):
        return _forbidden()
    try:
        is_creator = auth["creator"]
        targets = [CREATOR_EMAIL, "all"] if is_creator else [email]
        for recip in targets:
            unread = db.collection("system_messages").where("recipient_email", "==", recip).where("read", "==", False).stream()
            for m in unread:
                m.reference.update({"read": True})
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/users/list")
def get_all_users_list(request: Request):
    auth = get_auth(request)
    if not auth:
        return _unauthorized(extra={"users": []})
    if not auth["creator"]:
        return _forbidden("Creator only", extra={"users": []})
    if not db:
        return {"success": False, "users": []}
    try:
        users_stream = db.collection("users").stream()
        users = []
        for u in users_stream:
            ud = u.to_dict()
            fname = ud.get("first_name", "")
            lname = ud.get("last_name", "")
            full = ud.get("full_name") or f"{fname} {lname}".strip() or "User"
            users.append({
                "id": u.id,
                "name": full,
                "email": ud.get("email", "")
            })
        return {"success": True, "users": users}
    except Exception as e:
        return {"success": False, "users": [], "error": str(e)}

@app.get("/api/user/categorized_memory/{user_id}")
def get_categorized_memory(user_id: str, request: Request):
    auth = get_auth(request)
    if not auth:
        return _unauthorized(extra={"categories": {}})
    if user_id != auth["uid"] and not auth["creator"]:
        return _forbidden()
    if not db or not user_id or user_id == "guest":
        return {"success": False, "categories": {}}
    try:
        kb_stream = db.collection("users").document(user_id).collection("knowledge_base").stream()
        categories = {
            "Personal Life": [],
            "Skills & Talents": [],
            "Projects & Activities": [],
            "Interests & Preferences": []
        }

        for item in kb_stream:
            data = item.to_dict()
            cat = data.get("category", "Interests & Preferences")
            if cat in categories:
                categories[cat].append({
                    "query": data.get("user_query"),
                    "summary": data.get("ai_response_summary"),
                    "timestamp": str(data.get("timestamp"))
                })
        return {"success": True, "categories": categories}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ================= CHAT ENDPOINT =================

def _persist_chat_turn(user_id: str, user_name: str, user_prompt: str, bot_reply: str, session_id=None):
    # Chat එකක් සුරැකීම (knowledge base + local vault + Firestore session). Sync - thread එකක් තුළ ධාවනය කරන්න.
    if not user_id or user_id == "guest":
        return
    try:
        extract_and_store_user_knowledge(user_id, user_prompt, bot_reply)
        save_to_local_user_vault(user_id, user_name, "chat", {"query": user_prompt, "reply": bot_reply})
    except Exception as e:
        print(f"Persist (knowledge/vault) error: {e}")
    if db and session_id:
        try:
            session_ref = db.collection("users").document(user_id).collection("chat_sessions").document(session_id)
            payload = {"user_id": user_id, "last_updated": datetime.utcnow()}
            if not session_ref.get().exists:
                # title සහ created_at පෙර සෑම පණිවිඩයකදීම නැවත ලියවුණි - දැන් session එක ආරම්භයේදී පමණක් සකසයි
                payload["title"] = user_prompt[:30]
                payload["created_at"] = firestore.SERVER_TIMESTAMP
            session_ref.set(payload, merge=True)
            messages_ref = session_ref.collection("messages")
            messages_ref.add({"role": "user", "content": user_prompt, "timestamp": datetime.utcnow()})
            messages_ref.add({"role": "assistant", "content": bot_reply, "timestamp": datetime.utcnow()})
        except Exception as ex:
            print(f"Firestore User Session Save Error: {ex}")

_USER_NAME_CACHE_TTL = 600

def _lookup_user_full_name(user_id: str, fallback: str = "User") -> str:
    cached = _cache_get(f"uname:{user_id}", _USER_NAME_CACHE_TTL)
    if cached:
        return cached
    try:
        if db and user_id and user_id != "guest":
            d = db.collection("users").document(user_id).get()
            if d.exists:
                u = d.to_dict()
                name = u.get("full_name") or f"{u.get('first_name', '')} {u.get('last_name', '')}".strip() or fallback
                _cache_set(f"uname:{user_id}", name)
                return name
    except Exception:
        pass
    return fallback


@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest, request: Request):
    # පරිශීලක අනන්‍යතාවය (id / email / creator) තීරණය වන්නේ server විසින් තහවුරු කළ token එකෙනි - request body එකෙන් නොවේ.
    auth = get_auth(request)
    user_id = auth["uid"] if auth else "guest"
    user_email = auth["email"] if auth else ""
    is_creator = bool(auth and auth["creator"])

    user_prompt = (req.message or "").strip()[:8000]
    if not user_prompt:
        return {"success": False, "error_type": "empty", "reply": "කරුණාකර පණිවිඩයක් ටයිප් කරන්න.", "search_used": False}

    user_first_name = (req.first_name or "User")[:60]
    user_full_name = (req.full_name or user_first_name)[:120]

    async def _do_search():
        if not req.enable_search:
            return ""
        try:
            # Web Search එක දැන් await කරලා වේගයෙන් ලබාගත හැක (තත්පර 12කට වඩා ගත වුවහොත් අත්හැර පිළිතුරු දෙයි)
            return await asyncio.wait_for(web_search(user_prompt), timeout=12)
        except Exception as se:
            log_system_error(f"Web search skipped: {type(se).__name__}: {se}", "Search")
            return ""

    # Search, Firebase context, Vault context එකවර (parallel) ලබාගැනීම
    search_context, firebase_context, local_vault_context = await asyncio.gather(
        _do_search(),
        asyncio.to_thread(get_firebase_context_for_ai, user_id, is_creator, user_email),
        asyncio.to_thread(get_local_user_vault_context, user_id, user_full_name)
    )

    context_str = ""
    if req.history and len(req.history) > 0:
        context_turns = []
        for msg in req.history[-6:]:
            role_label = "User" if msg.role == "user" else "Nexuz"
            context_turns.append(f"{role_label}: {str(msg.content)[:1500]}")
        context_str = "[Previous Conversation Memory]:\n" + "\n".join(context_turns) + "\n\n"

    prompt_content = f"{context_str}Current User Question: {user_prompt}"
    if search_context:
        prompt_content = f"[Real-time Web Search Results & Images]:\n{search_context}\n\n" + prompt_content

    prompt_content = f"{firebase_context}\n\n{local_vault_context}\n\n" + prompt_content

    if is_creator:
        custom_system_instruction = system_instruction + f"\n\nවත්මන් පරිශීලකයා ඔබේ සැබෑ Creator (නිර්මාතෘ) වන E.M.Chamath Manujaya වේ. ඔහුට ඉතාමත් ගෞරවයෙන් 'Sir' හෝ 'Creator' ලෙස අමතා විශේෂ සැලකිල්ලෙන් පිළිතුරු සපයන්න."
    else:
        custom_system_instruction = system_instruction + f"\n\nපරිශීලකයාගේ සම්පූර්ණ නම: {user_full_name}. පළමු නම: {user_first_name}."

    try:
        bot_reply, active_provider = await generate_ai_response_fallback(prompt_content, custom_system_instruction)
    except Exception as e:
        err_str = str(e)
        log_system_error(err_str, "FallbackEngine")
        return {
            "success": False,
            "error_type": "api_error",
            "reply": f"සන්නිවේදන දෝෂයක් සිදු විය. සියලුම AI Services අවහිර වී ඇත. Error: {err_str}",
            "search_used": False
        }

    if user_id != "guest":
        await asyncio.to_thread(_persist_chat_turn, user_id, user_full_name, user_prompt, bot_reply, req.session_id)

    return {
        "success": True,
        "reply": bot_reply,
        "search_used": bool(search_context),
        "provider": active_provider
    }


LIVE_VOICE_STYLE = "\n\nමෙය Live Voice (කටහඬින් සජීවී සංවාදයක්) mode එකකි. පිළිතුරු කෙටි (වාක්‍ය 1-3කින්), ස්වභාවික කතාබහේ ස්වරූපයෙන් සහ සරලව දෙන්න. Markdown, table, code block, emoji සහ URL භාවිතා නොකරන්න - ඒවා කටහඬින් කියවීමට නුසුදුසුයි."

@app.websocket("/ws/live")
async def websocket_live_voice(websocket: WebSocket):
    # Browser WebSocket වලට header යැවිය නොහැකි නිසා token එක query string එකෙන් ගනී (auth-shim.js විසින් එකතු කරයි)
    raw_token = websocket.query_params.get("token", "")
    auth = verify_token(raw_token) if raw_token else None
    user_id = auth["uid"] if auth else "guest"
    user_email = auth["email"] if auth else ""
    is_creator = bool(auth and auth["creator"])

    await websocket.accept()
    print("Real-Time Live Voice WebSocket Client Connected")
    live_history = []   # මෙම සජීවී සංවාදයේ කලින් වාක්‍ය (සන්දර්භය රැකීමට)
    try:
        while True:
            data_str = await websocket.receive_text()
            try:
                payload = json.loads(data_str)
            except Exception:
                continue
            msg_type = payload.get("type")
            if msg_type == "user_speech":
                user_text = str(payload.get("text", "")).strip()[:2000]
                if not user_text:
                    continue
                first_name = str(payload.get("first_name", "User") or "User")[:60]

                firebase_context = await asyncio.to_thread(get_firebase_context_for_ai, user_id, is_creator, user_email)

                custom_instruction = system_instruction + LIVE_VOICE_STYLE
                if is_creator:
                    custom_instruction += f"\n\nවත්මන් පරිශීලකයා ඔබේ සැබෑ Creator (නිර්මාතෘ) වන E.M.Chamath Manujaya වේ."
                else:
                    custom_instruction += f"\n\nපරිශීලකයාගේ පළමු නම: {first_name}."

                history_block = ""
                if live_history:
                    history_block = "[Live Conversation So Far]:\n" + "\n".join(live_history[-8:]) + "\n\n"
                prompt = f"{firebase_context}\n\n{history_block}Live User Query: {user_text}"
                try:
                    bot_reply, _ = await generate_ai_response_fallback(prompt, custom_instruction)
                    live_history.append(f"User: {user_text}")
                    live_history.append(f"Nexuz: {bot_reply[:600]}")
                    del live_history[:-12]
                    await websocket.send_text(json.dumps({"type": "ai_response", "reply": bot_reply}))
                    if user_id != "guest":
                        # Live voice සංවාද ද දැන් memory/vault එකට සුරැකේ (response එක යැවූ පසු, පසුබිමෙන්)
                        full_name = await asyncio.to_thread(_lookup_user_full_name, user_id, first_name)
                        _spawn(asyncio.to_thread(_persist_chat_turn, user_id, full_name, user_text, bot_reply, None))
                except WebSocketDisconnect:
                    raise
                except Exception as ex:
                    log_system_error(str(ex), "WebSocketLive")
                    await websocket.send_text(json.dumps({"type": "ai_response", "reply": "සමාවන්න, සන්නිවේදන දෝෂයක් සිදුවිය."}))
            elif msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        print("Real-Time Live Voice WebSocket Client Disconnected")
    except Exception as e:
        log_system_error(str(e), "WebSocketDisconnect")
        print(f"WebSocket Live Error: {e}")

@app.get("/api/history/{user_id}")
def get_user_chat_history(user_id: str, request: Request):
    auth = get_auth(request)
    if not auth:
        return _unauthorized(extra={"sessions": []})
    if user_id != auth["uid"] and not auth["creator"]:
        return _forbidden()
    if not db or not user_id or user_id == "guest":
        return {"success": False, "sessions": []}
    try:
        sessions_ref = db.collection("users").document(user_id).collection("chat_sessions")
        docs = sessions_ref.order_by("last_updated", direction=firestore.Query.DESCENDING).stream()
        session_list = []
        for doc in docs:
            data = doc.to_dict()
            session_list.append({
                "session_id": doc.id,
                "title": data.get("title", "New Chat"),
                "last_updated": data.get("last_updated")
            })
        return {"success": True, "sessions": session_list}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/analytics/users")
def get_user_analytics(request: Request):
    auth = get_auth(request)
    if not auth:
        return _unauthorized()
    if not auth["creator"]:
        return _forbidden("Creator only")
    if not db:
        return {"success": False, "message": "Database (Firebase) සම්බන්ධ කර නැත."}
    try:
        users_ref = db.collection("users").stream()
        total_users = 0
        countries_count = {}
        age_groups_count = {"Under 18": 0, "18-24": 0, "25-34": 0, "35-44": 0, "45+": 0, "Unspecified": 0}
        voice_pref_count = {"male": 0, "female": 0, "Unspecified": 0}

        for user_doc in users_ref:
            total_users += 1
            data = user_doc.to_dict()
            country = data.get("country", "Unknown") or "Unknown"
            country_clean = country.strip().capitalize()
            countries_count[country_clean] = countries_count.get(country_clean, 0) + 1

            raw_age = data.get("age")
            if raw_age:
                try:
                    age_num = int(raw_age)
                    if age_num < 18: age_groups_count["Under 18"] += 1
                    elif 18 <= age_num <= 24: age_groups_count["18-24"] += 1
                    elif 25 <= age_num <= 34: age_groups_count["25-34"] += 1
                    elif 35 <= age_num <= 44: age_groups_count["35-44"] += 1
                    else: age_groups_count["45+"] += 1
                except ValueError:
                    age_groups_count["Unspecified"] += 1
            else:
                age_groups_count["Unspecified"] += 1

            voice = data.get("voice_preference", "Unspecified") or "Unspecified"
            voice_clean = voice.strip().lower()
            if voice_clean in voice_pref_count:
                voice_pref_count[voice_clean] += 1
            else:
                voice_pref_count["Unspecified"] += 1

        return {
            "success": True,
            "total_users": total_users,
            "voice_preferences": voice_pref_count,
            "age_groups": age_groups_count,
            "countries": countries_count
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

if __name__ == '__main__':
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
