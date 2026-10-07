let recognition = null;
let autoSendTimer = null;
let isLiveVoiceActive = false;
let selectedFiles = [];
let currentUser = null;
let conversationHistory = []; // Context Memory Store
let chatHistoryListArray = []; // Sidebar History Items
let activeSessionId = null;

// Audio Visualizer Context & Nodes
let audioCtx = null;
let analyser = null;
let micStream = null;
let animFrameId = null;

// Three.js 3D Wave Particle Visualizer Variables
let scene, camera, renderer, particleSystem;
let glowRingLine, glowRingGeometry;
let numParticles = 4000;
let particlePositions, originalPositions, particleScales;
let isAiSpeaking = false;
let aiVoiceWaveTime = 0;

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

// App Initialization on Page Load
document.addEventListener("DOMContentLoaded", () => {
    checkUserAuth();
    loadSavedHistory();
    if ('speechSynthesis' in window) {
        window.speechSynthesis.onvoiceschanged = () => {
            window.speechSynthesis.getVoices();
        };
    }
});

// User Auth Check
function checkUserAuth() {
    const savedUser = localStorage.getItem("nexuz_user_data");
    const authModal = document.getElementById("authModal");

    if (savedUser) {
        currentUser = JSON.parse(savedUser);
        if (authModal) authModal.style.display = "none";
        updateSidebarUserDisplay();
    } else {
        if (authModal) authModal.style.display = "flex";
    }
}

// Update User Profile Display in Sidebar & Settings Header
function updateSidebarUserDisplay() {
    if (!currentUser) return;

    const userDisplayElem = document.getElementById("userNameDisplay");
    const creatorBadgeElem = document.getElementById("creatorBadge");
    const settingsCreatorBadgeElem = document.getElementById("settingsCreatorBadge");
    const userAvatarImg = document.getElementById("userAvatarImg");
    const defaultUserIcon = document.getElementById("defaultUserIcon");
    const settingsGreeting = document.getElementById("settingsGreeting");

    const fullName = currentUser.full_name || `${currentUser.first_name || ''} ${currentUser.last_name || ''}`.trim() || currentUser.first_name || "Account User";

    if (userDisplayElem) {
        userDisplayElem.innerText = fullName;
    }

    if (settingsGreeting) {
        settingsGreeting.innerText = `Hi, ${currentUser.first_name || 'User'}!`;
    }

    const isCreator = currentUser.email && currentUser.email.toLowerCase() === "chamathmanujaya76@gmail.com";

    if (isCreator) {
        if (creatorBadgeElem) creatorBadgeElem.style.display = "inline-flex";
        if (settingsCreatorBadgeElem) settingsCreatorBadgeElem.style.display = "inline-flex";
    } else {
        if (creatorBadgeElem) creatorBadgeElem.style.display = "none";
        if (settingsCreatorBadgeElem) settingsCreatorBadgeElem.style.display = "none";
    }

    if (currentUser.profile_pic && userAvatarImg) {
        userAvatarImg.src = currentUser.profile_pic;
        userAvatarImg.style.display = "block";
        if (defaultUserIcon) defaultUserIcon.style.display = "none";
    } else if (userAvatarImg && defaultUserIcon) {
        userAvatarImg.style.display = "none";
        defaultUserIcon.style.display = "block";
    }
}

// Toggle Register / Login Form
function toggleAuthMode(mode) {
    const regForm = document.getElementById("registerForm");
    const loginForm = document.getElementById("loginForm");
    const subtitle = document.getElementById("authSubtitle");

    if (mode === 'login') {
        regForm.style.display = "none";
        loginForm.style.display = "flex";
        subtitle.innerText = "ඇප් එකට ප්‍රවේශ වීමට Sign In වන්න";
    } else {
        loginForm.style.display = "none";
        regForm.style.display = "flex";
        subtitle.innerText = "ඇප් එක පාවිච්චි කිරීමට ඔබගේ Account එක සාදන්න";
    }
}

// Register Handler
async function handleRegister(e) {
    e.preventDefault();

    const firstName = document.getElementById("regFirstName").value.trim();
    const lastName = document.getElementById("regLastName").value.trim();
    const age = document.getElementById("regAge").value.trim();
    const country = document.getElementById("regCountry").value.trim();
    const purpose = document.getElementById("regPurpose").value;
    const email = document.getElementById("regEmail").value.trim();
    const password = document.getElementById("regPassword").value.trim();

    try {
        const res = await fetch("/api/register", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                first_name: firstName,
                last_name: lastName,
                age: age,
                country: country,
                purpose: purpose,
                email: email,
                password: password
            })
        });

        const data = await res.json();
        if (data.success) {
            localStorage.setItem("nexuz_user_data", JSON.stringify(data.user));
            checkUserAuth();
        } else {
            alert(data.message || "Account එක සෑදීමට නොහැකි විය.");
        }
    } catch (err) {
        alert("සන්නිවේදන දෝෂයක් සිදුවිය!");
    }
}

// Login Handler
async function handleLogin(e) {
    e.preventDefault();

    const email = document.getElementById("loginEmail").value.trim();
    const password = document.getElementById("loginPassword").value.trim();

    try {
        const res = await fetch("/api/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email: email, password: password })
        });

        const data = await res.json();
        if (data.success) {
            localStorage.setItem("nexuz_user_data", JSON.stringify(data.user));
            checkUserAuth();
        } else {
            alert(data.message || "Login විය නොහැකි විය.");
        }
    } catch (err) {
        alert("සන්නිවේදන දෝෂයක් සිදුවිය!");
    }
}

// Show Logout Confirmation Modal
function showLogoutConfirmation() {
    const modal = document.getElementById("logoutConfirmModal");
    if (modal) modal.style.display = "flex";
}

// Confirm Logout Action
function confirmLogout(isConfirmed) {
    const modal = document.getElementById("logoutConfirmModal");
    if (modal) modal.style.display = "none";

    if (isConfirmed) {
        localStorage.removeItem("nexuz_user_data");
        location.reload();
    }
}

// Settings Vertical Tabs Switcher
function switchSettingsTab(tabName, btnElem) {
    const tabs = document.querySelectorAll(".tab-content");
    tabs.forEach(tab => {
        tab.style.display = "none";
        tab.classList.remove("active");
    });

    const buttons = document.querySelectorAll(".settings-nav-tabs-vertical .nav-tab-btn");
    buttons.forEach(btn => btn.classList.remove("active"));

    const targetTab = document.getElementById(`tab-${tabName}`);
    if (targetTab) {
        targetTab.style.display = "block";
        targetTab.classList.add("active");
    }

    if (btnElem) {
        btnElem.classList.add("active");
    }
}

// Settings Modal Setup
function openSettingsModal() {
    const modal = document.getElementById("settingsModal");
    if (!modal) return;

    if (currentUser) {
        document.getElementById("setFirstName").value = currentUser.first_name || "";
        document.getElementById("setLastName").value = currentUser.last_name || "";
        document.getElementById("setAge").value = currentUser.age || "";
        document.getElementById("setCountry").value = currentUser.country || "";
        document.getElementById("setPurpose").value = currentUser.purpose || "";
        document.getElementById("setEmail").value = currentUser.email || "";
        document.getElementById("setPassword").value = "";
        
        const voiceSelect = document.getElementById("voiceSelect");
        if (voiceSelect) {
            voiceSelect.value = currentUser.voice_preference || "male";
        }
        
        const preview = document.getElementById("settingsAvatarPreview");
        const defaultIcon = document.getElementById("settingsDefaultAvatarIcon");
        
        if (currentUser.profile_pic) {
            preview.src = currentUser.profile_pic;
            preview.style.display = "block";
            if (defaultIcon) defaultIcon.style.display = "none";
        } else {
            preview.style.display = "none";
            if (defaultIcon) defaultIcon.style.display = "block";
        }
    }
    
    switchSettingsTab('manage-account', document.querySelector('.settings-nav-tabs-vertical .nav-tab-btn'));
    modal.style.display = "flex";
}

function closeSettingsModal() {
    const modal = document.getElementById("settingsModal");
    if (modal) modal.style.display = "none";
}

function handleProfilePicUpload(event) {
    const file = event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = function (e) {
        const base64Pic = e.target.result;
        const preview = document.getElementById("settingsAvatarPreview");
        const defaultIcon = document.getElementById("settingsDefaultAvatarIcon");
        
        preview.src = base64Pic;
        preview.style.display = "block";
        if (defaultIcon) defaultIcon.style.display = "none";
        
        preview.dataset.base64 = base64Pic;
    };
    reader.readAsDataURL(file);
}

async function saveSettings(e) {
    e.preventDefault();
    if (!currentUser) return;

    const newAge = document.getElementById("setAge").value.trim();
    const newPurpose = document.getElementById("setPurpose").value.trim();
    const newPassword = document.getElementById("setPassword").value.trim();
    const voicePref = document.getElementById("voiceSelect") ? document.getElementById("voiceSelect").value : "male";
    const preview = document.getElementById("settingsAvatarPreview");
    const newPic = preview.dataset.base64 || currentUser.profile_pic || "";

    try {
        const res = await fetch("/api/update_profile", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                user_id: currentUser.id,
                first_name: currentUser.first_name,
                last_name: currentUser.last_name,
                age: newAge,
                country: currentUser.country,
                purpose: newPurpose,
                password: newPassword,
                voice_preference: voicePref,
                profile_pic: newPic
            })
        });

        const data = await res.json();
        if (data.success) {
            currentUser.age = newAge;
            currentUser.purpose = newPurpose;
            currentUser.voice_preference = voicePref;
            currentUser.profile_pic = newPic;

            localStorage.setItem("nexuz_user_data", JSON.stringify(currentUser));
            updateSidebarUserDisplay();
            closeSettingsModal();
            alert("Profile Settings සාර්ථකව සුරකින ලදී!");
        }
    } catch (err) {
        alert("Settings සුරැකීමට නොහැකි විය!");
    }
}

// Sidebar Drawer Management
function toggleSidebar() {
    const sidebar = document.getElementById("sidebar");
    const overlay = document.getElementById("sidebarOverlay");
    
    if (window.innerWidth <= 768) {
        sidebar.classList.toggle("mobile-open");
        if (overlay) overlay.classList.toggle("active");
    } else {
        sidebar.classList.toggle("collapsed");
    }
}

function closeMobileSidebar() {
    const sidebar = document.getElementById("sidebar");
    const overlay = document.getElementById("sidebarOverlay");
    if (sidebar) sidebar.classList.remove("mobile-open");
    if (overlay) overlay.classList.remove("active");
}

function startNewChat() {
    const chatContainer = document.getElementById("chatContainer");
    const heroBanner = document.getElementById("heroBanner");
    chatContainer.innerHTML = "";
    if (heroBanner) heroBanner.style.display = "flex";
    selectedFiles = [];
    conversationHistory = [];
    activeSessionId = "sess-" + Date.now();
    renderFilePreviews();
    closeMobileSidebar();
}

// Sidebar History Management
function loadSavedHistory() {
    const saved = localStorage.getItem("nexuz_chat_history_list");
    if (saved) {
        try {
            chatHistoryListArray = JSON.parse(saved);
        } catch (e) {
            chatHistoryListArray = [];
        }
    }
    renderSidebarHistory();
}

function saveHistoryToStorage() {
    localStorage.setItem("nexuz_chat_history_list", JSON.stringify(chatHistoryListArray));
}

function addHistoryItem(title, sessionId) {
    if (!title) return;
    const id = sessionId || "hist-" + Date.now();
    const existingIndex = chatHistoryListArray.findIndex(item => item.id === id);
    
    if (existingIndex !== -1) return;

    const newItem = {
        id: id,
        title: title.length > 25 ? title.substring(0, 22) + "..." : title,
        messages: [...conversationHistory]
    };
    chatHistoryListArray.unshift(newItem);
    if (chatHistoryListArray.length > 20) chatHistoryListArray.pop();
    saveHistoryToStorage();
    renderSidebarHistory();
}

function loadHistorySession(id) {
    const session = chatHistoryListArray.find(item => item.id === id);
    if (!session) return;

    activeSessionId = session.id;
    conversationHistory = [...(session.messages || [])];

    const chatContainer = document.getElementById("chatContainer");
    const heroBanner = document.getElementById("heroBanner");
    chatContainer.innerHTML = "";
    if (heroBanner) heroBanner.style.display = "none";

    conversationHistory.forEach(msg => {
        const className = msg.role === "user" ? "user-msg" : "bot-msg";
        appendMessage(msg.content, className, [], false);
    });

    renderSidebarHistory();
    closeMobileSidebar();
}

function deleteHistoryItem(id, event) {
    if (event) event.stopPropagation();
    chatHistoryListArray = chatHistoryListArray.filter(item => item.id !== id);
    saveHistoryToStorage();
    renderSidebarHistory();
    if (activeSessionId === id) startNewChat();
}

function renderSidebarHistory() {
    const container = document.getElementById("chatHistoryList");
    if (!container) return;

    container.innerHTML = "";
    if (chatHistoryListArray.length === 0) {
        container.innerHTML = `
            <div class="history-item active" onclick="startNewChat()">
                <i class="fa-regular fa-message"></i>
                <span class="hist-title-text">New Conversation</span>
            </div>
        `;
        return;
    }

    chatHistoryListArray.forEach((item) => {
        const isActive = item.id === activeSessionId;
        const div = document.createElement("div");
        div.className = `history-item ${isActive ? 'active' : ''}`;
        div.onclick = () => loadHistorySession(item.id);
        div.innerHTML = `
            <i class="fa-regular fa-message"></i>
            <span class="hist-title-text">${item.title}</span>
            <button class="delete-hist-btn" onclick="deleteHistoryItem('${item.id}', event)" title="Delete History">
                <i class="fa-solid fa-trash-can"></i>
            </button>
        `;
        container.appendChild(div);
    });
}

// File Attachment Handler
function handleFileSelect(e) {
    const files = Array.from(e.target.files);
    files.forEach(file => selectedFiles.push(file));
    renderFilePreviews();
    e.target.value = "";
}

function removeFile(index) {
    selectedFiles.splice(index, 1);
    renderFilePreviews();
}

function renderFilePreviews() {
    const container = document.getElementById("filePreviewContainer");
    if (!container) return;
    container.innerHTML = "";

    selectedFiles.forEach((file, index) => {
        const chip = document.createElement("div");
        chip.className = "file-chip";
        
        let iconClass = "fa-file";
        if (file.type.startsWith("image/")) iconClass = "fa-file-image";
        else if (file.type.startsWith("audio/")) iconClass = "fa-file-audio";
        else if (file.type.startsWith("video/")) iconClass = "fa-file-video";
        else if (file.name.endsWith(".pdf")) iconClass = "fa-file-pdf";
        else if (file.name.endsWith(".doc") || file.name.endsWith(".docx")) iconClass = "fa-file-word";
        else if (file.name.endsWith(".xls") || file.name.endsWith(".xlsx")) iconClass = "fa-file-excel";

        chip.innerHTML = `
            <i class="fa-solid ${iconClass}"></i>
            <span>${file.name.length > 18 ? file.name.substring(0, 15) + "..." : file.name}</span>
            <button class="remove-file-btn" onclick="removeFile(${index})"><i class="fa-solid fa-xmark"></i></button>
        `;
        container.appendChild(chip);
    });
}

// Custom Markdown Engine
function renderMarkdown(text) {
    if (!text) return "";
    
    let formatted = text.replace(/```([a-zA-Z0-9_+-]*)\n([\s\S]*?)```/g, (match, lang, code) => {
        const language = lang.trim() || 'code';
        const escapedCode = code
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");
        
        const codeId = "code-" + Math.random().toString(36).substring(2, 9);

        return `
            <div class="code-block-container">
                <div class="code-block-header">
                    <span class="code-lang"><i class="fa-solid fa-code"></i> ${language}</span>
                    <button class="copy-code-btn" onclick="copyCodeToClipboard('${codeId}', this)">
                        <i class="fa-regular fa-copy"></i> Copy code
                    </button>
                </div>
                <pre><code id="${codeId}">${escapedCode}</code></pre>
            </div>
        `;
    });

    formatted = formatted.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>');
    formatted = formatted.replace(/^### (.*$)/gim, '<h3>$1</h3>');
    formatted = formatted.replace(/^## (.*$)/gim, '<h2>$1</h2>');
    formatted = formatted.replace(/^# (.*$)/gim, '<h1>$1</h1>');
    formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    formatted = formatted.replace(/^\* (.*$)/gim, '<li>$1</li>');
    formatted = formatted.replace(/^- (.*$)/gim, '<li>$1</li>');
    formatted = formatted.replace(/(<li>.*<\/li>)/sim, '<ul>$1</ul>');
    formatted = formatted.replace(/\n/g, '<br>');

    return formatted;
}

function copyCodeToClipboard(codeId, buttonElem) {
    const codeElem = document.getElementById(codeId);
    if (!codeElem) return;

    const textToCopy = codeElem.innerText || codeElem.textContent;
    navigator.clipboard.writeText(textToCopy).then(() => {
        const originalHtml = buttonElem.innerHTML;
        buttonElem.innerHTML = `<i class="fa-solid fa-check" style="color: #00ff88;"></i> Copied!`;
        setTimeout(() => { buttonElem.innerHTML = originalHtml; }, 2000);
    });
}

// Message Sending Logic
async function sendMessage(presetMessage = null) {
    const input = document.getElementById("userInput");
    const message = presetMessage || input.value.trim();
    const searchToggle = document.getElementById("webSearchToggle").checked;
    const heroBanner = document.getElementById("heroBanner");

    if (!message && selectedFiles.length === 0) return;

    if (heroBanner) heroBanner.style.display = "none";

    if (!activeSessionId) {
        activeSessionId = "sess-" + Date.now();
    }

    if (conversationHistory.length === 0) {
        addHistoryItem(message, activeSessionId);
    }

    const currentFiles = [...selectedFiles];
    appendMessage(message, "user-msg", currentFiles);

    conversationHistory.push({ role: "user", content: message });
    updateHistoryMessages(activeSessionId);

    input.value = "";
    selectedFiles = [];
    renderFilePreviews();

    if (autoSendTimer) clearTimeout(autoSendTimer);

    const loadingHtml = `<div class="nova-star-loader"><i class="fa-solid fa-sparkles"></i></div>`;
    const loadingId = appendMessage(loadingHtml, "bot-msg", [], true);

    try {
        const userId = currentUser ? currentUser.id : "guest";
        const firstName = currentUser ? currentUser.first_name : "User";
        const fullName = currentUser ? (currentUser.full_name || `${currentUser.first_name || ''} ${currentUser.last_name || ''}`.trim()) : "User";
        const userEmail = currentUser ? currentUser.email : "";

        const res = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                user_id: userId,
                first_name: firstName,
                full_name: fullName,
                email: userEmail,
                message: message + (currentFiles.length > 0 ? ` [Attached Files: ${currentFiles.map(f => f.name).join(", ")}]` : ""),
                enable_search: searchToggle,
                session_id: activeSessionId,
                history: conversationHistory
            })
        });

        const data = await res.json();
        const botMsgElem = document.getElementById(loadingId);

        if (data.error_type === "rate_limit") {
            if (botMsgElem) {
                botMsgElem.innerHTML = `
                    <div class="rate-limit-card">
                        <i class="fa-solid fa-triangle-exclamation warning-icon"></i>
                        <div class="rate-limit-content">
                            <strong>Gemini API Key Limit Reached</strong>
                            <p>${data.reply}</p>
                        </div>
                    </div>
                `;
            }
            return;
        }

        const replyText = data.reply || "උත්තරයක් ලබාගැනීමට නොහැකි විය.";
        conversationHistory.push({ role: "assistant", content: replyText });
        updateHistoryMessages(activeSessionId);

        if (botMsgElem) {
            botMsgElem.innerHTML = renderMarkdown(replyText);
        }
    } catch (err) {
        const botMsgElem = document.getElementById(loadingId);
        if (botMsgElem) botMsgElem.innerText = "සන්නිවේදන දෝෂයක් සිදු විය. කරුණාකර නැවත උත්සාහ කරන්න.";
    }
}

function updateHistoryMessages(sessionId) {
    const session = chatHistoryListArray.find(item => item.id === sessionId);
    if (session) {
        session.messages = [...conversationHistory];
        saveHistoryToStorage();
    }
}

function appendMessage(content, className, files = [], isHtml = false) {
    const container = document.getElementById("chatContainer");
    
    const wrapper = document.createElement("div");
    wrapper.className = `msg-bubble-wrapper ${className === 'bot-msg' ? 'bot-wrapper' : 'user-wrapper'}`;

    const msgDiv = document.createElement("div");
    const id = "msg-" + Date.now();
    msgDiv.id = id;
    msgDiv.className = `msg-bubble ${className}`;

    if (files && files.length > 0) {
        files.forEach(file => {
            if (file.type.startsWith("image/")) {
                const img = document.createElement("img");
                img.className = "msg-img-preview";
                img.src = URL.createObjectURL(file);
                msgDiv.appendChild(img);
            } else {
                const badge = document.createElement("div");
                badge.className = "msg-attachment-badge";
                badge.innerHTML = `<i class="fa-solid fa-paperclip"></i> ${file.name}`;
                msgDiv.appendChild(badge);
            }
        });
    }

    if (content) {
        const textNode = document.createElement("div");
        if (isHtml) textNode.innerHTML = content;
        else textNode.innerHTML = renderMarkdown(content);
        msgDiv.appendChild(textNode);
    }

    wrapper.appendChild(msgDiv);
    container.appendChild(wrapper);
    container.scrollTop = container.scrollHeight;
    return id;
}

function handleKeyPress(e) {
    if (e.key === "Enter") sendMessage();
}

function toggleMicMenu() {
    const menu = document.getElementById("micOptionsMenu");
    if (menu) menu.classList.toggle("show");
}

document.addEventListener("click", (e) => {
    const micContainer = document.querySelector(".mic-dropdown-container");
    if (micContainer && !micContainer.contains(e.target)) {
        const menu = document.getElementById("micOptionsMenu");
        if (menu) menu.classList.remove("show");
    }
});

function startDirectVoiceChat() {
    const menu = document.getElementById("micOptionsMenu");
    if (menu) menu.classList.remove("show");

    if (!SpeechRecognition) {
        alert("ඔබේ Browser එකේ Voice Recognition පහසුකම නොමැත.");
        return;
    }

    const rec = new SpeechRecognition();
    rec.lang = "si-LK";
    rec.interimResults = false;

    const micBtn = document.getElementById("micBtn");
    if (micBtn) micBtn.classList.add("recording");

    rec.start();

    rec.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        if (micBtn) micBtn.classList.remove("recording");
        sendMessage(transcript);
    };

    rec.onerror = rec.onend = () => {
        if (micBtn) micBtn.classList.remove("recording");
    };
}

function startVoiceToText() {
    const menu = document.getElementById("micOptionsMenu");
    if (menu) menu.classList.remove("show");

    if (!SpeechRecognition) {
        alert("ඔබේ Browser එකේ Voice Recognition පහසුකම නොමැත.");
        return;
    }

    const rec = new SpeechRecognition();
    rec.lang = "si-LK";
    rec.interimResults = true;

    const micBtn = document.getElementById("micBtn");
    const input = document.getElementById("userInput");
    if (micBtn) micBtn.classList.add("recording");

    rec.start();

    rec.onresult = (event) => {
        let transcript = "";
        for (let i = event.resultIndex; i < event.results.length; i++) {
            transcript += event.results[i][0].transcript;
        }
        if (input) input.value = transcript;

        if (autoSendTimer) clearTimeout(autoSendTimer);
        autoSendTimer = setTimeout(() => {
            rec.stop();
            if (micBtn) micBtn.classList.remove("recording");
            if (input && input.value.trim()) sendMessage();
        }, 5000);
    };

    rec.onerror = rec.onend = () => {
        if (micBtn) micBtn.classList.remove("recording");
    };
}

// =========================================================================
// THREE.JS 3D GLOWING WAVEFORM PARTICLE SYSTEM ENGINE FOR NEXUZ LIVE VOICE
// =========================================================================

function createGlowTexture() {
    const canvas = document.createElement('canvas');
    canvas.width = 64;
    canvas.height = 64;
    const ctx = canvas.getContext('2d');
    const gradient = ctx.createRadialGradient(32, 32, 0, 32, 32, 32);
    gradient.addColorStop(0, 'rgba(255,255,255,1)');
    gradient.addColorStop(0.3, 'rgba(160,32,240,0.8)');
    gradient.addColorStop(0.7, 'rgba(123,0,255,0.3)');
    gradient.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, 64, 64);

    const texture = new THREE.Texture(canvas);
    texture.needsUpdate = true;
    return texture;
}

function initThreeGlowVisualizer() {
    const canvasElem = document.getElementById("threeGlowCanvas");
    if (!canvasElem) return;

    if (renderer) {
        renderer.dispose();
    }

    scene = new THREE.Scene();
    
    camera = new THREE.PerspectiveCamera(60, 1, 0.1, 1000);
    camera.position.z = 320;

    renderer = new THREE.WebGLRenderer({ canvas: canvasElem, alpha: true, antialias: true });
    renderer.setSize(380, 380);
    renderer.setPixelRatio(window.devicePixelRatio ? window.devicePixelRatio : 1);

    // 1. OUTER PARTICLE SYSTEM
    const geometry = new THREE.BufferGeometry();
    particlePositions = new Float32Array(numParticles * 3);
    originalPositions = new Float32Array(numParticles * 3);

    const baseRadius = 110;
    const rings = 40;
    const particlesPerRing = numParticles / rings;

    let index = 0;
    for (let r = 0; r < rings; r++) {
        const ringRadius = baseRadius + (r * 1.5);
        for (let p = 0; p < particlesPerRing; p++) {
            const angle = (p / particlesPerRing) * Math.PI * 2;
            const x = Math.cos(angle) * ringRadius;
            const y = Math.sin(angle) * ringRadius;
            const z = (Math.random() - 0.5) * 15;

            particlePositions[index * 3] = x;
            particlePositions[index * 3 + 1] = y;
            particlePositions[index * 3 + 2] = z;

            originalPositions[index * 3] = x;
            originalPositions[index * 3 + 1] = y;
            originalPositions[index * 3 + 2] = z;

            index++;
        }
    }

    geometry.setAttribute('position', new THREE.BufferAttribute(particlePositions, 3));

    const pMaterial = new THREE.PointsMaterial({
        color: 0x9d00ff,
        size: 5.0,
        map: createGlowTexture(),
        transparent: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false
    });

    particleSystem = new THREE.Points(geometry, pMaterial);
    scene.add(particleSystem);

    // 2. INNER SOLID NEON GLOWING WAVE RING
    const ringPointsCount = 200;
    const ringPositions = new Float32Array(ringPointsCount * 3);
    
    glowRingGeometry = new THREE.BufferGeometry();
    for (let i = 0; i < ringPointsCount; i++) {
        const angle = (i / ringPointsCount) * Math.PI * 2;
        ringPositions[i * 3] = Math.cos(angle) * 105;
        ringPositions[i * 3 + 1] = Math.sin(angle) * 105;
        ringPositions[i * 3 + 2] = 0;
    }
    glowRingGeometry.setAttribute('position', new THREE.BufferAttribute(ringPositions, 3));

    const lineMaterial = new THREE.LineBasicMaterial({
        color: 0xdf80ff,
        linewidth: 3.5,
        transparent: true,
        opacity: 0.95
    });

    glowRingLine = new THREE.LineLoop(glowRingGeometry, lineMaterial);
    scene.add(glowRingLine);
}

// Audio Stream Context Setup
async function initAudioVisualizer() {
    try {
        micStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        analyser = audioCtx.createAnalyser();
        analyser.fftSize = 128;

        const source = audioCtx.createMediaStreamSource(micStream);
        source.connect(analyser);

        initThreeGlowVisualizer();
        visualizeAudio();
    } catch (e) {
        console.log("Audio visualizer init error:", e);
        initThreeGlowVisualizer();
        visualizeAudio();
    }
}

// Live Real-Time Rendering & Wave Displacement Loop
function visualizeAudio() {
    if (!isLiveVoiceActive) return;

    let averageFrequency = 0;
    const dataArray = new Uint8Array(analyser ? analyser.frequencyBinCount : 0);

    if (analyser) {
        analyser.getByteFrequencyData(dataArray);
        let sum = 0;
        for (let i = 0; i < dataArray.length; i++) sum += dataArray[i];
        averageFrequency = sum / (dataArray.length || 1);
    }

    aiVoiceWaveTime += 0.05;
    const freqLen = dataArray.length || 1;

    if (particleSystem) {
        const positions = particleSystem.geometry.attributes.position.array;
        for (let i = 0; i < numParticles; i++) {
            const idx = i * 3;
            const ox = originalPositions[idx];
            const oy = originalPositions[idx + 1];
            const angle = Math.atan2(oy, ox);
            const freqIndex = Math.floor(((angle + Math.PI) / (Math.PI * 2)) * freqLen) % freqLen;
            
            let audioFactor = (dataArray[freqIndex] || 0) / 255;
            if (isAiSpeaking) {
                audioFactor = Math.abs(Math.sin(aiVoiceWaveTime * 3 + angle * 4)) * 0.85 + 0.15;
            }

            const wavePulse = Math.sin(angle * 6 + aiVoiceWaveTime * 4) * (audioFactor * 35);
            const radialMultiplier = 1 + (audioFactor * 0.35) + (wavePulse / 180);

            positions[idx] = ox * radialMultiplier;
            positions[idx + 1] = oy * radialMultiplier;
            positions[idx + 2] = (Math.sin(angle * 8 + aiVoiceWaveTime * 2) * audioFactor * 20);
        }
        particleSystem.geometry.attributes.position.needsUpdate = true;
        particleSystem.rotation.z += 0.003;
    }

    if (glowRingLine) {
        const ringPos = glowRingGeometry.attributes.position.array;
        const ringCount = ringPos.length / 3;
        for (let i = 0; i < ringCount; i++) {
            const angle = (i / ringCount) * Math.PI * 2;
            const freqIndex = Math.floor((i / ringCount) * freqLen) % freqLen;
            
            let audioFactor = (dataArray[freqIndex] || 0) / 255;
            if (isAiSpeaking) {
                audioFactor = Math.abs(Math.sin(aiVoiceWaveTime * 4 + angle * 5)) * 0.9 + 0.1;
            }

            const waveDisplace = Math.sin(angle * 8 + aiVoiceWaveTime * 5) * (audioFactor * 28);
            const radius = 105 + waveDisplace;

            ringPos[i * 3] = Math.cos(angle) * radius;
            ringPos[i * 3 + 1] = Math.sin(angle) * radius;
        }
        glowRingGeometry.attributes.position.needsUpdate = true;
        glowRingLine.rotation.z -= 0.002;
    }

    if (renderer && scene && camera) {
        renderer.render(scene, camera);
    }
    
    animFrameId = requestAnimationFrame(visualizeAudio);
}

function openLiveVoiceMode() {
    isLiveVoiceActive = true;
    document.getElementById("liveVoiceOverlay").classList.add("active");

    const firstName = currentUser ? currentUser.first_name : "User";
    const greetingText = `Hi ${firstName}, what shall we do today?`;

    const statusText = document.getElementById("liveVoiceStatus");
    if (statusText) statusText.innerText = greetingText;

    initAudioVisualizer();
    speakText(greetingText, () => {
        startLiveListening();
    });
}

function closeLiveVoiceMode() {
    isLiveVoiceActive = false;
    isAiSpeaking = false;
    if (recognition) recognition.stop();
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    if (micStream) micStream.getTracks().forEach(t => t.stop());
    if (animFrameId) cancelAnimationFrame(animFrameId);
    
    document.getElementById("liveVoiceOverlay").classList.remove("active");
}

function speakText(text, onCompleteCallback = null) {
    if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
        
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.rate = 1.0;

        utterance.onstart = () => { isAiSpeaking = true; };
        utterance.onend = () => { 
            isAiSpeaking = false; 
            if (onCompleteCallback) onCompleteCallback();
        };
        utterance.onerror = () => {
            isAiSpeaking = false;
            if (onCompleteCallback) onCompleteCallback();
        };

        const selectedGender = (currentUser && currentUser.voice_preference) ? currentUser.voice_preference : "male";
        const voices = window.speechSynthesis.getVoices();

        if (voices.length > 0) {
            let matchedVoice = null;
            if (selectedGender === "female") {
                matchedVoice = voices.find(v => v.name.includes("Female") || v.name.includes("Zira") || v.name.includes("Google UK English Female") || v.name.includes("Samantha") || v.name.includes("Victoria") || v.name.includes("Karen"));
            } else {
                matchedVoice = voices.find(v => v.name.includes("Male") || v.name.includes("David") || v.name.includes("Google UK English Male") || v.name.includes("Alex") || v.name.includes("George"));
            }
            if (matchedVoice) utterance.voice = matchedVoice;
        }

        window.speechSynthesis.speak(utterance);
    } else {
        if (onCompleteCallback) onCompleteCallback();
    }
}

function startLiveListening() {
    if (!isLiveVoiceActive || !SpeechRecognition) return;

    const statusText = document.getElementById("liveVoiceStatus");
    const transcriptText = document.getElementById("liveTranscript");

    if (statusText) statusText.innerText = "සවන්දෙමින් පවතී... කතා කරන්න...";

    if (recognition) {
        try { recognition.stop(); } catch(e){}
    }

    recognition = new SpeechRecognition();
    recognition.lang = "si-LK";
    recognition.interimResults = true;

    recognition.start();

    recognition.onresult = (e) => {
        let text = "";
        for (let i = e.resultIndex; i < e.results.length; i++) {
            text += e.results[i][0].transcript;
        }
        if (transcriptText) transcriptText.innerText = text;

        if (e.results[0].isFinal) {
            recognition.stop();
            processLiveVoiceInput(text);
        }
    };

    recognition.onerror = (e) => {
        if (isLiveVoiceActive && !isAiSpeaking) {
            setTimeout(startLiveListening, 1200);
        }
    };
}

async function processLiveVoiceInput(userText) {
    if (!userText || !userText.trim()) {
        if (isLiveVoiceActive) startLiveListening();
        return;
    }

    const statusText = document.getElementById("liveVoiceStatus");
    if (statusText) statusText.innerText = "Nexuz සිතමින් පවතී...";

    try {
        const userId = currentUser ? currentUser.id : "guest";
        const firstName = currentUser ? currentUser.first_name : "User";
        const fullName = currentUser ? (currentUser.full_name || `${currentUser.first_name || ''} ${currentUser.last_name || ''}`.trim()) : "User";
        const userEmail = currentUser ? currentUser.email : "";

        const res = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                user_id: userId,
                first_name: firstName,
                full_name: fullName,
                email: userEmail,
                message: userText,
                enable_search: true,
                session_id: activeSessionId,
                history: conversationHistory
            })
        });

        const data = await res.json();
        const reply = data.reply || "සමාවන්න, මට එය තේරුණේ නැත.";

        if (statusText) statusText.innerText = reply;
        speakText(reply, () => {
            if (isLiveVoiceActive) startLiveListening();
        });

    } catch (err) {
        if (statusText) statusText.innerText = "සන්නිවේදන දෝෂයක් සිදු විය.";
        setTimeout(startLiveListening, 2000);
    }
}

function toggleLiveMic() {
    const btn = document.getElementById("liveMicToggle");
    if (btn && btn.classList.contains("active")) {
        btn.classList.remove("active");
        if (recognition) recognition.stop();
        document.getElementById("liveVoiceStatus").innerText = "Mic අක්‍රියයි";
    } else if (btn) {
        btn.classList.add("active");
        startLiveListening();
    }
}