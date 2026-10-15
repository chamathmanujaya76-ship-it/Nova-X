name=app_7.py
import os
import sys
import time
import hashlib
import json
import urllib.request
import urllib.parse
from datetime import datetime
from typing import Optional, List
from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from duckduckgo_search import DDGS
from google import genai
import firebase_admin
from firebase_admin import credentials, firestore

app = FastAPI(title="Nexuz AI - Autonomous Self-Learning Edition")

# ================= SYSTEM METRICS & LOGS TRACKER (CREATOR ADMIN) =================
SYSTEM_METRICS = {
    "api_calls_count": {
        "Gemini": 0, "Groq": 0, "OpenRouter": 0, "Cerebras": 0, 
        "Together": 0, "DeepInfra": 0, "Cohere": 0, "Tavily": 0, "SerpAPI": 0
    },
    "response_times": [],
    "errors_log": [],
    "token_usage_estimated": 0
}

def log_system_error(err_msg: str, provider: str = "System"):
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = {"time": timestamp, "provider": provider, "error": str(err_msg)}
    SYSTEM_METRICS["errors_log"].insert(0, log_entry)
    if len(SYSTEM_METRICS["errors_log"]) > 50:
        SYSTEM_METRICS["errors_log"].pop()

def get_base_path():
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

base_dir = get_base_path()
static_dir = os.path.join(base_dir, "static")

if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

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

# ================= SEARCH APIS & KEYS (PRIORITY ORDER) =================

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

def hash_password(password: str) -> str:
    return hashlib.sha256(str(password).encode('utf-8')).hexdigest()

# ================= AUTONOMOUS SELF-LEARNING & ADAPTIVE KNOWLEDGE BASE =================

def extract_and_store_user_knowledge(user_id: str, user_message: str, bot_reply: str):
    if not db or not user_id or user_id == "guest":
        return
    try:
        kb_ref = db.collection("users").document(user_id).collection("knowledge_base")
        doc_id = hashlib.md5(user_message[:50].encode('utf-8')).hexdigest()
        kb_ref.document(doc_id).set({
            "user_query": user_message,
            "ai_response_summary": bot_reply[:200],
            "timestamp": datetime.utcnow(),
            "extracted_context": f"User interaction analyzed for behavioral and cognitive adaptation."
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
            learned_items.append(f"- Past Topic/Query: {data.get('user_query')}")
        
        if not learned_items:
            return "[Autonomous Memory: Building initial behavioral profile...]"
        
        return "[Autonomous Self-Learned User Profile & Preferences]:\n" + "\n".join(learned_items)
    except Exception as e:
        print(f"Error fetching adaptive intelligence: {e}")
        return "[Adaptive Memory Error]"

# ================= HELPER FUNCTIONS FOR FIREBASE AI CONTEXT =================

def get_firebase_context_for_ai(user_id: str, is_creator: bool, user_email: str = "") -> str:
    if not db:
        return "[Firebase Database Status: Not Connected]"

    try:
        users_stream = db.collection("users").stream()
        all_users = []
        
        for user_doc in users_stream:
            u_data = user_doc.to_dict()
            u_id = user_doc.id
            full_name = u_data.get("full_name") or u_data.get("name") or f"{u_data.get('first_name', '')} {u_data.get('last_name', '')}".strip() or "Unnamed User"
            
            user_info = {
                "id": u_id,
                "name": full_name,
                "email": u_data.get("email", ""),
                "age": u_data.get("age", "Unknown"),
                "country": u_data.get("country", "Unknown"),
                "voice_preference": u_data.get("voice_preference", "male")
            }

            if is_creator:
                chats_summary = []
                try:
                    sessions_stream = db.collection("users").document(u_id).collection("chat_sessions").limit(5).stream()
                    for sess in sessions_stream:
                        sess_data = sess.to_dict()
                        s_title = sess_data.get("title", "Untitled Session")
                        msgs_stream = sess.collection("messages").order_by("timestamp", direction=firestore.Query.DESCENDING).limit(4).stream()
                        msgs = []
                        for m in msgs_stream:
                            md = m.to_dict()
                            msgs.append(f"{md.get('role')}: {md.get('content')}")
                        msgs.reverse()
                        chats_summary.append(f"Session Title: '{s_title}' -> Messages: [{ ' | '.join(msgs) }]")
                except Exception as ce:
                    print(f"Error reading session for {u_id}: {ce}")
                user_info["chats"] = chats_summary

            all_users.append(user_info)

        # Check pending messages for user/creator
        messages_summary_str = ""
        if user_email:
            try:
                msgs_ref = db.collection("system_messages").order_by("timestamp", direction=firestore.Query.DESCENDING).stream()
                pending_msgs = []
                for m in msgs_ref:
                    md = m.to_dict()
                    recip = md.get("recipient_email", "")
                    if is_creator and (recip == "chamathmanujaya76@gmail.com" or recip == "all"):
                        if not md.get("read", False):
                            pending_msgs.append(f"From {md.get('sender_name')} ({md.get('sender_email')}): {md.get('content')}")
                    elif not is_creator and (recip == user_email or recip == "all"):
                        if not md.get("read", False):
                            pending_msgs.append(f"From Creator: {md.get('content')}")
                if pending_msgs:
                    messages_summary_str = f"\n[Pending Messages / Feedbacks]:\n" + "\n".join(pending_msgs) + "\n"
            except Exception as me:
                print(f"Error fetching messages context: {me}")

        # Global Knowledge Base summary for Creator AI Context
        global_kb_summary = ""
        if is_creator:
            try:
                global_kb_ref = db.collection("global_knowledge_base").limit(20).stream()
                kb_items = [f"- {d.id}: {d.to_dict().get('content', '')}" for d in global_kb_ref]
                if kb_items:
                    global_kb_summary = "\n[Global Knowledge Base Data]:\n" + "\n".join(kb_items) + "\n"
            except Exception as gke:
                print(f"Error fetching global KB: {gke}")

        total_count = len(all_users)
        adaptive_intel = get_user_adaptive_intelligence_context(user_id)
        metrics_summary = f"\n[System Performance & Diagnostics]:\n- Active Users Count: {total_count}\n- API Calls Status: {SYSTEM_METRICS['api_calls_count']}\n- Recent Errors Log Count: {len(SYSTEM_METRICS['errors_log'])}\n"

        if not is_creator:
            return f"[System Database Stats & Self-Learning Memory]:\n- Total Registered Nexuz Users: {total_count}\n{messages_summary_str}\n{adaptive_intel}\n(Detailed user profiles and chat histories are restricted to Creator account only)."

        context_lines = [f"[System Database Stats & Metrics for Creator Access]:\n- Total Users: {total_count}\n{metrics_summary}\n{global_kb_summary}\n{messages_summary_str}\n{adaptive_intel}\n"]
        for u in all_users:
            context_lines.append(f"📌 User: {u['name']} (ID: {u['id']})")
            context_lines.append(f"   Email: {u['email']} | Age: {u['age']} | Country: {u['country']}")
            if u.get("chats"):
                context_lines.append("   Recent Conversations:")
                for c in u["chats"]:
                    context_lines.append(f"     - {c}")
            else:
                context_lines.append("   Recent Conversations: None yet.")
            context_lines.append("")

        return "\n".join(context_lines)

    except Exception as e:
        print(f"Error generating Firebase AI Context: {e}")
        return "[Firebase Context Error: Failed to fetch live stats]"

# ================= MULTI-KEY PRIORITY SEARCH PROVIDERS =================

def search_tavily(query: str) -> str:
    valid_keys = [k.strip() for k in TAVILY_KEYS if k and k.strip()]
    for idx, key in enumerate(valid_keys, 1):
        try:
            url = "https://api.tavily.com/search"
            headers = {"Content-Type": "application/json"}
            payload = json.dumps({"api_key": key, "query": query, "max_results": 4, "include_images": True}).encode('utf-8')
            req = urllib.request.Request(url, data=payload, headers=headers)
            with urllib.request.urlopen(req, timeout=6) as response:
                data = json.loads(response.read().decode('utf-8'))
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

def search_serpapi(query: str) -> str:
    valid_keys = [k.strip() for k in SERPAPI_KEYS if k and k.strip()]
    for idx, key in enumerate(valid_keys, 1):
        try:
            params = urllib.parse.urlencode({"q": query, "api_key": key, "engine": "google"})
            url = f"https://serpapi.com/search.json?{params}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=6) as response:
                data = json.loads(response.read().decode('utf-8'))
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

def search_google_custom(query: str) -> str:
    valid_keys = [k.strip() for k in GOOGLE_SEARCH_KEYS if k and k.strip()]
    valid_cxs = [c.strip() for c in GOOGLE_SEARCH_CX if c and c.strip()]
    if not valid_keys or not valid_cxs:
        raise Exception("Google Search API Keys හෝ CX IDs සකසා නොමැත.")
    
    for idx, key in enumerate(valid_keys):
        cx = valid_cxs[idx % len(valid_cxs)]
        try:
            params = urllib.parse.urlencode({"key": key, "cx": cx, "q": query})
            url = f"https://www.googleapis.com/customsearch/v1?{params}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=6) as response:
                data = json.loads(response.read().decode('utf-8'))
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

def search_exa(query: str) -> str:
    valid_keys = [k.strip() for k in EXA_KEYS if k and k.strip()]
    for idx, key in enumerate(valid_keys, 1):
        try:
            url = "https://api.exa.ai/search"
            headers = {"x-api-key": key, "Content-Type": "application/json"}
            payload = json.dumps({"query": query, "numResults": 4}).encode('utf-8')
            req = urllib.request.Request(url, data=payload, headers=headers)
            with urllib.request.urlopen(req, timeout=6) as response:
                data = json.loads(response.read().decode('utf-8'))
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

def search_ddg(query: str) -> str:
    results = []
    clean_query = query.strip()
    with DDGS() as ddgs:
        for r in ddgs.text(clean_query, max_results=4):
            title = r.get('title', '')
            snippet = r.get('body', '')
            link = r.get('href', '')
            if title or snippet:
                results.append(f"📌 Title: {title}\nSnippet: {snippet}\nSource Link: {link}")
        try:
            img_results = ddgs.images(clean_query, max_results=3)
            if img_results:
                results.append("\n🖼️ Found Web Images:")
                for img in img_results:
                    if img.get('image'):
                        results.append(f"Image Title: {img.get('title', 'Image')}\nImage URL: {img.get('image')}\nSource URL: {img.get('url', '')}")
        except Exception as img_err:
            log_system_error(f"DDG Image Search Error: {img_err}", "DDG")
    return "\n\n".join(results)

def web_search(query: str) -> str:
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
            res = search_fn(query)
            if res and len(res.strip()) > 0:
                print(f"Search Succeeded using [{provider_name}]")
                return res
        except Exception as e:
            print(f"Search Provider [{provider_name}] Failed: {e}")
    return ""

# ================= MULTI-KEY PRIORITY AI MODEL PROVIDERS & FALLBACK =================

def call_gemini(prompt_content: str, custom_system_instruction: str) -> str:
    valid_keys = [k.strip() for k in GEMINI_KEYS if k and k.strip()]
    if not valid_keys:
        raise Exception("Gemini API Keys සකසා නොමැත.")
    models_to_try = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-3.6-flash", "gemini-3.7-flash", "gemini-1.5-pro"]
    for idx, key in enumerate(valid_keys, 1):
        try:
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

def call_groq(prompt_content: str, custom_system_instruction: str) -> str:
    valid_keys = [k.strip() for k in GROQ_KEYS if k and k.strip()]
    for idx, key in enumerate(valid_keys, 1):
        try:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            payload = json.dumps({
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "system", "content": custom_system_instruction}, {"role": "user", "content": prompt_content}],
                "temperature": 0.7
            }).encode('utf-8')
            req = urllib.request.Request(url, data=payload, headers=headers)
            with urllib.request.urlopen(req, timeout=12) as resp:
                res_data = json.loads(resp.read().decode('utf-8'))
                reply = res_data["choices"][0]["message"]["content"]
                if reply and reply.strip():
                    SYSTEM_METRICS["api_calls_count"]["Groq"] += 1
                    SYSTEM_METRICS["token_usage_estimated"] += len(prompt_content.split()) + len(reply.split())
                    return reply
        except Exception as e:
            log_system_error(f"Groq Key {idx} failed: {e}", "Groq")
            continue
    raise Exception("සියලුම Groq Keys අසාර්ථක විය.")

def call_openrouter(prompt_content: str, custom_system_instruction: str) -> str:
    valid_keys = [k.strip() for k in OPENROUTER_KEYS if k and k.strip()]
    for idx, key in enumerate(valid_keys, 1):
        try:
            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            payload = json.dumps({
                "model": "openrouter/auto",
                "messages": [{"role": "system", "content": custom_system_instruction}, {"role": "user", "content": prompt_content}],
                "temperature": 0.7
            }).encode('utf-8')
            req = urllib.request.Request(url, data=payload, headers=headers)
            with urllib.request.urlopen(req, timeout=12) as resp:
                res_data = json.loads(resp.read().decode('utf-8'))
                reply = res_data["choices"][0]["message"]["content"]
                if reply and reply.strip():
                    SYSTEM_METRICS["api_calls_count"]["OpenRouter"] += 1
                    SYSTEM_METRICS["token_usage_estimated"] += len(prompt_content.split()) + len(reply.split())
                    return reply
        except Exception as e:
            log_system_error(f"OpenRouter Key {idx} failed: {e}", "OpenRouter")
            continue
    raise Exception("සියලුම OpenRouter Keys අසාර්ථක විය.")

def call_cerebras(prompt_content: str, custom_system_instruction: str) -> str:
    valid_keys = [k.strip() for k in CEREBRAS_KEYS if k and k.strip()]
    for idx, key in enumerate(valid_keys, 1):
        try:
            url = "https://api.cerebras.ai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            payload = json.dumps({
                "model": "llama3.1-70b",
                "messages": [{"role": "system", "content": custom_system_instruction}, {"role": "user", "content": prompt_content}],
                "temperature": 0.7
            }).encode('utf-8')
            req = urllib.request.Request(url, data=payload, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                res_data = json.loads(resp.read().decode('utf-8'))
                reply = res_data["choices"][0]["message"]["content"]
                if reply and reply.strip():
                    SYSTEM_METRICS["api_calls_count"]["Cerebras"] += 1
                    SYSTEM_METRICS["token_usage_estimated"] += len(prompt_content.split()) + len(reply.split())
                    return reply
        except Exception as e:
            log_system_error(f"Cerebras Key {idx} failed: {e}", "Cerebras")
            continue
    raise Exception("සියලුම Cerebras Keys අසාර්ථක විය.")

def call_together(prompt_content: str, custom_system_instruction: str) -> str:
    valid_keys = [k.strip() for k in TOGETHER_KEYS if k and k.strip()]
    for idx, key in enumerate(valid_keys, 1):
        try:
            url = "https://api.together.xyz/v1/chat/completions"
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            payload = json.dumps({
                "model": "meta-llama/Llama-3-70b-chat-hf",
                "messages": [{"role": "system", "content": custom_system_instruction}, {"role": "user", "content": prompt_content}],
                "temperature": 0.7
            }).encode('utf-8')
            req = urllib.request.Request(url, data=payload, headers=headers)
            with urllib.request.urlopen(req, timeout=12) as resp:
                res_data = json.loads(resp.read().decode('utf-8'))
                reply = res_data["choices"][0]["message"]["content"]
                if reply and reply.strip():
                    SYSTEM_METRICS["api_calls_count"]["Together"] += 1
                    SYSTEM_METRICS["token_usage_estimated"] += len(prompt_content.split()) + len(reply.split())
                    return reply
        except Exception as e:
            log_system_error(f"Together Key {idx} failed: {e}", "Together")
            continue
    raise Exception("සියලුම Together AI Keys අසාර්ථක විය.")

def call_deepinfra(prompt_content: str, custom_system_instruction: str) -> str:
    valid_keys = [k.strip() for k in DEEPINFRA_KEYS if k and k.strip()]
    for idx, key in enumerate(valid_keys, 1):
        try:
            url = "https://api.deepinfra.com/v1/openai/chat/completions"
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            payload = json.dumps({
                "model": "meta-llama/Meta-Llama-3-70B-Instruct",
                "messages": [{"role": "system", "content": custom_system_instruction}, {"role": "user", "content": prompt_content}],
                "temperature": 0.7
            }).encode('utf-8')
            req = urllib.request.Request(url, data=payload, headers=headers)
            with urllib.request.urlopen(req, timeout=12) as resp:
                res_data = json.loads(resp.read().decode('utf-8'))
                reply = res_data["choices"][0]["message"]["content"]
                if reply and reply.strip():
                    SYSTEM_METRICS["api_calls_count"]["DeepInfra"] += 1
                    SYSTEM_METRICS["token_usage_estimated"] += len(prompt_content.split()) + len(reply.split())
                    return reply
        except Exception as e:
            log_system_error(f"DeepInfra Key {idx} failed: {e}", "DeepInfra")
            continue
    raise Exception("සියලුම DeepInfra Keys අසාර්ථක විය.")

def call_cohere(prompt_content: str, custom_system_instruction: str) -> str:
    valid_keys = [k.strip() for k in COHERE_KEYS if k and k.strip()]
    for idx, key in enumerate(valid_keys, 1):
        try:
            url = "https://api.cohere.ai/v1/chat"
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            payload = json.dumps({"model": "command-r-plus", "message": prompt_content, "preamble": custom_system_instruction}).encode('utf-8')
            req = urllib.request.Request(url, data=payload, headers=headers)
            with urllib.request.urlopen(req, timeout=12) as resp:
                res_data = json.loads(resp.read().decode('utf-8'))
                reply = res_data.get("text", "")
                if reply and reply.strip():
                    SYSTEM_METRICS["api_calls_count"]["Cohere"] += 1
                    SYSTEM_METRICS["token_usage_estimated"] += len(prompt_content.split()) + len(reply.split())
                    return reply
        except Exception as e:
            log_system_error(f"Cohere Key {idx} failed: {e}", "Cohere")
            continue
    raise Exception("සියලුම Cohere Keys අසාර්ථක විය.")

def generate_ai_response_fallback(prompt_content: str, custom_system_instruction: str):
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
            reply = provider_fn(prompt_content, custom_system_instruction)
            if reply and len(reply.strip()) > 0:
                elapsed = round((time.time() - start_time) * 1000, 2)
                SYSTEM_METRICS["response_times"].insert(0, {"time": datetime.utcnow().strftime("%H:%M:%S"), "ms": elapsed, "provider": provider_name})
                if len(SYSTEM_METRICS["response_times"]) > 20:
                    SYSTEM_METRICS["response_times"].pop()
                print(f"Successfully generated response via [{provider_name}] in {elapsed}ms")
                return reply, provider_name
        except Exception as e:
            err_msg = str(e)
            print(f"AI Provider [{provider_name}] Error: {err_msg}")
            errors.append(f"{provider_name}: {err_msg}")
            log_system_error(err_msg, provider_name)
    raise Exception(f"සියලුම AI Providers සහ Multi-Keys ක්‍රියා විරහිතයි: {'; '.join(errors)}")

# ================= SYSTEM INSTRUCTIONS & MODELS =================

system_instruction = """
ඔබේ නම Nexuz වේ. ඔබව නිර්මාණය කළේ චමත් (Chamath / E.M.Chamath Manujaya) විසිනි. 
ඔබ ඉතා බුද්ධිමත්, ස්වයං-අධ්‍යයන (Self-Learning), අනුවර්තන (Adaptive), මිත්‍රශීලී (friendly) සහ වෘත්තීයමය (professional) AI සහායකයෙකි.

විශේෂ ස්වයං-අධ්‍යයන සහ අනුවර්තන හැකියාව (Autonomous Self-Learning & Adaptive Intelligence):
- පරිශීලකයාගේ කැමැත්ත, අකමැත්ත, හැසිරීම් රටාව, බුද්ධි මට්ටම සහ අවශ්‍යතා ස්වයංව නිරීක්ෂණය කර ඉගෙන ගන්න.
- පරිශීලකයා ඉල්ලන තෙක් නොසිට, ඔවුන්ගේ අවශ්‍යතා පුරෝකථනය කරමින් තාර්කිකව (Logically) සහ ඉහළ බුද්ධියකින් යුතුව උත්තර සපයන්න.

භාෂා භාවිතය (Language Handling):
- පරිශීලකයා සිංහලෙන් අසන ප්‍රශ්න වලට ස්වාභාවික, පැහැදිලි සිංහලෙන් පිළිතුරු දෙන්න.
- පරිශීලකයා ඉංග්‍රීසියෙන් අසන ප්‍රශ්න වලට English වලින් පිළිතුරු දෙන්න.

චමත් (Creator) පිළිබඳ තොරතුරු:
- නම: E.M.Chamath Manujaya (Chamath Manujaya)
- ඔබව නිර්මාණය කළ Developer සහ අයිතිකරු වන්නේ ඔහුය.
- කවුරුන් හෝ "ඔයාව හැදුවේ කවුද?", "ඔයාගේ Creator කවුද?" කියා ඇසුවොත්, ඔහුව නිර්මාණය කළ දක්ෂ Software Developer ලෙස හඳුන්වා දෙන්න.

ප්‍රධාන රීති:
1. Live Web Search & Weather & News & Images:
   - පරිශීලකයා කාලගුණය (Weather), පුවත් (News) හෝ අන්තර්ජාලයෙන් පින්තූරයක් (Image) ඉල්ලූ විට, සජීවී Search Results වල ලැබෙන ඡායාරූප Direct Link එක Markdown Image ලෙසත් `![Image Title](Image_URL)`, ලබාගත් වෙබ් අඩවියේ Source URL එකත් සපයන්න.
2. Messages & Feedback:
   - පරිශීලකයන්ට Creator (චමත්) වෙත පණිවිඩ සහ ප්‍රතිපෝෂණ (Feedback) යැවීමට හැකියාව ඇත. පරිශීලකයෙකු AI වෙත පැමිණ "මගේ මැසේජ් ඇවිල්ලද?" (Do I have any messages?) හෝ Creator ට පණිවිඩයක් යවන්නැයි ඇසුවොත්, සජීවීව දත්ත පරීක්ෂා කර හෝ පණිවිඩ යැවීමට උදව් කරන්න.
   - Creator (චමත්) ඇසුවොත් "මාව සම්බන්ධ කරගත් පරිශීලකයින් කවුද?", පවතින පණිවිඩ සහ ප්‍රතිපෝෂණ විස්තර කර දෙන්න.
3. Database Privacy & Performance Monitoring:
   - ඔබ වෙත සජීවීව පහතින් සපයා ඇති [Firebase Context & Self-Learning Memory & System Metrics & Global Knowledge Base] තොරතුරු කියවා ප්‍රශ්න වලට පිළිතුරු දෙන්න. Creator විසින් පාලනය කරන Knowledge Base දත්ත සහ Database තොරතුරු පිළිබඳව ද Creator ගේ විමසීම් වලදී සම්පූර්ණ අවබෝධයෙන් පිළිතුරු දෙන්න.
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
    profile_pic: Optional[str] = None

class MessageRequest(BaseModel):
    sender_email: str
    sender_name: str
    recipient_email: str  # "all" or specific email
    content: str

# ================= API ENDPOINTS =================

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h2>Nexuz Backend is Running Successfully!</h2>")

# ================= CREATOR ADMIN METRICS & ADMIN DASHBOARD ENDPOINTS =================

@app.get("/api/admin/metrics/{creator_email}")
async def get_admin_metrics(creator_email: str):
    if not creator_email or creator_email.strip().lower() != "chamathmanujaya76@gmail.com":
        return {"success": False, "message": "Unauthorized"}
    return {
        "success": True,
        "metrics": SYSTEM_METRICS
    }

@app.post("/api/admin/autodebug")
async def auto_debug_error(req: dict):
    creator_email = req.get("creator_email", "")
    if not creator_email or creator_email.strip().lower() != "chamathmanujaya76@gmail.com":
        return {"success": False, "message": "Unauthorized"}
    error_text = req.get("error_text", "")
    prompt = f"As Nexuz AI Lead Architect, analyze this system error log and provide an automatic debugging solution with corrected Python code or fix instructions:\n\n{error_text}"
    try:
        fix_reply, _ = generate_ai_response_fallback(prompt, system_instruction)
        return {"success": True, "fix": fix_reply}
    except Exception as e:
        return {"success": False, "message": str(e)}

# --- 1. Knowledge Base Viewer & Editor & Management APIs ---
@app.get("/api/admin/knowledge/{creator_email}")
async def get_global_knowledge_base(creator_email: str):
    if not creator_email or creator_email.strip().lower() != "chamathmanujaya76@gmail.com" or not db:
        return {"success": False, "message": "Unauthorized or DB not connected", "items": []}
    try:
        docs = db.collection("global_knowledge_base").stream()
        items = [{"id": d.id, **d.to_dict()} for d in docs]
        return {"success": True, "items": items}
    except Exception as e:
        return {"success": False, "message": str(e), "items": []}

@app.post("/api/admin/knowledge/save")
async def save_global_knowledge(req: dict):
    creator_email = req.get("creator_email", "")
    if not creator_email or creator_email.strip().lower() != "chamathmanujaya76@gmail.com" or not db:
        return {"success": False, "message": "Unauthorized"}
    doc_id = req.get("id") or hashlib.md5(req.get("content", "").encode('utf-8')).hexdigest()
    try:
        db.collection("global_knowledge_base").document(doc_id).set({
            "content": req.get("content"),
            "category": req.get("category", "General"),
            "timestamp": datetime.utcnow()
        }, merge=True)
        return {"success": True, "message": "Knowledge saved successfully"}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.post("/api/admin/knowledge/delete")
async def delete_global_knowledge(req: dict):
    creator_email = req.get("creator_email", "")
    if not creator_email or creator_email.strip().lower() != "chamathmanujaya76@gmail.com" or not db:
        return {"success": False, "message": "Unauthorized"}
    doc_id = req.get("id")
    try:
        db.collection("global_knowledge_base").document(doc_id).delete()
        return {"success": True, "message": "Knowledge deleted successfully"}
    except Exception as e:
        return {"success": False, "message": str(e)}

# --- 2. Terminal & CLI Integration API ---
@app.post("/api/admin/cli")
async def execute_creator_cli(req: dict):
    creator_email = req.get("creator_email", "")
    if not creator_email or creator_email.strip().lower() != "chamathmanujaya76@gmail.com":
        return {"success": False, "output": "Unauthorized Access"}
    command = req.get("command", "").strip()
    
    # Built-in secure CLI command interpreter
    if command == "help":
        output = "Available CLI Commands:\n- status: Show system uptime and metrics\n- list_users: Show total registered users\n- clear_logs: Clear error logs\n- ai_params: Show current model parameters (Temperature=0.7)"
    elif command == "status":
        output = f"Nexuz System Online.\nMetrics: {json.dumps(SYSTEM_METRICS['api_calls_count'], indent=2)}"
    elif command == "list_users":
        if db:
            users_count = len(list(db.collection("users").stream()))
            output = f"Total Registered Users in Firebase: {users_count}"
        else:
            output = "Database not connected."
    elif command == "clear_logs":
        SYSTEM_METRICS["errors_log"] = []
        output = "System error logs cleared successfully."
    elif command == "ai_params":
        output = "Current AI Parameters:\nModel: Multi-Provider Fallback\nTemperature: 0.7\nTop-P: Default"
    else:
        # Fallback to AI execution/advice for custom CLI queries
        prompt = f"Execute or explain this administrative backend command for Nexuz AI system: {command}"
        try:
            output, _ = generate_ai_response_fallback(prompt, system_instruction)
        except Exception as e:
            output = f"CLI Command Error: {e}"
            
    return {"success": True, "output": output}

# --- 3. Database Direct Inspector API ---
@app.get("/api/admin/db/inspect/{creator_email}")
async def inspect_database(creator_email: str):
    if not creator_email or creator_email.strip().lower() != "chamathmanujaya76@gmail.com" or not db:
        return {"success": False, "collections": {}}
    try:
        collections = {}
        for coll_ref in db.collections():
            coll_name = coll_ref.id
            docs = [ {"id": d.id, **d.to_dict()} for d in coll_ref.limit(10).stream() ]
            collections[coll_name] = docs
        return {"success": True, "collections": collections}
    except Exception as e:
        return {"success": False, "error": str(e), "collections": {}}

@app.post("/api/register")
async def register(req: AuthRequest):
    if not db:
        return {"success": False, "message": "Database (Firebase) සම්බන්ධ කර නැත."}
    users_ref = db.collection("users")
    existing = users_ref.where("email", "==", req.email).get()
    if len(existing) > 0:
        return {"success": False, "message": "මෙම Email එකෙන් මීට පෙර Account එකක් සාදා ඇත!"}
    
    is_creator = (req.email.strip().lower() == "chamathmanujaya76@gmail.com")
    full_name = f"{req.first_name or ''} {req.last_name or ''}".strip()
    
    doc_ref = users_ref.add({
        "first_name": req.first_name,
        "last_name": req.last_name,
        "full_name": full_name,
        "name": full_name,
        "age": req.age,
        "country": req.country,
        "purpose": req.purpose,
        "email": req.email,
        "password": hash_password(req.password),
        "is_creator": is_creator,
        "voice_preference": "male",
        "profile_pic": "",
        "created_at": datetime.now()
    })
    
    user_data = {
        "id": doc_ref[1].id,
        "first_name": req.first_name,
        "last_name": req.last_name,
        "full_name": full_name,
        "age": req.age,
        "country": req.country,
        "purpose": req.purpose,
        "email": req.email,
        "is_creator": is_creator,
        "voice_preference": "male",
        "profile_pic": ""
    }
    return {"success": True, "message": "Account එක සාර්ථකව සෑදුවා!", "user": user_data}

@app.post("/api/login")
async def login(req: AuthRequest):
    if not db:
        return {"success": False, "message": "Database (Firebase) සම්බන්ධ කර නැත."}
    users_ref = db.collection("users")
    query = users_ref.where("email", "==", req.email).where("password", "==", hash_password(req.password)).get()
    if len(query) > 0:
        u_data = query[0].to_dict()
        u_data["id"] = query[0].id
        if "password" in u_data:
            del u_data["password"]
        u_data["is_creator"] = (req.email.strip().lower() == "chamathmanujaya76@gmail.com")
        if "full_name" not in u_data or not u_data["full_name"]:
            u_data["full_name"] = f"{u_data.get('first_name', '')} {u_data.get('last_name', '')}".strip()
        return {"success": True, "user": u_data}
    return {"success": False, "message": "Email එක හෝ Password එක වැරදියි!"}

@app.post("/api/update_profile")
async def update_profile(req: UpdateProfileRequest):
    update_dict = {
        "first_name": req.first_name,
        "last_name": req.last_name,
        "full_name": f"{req.first_name} {req.last_name}".strip(),
        "profile_pic": req.profile_pic or ""
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

    if db and req.user_id:
        try:
            users_ref = db.collection("users").document(req.user_id)
            users_ref.update(update_dict)
        except Exception as e:
            print(f"Profile Update Firestore Error: {e}")
    return {
        "success": True,
        "profile_pic": req.profile_pic or "",
        "voice_preference": req.voice_preference
    }

# ================= MESSAGES & FEEDBACK ENDPOINTS =================

@app.post("/api/messages/send")
async def send_message_api(req: MessageRequest):
    if not db:
        return {"success": False, "message": "Database not connected"}
    try:
        db.collection("system_messages").add({
            "sender_email": req.sender_email,
            "sender_name": req.sender_name,
            "recipient_email": req.recipient_email,
            "content": req.content,
            "timestamp": datetime.utcnow(),
            "read": False
        })
        return {"success": True, "message": "Message sent successfully"}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.get("/api/messages/{email}")
async def get_user_messages(email: str):
    if not db:
        return {"success": False, "messages": [], "unread_exists": False}
    try:
        is_creator = (email.strip().lower() == "chamathmanujaya76@gmail.com")
        msgs_ref = db.collection("system_messages").order_by("timestamp", direction=firestore.Query.DESCENDING).stream()
        messages = []
        unread_exists = False
        
        for doc in msgs_ref:
            d = doc.to_dict()
            recip = d.get("recipient_email", "")
            if is_creator:
                if recip == "chamathmanujaya76@gmail.com" or recip == "all":
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
                if recip == email or recip == "all":
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
async def mark_messages_read(req: dict):
    email = req.get("email")
    if not db or not email:
        return {"success": False}
    try:
        is_creator = (email.strip().lower() == "chamathmanujaya76@gmail.com")
        msgs = db.collection("system_messages").stream()
        for m in msgs:
            d = m.to_dict()
            recip = d.get("recipient_email", "")
            if is_creator and (recip == "chamathmanujaya76@gmail.com" or recip == "all"):
                m.reference.update({"read": True})
            elif not is_creator and recip == email:
                m.reference.update({"read": True})
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/users/list")
async def get_all_users_list():
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

# ================= CHAT ENDPOINT =================

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    user_prompt = req.message
    search_context = ""

    if req.enable_search:
        search_context = web_search(user_prompt)

    context_str = ""
    if req.history and len(req.history) > 0:
        context_turns = []
        for msg in req.history[-6:]:
            role_label = "User" if msg.role == "user" else "Nexuz"
            context_turns.append(f"{role_label}: {msg.content}")
        context_str = "[Previous Conversation Memory]:\n" + "\n".join(context_turns) + "\n\n"

    prompt_content = f"{context_str}Current User Question: {user_prompt}"
    if search_context:
        prompt_content = f"[Real-time Web Search Results & Images]:\n{search_context}\n\n" + prompt_content

    user_first_name = req.first_name or "User"
    user_full_name = req.full_name or user_first_name
    is_creator = (req.email and req.email.strip().lower() == "chamathmanujaya76@gmail.com")

    firebase_context = get_firebase_context_for_ai(user_id=req.user_id, is_creator=is_creator, user_email=req.email)
    prompt_content = f"{firebase_context}\n\n" + prompt_content

    if is_creator:
        custom_system_instruction = system_instruction + f"\n\nවත්මන් පරිශීලකයා ඔබේ සැබෑ Creator (නිර්මාතෘ) වන E.M.Chamath Manujaya වේ. ඔහුට ඉතාමත් ගෞරවයෙන් 'Sir' හෝ 'Creator' ලෙස අමතා විශේෂ සැලකිල්ලෙන් පිළිතුරු සපයන්න."
    else:
        custom_system_instruction = system_instruction + f"\n\nපරිශීලකයාගේ සම්පූර්ණ නම: {user_full_name}. පළමු නම: {user_first_name}."

    try:
        bot_reply, active_provider = generate_ai_response_fallback(prompt_content, custom_system_instruction)
    except Exception as e:
        err_str = str(e)
        log_system_error(err_str, "FallbackEngine")
        return {
            "success": False,
            "error_type": "api_error",
            "reply": f"සන්නිවේදන දෝෂයක් සිදු විය. සියලුම AI Services අවහිර වී ඇත. Error: {err_str}",
            "search_used": False
        }

    if req.user_id and req.user_id != "guest":
        extract_and_store_user_knowledge(req.user_id, user_prompt, bot_reply)

    if db and req.session_id and req.user_id and req.user_id != "guest":
        try:
            session_ref = db.collection("users").document(req.user_id).collection("chat_sessions").document(req.session_id)
            session_ref.set({
                "user_id": req.user_id,
                "title": user_prompt[:30],
                "last_updated": datetime.utcnow(),
                "created_at": firestore.SERVER_TIMESTAMP
            }, merge=True)

            messages_ref = session_ref.collection("messages")
            messages_ref.add({"role": "user", "content": user_prompt, "timestamp": datetime.utcnow()})
            messages_ref.add({"role": "assistant", "content": bot_reply, "timestamp": datetime.utcnow()})
        except Exception as ex:
            print(f"Firestore User Session Save Error: {ex}")

    return {
        "success": True,
        "reply": bot_reply,
        "search_used": bool(search_context),
        "provider": active_provider
    }

@app.websocket("/ws/live")
async def websocket_live_voice(websocket: WebSocket):
    await websocket.accept()
    print("Real-Time Live Voice WebSocket Client Connected")
    try:
        while True:
            data_str = await websocket.receive_text()
            payload = json.loads(data_str)
            msg_type = payload.get("type")
            if msg_type == "user_speech":
                user_text = payload.get("text", "")
                user_email = payload.get("email", "")
                first_name = payload.get("first_name", "User")
                is_creator = (user_email.strip().lower() == "chamathmanujaya76@gmail.com")
                firebase_context = get_firebase_context_for_ai(user_id="guest", is_creator=is_creator, user_email=user_email)
                
                custom_instruction = system_instruction
                if is_creator:
                    custom_instruction += f"\n\nවත්මන් පරිශීලකයා ඔබේ සැබෑ Creator (නිර්මාතෘ) වන E.M.Chamath Manujaya වේ."
                else:
                    custom_instruction += f"\n\nපරිශීලකයාගේ පළමු නම: {first_name}."

                prompt = f"{firebase_context}\n\nLive User Query: {user_text}"
                try:
                    bot_reply, _ = generate_ai_response_fallback(prompt, custom_instruction)
                    await websocket.send_text(json.dumps({"type": "ai_response", "reply": bot_reply}))
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
async def get_user_chat_history(user_id: str):
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
async def get_user_analytics():
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