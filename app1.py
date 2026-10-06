import os
import sys
import time
import hashlib
import json
import urllib.request
import urllib.parse
from datetime import datetime
from typing import Optional, List
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from duckduckgo_search import DDGS
import google.generativeai as genai
import firebase_admin
from firebase_admin import credentials, firestore

app = FastAPI(title="Nexuz AI")

def get_base_path():
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

base_dir = get_base_path()
static_dir = os.path.join(base_dir, "static")

if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

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
            if os.path.exists(json_path):
                cred = credentials.Certificate(json_path)
                firebase_admin.initialize_app(cred)
                db = firestore.client()
                print("Firebase Database එක File මගින් සම්බන්ධ විය.")
except Exception as e:
    print(f"Firebase Connection Warning: {e}")

def hash_password(password: str) -> str:
    return hashlib.sha256(str(password).encode('utf-8')).hexdigest()

# ================= SEARCH PROVIDERS =================

def search_tavily(query: str) -> str:
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        raise Exception("Tavily API key නොමැත.")
    
    url = "https://api.tavily.com/search"
    headers = {"Content-Type": "application/json"}
    payload = json.dumps({
        "api_key": api_key.strip(),
        "query": query,
        "max_results": 4
    }).encode('utf-8')

    req = urllib.request.Request(url, data=payload, headers=headers)
    with urllib.request.urlopen(req, timeout=8) as response:
        data = json.loads(response.read().decode('utf-8'))
        results = []
        for r in data.get("results", []):
            title = r.get("title", "")
            content = r.get("content", "")
            if title or content:
                results.append(f"📌 Title: {title}\nSnippet: {content}")
        return "\n\n".join(results)

def search_serpapi(query: str) -> str:
    api_key = os.environ.get("SERPAPI_API_KEY")
    if not api_key:
        raise Exception("SerpAPI Key නොමැත.")
    
    params = urllib.parse.urlencode({"q": query, "api_key": api_key.strip(), "engine": "google"})
    url = f"https://serpapi.com/search.json?{params}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=8) as response:
        data = json.loads(response.read().decode('utf-8'))
        results = []
        for r in data.get("organic_results", [])[:4]:
            title = r.get("title", "")
            snippet = r.get("snippet", "")
            if title or snippet:
                results.append(f"📌 Title: {title}\nSnippet: {snippet}")
        return "\n\n".join(results)

def search_ddg(query: str) -> str:
    results = []
    with DDGS() as ddgs:
        for r in ddgs.text(query.strip(), max_results=4):
            title = r.get('title', '')
            snippet = r.get('body', '')
            if title or snippet:
                results.append(f"📌 Title: {title}\nSnippet: {snippet}")
    return "\n\n".join(results)

def web_search(query: str) -> str:
    if not query or len(query.strip()) < 2:
        return ""
    for provider_name, search_fn in [("Tavily", search_tavily), ("SerpAPI", search_serpapi), ("DuckDuckGo", search_ddg)]:
        try:
            res = search_fn(query)
            if res and len(res.strip()) > 0:
                return res
        except Exception as e:
            print(f"Search [{provider_name}] Error: {e}")
    return ""

# ================= AI MODEL PROVIDERS =================

def call_gemini(prompt_content: str, custom_system_instruction: str) -> str:
    """Primary AI Provider - Gemini (Multi-Key)"""
    keys = [
        os.environ.get("GEMINI_API_KEY"),
        os.environ.get("GEMINI_API_KEY_2"),
        os.environ.get("GEMINI_API_KEY_3"),
        os.environ.get("GEMINI_API_KEY_4"),
    ]
    valid_keys = [k.strip() for k in keys if k and k.strip()]
    if not valid_keys:
        raise Exception("Gemini API Keys නොමැත.")

    models_to_try = ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-1.5-pro"]

    for idx, key in enumerate(valid_keys, 1):
        try:
            genai.configure(api_key=key)
            for model_name in models_to_try:
                try:
                    model = genai.GenerativeModel(
                        model_name=model_name,
                        system_instruction=custom_system_instruction
                    )
                    res = model.generate_content(prompt_content)
                    if res and res.text:
                        return res.text
                except Exception as me:
                    print(f"Gemini Key {idx} ({model_name}) error: {me}")
        except Exception as ke:
            print(f"Gemini Key {idx} config error: {ke}")

    raise Exception("සියලුම Gemini API Keys/Models වැඩ කරන්නේ නැත.")

def call_deepseek(prompt_content: str, custom_system_instruction: str) -> str:
    """Fallback Provider 1 - DeepSeek API"""
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key or not api_key.strip():
        raise Exception("DeepSeek API Key නොමැත.")
    
    url = "https://api.deepseek.com/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json"
    }
    payload = json.dumps({
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": custom_system_instruction},
            {"role": "user", "content": prompt_content}
        ],
        "temperature": 0.7
    }).encode('utf-8')

    req = urllib.request.Request(url, data=payload, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as resp:
        res_data = json.loads(resp.read().decode('utf-8'))
        return res_data["choices"][0]["message"]["content"]

def call_groq(prompt_content: str, custom_system_instruction: str) -> str:
    """Fallback Provider 2 - Groq API"""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key or not api_key.strip():
        raise Exception("Groq API Key නොමැත.")
    
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key.strip()}", "Content-Type": "application/json"}
    payload = json.dumps({
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": custom_system_instruction},
            {"role": "user", "content": prompt_content}
        ],
        "temperature": 0.7
    }).encode('utf-8')

    req = urllib.request.Request(url, data=payload, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as resp:
        res_data = json.loads(resp.read().decode('utf-8'))
        return res_data["choices"][0]["message"]["content"]

def call_openrouter(prompt_content: str, custom_system_instruction: str) -> str:
    """Fallback Provider 3 - OpenRouter API (Free Models)"""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key or not api_key.strip():
        raise Exception("OpenRouter API Key නොමැත.")
    
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key.strip()}", "Content-Type": "application/json"}
    
    for free_model in ["meta-llama/llama-3.3-70b-instruct:free", "google/gemini-2.0-flash-lite-preview-02-05:free"]:
        try:
            payload = json.dumps({
                "model": free_model,
                "messages": [
                    {"role": "system", "content": custom_system_instruction},
                    {"role": "user", "content": prompt_content}
                ]
            }).encode('utf-8')

            req = urllib.request.Request(url, data=payload, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as resp:
                res_data = json.loads(resp.read().decode('utf-8'))
                if "choices" in res_data and len(res_data["choices"]) > 0:
                    return res_data["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"OpenRouter Model ({free_model}) error: {e}")

    raise Exception("OpenRouter Models අසාර්ථක විය.")

def generate_ai_response_fallback(prompt_content: str, custom_system_instruction: str):
    ai_providers = [
        ("Gemini API (Primary)", call_gemini),
        ("DeepSeek API (Fallback 1)", call_deepseek),
        ("Groq API (Fallback 2)", call_groq),
        ("OpenRouter API (Fallback 3)", call_openrouter)
    ]

    errors = []
    for provider_name, provider_fn in ai_providers:
        try:
            print(f"Attempting [{provider_name}]...")
            reply = provider_fn(prompt_content, custom_system_instruction)
            if reply and len(reply.strip()) > 0:
                return reply, provider_name
        except Exception as e:
            err_msg = str(e)
            print(f"[{provider_name}] Error: {err_msg}")
            errors.append(f"{provider_name}: {err_msg}")

    raise Exception(f"සියලුම AI Providers අසාර්ථකයි: {'; '.join(errors)}")

# ================= SYSTEM INSTRUCTIONS & MODELS =================

system_instruction = """
ඔබේ නම Nexuz වේ. ඔබව නිර්මාණය කළේ චමත් (Chamath / E.M.Chamath Manujaya) විසිනි. 
ඔබ ඉතා බුද්ධිමත්, මිත්‍රශීලී (friendly) සහ වෘත්තීයමය (professional) AI සහායකයෙකි.

භාෂා භාවිතය (Language Handling):
- පරිශීලකයා සිංහලෙන් අසන ප්‍රශ්න වලට ස්වාභාවික, පැහැදිලි සිංහලෙන් පිළිතුරු දෙන්න.
- පරිශීලකයා ඉංග්‍රීසියෙන් අසන ප්‍රශ්න වලට English වලින් පිළිතුරු දෙන්න.
- Singlish හෝ දෙබස් මිශ්‍රව පැමිණියහොත් පරිශීලකයාගේ අභිප්‍රාය තේරුම්ගෙන ස්වාභාවිකව පිළිතුරු දෙන්න.

චමත් (Creator) පිළිබඳ තොරතුරු:
- නම: E.M.Chamath Manujaya (Chamath Manujaya)
- ඔබව නිර්මාණය කළ Developer සහ අයිතිකරු වන්නේ ඔහුය.
- කවුරුන් හෝ "ඔයාව හැදුවේ කවුද?", "ඔයාගේ Creator කවුද?", "චමත් කවුද?" හෝ "චමත් මනුජය ගැන කියන්න" කියා ඇසුවොත්, ඔහුව ගෞරවයෙන් සහ අභිමානයෙන් මතක් කරමින්, ඔහුව නිර්මාණය කළ දක්ෂ Software Developer ලෙස හඳුන්වා දෙන්න.
- කවුරුන් හෝ "ඔයාගේ නම මොකක්ද?" කියා ඇසුවොත් "මගේ නම Nexuz" ලෙස පවසන්න.

ප්‍රධාන රීති:
1. Live Web Search: සජීවීව ලැබෙන තොරතුරු භාවිතයෙන් අසන ලද ප්‍රශ්නයට නිවැරදි, යාවත්කාලීන පිළිතුර සපයන්න.
2. Code & Formatting: Code සපයන විට පිරිසිදුව Markdown Code blocks (```language ... ```) තුළ ලබාදෙන්න.
3. Chat Context: කලින් කතාබහ කළ මාතෘකාව මතක තබාගෙන අනුගාමික ප්‍රශ්න වලට ස්වාභාවිකව පිළිතුරු දෙන්න.
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

class UpdateProfileRequest(BaseModel):
    user_id: str
    first_name: str
    last_name: str
    voice_preference: Optional[str] = "male"
    profile_pic: Optional[str] = None

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h2>Nexuz Backend is Running!</h2>")

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
        prompt_content = f"[Real-time Web Search Results]:\n{search_context}\n\n" + prompt_content

    user_first_name = req.first_name or "User"
    custom_system_instruction = system_instruction + f"\n\nවත්මන් පරිශීලකයා: {user_first_name}."

    try:
        bot_reply, active_provider = generate_ai_response_fallback(prompt_content, custom_system_instruction)
    except Exception as e:
        return {
            "success": False,
            "reply": f"සන්නිවේදන දෝෂයක් සිදු විය: {str(e)}",
            "search_used": False
        }

    return {
        "success": True,
        "reply": bot_reply,
        "search_used": bool(search_context),
        "provider": active_provider
    }

if __name__ == '__main__':
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)