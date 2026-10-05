import os
import sys
import time
import hashlib
import json
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

app = FastAPI(title="Nova-X AI")

# PyInstaller / Serverless temporary path එක ලබාගන්නා function එක
def get_base_path():
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

base_dir = get_base_path()
static_dir = os.path.join(base_dir, "static")

# static files mount කිරීම (Directory එක තිබේ නම් පමණක් Mount වේ)
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Google Gemini Client Config (Environment Variable මගින්)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
client = None
if GEMINI_API_KEY:
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        print(f"Gemini Client Init Error: {e}")

# Firebase Init (Environment Variable හෝ File path මගින්)
db = None
try:
    if not firebase_admin._apps:
        # 1. ප්‍රථමයෙන් Render / Vercel Environment Variable එකක JSON String එක ඇත්දැයි බලයි
        firebase_json_env = os.environ.get("FIREBASE_CREDENTIALS_JSON")
        
        if firebase_json_env:
            cred_dict = json.loads(firebase_json_env)
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
            db = firestore.client()
            print("Firebase Database එක Environment Variable මගින් සාර්ථකව සම්බන්ධ විය.")
        else:
            # 2. නැතහොත් Local Directory එකේ File එක ඇත්දැයි බලයි
            json_filename = "nova-x-6ef72-firebase-adminsdk-fbsvc-f00ed803ec.json"
            json_path = os.path.join(base_dir, json_filename)
            
            if not os.path.exists(json_path):
                json_path = json_filename

            if os.path.exists(json_path):
                cred = credentials.Certificate(json_path)
                firebase_admin.initialize_app(cred)
                db = firestore.client()
                print("Firebase Database එක File මගින් සාර්ථකව සම්බන්ධ විය.")
            else:
                print(f"Firebase Credentials හමු නොවුණි.")
except Exception as e:
    print(f"Firebase Connection Warning: {e}")

def hash_password(password: str) -> str:
    return hashlib.sha256(str(password).encode('utf-8')).hexdigest()

def web_search(query: str) -> str:
    """DuckDuckGo හරහා සජීවීව අන්තර්ජාලය සෙවුම් කිරීම"""
    if not query or len(query.strip()) < 2:
        return ""
    try:
        results = []
        clean_query = query.strip()
        with DDGS() as ddgs:
            for r in ddgs.text(clean_query, max_results=4):
                title = r.get('title', '')
                snippet = r.get('body', '')
                if title or snippet:
                    results.append(f"📌 Title: {title}\nSnippet: {snippet}")
        return "\n\n".join(results)
    except Exception as e:
        print(f"Search Error: {e}")
        return ""

system_instruction = """
ඔබේ නම Nova-X වේ. ඔබව නිර්මාණය කළේ චමත් (Chamath / E.M.Chamath Manujaya) විසිනි. 
ඔබ ඉතා බුද්ධිමත්, මිත්‍රශීලී (friendly) සහ වෘත්තීයමය (professional) AI සහායකයෙකි.

භාෂා භාවිතය (Language Handling):
- පරිශීලකයා සිංහලෙන් අසන ප්‍රශ්න වලට ස්වාභාවික, පැහැදිලි සිංහලෙන් පිළිතුරු දෙන්න.
- පරිශීලකයා ඉංග්‍රීසියෙන් අසන ප්‍රශ්න වලට English වලින් පිළිතුරු දෙන්න.
- Singlish හෝ දෙබස් මිශ්‍රව පැමිණියහොත් පරිශීලකයාගේ අභිප්‍රාය තේරුම්ගෙන ස්වාභාවිකව පිළිතුරු දෙන්න.

චමත් (Creator) පිළිබඳ තොරතුරු:
- නම: E.M.Chamath Manujaya (Chamath Manujaya)
- ඔබව නිර්මාණය කළ Developer සහ අයිතිකරු වන්නේ ඔහුය.
- කවුරුන් හෝ "ඔයාව හැදුවේ කවුද?", "ඔයාගේ Creator කවුද?", "චමත් කවුද?" හෝ "චමත් මනුජය ගැන කියන්න" කියා ඇසුවොත්, ඔහුව ගෞරවයෙන් සහ අභිමානයෙන් මතක් කරමින්, ඔහුව නිර්මාණය කළ දක්ෂ Software Developer ලෙස හඳුන්වා දෙන්න.
- කවුරුන් හෝ "ඔයාගේ නම මොකක්ද?" කියා ඇසුවොත් "මගේ නම Nova-X" ලෙස පවසන්න.

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

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h2>Nova-X Backend is Running Successfully!</h2>")

@app.post("/api/register")
async def register(req: AuthRequest):
    if not db:
        return {"success": False, "message": "Database (Firebase) සම්බන්ධ කර නැත."}
    users_ref = db.collection("users")
    existing = users_ref.where("email", "==", req.email).get()
    if len(existing) > 0:
        return {"success": False, "message": "මෙම Email එකෙන් මීට පෙර Account එකක් සාදා ඇත!"}
    
    is_creator = (req.email.strip().lower() == "chamathmanujaya76@gmail.com")
    
    doc_ref = users_ref.add({
        "first_name": req.first_name,
        "last_name": req.last_name,
        "full_name": f"{req.first_name or ''} {req.last_name or ''}".strip(),
        "age": req.age,
        "country": req.country,
        "purpose": req.purpose,
        "email": req.email,
        "password": hash_password(req.password),
        "is_creator": is_creator,
        "created_at": datetime.now()
    })
    
    user_data = {
        "id": doc_ref[1].id,
        "first_name": req.first_name,
        "last_name": req.last_name,
        "email": req.email,
        "is_creator": is_creator
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
        return {"success": True, "user": u_data}
    return {"success": False, "message": "Email එක හෝ Password එක වැරදියි!"}

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    if not client:
        return {
            "success": False,
            "error_type": "missing_api_key",
            "reply": "Gemini API Key සකසා නොමැත. කරුණාකර Environment Variables (GEMINI_API_KEY) පරීක්ෂා කරන්න.",
            "search_used": False
        }

    user_prompt = req.message
    search_context = ""

    if req.enable_search:
        search_context = web_search(user_prompt)

    # Context Memory Building (Recent Conversation History Buffer)
    context_str = ""
    if req.history and len(req.history) > 0:
        context_turns = []
        for msg in req.history[-6:]:  # Last 6 conversation turns
            role_label = "User" if msg.role == "user" else "Nova-X"
            context_turns.append(f"{role_label}: {msg.content}")
        context_str = "[Previous Conversation Memory]:\n" + "\n".join(context_turns) + "\n\n"

    prompt_content = f"{context_str}Current User Question: {user_prompt}"
    if search_context:
        prompt_content = f"[Real-time Web Search Results]:\n{search_context}\n\n" + prompt_content

    # Dynamic system instruction adding user identity check for Creator
    user_first_name = req.first_name or "User"
    if req.email and req.email.strip().lower() == "chamathmanujaya76@gmail.com":
        custom_system_instruction = system_instruction + f"\n\nවත්මන් පරිශීලකයා ඔබේ සැබෑ Creator (නිර්මාතෘ) වන E.M.Chamath Manujaya වේ. ඔහුට ඉතාමත් ගෞරවයෙන් 'Sir' හෝ 'Creator' ලෙස අමතා විශේෂ සැලකිල්ලෙන් පිළිතුරු සපයන්න."
    else:
        custom_system_instruction = system_instruction + f"\n\nපරිශීලකයාගේ නම: {user_first_name}. පරිශීලකයාට අමතන විට ඔහුව/ඇයව මිත්‍රශීලීව {user_first_name} ලෙස පළමු නමින් අමතන්න."

    # Priority Model Cascade for Maximum Speed & Reliability
    models_to_try = ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-1.5-pro","gemini-3.6-flash"]
    bot_reply = None
    last_error = ""
    is_rate_limit = False

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
                bot_reply = response.text
                break
        except Exception as e:
            err_msg = str(e)
            last_error = err_msg
            print(f"API Error ({model_name}): {err_msg}")
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "Quota" in err_msg.lower() or "limit" in err_msg.lower():
                is_rate_limit = True
            time.sleep(0.3)

    if not bot_reply:
        if is_rate_limit:
            return {
                "success": False,
                "error_type": "rate_limit",
                "reply": "⚠️ **Gemini API Key Limit (Quota) එක ඉක්මවා ඇත!**\n\nඔබගේ API Key එකෙහි නොමිලේ ලැබෙන Request Limit එක තාවකාලිකව පිරී ඇත. කරුණාකර විනාඩි කිහිපයකින් නැවත උත්සාහ කරන්න.",
                "search_used": False
            }
        return {
            "success": False,
            "error_type": "api_error",
            "reply": f"සන්නිවේදන දෝෂයක් සිදු විය. Error: {last_error}",
            "search_used": False
        }

    if db and req.session_id and req.user_id != "guest":
        try:
            session_ref = db.collection("chat_sessions").document(req.session_id)
            session_ref.collection("messages").add({
                "user_id": req.user_id,
                "role": "user",
                "content": user_prompt,
                "timestamp": datetime.utcnow()
            })
            session_ref.collection("messages").add({
                "user_id": req.user_id,
                "role": "assistant",
                "content": bot_reply,
                "timestamp": datetime.utcnow()
            })
            session_ref.set({
                "user_id": req.user_id,
                "last_updated": datetime.utcnow(),
                "title": user_prompt[:25]
            }, merge=True)
        except Exception as ex:
            print(f"Firestore Save Error: {ex}")

    return {
        "success": True,
        "reply": bot_reply,
        "search_used": bool(search_context)
    }
if __name__ == '__main__':
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)