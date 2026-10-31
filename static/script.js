let recognition = null;
let autoSendTimer = null;
let isLiveVoiceActive = false;
let selectedFiles = [];
let currentUser = null;
let conversationHistory = [];
let chatHistoryListArray = [];
let activeSessionId = null;

let liveSocket = null;
let silenceTimer = null;
let isRecognitionRunning = false;
let animFrameId = null;

let scene, camera, renderer, sphereMesh, particleDustSystem;
let isAiSpeaking = false;
let waveTime = 0;
let originalPositions = null;

let allSystemUsers = [];
let selectedRecipientEmail = "all";

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

document.addEventListener("DOMContentLoaded", () => {
    checkUserAuth();
    loadSavedHistory();
    if ('speechSynthesis' in window) {
        window.speechSynthesis.onvoiceschanged = () => window.speechSynthesis.getVoices();
    }
});

function checkUserAuth() {
    const savedUser = localStorage.getItem("nexuz_user_data");
    const authModal = document.getElementById("authModal");
    if (savedUser) {
        currentUser = JSON.parse(savedUser);
        if (authModal) authModal.style.display = "none";
        updateSidebarUserDisplay();
        checkUnreadNotifications();
    } else {
        if (authModal) authModal.style.display = "flex";
    }
}

async function checkUnreadNotifications() {
    if (!currentUser || !currentUser.email) return;
    try {
        const res = await fetch(`/api/messages/${currentUser.email}`);
        const data = await res.json();
        const redDot = document.getElementById("settingsRedDot");
        const tabDot = document.getElementById("tabUnreadDot");
        if (data.success && data.unread_exists) {
            if (redDot) redDot.style.display = "block";
            if (tabDot) tabDot.style.display = "block";
        }
    } catch (e) {}
}

function updateSidebarUserDisplay() {
    if (!currentUser) return;
    const userDisplayElem = document.getElementById("userNameDisplay");
    const creatorBadgeElem = document.getElementById("creatorBadge");
    const settingsCreatorBadgeElem = document.getElementById("settingsCreatorBadge");
    const creatorControlTabBtn = document.getElementById("creatorControlTabBtn");
    const userAvatarImg = document.getElementById("userAvatarImg");
    const defaultUserIcon = document.getElementById("defaultUserIcon");
    const settingsGreeting = document.getElementById("settingsGreeting");

    const fullName = currentUser.full_name || `${currentUser.first_name || ''} ${currentUser.last_name || ''}`.trim() || "Account User";
    if (userDisplayElem) userDisplayElem.innerText = fullName;
    if (settingsGreeting) settingsGreeting.innerText = `Hi, ${currentUser.first_name || 'User'}!`;

    const isCreator = currentUser.email && currentUser.email.toLowerCase() === "chamathmanujaya76@gmail.com";
    if (isCreator) {
        if (creatorBadgeElem) creatorBadgeElem.style.display = "inline-flex";
        if (settingsCreatorBadgeElem) settingsCreatorBadgeElem.style.display = "inline-flex";
        if (creatorControlTabBtn) creatorControlTabBtn.style.display = "flex";
    }

    if (currentUser.profile_pic && userAvatarImg) {
        userAvatarImg.src = currentUser.profile_pic;
        userAvatarImg.style.display = "block";
        if (defaultUserIcon) defaultUserIcon.style.display = "none";
    }
}

async function loadMessagesAndUsersTab() {
    if (!currentUser || !currentUser.email) return;
    const isCreator = currentUser.email.toLowerCase() === "chamathmanujaya76@gmail.com";
    const container = document.getElementById("messagesFeedbackContainer");
    if (!container) return;
    try {
        const msgRes = await fetch(`/api/messages/${currentUser.email}`);
        const msgData = await msgRes.json();
        const messages = msgData.messages || [];
        await fetch("/api/messages/mark_read", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: currentUser.email }) });
        checkUnreadNotifications();

        if (isCreator) {
            const usersRes = await fetch("/api/users/list");
            const usersData = await usersRes.json();
            allSystemUsers = usersData.users || [];
            container.innerHTML = `
                <div style="display: flex; flex-direction: column; gap: 12px;">
                    <h3 style="color: #FFD700; font-size: 15px;"><i class="fa-solid fa-comments"></i> Creator Broadcast</h3>
                    <textarea id="creatorMessageContent" placeholder="Type message..." style="width: 100%; height: 70px; background: #000; border: 1px solid #7B00FF; border-radius: 8px; padding: 8px; color: #fff;"></textarea>
                    <button onclick="sendCreatorMessageAction()" style="background: #7B00FF; color: #fff; border: none; padding: 8px; border-radius: 8px; cursor: pointer;">Send</button>
                </div>`;
        } else {
            container.innerHTML = `
                <div style="display: flex; flex-direction: column; gap: 14px;">
                    <h3 style="color: #7B00FF; font-size: 15px;">Messages & Feedback</h3>
                    <textarea id="userFeedbackContent" placeholder="Send feedback to creator..." style="width: 100%; height: 90px; background: #000; border: 1px solid #7B00FF; border-radius: 8px; padding: 10px; color: #fff;"></textarea>
                    <button onclick="sendUserFeedbackAction()" style="background: #7B00FF; color: #fff; border: none; padding: 10px; border-radius: 8px; cursor: pointer;">Send to Creator</button>
                </div>`;
        }
    } catch (e) {}
}

async function sendCreatorMessageAction() {
    const content = document.getElementById("creatorMessageContent").value.trim();
    if (!content) return;
    await fetch("/api/messages/send", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sender_email: currentUser.email, sender_name: currentUser.full_name, recipient_email: selectedRecipientEmail, content }) });
    alert("Sent successfully!");
    document.getElementById("creatorMessageContent").value = "";
}

async function sendUserFeedbackAction() {
    const content = document.getElementById("userFeedbackContent").value.trim();
    if (!content) return;
    await fetch("/api/messages/send", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sender_email: currentUser.email, sender_name: currentUser.full_name, recipient_email: "chamathmanujaya76@gmail.com", content }) });
    alert("Feedback sent!");
    document.getElementById("userFeedbackContent").value = "";
}

function switchSettingsTab(tabName, btnElem) {
    document.querySelectorAll(".tab-content").forEach(tab => { tab.style.display = "none"; tab.classList.remove("active"); });
    document.querySelectorAll(".settings-nav-tabs-vertical .nav-tab-btn").forEach(btn => btn.classList.remove("active"));
    const targetTab = document.getElementById(`tab-${tabName}`);
    if (targetTab) { targetTab.style.display = "block"; targetTab.classList.add("active"); }
    if (btnElem) btnElem.classList.add("active");
}

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
        document.getElementById("voiceSelect").value = currentUser.voice_preference || "male";
        document.getElementById("displayTypeSelect").value = currentUser.display_type || "sphere";
    }
    switchSettingsTab('manage-account', document.querySelector('.settings-nav-tabs-vertical .nav-tab-btn'));
    modal.style.display = "flex";
}

function closeSettingsModal() {
    document.getElementById("settingsModal").style.display = "none";
}

async function saveSettings(e) {
    e.preventDefault();
    if (!currentUser) return;
    const newFirstName = document.getElementById("setFirstName").value.trim();
    const newLastName = document.getElementById("setLastName").value.trim();
    const voicePref = document.getElementById("voiceSelect").value;
    const displayType = document.getElementById("displayTypeSelect").value;

    const res = await fetch("/api/update_profile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: currentUser.id, first_name: newFirstName, last_name: newLastName, voice_preference: voicePref, display_type: displayType })
    });
    const data = await res.json();
    if (data.success) {
        currentUser.first_name = newFirstName;
        currentUser.last_name = newLastName;
        currentUser.voice_preference = voicePref;
        currentUser.display_type = displayType;
        localStorage.setItem("nexuz_user_data", JSON.stringify(currentUser));
        updateSidebarUserDisplay();
        closeSettingsModal();
        alert("Settings saved!");
    }
}

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
    document.getElementById("sidebar").classList.remove("mobile-open");
    document.getElementById("sidebarOverlay").classList.remove("active");
}

function startNewChat() {
    document.getElementById("chatContainer").innerHTML = "";
    document.getElementById("heroBanner").style.display = "flex";
    selectedFiles = [];
    conversationHistory = [];
    activeSessionId = "sess-" + Date.now();
    renderFilePreviews();
    closeMobileSidebar();
}

function loadSavedHistory() {
    const saved = localStorage.getItem("nexuz_chat_history_list");
    if (saved) {
        try { chatHistoryListArray = JSON.parse(saved); } catch(e){}
    }
    renderSidebarHistory();
}

function saveHistoryToStorage() {
    localStorage.setItem("nexuz_chat_history_list", JSON.stringify(chatHistoryListArray));
}

function addHistoryItem(title, sessionId) {
    if (!title) return;
    const id = sessionId || "hist-" + Date.now();
    if (chatHistoryListArray.some(item => item.id === id)) return;
    chatHistoryListArray.unshift({ id, title: title.substring(0, 22), messages: [...conversationHistory] });
    saveHistoryToStorage();
    renderSidebarHistory();
}

function renderSidebarHistory() {
    const container = document.getElementById("chatHistoryList");
    if (!container) return;
    container.innerHTML = chatHistoryListArray.length === 0 ? `<div class="history-item active">New Conversation</div>` :
        chatHistoryListArray.map(item => `<div class="history-item ${item.id === activeSessionId ? 'active' : ''}" onclick="loadHistorySession('${item.id}')">${item.title}</div>`).join('');
}

function loadHistorySession(id) {
    const session = chatHistoryListArray.find(item => item.id === id);
    if (!session) return;
    activeSessionId = session.id;
    conversationHistory = [...session.messages];
    document.getElementById("chatContainer").innerHTML = "";
    document.getElementById("heroBanner").style.display = "none";
    conversationHistory.forEach(msg => appendMessage(msg.content, msg.role === "user" ? "user-msg" : "bot-msg"));
}

function handleFileSelect(e) {
    Array.from(e.target.files).forEach(file => selectedFiles.push(file));
    renderFilePreviews();
}

function removeFile(index) {
    selectedFiles.splice(index, 1);
    renderFilePreviews();
}

function renderFilePreviews() {
    const container = document.getElementById("filePreviewContainer");
    if (!container) return;
    container.innerHTML = selectedFiles.map((file, i) => `<div class="file-chip">${file.name} <button onclick="removeFile(${i})">x</button></div>`).join('');
}

function renderMarkdown(text) {
    if (!text) return "";
    return text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>').replace(/\n/g, '<br>');
}

async function sendMessage(presetMessage = null) {
    const input = document.getElementById("userInput");
    const message = presetMessage || input.value.trim();
    if (!message && selectedFiles.length === 0) return;
    document.getElementById("heroBanner").style.display = "none";
    if (!activeSessionId) activeSessionId = "sess-" + Date.now();
    if (conversationHistory.length === 0) addHistoryItem(message, activeSessionId);

    appendMessage(message, "user-msg");
    conversationHistory.push({ role: "user", content: message });
    input.value = "";
    selectedFiles = [];
    renderFilePreviews();

    const loadingId = appendMessage(`<i class="fa-solid fa-sparkles"></i>`, "bot-msg", true);

    try {
        const res = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                user_id: currentUser ? currentUser.id : "guest",
                first_name: currentUser ? currentUser.first_name : "User",
                full_name: currentUser ? currentUser.full_name : "User",
                email: currentUser ? currentUser.email : "",
                message: message,
                enable_search: true,
                session_id: activeSessionId,
                history: conversationHistory
            })
        });
        const data = await res.json();
        const replyText = data.reply || "Error.";
        conversationHistory.push({ role: "assistant", content: replyText });
        document.getElementById(loadingId).innerHTML = renderMarkdown(replyText);
    } catch (err) {
        document.getElementById(loadingId).innerText = "Connection error.";
    }
}

function appendMessage(content, className, isHtml = false) {
    const container = document.getElementById("chatContainer");
    const wrapper = document.createElement("div");
    wrapper.className = `msg-bubble-wrapper ${className === 'bot-msg' ? 'bot-wrapper' : 'user-wrapper'}`;
    const msgDiv = document.createElement("div");
    const id = "msg-" + Date.now();
    msgDiv.id = id;
    msgDiv.className = `msg-bubble ${className}`;
    msgDiv.innerHTML = isHtml ? content : renderMarkdown(content);
    wrapper.appendChild(msgDiv);
    container.appendChild(wrapper);
    container.scrollTop = container.scrollHeight;
    return id;
}

function handleKeyPress(e) { if (e.key === "Enter") sendMessage(); }

function toggleMicMenu() { document.getElementById("micOptionsMenu").classList.toggle("show"); }

function startDirectVoiceChat() {
    document.getElementById("micOptionsMenu").classList.remove("show");
    if (!SpeechRecognition) return;
    const rec = new SpeechRecognition();
    rec.lang = "si-LK";
    rec.start();
    rec.onresult = (e) => sendMessage(e.results[0][0].transcript);
}

// =========================================================================
// THREE.JS NEON WIREFRAME AUDIO-REACTIVE SPHERE ENGINE (Replaces Face)
// =========================================================================

function initNeonSphereVisualizer() {
    const canvasElem = document.getElementById("threeGlowCanvas");
    if (!canvasElem) return;

    if (renderer) renderer.dispose();

    scene = new THREE.Scene();
    camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 1000);
    camera.position.z = 6;

    renderer = new THREE.WebGLRenderer({ canvas: canvasElem, alpha: true, antialias: true });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

    window.addEventListener('resize', () => {
        if (!camera || !renderer) return;
        camera.aspect = window.innerWidth / window.innerHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(window.innerWidth, window.innerHeight);
    });

    // 1. Neon Wireframe Sphere (IcosahedronGeometry for high detail grid)
    const geometry = new THREE.IcosahedronGeometry(2, 4);
    const positionAttribute = geometry.attributes.position;
    originalPositions = new Float32Array(positionAttribute.array);

    const material = new THREE.MeshBasicMaterial({
        color: 0x00d2ff,
        wireframe: true,
        transparent: true,
        opacity: 0.85
    });

    sphereMesh = new THREE.Mesh(geometry, material);
    scene.add(sphereMesh);

    // 2. Background Particle Dust Sphere
    const particleGeo = new THREE.BufferGeometry();
    const particleCount = 1200;
    const posArray = new Float32Array(particleCount * 3);
    for (let i = 0; i < particleCount * 3; i += 3) {
        const theta = Math.random() * Math.PI * 2;
        const phi = Math.acos((Math.random() * 2) - 1);
        const r = 3.5 + Math.random() * 2.0;
        posArray[i] = r * Math.sin(phi) * Math.cos(theta);
        posArray[i + 1] = r * Math.sin(phi) * Math.sin(theta);
        posArray[i + 2] = r * Math.cos(phi);
    }
    particleGeo.setAttribute('position', new THREE.BufferAttribute(posArray, 3));
    const particleMat = new THREE.PointsMaterial({ size: 0.04, color: 0xa855f7, transparent: true, opacity: 0.6 });
    particleDustSystem = new THREE.Points(particleGeo, particleMat);
    scene.add(particleDustSystem);
}

function visualizeAudio() {
    if (!isLiveVoiceActive) return;

    waveTime += 0.04;

    if (sphereMesh && originalPositions) {
        const positions = sphereMesh.geometry.attributes.position;
        const vertex = new THREE.Vector3();

        // Dynamic Neon Color shift between Neon Blue and Magenta/Purple
        const hue = (Math.sin(waveTime * 0.2) + 1) * 0.15 + 0.55;
        sphereMesh.material.color.setHSL(hue, 0.95, 0.6);

        for (let i = 0; i < positions.count; i++) {
            vertex.fromArray(originalPositions, i * 3);
            
            // Audio-reactive vertex displacement (Waves & pulsating shape)
            const length = vertex.length() + Math.sin(waveTime * 5 + i * 0.4) * (isAiSpeaking ? 0.35 : 0.12);
            vertex.normalize().multiplyScalar(length);

            positions.setXYZ(i, vertex.x, vertex.y, vertex.z);
        }
        positions.needsUpdate = true;
        sphereMesh.rotation.y += 0.005;
        sphereMesh.rotation.x += 0.002;
    }

    if (particleDustSystem) {
        particleDustSystem.rotation.y -= 0.002;
    }

    if (renderer && scene && camera) {
        renderer.render(scene, camera);
    }

    animFrameId = requestAnimationFrame(visualizeAudio);
}

function openLiveVoiceMode() {
    isLiveVoiceActive = true;
    document.getElementById("liveVoiceOverlay").classList.add("active");

    const displayType = (currentUser && currentUser.display_type) ? currentUser.display_type : "sphere";
    const canvasElem = document.getElementById("threeGlowCanvas");
    const visualizerBox = document.getElementById("classicVisualizerBox");

    if (displayType === "visualizer") {
        if (canvasElem) canvasElem.style.display = "none";
        if (visualizerBox) visualizerBox.style.display = "flex";
    } else {
        if (canvasElem) canvasElem.style.display = "block";
        if (visualizerBox) visualizerBox.style.display = "none";
        initNeonSphereVisualizer();
        visualizeAudio();
    }

    const firstName = currentUser ? currentUser.first_name : "User";
    const greetingText = `ආයුබෝවන් ${firstName}, අද මම ඔබට උදව් කළ යුත්තේ කෙසේද?`;
    document.getElementById("liveVoiceStatus").innerText = greetingText;

    connectLiveWebSocket();
    speakText(greetingText, () => {
        if (isLiveVoiceActive) setTimeout(startLiveListening, 600);
    });
}

function connectLiveWebSocket() {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    try {
        liveSocket = new WebSocket(`${wsProtocol}//${window.location.host}/ws/live`);
        liveSocket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === "ai_response") {
                const reply = data.reply || "සමාවන්න.";
                document.getElementById("liveVoiceStatus").innerText = reply;
                speakText(reply, () => { if (isLiveVoiceActive) setTimeout(startLiveListening, 800); });
            }
        };
    } catch(e){}
}

function closeLiveVoiceMode() {
    isLiveVoiceActive = false;
    isAiSpeaking = false;
    if (recognition) { try { recognition.abort(); } catch(e){} recognition = null; }
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    if (animFrameId) cancelAnimationFrame(animFrameId);
    if (liveSocket) liveSocket.close();
    document.getElementById("liveVoiceOverlay").classList.remove("active");
}

function cleanTextForSpeech(text) {
    if (!text) return "";
    return text.replace(/[*#`_]/g, ' ').trim();
}

async function speakText(text, onCompleteCallback = null) {
    if (!text || !text.trim()) { if (onCompleteCallback) onCompleteCallback(); return; }
    isAiSpeaking = true;
    const cleanedText = cleanTextForSpeech(text);
    const selectedGender = (currentUser && currentUser.voice_preference) ? currentUser.voice_preference : "male";

    try {
        const response = await fetch("/api/tts", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text: cleanedText, voice: selectedGender })
        });
        if (!response.ok) throw new Error();
        const blob = await response.blob();
        const audio = new Audio(URL.createObjectURL(blob));
        audio.onended = () => { isAiSpeaking = false; if (onCompleteCallback) onCompleteCallback(); };
        audio.onerror = () => { isAiSpeaking = false; if (onCompleteCallback) onCompleteCallback(); };
        await audio.play();
    } catch (e) {
        if ('speechSynthesis' in window) {
            const utterance = new SpeechSynthesisUtterance(cleanedText);
            utterance.lang = "si-LK";
            utterance.onend = () => { isAiSpeaking = false; if (onCompleteCallback) onCompleteCallback(); };
            window.speechSynthesis.speak(utterance);
        } else {
            isAiSpeaking = false;
            if (onCompleteCallback) onCompleteCallback();
        }
    }
}

function startLiveListening() {
    if (!isLiveVoiceActive || !SpeechRecognition || isRecognitionRunning) return;
    try {
        isRecognitionRunning = true;
        recognition = new SpeechRecognition();
        recognition.lang = "si-LK";
        recognition.start();
        recognition.onresult = (e) => {
            const text = e.results[0][0].transcript;
            document.getElementById("liveTranscript").innerText = text;
            isRecognitionRunning = false;
            if (liveSocket && liveSocket.readyState === WebSocket.OPEN) {
                liveSocket.send(JSON.stringify({ type: "user_speech", text }));
            }
        };
        recognition.onerror = recognition.onend = () => { isRecognitionRunning = false; };
    } catch (err) { isRecognitionRunning = false; }
}

function toggleLiveMic() {
    startLiveListening();
}