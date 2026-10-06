let recognition = null;
let autoSendTimer = null;
let isLiveVoiceActive = false;
let selectedFiles = [];
let currentUser = null;
let conversationHistory = []; // Context Memory Store
let chatHistoryListArray = []; // Sidebar History Items

// Audio Visualizer Context & Nodes
let audioCtx = null;
let analyser = null;
let micStream = null;
let animFrameId = null;

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

// App Initialization on Page Load
document.addEventListener("DOMContentLoaded", () => {
    checkUserAuth();
    loadSavedHistory();
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

// Update User Profile Display in Sidebar
function updateSidebarUserDisplay() {
    if (!currentUser) return;

    const userDisplayElem = document.getElementById("userNameDisplay");
    const creatorBadgeElem = document.getElementById("creatorBadge");
    const userAvatarImg = document.getElementById("userAvatarImg");
    const defaultUserIcon = document.getElementById("defaultUserIcon");

    if (userDisplayElem) {
        const fullName = currentUser.full_name || `${currentUser.first_name || ''} ${currentUser.last_name || ''}`.trim() || currentUser.first_name || "Account User";
        userDisplayElem.innerText = fullName;
    }

    if (currentUser.email && currentUser.email.toLowerCase() === "chamathmanujaya76@gmail.com") {
        if (creatorBadgeElem) creatorBadgeElem.style.display = "inline-flex";
    } else {
        if (creatorBadgeElem) creatorBadgeElem.style.display = "none";
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

function logoutUser() {
    if (confirm("ඔබට Account එකෙන් ඉවත් වීමට අවශ්‍යද?")) {
        localStorage.removeItem("nexuz_user_data");
        location.reload();
    }
}

// Settings Modal & Profile Photo Setup
function openSettingsModal() {
    const modal = document.getElementById("settingsModal");
    if (!modal) return;

    if (currentUser) {
        document.getElementById("setFirstName").value = currentUser.first_name || "";
        document.getElementById("setLastName").value = currentUser.last_name || "";
        
        const preview = document.getElementById("settingsAvatarPreview");
        if (currentUser.profile_pic) {
            preview.src = currentUser.profile_pic;
            preview.style.display = "block";
        } else {
            preview.style.display = "none";
        }
    }
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
        preview.src = base64Pic;
        preview.style.display = "block";
        preview.dataset.base64 = base64Pic;
    };
    reader.readAsDataURL(file);
}

async function saveSettings(e) {
    e.preventDefault();
    if (!currentUser) return;

    const newFirstName = document.getElementById("setFirstName").value.trim();
    const newLastName = document.getElementById("setLastName").value.trim();
    const preview = document.getElementById("settingsAvatarPreview");
    const newPic = preview.dataset.base64 || currentUser.profile_pic || "";

    try {
        const res = await fetch("/api/update_profile", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                user_id: currentUser.id,
                first_name: newFirstName,
                last_name: newLastName,
                profile_pic: newPic
            })
        });

        const data = await res.json();
        if (data.success) {
            currentUser.first_name = newFirstName;
            currentUser.last_name = newLastName;
            currentUser.full_name = data.full_name;
            currentUser.profile_pic = newPic;

            localStorage.setItem("nexuz_user_data", JSON.stringify(currentUser));
            updateSidebarUserDisplay();
            closeSettingsModal();
            alert("Profile Settings සාර්ථකව යාවත්කාලීන විය!");
        }
    } catch (err) {
        alert("Settings සුරැකීමට නොහැකි විය!");
    }
}

// Sidebar Drawer Management (Desktop + Mobile)
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

function addHistoryItem(title) {
    if (!title) return;
    const newItem = {
        id: "hist-" + Date.now(),
        title: title.length > 25 ? title.substring(0, 22) + "..." : title
    };
    chatHistoryListArray.unshift(newItem);
    if (chatHistoryListArray.length > 20) chatHistoryListArray.pop();
    saveHistoryToStorage();
    renderSidebarHistory();
}

function deleteHistoryItem(id, event) {
    if (event) event.stopPropagation();
    chatHistoryListArray = chatHistoryListArray.filter(item => item.id !== id);
    saveHistoryToStorage();
    renderSidebarHistory();
}

function renderSidebarHistory() {
    const container = document.getElementById("chatHistoryList");
    if (!container) return;

    container.innerHTML = "";
    if (chatHistoryListArray.length === 0) {
        container.innerHTML = `
            <div class="history-item active">
                <i class="fa-regular fa-message"></i>
                <span>New Conversation</span>
            </div>
        `;
        return;
    }

    chatHistoryListArray.forEach((item, index) => {
        const div = document.createElement("div");
        div.className = `history-item ${index === 0 ? 'active' : ''}`;
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

// Message Sending Logic with Star Loader Fix
async function sendMessage(presetMessage = null) {
    const input = document.getElementById("userInput");
    const message = presetMessage || input.value.trim();
    const searchToggle = document.getElementById("webSearchToggle").checked;
    const heroBanner = document.getElementById("heroBanner");

    if (!message && selectedFiles.length === 0) return;

    if (heroBanner) heroBanner.style.display = "none";

    if (conversationHistory.length === 0) {
        addHistoryItem(message);
    }

    const currentFiles = [...selectedFiles];
    appendMessage(message, "user-msg", currentFiles);

    conversationHistory.push({ role: "user", content: message });

    input.value = "";
    selectedFiles = [];
    renderFilePreviews();

    if (autoSendTimer) clearTimeout(autoSendTimer);

    // Star Loading Animation Insertion
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

        if (botMsgElem) {
            botMsgElem.innerHTML = renderMarkdown(replyText);
        }
    } catch (err) {
        const botMsgElem = document.getElementById(loadingId);
        if (botMsgElem) botMsgElem.innerText = "සන්නිවේදන දෝෂයක් සිදු විය. කරුණාකර නැවත උත්සාහ කරන්න.";
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

// Web Audio API Sound-to-Animation Visualizer Engine
async function initAudioVisualizer() {
    try {
        micStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        analyser = audioCtx.createAnalyser();
        analyser.fftSize = 64;

        const source = audioCtx.createMediaStreamSource(micStream);
        source.connect(analyser);

        visualizeAudio();
    } catch (e) {
        console.log("Audio visualizer init error:", e);
    }
}

function visualizeAudio() {
    if (!isLiveVoiceActive || !analyser) return;

    const dataArray = new Uint8Array(analyser.frequencyBinCount);
    analyser.getByteFrequencyData(dataArray);

    let sum = 0;
    for (let i = 0; i < dataArray.length; i++) {
        sum += dataArray[i];
    }
    const average = sum / dataArray.length; // Voice frequency level

    const coreOrb = document.getElementById("coreOrb");
    const wave1 = document.getElementById("wave1");
    const wave2 = document.getElementById("wave2");
    const wave3 = document.getElementById("wave3");

    // Dynamic Sound Animation Scaling
    const scale = 1 + (average / 120); 
    const glow = 20 + (average * 0.8);

    if (coreOrb) {
        coreOrb.style.transform = `scale(${scale})`;
        coreOrb.style.boxShadow = `0 0 ${glow}px #7B00FF, inset 0 0 ${glow + 10}px #0044FF`;
    }
    if (wave1) wave1.style.transform = `scale(${scale * 1.05})`;
    if (wave2) wave2.style.transform = `scale(${scale * 1.1})`;
    if (wave3) wave3.style.transform = `scale(${scale * 1.15})`;

    animFrameId = requestAnimationFrame(visualizeAudio);
}

// Fullscreen Sci-Fi Live Voice Mode with Speech Synthesis & Sound Animation
function openLiveVoiceMode() {
    isLiveVoiceActive = true;
    document.getElementById("liveVoiceOverlay").classList.add("active");

    const firstName = currentUser ? currentUser.first_name : "User";
    const greetingText = `Hi ${firstName}, what shall we do today?`;

    const statusText = document.getElementById("liveVoiceStatus");
    if (statusText) statusText.innerText = greetingText;

    speakText(greetingText);
    initAudioVisualizer();

    setTimeout(startLiveListening, 2500);
}

function closeLiveVoiceMode() {
    isLiveVoiceActive = false;
    if (recognition) recognition.stop();
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    if (micStream) micStream.getTracks().forEach(t => t.stop());
    if (animFrameId) cancelAnimationFrame(animFrameId);
    
    document.getElementById("liveVoiceOverlay").classList.remove("active");
}

function speakText(text) {
    if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel(); // Reset previous voice
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = "en-US";
        utterance.rate = 1.0;
        window.speechSynthesis.speak(utterance);
    }
}

function startLiveListening() {
    if (!isLiveVoiceActive || !SpeechRecognition) return;

    const statusText = document.getElementById("liveVoiceStatus");
    const transcriptText = document.getElementById("liveTranscript");

    if (statusText) statusText.innerText = "සවන්දෙමින් පවතී... කතා කරන්න...";

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

    recognition.onerror = () => {
        if (isLiveVoiceActive) setTimeout(startLiveListening, 1000);
    };
}

async function processLiveVoiceInput(userText) {
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
                history: conversationHistory
            })
        });

        const data = await res.json();
        const reply = data.reply || "සමාවන්න, මට එය තේරුණේ නැත.";

        if (statusText) statusText.innerText = reply;
        speakText(reply); // Speech Output for Live Voice Mode

        setTimeout(startLiveListening, 4500);
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