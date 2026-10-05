let recognition = null;
let autoSendTimer = null;
let isLiveVoiceActive = false;
let selectedFiles = [];
let currentUser = null;
let conversationHistory = []; // Context Memory Store

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

// App Initialization on Page Load
document.addEventListener("DOMContentLoaded", () => {
    checkUserAuth();
});

// User Auth Check
function checkUserAuth() {
    const savedUser = localStorage.getItem("nova_user_data");
    const authModal = document.getElementById("authModal");

    if (savedUser) {
        currentUser = JSON.parse(savedUser);
        if (authModal) authModal.style.display = "none";
        
        const userDisplayElem = document.getElementById("userNameDisplay");
        const creatorBadgeElem = document.getElementById("creatorBadge");

        if (userDisplayElem) {
            userDisplayElem.innerText = currentUser.first_name + " " + (currentUser.last_name || "");
        }

        if (currentUser.email && currentUser.email.toLowerCase() === "chamathmanujaya76@gmail.com") {
            if (creatorBadgeElem) creatorBadgeElem.style.display = "inline-flex";
        } else {
            if (creatorBadgeElem) creatorBadgeElem.style.display = "none";
        }
    } else {
        if (authModal) authModal.style.display = "flex";
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
            localStorage.setItem("nova_user_data", JSON.stringify(data.user));
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
            localStorage.setItem("nova_user_data", JSON.stringify(data.user));
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
        localStorage.removeItem("nova_user_data");
        location.reload();
    }
}

// Collapsible Sidebar Toggle (Gemini Style)
function toggleSidebar() {
    const sidebar = document.getElementById("sidebar");
    if (sidebar) sidebar.classList.toggle("collapsed");
}

function startNewChat() {
    const chatContainer = document.getElementById("chatContainer");
    const heroBanner = document.getElementById("heroBanner");
    chatContainer.innerHTML = "";
    if (heroBanner) heroBanner.style.display = "flex";
    selectedFiles = [];
    conversationHistory = []; // Reset Context Memory
    renderFilePreviews();
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

// Custom Markdown & Code Formatting Engine
function renderMarkdown(text) {
    if (!text) return "";
    
    // Code blocks with syntax header and Copy Button
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

    // Inline Code
    formatted = formatted.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>');

    // Headings
    formatted = formatted.replace(/^### (.*$)/gim, '<h3>$1</h3>');
    formatted = formatted.replace(/^## (.*$)/gim, '<h2>$1</h2>');
    formatted = formatted.replace(/^# (.*$)/gim, '<h1>$1</h1>');

    // Bold
    formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    
    // Bullet Points
    formatted = formatted.replace(/^\* (.*$)/gim, '<li>$1</li>');
    formatted = formatted.replace(/^- (.*$)/gim, '<li>$1</li>');
    formatted = formatted.replace(/(<li>.*<\/li>)/sim, '<ul>$1</ul>');

    // Newlines to <br> (outside code blocks)
    formatted = formatted.replace(/\n/g, '<br>');

    return formatted;
}

// One-Click Copy Code Function
function copyCodeToClipboard(codeId, buttonElem) {
    const codeElem = document.getElementById(codeId);
    if (!codeElem) return;

    const textToCopy = codeElem.innerText || codeElem.textContent;
    navigator.clipboard.writeText(textToCopy).then(() => {
        const originalHtml = buttonElem.innerHTML;
        buttonElem.innerHTML = `<i class="fa-solid fa-check" style="color: #00ff88;"></i> Copied!`;
        setTimeout(() => {
            buttonElem.innerHTML = originalHtml;
        }, 2000);
    }).catch(err => {
        alert("කෝඩ් එක Copy කරගැනීමට නොහැකි විය.");
    });
}

// Text Message Sending Logic with Nova Star Loading Animation
async function sendMessage(presetMessage = null) {
    const input = document.getElementById("userInput");
    const message = presetMessage || input.value.trim();
    const searchToggle = document.getElementById("webSearchToggle").checked;
    const heroBanner = document.getElementById("heroBanner");

    if (!message && selectedFiles.length === 0) return;

    if (heroBanner) heroBanner.style.display = "none";

    const currentFiles = [...selectedFiles];
    appendMessage(message, "user-msg", currentFiles);

    // Save to conversation history memory
    conversationHistory.push({ role: "user", content: message });

    input.value = "";
    selectedFiles = [];
    renderFilePreviews();

    if (autoSendTimer) clearTimeout(autoSendTimer);

    // Show Nova Star Loading Animation
    const loadingHtml = `<div class="nova-star-loader"><i class="fa-solid fa-sparkles"></i></div>`;
    const loadingId = appendMessage(loadingHtml, "bot-msg", [], true);

    try {
        const userId = currentUser ? currentUser.id : "guest";
        const firstName = currentUser ? currentUser.first_name : "User";
        const userEmail = currentUser ? currentUser.email : "";

        const res = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                user_id: userId,
                first_name: firstName,
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
        
        // Save assistant response to conversation history memory
        conversationHistory.push({ role: "assistant", content: replyText });

        if (botMsgElem) {
            botMsgElem.innerHTML = renderMarkdown(replyText);
        }
    } catch (err) {
        const botMsgElem = document.getElementById(loadingId);
        if (botMsgElem) botMsgElem.innerText = "සන්නිවේදන දෝෂයක් සිදු විය. කරුණාකර නැවත උත්සාහ කරන්න.";
    }
}

// Append Message UI Helper
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
        if (isHtml) {
            textNode.innerHTML = content;
        } else {
            textNode.innerHTML = renderMarkdown(content);
        }
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
            if (input && input.value.trim()) {
                sendMessage();
            }
        }, 5000);
    };

    rec.onerror = rec.onend = () => {
        if (micBtn) micBtn.classList.remove("recording");
    };
}

// Fullscreen Nova-X Live Voice Mode with User Greeting
function openLiveVoiceMode() {
    isLiveVoiceActive = true;
    document.getElementById("liveVoiceOverlay").classList.add("active");

    const firstName = currentUser ? currentUser.first_name : "User";
    const greetingText = `Hi ${firstName}, what shall we do today?`;

    const statusText = document.getElementById("liveVoiceStatus");
    if (statusText) statusText.innerText = greetingText;

    if ('speechSynthesis' in window) {
        const utterance = new SpeechSynthesisUtterance(greetingText);
        utterance.lang = "en-US";
        window.speechSynthesis.speak(utterance);
    }

    setTimeout(startLiveListening, 2500);
}

function closeLiveVoiceMode() {
    isLiveVoiceActive = false;
    if (recognition) recognition.stop();
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    document.getElementById("liveVoiceOverlay").classList.remove("active");
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
    if (statusText) statusText.innerText = "Nova-X සිතමින් පවතී...";

    try {
        const userId = currentUser ? currentUser.id : "guest";
        const firstName = currentUser ? currentUser.first_name : "User";
        const userEmail = currentUser ? currentUser.email : "";

        const res = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                user_id: userId,
                first_name: firstName,
                email: userEmail,
                message: userText,
                enable_search: true,
                history: conversationHistory
            })
        });

        const data = await res.json();
        const reply = data.reply || "සමාවන්න, මට එය තේරුණේ නැත.";

        if (statusText) statusText.innerText = reply;
        setTimeout(startLiveListening, 3500);
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