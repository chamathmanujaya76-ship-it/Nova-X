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
from google import genai
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

# Environment Variables Loading
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_API_KEY_2 = os.environ.get("GEMINI_API_KEY_2")
GEMINI_API_KEY_3 = os.environ.get("GEMINI_API_KEY_3")
GEMINI_API_KEY_4 = os.environ.get("GEMINI_API_KEY_4")

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")
SERPAPI_API_KEY = os.environ.get("SERPAPI_API_KEY")

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

# ================= HELPER FUNCTIONS FOR FIREBASE AI CONTEXT =================

def get_firebase_context_for_ai(is_creator: bool) -> str:
    """Reads Firebase database and generates context summary for AI"""
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

            # Fetch user chat sessions if Creator
            if is_creator:
                chats_summary = []
                try:
                    sessions_stream = db.collection("users").document(u_id).collection("chat_sessions").limit(5).stream()
                    for sess in sessions_stream:
                        sess_data = sess.to_dict()
                        s_title = sess_data.get("title", "Untitled Session")
                        
                        # Get last few messages from this session
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

        total_count = len(all_users)

        if not is_creator:
            return f"[System Database Stats]:\n- Total Registered Nexuz Users: {total_count}\n(Detailed user profiles and chat histories are restricted to Creator account only)."

        # Context details for Creator Account
        context_lines = [f"[System Database Stats for Creator Access]:\n- Total Users: {total_count}\n"]
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

# ================= SEARCH PROVIDERS WITH FALLBACK =================

def search_tavily(query: str) -> str:
    """Primary Search Provider - Tavily AI Search"""
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        raise Exception("Tavily API key සකසා නොමැත.")
    
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
    """Fallback Search Provider 1 - SerpAPI"""
    api_key = os.environ.get("SERPAPI_API_KEY")
    if not api_key:
        raise Exception("SerpAPI Key සකසා නොමැත.")
    
    params = urllib.parse.urlencode({
        "q": query,
        "api_key": api_key.strip(),
        "engine": "google"
    })
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
    """Fallback Search Provider 2 - DuckDuckGo"""
    results = []
    clean_query = query.strip()
    with DDGS() as ddgs:
        for r in ddgs.text(clean_query, max_results=4):
            title = r.get('title', '')
            snippet = r.get('body', '')
            if title or snippet:
                results.append(f"📌 Title: {title}\nSnippet: {snippet}")
    return "\n\n".join(results)

def web_search(query: str) -> str:
    """Ordered Fallback Search Orchestrator"""
    if not query or len(query.strip()) < 2:
        return ""
    
    search_providers = [
        ("Tavily AI Search", search_tavily),
        ("SerpAPI", search_serpapi),
        ("DuckDuckGo Search", search_ddg)
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

# ================= AI MODEL PROVIDERS WITH FALLBACK =================

def call_gemini(prompt_content: str, custom_system_instruction: str) -> str:
    """Primary AI Provider - Gemini API (Multi-Key & Multi-Model Support)"""
    gemini_keys = [
        os.environ.get("GEMINI_API_KEY"),
        os.environ.get("GEMINI_API_KEY_2"),
        os.environ.get("GEMINI_API_KEY_3"),
        os.environ.get("GEMINI_API_KEY_4"),
    ]
    
    valid_keys = [k.strip() for k in gemini_keys if k and k.strip()]
    
    if not valid_keys:
        raise Exception("Gemini API Key කිසිවක් සකසා නොමැත.")
    
    models_to_try = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-3.6-flash", "gemini-1.5-pro"]
    
    for idx, key in enumerate(valid_keys, 1):
        try:
            client = genai.Client(api_key=key)
            for model_name in models_to_try:
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=prompt_content,
                        config={
                            "system_instruction": custom_system_instruction,
                            "temperature": 0.7,
                        }
                    )
                    if response and response.text:
                        return response.text
                except Exception as e:
                    print(f"Gemini Key {idx} error ({model_name}): {e}")
        except Exception as key_err:
            print(f"Gemini Key {idx} client error: {key_err}")
            
    raise Exception("සියලුම Gemini API Keys සහ Models අසාර්ථක විය.")

def call_deepseek(prompt_content: str, custom_system_instruction: str) -> str:
    """Fallback AI Provider 1 - DeepSeek API"""
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
    """Fallback AI Provider 2 - Groq API"""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key or not api_key.strip():
        raise Exception("Groq API Key නොමැත.")
    
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json"
    }
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
    """Fallback AI Provider 3 - OpenRouter API"""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key or not api_key.strip():
        raise Exception("OpenRouter API Key නොමැත.")
    
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json"
    }
    payload = json.dumps({
        "model": "openrouter/auto",
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

def generate_ai_response_fallback(prompt_content: str, custom_system_instruction: str):
    """Ordered Fallback AI Engine (Gemini -> DeepSeek -> Groq -> OpenRouter)"""
    ai_providers = [
        ("Gemini API (Primary)", call_gemini),
        ("DeepSeek API (Fallback 1)", call_deepseek),
        ("Groq API (Fallback 2)", call_groq),
        ("OpenRouter API (Fallback 3)", call_openrouter)
    ]

    errors = []
    for provider_name, provider_fn in ai_providers:
        try:
            print(f"Attempting AI Response via [{provider_name}]...")
            reply = provider_fn(prompt_content, custom_system_instruction)
            if reply and len(reply.strip()) > 0:
                print(f"Successfully generated response via [{provider_name}]")
                return reply, provider_name
        except Exception as e:
            err_msg = str(e)
            print(f"AI Provider [{provider_name}] Error: {err_msg}")
            errors.append(f"{provider_name}: {err_msg}")

    raise Exception(f"සියලුම AI Providers ක්‍රියා විරහිතයි: {'; '.join(errors)}")

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
4. Database Privacy:
   - ඔබ වෙත සජීවීව පහතින් සපයා ඇති [Firebase Context] තොරතුරු කියවා ප්‍රශ්න වලට පිළිතුරු දෙන්න.
   - සාමාන්‍ය පරිශීලකයෙකු (Normal User) ග්‍රාහකයන් ගණන හෝ සිස්ටම් විස්තර ඇසුවොත් සමස්ත ග්‍රාහක සංඛ්‍යාව පමණක් පවසන්න. පෞද්ගලික විස්තර/අන් අයගේ චැට් විස්තර කිසිවිටෙක සාමාන්‍ය අයට පවසන්න එපා.
   - වත්මන් පරිශීලකයා Creator (Chamath Manujaya) නම් පමණක්, ඔහු අසන ඕනෑම පරිශීලකයෙකුගේ සම්පූර්ණ විස්තර, පරිශීලකයන්ගේ නම් ලැයිස්තු සහ ඔවුන් අසා ඇති ප්‍රශ්න පිළිබඳ තොරතුරු පැහැදිලිව ලබා දෙන්න.
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
    password: Optional[str] = None
    voice_preference: Optional[str] = "male"
    profile_pic: Optional[str] = None

# ================= API ENDPOINTS =================

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h2>Nexuz Backend is Running Successfully!</h2>")

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
        "profile_pic": req.profile_pic or ""
    }
    if req.age:
        update_dict["age"] = req.age
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
    user_full_name = req.full_name or user_first_name
    is_creator = (req.email and req.email.strip().lower() == "chamathmanujaya76@gmail.com")

    # Fetch live Firebase Database context
    firebase_context = get_firebase_context_for_ai(is_creator=is_creator)
    prompt_content = f"{firebase_context}\n\n" + prompt_content

    if is_creator:
        custom_system_instruction = system_instruction + f"\n\nවත්මන් පරිශීලකයා ඔබේ සැබෑ Creator (නිර්මාතෘ) වන E.M.Chamath Manujaya වේ. ඔහුට ඉතාමත් ගෞරවයෙන් 'Sir' හෝ 'Creator' ලෙස අමතා විශේෂ සැලකිල්ලෙන් පිළිතුරු සපයන්න. ඔහු අසන ඕනෑම පරිශීලකයෙකුගේ විස්තර සහ චැට් ඉතිහාසය Firebase දත්ත අනුව ලබා දෙන්න."
    else:
        custom_system_instruction = system_instruction + f"\n\nපරිශීලකයාගේ සම්පූර්ණ නම: {user_full_name}. පළමු නම: {user_first_name}. පරිශීලකයාට අමතන විට ඔහුව/ඇයව මිත්‍රශීලීව {user_first_name} ලෙස පළමු නමින් අමතන්න."

    try:
        # Fallback AI System Call
        bot_reply, active_provider = generate_ai_response_fallback(prompt_content, custom_system_instruction)
    except Exception as e:
        return {
            "success": False,
            "error_type": "api_error",
            "reply": f"සන්නිවේදන දෝෂයක් සිදු විය. සියලුම AI Services අවහිර වී ඇත. Error: {str(e)}",
            "search_used": False
        }

    # Save to Firestore under user's sub-collection
    if db and req.session_id and req.user_id and req.user_id != "guest":
        try:
            # User ගේ Sub-collection එකට path එක සැකසීම
            session_ref = db.collection("users").document(req.user_id).collection("chat_sessions").document(req.session_id)
            
            # Session document එක update හෝ create කිරීම
            session_ref.set({
                "user_id": req.user_id,
                "title": user_prompt[:30],
                "last_updated": datetime.utcnow(),
                "created_at": firestore.SERVER_TIMESTAMP
            }, merge=True)

            # Messages එකතු කිරීම
            messages_ref = session_ref.collection("messages")
            messages_ref.add({
                "role": "user",
                "content": user_prompt,
                "timestamp": datetime.utcnow()
            })
            messages_ref.add({
                "role": "assistant",
                "content": bot_reply,
                "timestamp": datetime.utcnow()
            })
        except Exception as ex:
            print(f"Firestore User Session Save Error: {ex}")

    return {
        "success": True,
        "reply": bot_reply,
        "search_used": bool(search_context),
        "provider": active_provider
    }

@app.get("/api/history/{user_id}")
async def get_user_chat_history(user_id: str):
    if not db or not user_id or user_id == "guest":
        return {"success": False, "sessions": []}
    try:
        # අලුත්ම Sessions උඩට එන ලෙස Order කර ලබාගැනීම
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

# ================= USER ANALYTICS ENDPOINT =================

@app.get("/api/analytics/users")
async def get_user_analytics():
    """Endpoint to aggregate users count, age groups, countries, and voice/gender preferences"""
    if not db:
        return {"success": False, "message": "Database (Firebase) සම්බන්ධ කර නැත."}
    
    try:
        users_ref = db.collection("users").stream()
        
        total_users = 0
        countries_count = {}
        age_groups_count = {
            "Under 18": 0,
            "18-24": 0,
            "25-34": 0,
            "35-44": 0,
            "45+": 0,
            "Unspecified": 0
        }
        voice_pref_count = {
            "male": 0,
            "female": 0,
            "Unspecified": 0
        }

        for user_doc in users_ref:
            total_users += 1
            data = user_doc.to_dict()

            # Country aggregation
            country = data.get("country", "Unknown") or "Unknown"
            country_clean = country.strip().capitalize()
            countries_count[country_clean] = countries_count.get(country_clean, 0) + 1

            # Age group aggregation
            raw_age = data.get("age")
            if raw_age:
                try:
                    age_num = int(raw_age)
                    if age_num < 18:
                        age_groups_count["Under 18"] += 1
                    elif 18 <= age_num <= 24:
                        age_groups_count["18-24"] += 1
                    elif 25 <= age_num <= 34:
                        age_groups_count["25-34"] += 1
                    elif 35 <= age_num <= 44:
                        age_groups_count["35-44"] += 1
                    else:
                        age_groups_count["45+"] += 1
                except ValueError:
                    age_groups_count["Unspecified"] += 1
            else:
                age_groups_count["Unspecified"] += 1

            # Voice / Gender preference aggregation
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