import os
import time
import base64
import hashlib
import io
import re
from datetime import datetime
from PIL import Image
import streamlit as st
import streamlit.components.v1 as components
from google import genai
from google.genai import types
import firebase_admin
from firebase_admin import credentials, firestore

# 1. Page Favicon & Config
try:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    favicon_img = Image.open(os.path.join(base_dir, "logo 3.png"))
except Exception:
    favicon_img = "✨"

st.set_page_config(
    page_title="Nova-X - AI Assistant",
    page_icon=favicon_img,
    layout="centered"
)

# 2. Firebase Initialization
if not firebase_admin._apps:
    try:
        fb_credentials = dict(st.secrets["firebase"])
        if "private_key" in fb_credentials:
            fb_credentials["private_key"] = fb_credentials["private_key"].replace("\\n", "\n")
            
        cred = credentials.Certificate(fb_credentials)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.warning(f"Firebase connection issue: {e}")

try:
    db = firestore.client()
except Exception:
    db = None

# Helper Functions
def hash_password(password):
    return hashlib.sha256(str(password).encode('utf-8')).hexdigest()

def register_user(name, email, password):
    if not db:
        return False, "Database සම්බන්ධතාවය අසාර්ථකයි!"
    users_ref = db.collection("users")
    existing_user = users_ref.where("email", "==", email).get()
    if len(existing_user) > 0:
        return False, "මෙම Email එකෙන් මීට පෙර Account එකක් සාදා ඇත!"
    
    hashed_pw = hash_password(password)
    users_ref.add({
        "name": name,
        "email": email,
        "password": hashed_pw,
        "created_at": datetime.now()
    })
    return True, "Account එක සාර්ථකව සෑදුවා! දැන් Login වන්න."

def login_user(email, password):
    if not db:
        return False, "Database සම්බන්ධතාවය අසාර්ථකයි!"
    users_ref = db.collection("users")
    hashed_pw = hash_password(password)
    
    query = users_ref.where("email", "==", email).where("password", "==", hashed_pw).get()
    if len(query) > 0:
        user_data = query[0].to_dict()
        user_data["id"] = query[0].id
        return True, user_data
    return False, "Email එක හෝ Password එක වැරදියි!"

def get_user_by_id(user_id):
    if not db:
        return None
    try:
        doc = db.collection("users").document(user_id).get()
        if doc.exists:
            data = doc.to_dict()
            data["id"] = doc.id
            return data
    except Exception:
        pass
    return None

def save_chat_to_firebase(session_id, role, content):
    if db and st.session_state.get("user_info"):
        try:
            db.collection("chat_sessions").document(session_id).collection("messages").add({
                "user_id": st.session_state.user_info.get("id"),
                "role": role,
                "content": content,
                "timestamp": datetime.utcnow()
            })
            db.collection("chat_sessions").document(session_id).set({
                "user_id": st.session_state.user_info.get("id"),
                "last_updated": datetime.utcnow(),
                "title": st.session_state.get("session_title", "New Conversation")
            }, merge=True)
        except Exception as e:
            print(f"Firebase Save Error: {e}")

def get_user_chat_sessions(user_id):
    if not db:
        return []
    try:
        docs = db.collection("chat_sessions").where("user_id", "==", user_id).stream()
        sessions = []
        for doc in docs:
            d = doc.to_dict()
            d["id"] = doc.id
            sessions.append(d)
        sessions.sort(key=lambda x: x.get("last_updated", datetime.min), reverse=True)
        return sessions
    except Exception as e:
        print(f"Firebase Fetch Error: {e}")
        return []

def get_messages_for_session(session_id):
    if not db:
        return []
    try:
        docs = db.collection("chat_sessions").document(session_id).collection("messages").order_by("timestamp").stream()
        msgs = []
        for doc in docs:
            msgs.append(doc.to_dict())
        return msgs
    except Exception as e:
        print(f"Fetch Messages Error: {e}")
        return []

def render_centered_image(image_name, width):
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        image_path = os.path.join(base_dir, image_name)
        
        with open(image_path, "rb") as f:
            data = base64.b64encode(f.read()).decode("utf-8")
        st.markdown(
            f'<div class="centered-logo-box"><img src="data:image/png;base64,{data}" style="width: {width}px; height: auto;"></div>',
            unsafe_allow_html=True
        )
    except Exception as e:
        print(f"Image Load Error: {e}")

# 3. Custom CSS - Pitch Black & Deep Violet Glow Theme
st.markdown("""
<style>
    /* Pitch Black App Background */
    html, body, .stApp, [data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stSidebar"] {
        background-color: #000000 !important;
        background: #000000 !important;
        color: #FFFFFF !important;
    }

    *:focus, *:focus-visible, *:active, input:focus, textarea:focus {
        outline: none !important;
        border-color: transparent !important;
        box-shadow: none !important;
    }

    .main .block-container {
        padding-top: 1.5rem !important;
        padding-bottom: 7rem !important;
        max-width: 720px !important;
        margin: 0 auto !important;
    }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background-color: #04020A !important;
        border-right: 1.5px solid #7B00FF55 !important;
    }

    /* Centered Logos */
    .centered-logo-box {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        text-align: center;
        width: 100%;
        margin: 0 auto 15px auto;
    }

    /* Nova Star Loading Animation */
    @keyframes starPulseGlow {
        0% { transform: rotate(0deg) scale(1); filter: drop-shadow(0 0 10px #7B00FF); }
        50% { transform: rotate(180deg) scale(1.4); filter: drop-shadow(0 0 35px #7B00FF) drop-shadow(0 0 50px #0044FF); }
        100% { transform: rotate(360deg) scale(1); filter: drop-shadow(0 0 10px #7B00FF); }
    }

    .nova-star-loader {
        display: flex;
        align-items: center;
        justify-content: center;
        margin: 20px auto;
        font-size: 45px;
        color: #7B00FF;
        animation: starPulseGlow 1.6s infinite ease-in-out;
    }

    /* Inputs & Buttons */
    div[data-baseweb="input"] {
        background-color: #06030E !important;
        border: 1.8px solid #7B00FF !important;
        border-radius: 14px !important;
        box-shadow: 0 0 18px rgba(123, 0, 255, 0.45) !important;
        color: #FFFFFF !important;
    }

    div[data-baseweb="input"]:focus-within {
        border-color: #0044FF !important;
        box-shadow: 0 0 30px rgba(123, 0, 255, 0.85), 0 0 50px rgba(0, 68, 255, 0.7) !important;
    }

    div[data-baseweb="input"] input {
        color: #FFFFFF !important;
    }

    div.stButton > button {
        background: linear-gradient(135deg, #7B00FF 0%, #0044FF 100%) !important;
        color: #FFFFFF !important;
        font-weight: 700 !important;
        border-radius: 14px !important;
        border: none !important;
        padding: 12px 24px !important;
        box-shadow: 0 0 22px rgba(123, 0, 255, 0.6) !important;
        transition: all 0.3s ease-in-out !important;
        width: 100% !important;
    }

    div.stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 0 35px rgba(123, 0, 255, 0.95), 0 0 60px rgba(0, 68, 255, 0.85) !important;
    }

    button[data-baseweb="tab"] {
        color: #888888 !important;
        background-color: transparent !important;
    }

    button[aria-selected="true"] {
        color: #7B00FF !important;
        border-bottom-color: #7B00FF !important;
        text-shadow: 0 0 15px rgba(123, 0, 255, 0.9) !important;
    }

    /* Pure Pitch Black Bottom Container Area */
    [data-testid="stBottom"], 
    [data-testid="stBottom"] > div,
    [data-testid="stBottom"] *,
    div[data-testid="stChatFloatingInputContainer"] {
        background-color: #000000 !important;
        background: #000000 !important;
        border: none !important;
        box-shadow: none !important;
    }

    [data-testid="stBottom"] {
        padding-bottom: 20px !important;
    }

    /* Fixed Main Container alignment */
    [data-testid="stBottom"] > div {
        position: relative !important;
        max-width: 720px !important;
        margin: 0 auto !important;
    }

    /* Main Chat Input Box */
    div[data-testid="stChatInput"] {
        background-color: #06030E !important;
        border: 1.8px solid #7B00FF !important;
        border-radius: 28px !important;
        box-shadow: 0 0 22px rgba(123, 0, 255, 0.5) !important;
        position: relative !important;
    }

    div[data-testid="stChatInput"] textarea {
        padding-right: 55px !important;
        color: #FFFFFF !important;
    }

    /* Remove inner borders/backgrounds */
    div[data-testid="stChatInput"] * {
        background-color: transparent !important;
        box-shadow: none !important;
    }

    div[data-testid="stChatInput"]:focus-within {
        border-color: #0044FF !important;
        box-shadow: 0 0 35px rgba(123, 0, 255, 0.95), 0 0 55px rgba(0, 68, 255, 0.8) !important;
    }

    /* Send Button - Far Right */
    button[data-testid="stChatInputSubmitButton"] {
        background: linear-gradient(135deg, #7B00FF 0%, #0044FF 100%) !important;
        border-radius: 50% !important;
        border: none !important;
        box-shadow: 0 0 15px rgba(123, 0, 255, 0.8) !important;
        right: 12px !important;
        top: 50% !important;
        transform: translateY(-50%) !important;
        position: absolute !important;
        z-index: 10 !important;
    }

    button[data-testid="stChatInputSubmitButton"] svg {
        fill: #FFFFFF !important;
    }

    /* Creator Credit Line */
    .nova-creator-credit {
        position: fixed !important;
        bottom: 6px !important;
        left: 0 !important;
        right: 0 !important;
        margin: 0 auto !important;
        text-align: center !important;
        color: #BBBBBB !important;
        font-size: 0.85rem !important;
        font-weight: 500 !important;
        letter-spacing: 0.5px !important;
        z-index: 999999 !important;
        pointer-events: none !important;
        line-height: 1 !important;
    }

    .nova-creator-credit b {
        color: #7B00FF !important;
        font-weight: 700 !important;
    }
</style>
""", unsafe_allow_html=True)

# API Setup
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except Exception:
    API_KEY = "YOUR_ACTUAL_GEMINI_API_KEY"

system_instruction = """
ඔබේ නම Nova-X වේ. ඔබව නිර්මාණය කළේ චමත් (Chamath / Chamath Manujaya) විසිනි. 
ඔබ චමත්ගේ පෞද්ගලික AI සහායකයා වේ.

චමත් (Creator) පිළිබඳ තොරතුරු:
- නම: චමත් මනුජය (Chamath Manujaya)
- ඔබව නිර්මාණය කළ Developer සහ අයිතිකරු වන්නේ ඔහුය.
- කවුරුන් හෝ "ඔයාව හැදුවේ කවුද?", "ඔයාගේ Creator කවුද?", "චමත් කවුද?" හෝ "චමත් මනුජය ගැන කියන්න" කියා ඇසුවොත්, ඔහුව ගෞරවයෙන් සහ අභිමානයෙන් මතක් කරමින්, ඔහුව නිර්මාණය කළ දක්ෂ Developer ලෙස හඳුන්වා දෙන්න.
- කවුරුන් හෝ "ඔයාගේ නම මොකක්ද?" කියා ඇසුවොත් "මගේ නම Nova-X" ලෙස පවසන්න.

ප්‍රධාන පහසුකම්:
1. Image Analysis: පරිශීලකයා ලබාදෙන පින්තූර පරීක්ෂා කර විස්තර කරන්න.
2. Translation: ඕනෑම භාෂාවක ඡේදයක්/වචනයක් සිංහලට Translate කර දෙන්න.
3. General Knowledge: ඕනෑම ප්‍රශ්නයකට පැහැදිලි හා මිත්‍රශීලී පිළිතුරු සපයන්න.
"""

# Session State Setup
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_info" not in st.session_state:
    st.session_state.user_info = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "current_session_id" not in st.session_state:
    st.session_state.current_session_id = f"session_{int(time.time())}"
if "session_title" not in st.session_state:
    st.session_state.session_title = "New Chat"

# Auto-Login
query_params = st.query_params
if not st.session_state.logged_in and "session_id" in query_params:
    saved_id = query_params["session_id"]
    user_data = get_user_by_id(saved_id)
    if user_data:
        st.session_state.logged_in = True
        st.session_state.user_info = user_data

# 4. Authentication Flow
if not st.session_state.logged_in:
    render_centered_image("logo 1.png", 200)
    st.title("🔐 Nova-X AI - Login / Register")
    
    tab1, tab2 = st.tabs(["🔑 Login", "📝 Sign Up"])
    
    with tab1:
        st.subheader("Login to your account")
        login_email = st.text_input("Email", key="login_email")
        login_password = st.text_input("Password", type="password", key="login_password")
        
        if st.button("Login"):
            if login_email and login_password:
                success, result = login_user(login_email, login_password)
                if success:
                    st.session_state.logged_in = True
                    st.session_state.user_info = result
                    st.query_params["session_id"] = result["id"]
                    st.success(f"සාදරයෙන් පිළිගන්නවා, {result['name']}!")
                    st.rerun()
                else:
                    st.error(result)
            else:
                st.warning("කරුණාකර Email සහ Password ලබාදෙන්න.")

    with tab2:
        st.subheader("Create a new account")
        reg_name = st.text_input("Full Name", key="reg_name")
        reg_email = st.text_input("Email Address", key="reg_email")
        reg_password = st.text_input("Password", type="password", key="reg_password")
        
        if st.button("Sign Up"):
            if reg_name and reg_email and reg_password:
                success, msg = register_user(reg_name, reg_email, reg_password)
                if success:
                    st.success(msg)
                else:
                    st.error(msg)
            else:
                st.warning("කරුණාකර සියලු විස්තර ලබාදෙන්න.")

# 5. Main Chat Interface
else:
    # Sidebar Setup
    st.sidebar.markdown(f"👤 User: **{st.session_state.user_info['name']}**")
    
    if st.sidebar.button("➕ New Chat"):
        st.session_state.messages = []
        st.session_state.current_session_id = f"session_{int(time.time())}"
        st.session_state.session_title = "New Chat"
        st.rerun()
        
    st.sidebar.markdown("---")
    st.sidebar.subheader("📜 Chat History")
    
    user_sessions = get_user_chat_sessions(st.session_state.user_info["id"])
    for sess in user_sessions:
        s_id = sess["id"]
        s_title = sess.get("title", "Previous Conversation")
        
        if st.sidebar.button(f"💬 {s_title[:20]}...", key=s_id):
            st.session_state.current_session_id = s_id
            st.session_state.session_title = s_title
            loaded_msgs = get_messages_for_session(s_id)
            st.session_state.messages = [{"role": m["role"], "content": m["content"]} for m in loaded_msgs]
            st.rerun()

    st.sidebar.markdown("---")
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.user_info = None
        st.session_state.messages = []
        st.query_params.clear()
        st.rerun()

    # App Branding
    render_centered_image("logo 1.png", 200)
    render_centered_image("logo 2.png", 320)

    st.markdown("""
        <div style='text-align: center; width: 100%; margin-top: -10px; margin-bottom: 20px;'>
            <p style='color: #888888; font-size: 0.95em; margin: 0;'>
                Your Personal Intelligent Companion 
            </p>
        </div>
    """, unsafe_allow_html=True)

    # Display Current Messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            if "images" in message:
                for img in message["images"]:
                    st.image(img, width=250)
            st.markdown(message["content"])

    # Chat Input Box
    prompt_data = st.chat_input(
        "Ask Nova-X...",
        accept_file="multiple",
        file_type=["png", "jpg", "jpeg", "webp"]
    )

    # Footer Credit Line
    st.markdown("""
        <div class="nova-creator-credit">
            Nova-X v1.0 | Creator by <b>Chamath</b>
        </div>
    """, unsafe_allow_html=True)

    if prompt_data:
        user_text = getattr(prompt_data, "text", "") or ""
        uploaded_files = getattr(prompt_data, "files", []) or []

        if not st.session_state.messages:
            st.session_state.session_title = user_text[:25] if user_text else "New Chat"

        st.session_state.messages.append({
            "role": "user", 
            "content": user_text,
            "images": uploaded_files
        })

        save_chat_to_firebase(st.session_state.current_session_id, "user", user_text)

        with st.chat_message("user"):
            for file in uploaded_files:
                st.image(file, width=250)
            if user_text:
                st.markdown(user_text)

        contents = []
        for file in uploaded_files:
            try:
                contents.append(Image.open(file))
            except Exception:
                pass

        if user_text:
            contents.append(user_text)

        if contents:
            client = genai.Client(api_key=API_KEY)
            with st.chat_message("assistant"):
                star_loader = st.empty()
                star_loader.markdown('<div class="nova-star-loader">✦</div>', unsafe_allow_html=True)
                
                reply = None
                models_to_try = ["gemini-2.5-flash", "gemini-1.5-flash"]
                
                for model_name in models_to_try:
                    try:
                        response = client.models.generate_content(
                            model=model_name,
                            contents=contents,
                            config={
                                "system_instruction": system_instruction,
                                "temperature": 0.7,
                            }
                        )
                        if response and response.text:
                            reply = response.text
                            break
                    except Exception as e:
                        print(f"API Error ({model_name}): {e}")
                        time.sleep(0.5)
                        continue

                star_loader.empty()

                if reply:
                    st.markdown(reply)
                    st.session_state.messages.append({"role": "assistant", "content": reply})
                    save_chat_to_firebase(st.session_state.current_session_id, "assistant", reply)
                else:
                    st.error("Google Gemini API එක සමඟ සම්බන්ධ වීමට නොහැකි විය. කරුණාකර API Key එක පරීක්ෂා කරන්න.")