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
let isUserSpeaking = false;
let isRecognitionRunning = false;

let audioCtx = null;
let analyser = null;
let micStream = null;
let animFrameId = null;

let scene, camera, renderer, particleSystem;
let glowRingLine, glowRingGeometry;
let numParticles = 5000;
let particlePositions, originalPositions, targetPositions;
let isAiSpeaking = false;
let aiVoiceWaveTime = 0;
let assemblyProgress = 0; // 0 = scattered dust/stars, 1 = fully assembled face

let allSystemUsers = [];
let selectedRecipientEmail = "all";

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

document.addEventListener("DOMContentLoaded", () => {
    checkUserAuth();
    loadSavedHistory();
    if ('speechSynthesis' in window) {
        window.speechSynthesis.onvoiceschanged = () => {
            window.speechSynthesis.getVoices();
        };
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
        } else {
            if (redDot) redDot.style.display = "none";
            if (tabDot) tabDot.style.display = "none";
        }
    } catch (e) {
        console.error("Error checking notifications:", e);
    }
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
        if (creatorControlTabBtn) creatorControlTabBtn.style.display = "flex";
    } else {
        if (creatorBadgeElem) creatorBadgeElem.style.display = "none";
        if (settingsCreatorBadgeElem) settingsCreatorBadgeElem.style.display = "none";
        if (creatorControlTabBtn) creatorControlTabBtn.style.display = "none";
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

// MESSAGES & FEEDBACK TAB LOGIC
async function loadMessagesAndUsersTab() {
    if (!currentUser || !currentUser.email) return;
    const isCreator = currentUser.email.toLowerCase() === "chamathmanujaya76@gmail.com";
    const container = document.getElementById("messagesFeedbackContainer");
    if (!container) return;

    container.innerHTML = `<div style="text-align:center; color:#888; padding:20px;">Loading messages...</div>`;

    try {
        const msgRes = await fetch(`/api/messages/${currentUser.email}`);
        const msgData = await msgRes.json();
        const messages = msgData.messages || [];

        await fetch("/api/messages/mark_read", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email: currentUser.email })
        });
        checkUnreadNotifications();

        if (isCreator) {
            const usersRes = await fetch("/api/users/list");
            const usersData = await usersRes.json();
            allSystemUsers = usersData.users || [];

            let html = `
                <div style="display: flex; flex-direction: column; gap: 12px;">
                    <h3 style="color: #FFD700; font-size: 15px;"><i class="fa-solid fa-comments"></i> Creator Broadcast & Direct Messaging Box</h3>
                    <p style="font-size: 12px; color: #aaa;">සියලුම පරිශීලකයින්ට (All) හෝ විශේෂිත පරිශීලකයෙකුට පණිවිඩ යවන්න සහ ලැබුණු ප්‍රතිපෝෂණ බලන්න.</p>
                    
                    <div style="background: #0b0516; border: 1px solid #7B00FF; border-radius: 12px; padding: 12px; display: flex; flex-direction: column; gap: 10px;">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <span style="font-size: 12px; color: #a855f7; font-weight: 700;">Recipient: <span id="selectedRecipientDisplay" style="color: #00ff88;">All Users (Broadcast)</span></span>
                            <button onclick="selectRecipient('all', 'All Users (Broadcast)')" style="background: #120826; border: 1px solid #7B00FF; color: #fff; padding: 4px 10px; border-radius: 6px; font-size: 11px; cursor: pointer;">Select All</button>
                        </div>

                        <input type="text" id="userSearchInput" placeholder="Search user by name..." oninput="filterUserAccountList()" style="width: 100%; background: #000; border: 1px solid rgba(123,0,255,0.4); border-radius: 8px; padding: 8px 12px; color: #fff; font-size: 12px; outline: none;">

                        <div id="usersAccountListContainer" style="max-height: 110px; overflow-y: auto; display: flex; flex-direction: column; gap: 4px; background: #000; padding: 8px; border-radius: 8px; border: 1px solid rgba(123,0,255,0.2);">
                            ${renderUserAccountListItems(allSystemUsers)}
                        </div>

                        <textarea id="creatorMessageContent" placeholder="Type your message here..." style="width: 100%; height: 70px; background: #000; border: 1px solid #7B00FF; border-radius: 8px; padding: 8px; color: #fff; font-size: 12px; outline: none; resize: none;"></textarea>
                        
                        <button onclick="sendCreatorMessageAction()" style="background: linear-gradient(135deg, #7B00FF 0%, #0044FF 100%); color: #fff; border: none; padding: 8px; border-radius: 8px; font-size: 13px; font-weight: 700; cursor: pointer;">Send Message</button>
                    </div>

                    <h4 style="color: #fff; font-size: 13px; margin-top: 5px;">Inbox / User Feedbacks & Messages</h4>
                    <div style="max-height: 180px; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; background: #000; padding: 10px; border-radius: 10px; border: 1px solid rgba(123,0,255,0.3);">
                        ${messages.length === 0 ? '<div style="color: #666; font-size: 12px; text-align: center;">No messages or feedback received yet.</div>' : messages.map(m => `
                            <div style="background: #0b0516; border: 1px solid rgba(123,0,255,0.3); border-radius: 8px; padding: 8px; font-size: 12px;">
                                <div style="display: flex; justify-content: space-between; color: #a855f7; font-weight: 600; margin-bottom: 2px;">
                                    <span>${m.sender_name || m.sender_email}</span>
                                    <span style="font-size: 10px; color: #666;">To: ${m.recipient_email}</span>
                                </div>
                                <div style="color: #fff;">${m.content}</div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;
            container.innerHTML = html;
        } else {
            let html = `
                <div style="display: flex; flex-direction: column; gap: 14px;">
                    <h3 style="color: #7B00FF; font-size: 15px;"><i class="fa-solid fa-comments"></i> Messages and Feedback</h3>
                    <p style="font-size: 12px; color: #aaa;">You can send messages or feedback directly to the creator (Chamath Manujaya) here.</p>
                    
                    <div style="background: #0b0516; border: 1px solid #7B00FF; border-radius: 12px; padding: 12px; display: flex; flex-direction: column; gap: 10px;">
                        <textarea id="userFeedbackContent" placeholder="Send a message or feedback to the creator..." style="width: 100%; height: 90px; background: #000; border: 1px solid #7B00FF; border-radius: 8px; padding: 10px; color: #fff; font-size: 13px; outline: none; resize: none;"></textarea>
                        <button onclick="sendUserFeedbackAction()" style="background: linear-gradient(135deg, #7B00FF 0%, #0044FF 100%); color: #fff; border: none; padding: 10px; border-radius: 8px; font-size: 13px; font-weight: 700; cursor: pointer;">Send to Creator</button>
                    </div>

                    <h4 style="color: #fff; font-size: 13px; margin-top: 5px;">Messages from Creator</h4>
                    <div style="max-height: 180px; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; background: #000; padding: 10px; border-radius: 10px; border: 1px solid rgba(123,0,255,0.3);">
                        ${messages.length === 0 ? '<div style="color: #666; font-size: 12px; text-align: center;">No messages from creator.</div>' : messages.map(m => `
                            <div style="background: #0b0516; border: 1px solid rgba(123,0,255,0.3); border-radius: 8px; padding: 8px; font-size: 12px;">
                                <div style="color: #FFD700; font-weight: 600; margin-bottom: 2px;"><i class="fa-solid fa-crown"></i> From Creator</div>
                                <div style="color: #fff;">${m.content}</div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;
            container.innerHTML = html;
        }
    } catch (e) {
        container.innerHTML = `<div style="color: #ff4d4d; font-size: 12px; text-align: center;">Error loading messages.</div>`;
    }
}

function renderUserAccountListItems(users) {
    if (!users || users.length === 0) return '<div style="color:#666; font-size:11px; text-align:center;">No users found</div>';
    return users.map(u => `
        <div onclick="selectRecipient('${u.email}', '${u.name}')" style="padding: 6px 8px; border-radius: 6px; cursor: pointer; display: flex; justify-content: space-between; align-items: center; background: #120826; transition: background 0.2s;" onmouseover="this.style.background='#1f0d3d'" onmouseout="this.style.background='#120826'">
            <span style="color: #fff; font-weight: 600;">${u.name}</span>
            <span style="color: #888; font-size: 11px;">${u.email}</span>
        </div>
    `).join('');
}

function filterUserAccountList() {
    const query = document.getElementById("userSearchInput").value.toLowerCase();
    const filtered = allSystemUsers.filter(u => u.name.toLowerCase().includes(query) || u.email.toLowerCase().includes(query));
    const container = document.getElementById("usersAccountListContainer");
    if (container) {
        container.innerHTML = renderUserAccountListItems(filtered);
    }
}

function selectRecipient(email, name) {
    selectedRecipientEmail = email;
    const display = document.getElementById("selectedRecipientDisplay");
    if (display) {
        display.innerText = name;
        display.style.color = email === 'all' ? '#00ff88' : '#a855f7';
    }
}

async function sendCreatorMessageAction() {
    const content = document.getElementById("creatorMessageContent").value.trim();
    if (!content) {
        alert("කරුණාකර පණිවිඩයක් ටයිප් කරන්න.");
        return;
    }
    const senderName = currentUser.full_name || currentUser.first_name || "Creator";

    try {
        const res = await fetch("/api/messages/send", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                sender_email: currentUser.email,
                sender_name: senderName,
                recipient_email: selectedRecipientEmail,
                content: content
            })
        });
        const data = await res.json();
        if (data.success) {
            alert("පණිවිඩය සාර්ථකව යවන ලදී!");
            document.getElementById("creatorMessageContent").value = "";
            loadMessagesAndUsersTab();
        } else {
            alert("පණිවිඩය යැවීමට නොහැකි විය.");
        }
    } catch (e) {
        alert("සන්නිවේදන දෝෂයක් සිදුවිය!");
    }
}

async function sendUserFeedbackAction() {
    const content = document.getElementById("userFeedbackContent").value.trim();
    if (!content) {
        alert("Please enter a message or feedback.");
        return;
    }
    const senderName = currentUser.full_name || `${currentUser.first_name || ''} ${currentUser.last_name || ''}`.trim() || currentUser.first_name || "User";

    try {
        const res = await fetch("/api/messages/send", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                sender_email: currentUser.email,
                sender_name: senderName,
                recipient_email: "chamathmanujaya76@gmail.com",
                content: content
            })
        });
        const data = await res.json();
        if (data.success) {
            alert("Feedback sent successfully to Creator!");
            document.getElementById("userFeedbackContent").value = "";
            loadMessagesAndUsersTab();
        } else {
            alert("Failed to send feedback.");
        }
    } catch (e) {
        alert("Connection error!");
    }
}

// CREATOR ADMIN METRICS & ADVANCED ADMIN DASHBOARD FUNCTIONS
async function fetchCreatorMetrics() {
    if (!currentUser || currentUser.email.toLowerCase() !== "chamathmanujaya76@gmail.com") return;

    try {
        const res = await fetch(`/api/admin/metrics/${currentUser.email}`);
        const data = await res.json();
        if (data.success && data.metrics) {
            const metrics = data.metrics;
            document.getElementById("statTokenCount").innerText = metrics.token_usage_estimated || 0;
            document.getElementById("statErrorCount").innerText = metrics.errors_log ? metrics.errors_log.length : 0;

            const usageListElem = document.getElementById("apiKeyUsageList");
            if (usageListElem) {
                let html = "";
                for (const [provider, count] of Object.entries(metrics.api_calls_count || {})) {
                    html += `<div style="display: flex; justify-content: space-between; padding: 2px 0;"><span>${provider}:</span><strong style="color: #00ff88;">${count} calls</strong></div>`;
                }
                usageListElem.innerHTML = html;
            }

            const errorBox = document.getElementById("systemErrorsLogBox");
            if (errorBox && metrics.errors_log) {
                if (metrics.errors_log.length === 0) {
                    errorBox.innerHTML = "No errors logged.";
                } else {
                    let errHtml = "";
                    metrics.errors_log.forEach(err => {
                        errHtml += `[${err.time}] (${err.provider}): ${err.error}<br>`;
                    });
                    errorBox.innerHTML = errHtml;
                }
            }
        }
        loadCreatorKnowledgeBase();
        loadDatabaseInspector();
    } catch (e) {
        console.error("Error fetching creator metrics:", e);
    }
}

// --- Knowledge Base Viewer & Editor frontend functions ---
async function loadCreatorKnowledgeBase() {
    try {
        const res = await fetch(`/api/admin/knowledge/${currentUser.email}`);
        const data = await res.json();
        const container = document.getElementById("creatorKnowledgeList");
        if (!container) return;
        if (data.success && data.items.length > 0) {
            container.innerHTML = data.items.map(item => `
                <div style="background: #06030E; border: 1px solid rgba(123,0,255,0.4); border-radius: 8px; padding: 8px; font-size: 12px; display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                    <div><span style="color:#a855f7; font-weight:700;">[${item.category}]</span> ${item.content}</div>
                    <button onclick="deleteCreatorKnowledge('${item.id}')" style="background: #ef4444; border: none; color: #fff; padding: 3px 8px; border-radius: 4px; cursor: pointer; font-size: 11px;"><i class="fa-solid fa-trash"></i></button>
                </div>
            `).join('');
        } else {
            container.innerHTML = `<div style="color: #666; font-size: 12px; text-align: center;">No custom Knowledge Base entries found.</div>`;
        }
    } catch (e) {
        console.error("Error loading knowledge base:", e);
    }
}

async function addCreatorKnowledgeItem() {
    const content = document.getElementById("newKnowledgeInput").value.trim();
    const category = document.getElementById("newKnowledgeCategory").value;
    if (!content) return alert("Please enter knowledge content.");

    try {
        const res = await fetch("/api/admin/knowledge/save", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ creator_email: currentUser.email, content: content, category: category })
        });
        const data = await res.json();
        if (data.success) {
            document.getElementById("newKnowledgeInput").value = "";
            loadCreatorKnowledgeBase();
            alert("Knowledge injected successfully!");
        } else {
            alert("Failed to inject knowledge.");
        }
    } catch (e) {
        alert("Connection error.");
    }
}

async function deleteCreatorKnowledge(id) {
    if (!confirm("Are you sure you want to delete this knowledge entry?")) return;
    try {
        await fetch("/api/admin/knowledge/delete", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ creator_email: currentUser.email, id: id })
        });
        loadCreatorKnowledgeBase();
    } catch (e) {
        alert("Error deleting entry.");
    }
}

// --- Terminal & CLI Integration frontend functions ---
async function handleCreatorCliKeydown(e) {
    if (e.key === "Enter") {
        const cmd = e.target.value.trim();
        if (!cmd) return;
        const outputBox = document.getElementById("cliOutputBox");
        outputBox.innerHTML += `<br><span style="color: #00ff88;">> ${cmd}</span>`;
        e.target.value = "";

        try {
            const res = await fetch("/api/admin/cli", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ creator_email: currentUser.email, command: cmd })
            });
            const data = await res.json();
            outputBox.innerHTML += `<br><span style="color: #fff; white-space: pre-wrap;">${data.output}</span>`;
            outputBox.scrollTop = outputBox.scrollHeight;
        } catch (err) {
            outputBox.innerHTML += `<br><span style="color: #ff4d4d;">CLI Execution Error</span>`;
        }
    }
}

// --- Database Direct Inspector frontend functions ---
async function loadDatabaseInspector() {
    try {
        const res = await fetch(`/api/admin/db/inspect/${currentUser.email}`);
        const data = await res.json();
        const container = document.getElementById("dbInspectorContainer");
        if (!container) return;
        if (data.success && data.collections) {
            let html = "";
            for (const [collName, docs] of Object.entries(data.collections)) {
                html += `
                    <div style="background: #06030E; border: 1px solid #7B00FF; border-radius: 8px; padding: 10px; margin-bottom: 8px;">
                        <strong style="color: #FFD700; font-size: 13px;"><i class="fa-solid fa-database"></i> Collection: ${collName} (${docs.length} docs)</strong>
                        <pre style="font-size: 11px; color: #38bdf8; max-height: 100px; overflow-y: auto; margin-top: 6px;">${JSON.stringify(docs, null, 2)}</pre>
                    </div>
                `;
            }
            container.innerHTML = html || "No collections found.";
        } else {
            container.innerHTML = "Failed to inspect database.";
        }
    } catch (e) {
        console.error("Error inspecting DB:", e);
    }
}

async function runAutoDebugCheck() {
    if (!currentUser || currentUser.email.toLowerCase() !== "chamathmanujaya76@gmail.com") return;
    
    const errorBox = document.getElementById("systemErrorsLogBox");
    const errorText = errorBox ? errorBox.innerText : "No errors.";
    
    const debugContainer = document.getElementById("autoDebugResultContainer");
    const debugTextElem = document.getElementById("autoDebugText");
    
    if (debugContainer) debugContainer.style.display = "block";
    if (debugTextElem) debugTextElem.innerText = "AI is analyzing errors and generating debug fix...";

    try {
        const res = await fetch("/api/admin/autodebug", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                creator_email: currentUser.email,
                error_text: errorText
            })
        });
        const data = await res.json();
        if (data.success) {
            if (debugTextElem) debugTextElem.innerText = data.fix;
        } else {
            if (debugTextElem) debugTextElem.innerText = "Auto-debug failed: " + data.message;
        }
    } catch (e) {
        if (debugTextElem) debugTextElem.innerText = "Connection error during auto-debug.";
    }
}

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
            alert(data.message || "Email එක හෝ Password එක වැරදියි!");
        }
    } catch (err) {
        alert("සන්නිවේදන දෝෂයක් සිදුවිය!");
    }
}

function showLogoutConfirmation() {
    const modal = document.getElementById("logoutConfirmModal");
    if (modal) modal.style.display = "flex";
}

function confirmLogout(isConfirmed) {
    const modal = document.getElementById("logoutConfirmModal");
    if (modal) modal.style.display = "none";

    if (isConfirmed) {
        localStorage.removeItem("nexuz_user_data");
        location.reload();
    }
}

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

    const newFirstName = document.getElementById("setFirstName").value.trim() || currentUser.first_name;
    const newLastName = document.getElementById("setLastName").value.trim() || currentUser.last_name;
    const newAge = document.getElementById("setAge").value.trim();
    const newCountry = document.getElementById("setCountry").value.trim() || currentUser.country;
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
                first_name: newFirstName,
                last_name: newLastName,
                age: newAge,
                country: newCountry,
                purpose: newPurpose,
                password: newPassword,
                voice_preference: voicePref,
                profile_pic: newPic
            })
        });

        const data = await res.json();
        if (data.success) {
            currentUser.first_name = newFirstName;
            currentUser.last_name = newLastName;
            currentUser.full_name = `${newFirstName} ${newLastName}`.trim();
            currentUser.age = newAge;
            currentUser.country = newCountry;
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
// THREE.JS 3D SCI-FI PARTICLE AI FACE & LIVE VOICE ENGINE
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
    camera.position.z = 280;

    renderer = new THREE.WebGLRenderer({ canvas: canvasElem, alpha: true, antialias: true });
    renderer.setSize(380, 380);
    renderer.setPixelRatio(window.devicePixelRatio ? window.devicePixelRatio : 1);

    const geometry = new THREE.BufferGeometry();
    particlePositions = new Float32Array(numParticles * 3);
    originalPositions = new Float32Array(numParticles * 3);
    targetPositions = new Float32Array(numParticles * 3);

    const isFemale = currentUser && currentUser.voice_preference === "female";

    // Procedural 3D Particle Face Mesh Coordinates Generator
    for (let i = 0; i < numParticles; i++) {
        // Start scattered in outer space (dust/starfield)
        const startTheta = Math.random() * Math.PI * 2;
        const startPhi = Math.acos((Math.random() * 2) - 1);
        const startR = 250 + Math.random() * 150;
        
        const sx = startR * Math.sin(startPhi) * Math.cos(startTheta);
        const sy = startR * Math.sin(startPhi) * Math.sin(startTheta);
        const sz = startR * Math.cos(startPhi);

        originalPositions[i * 3] = sx;
        originalPositions[i * 3 + 1] = sy;
        originalPositions[i * 3 + 2] = sz;

        particlePositions[i * 3] = sx;
        particlePositions[i * 3 + 1] = sy;
        particlePositions[i * 3 + 2] = sz;

        // Target Face Shape Coordinates (Male vs Female proportions)
        let fx, fy, fz;
        const u = (Math.random() - 0.5) * 120;
        const v = (Math.random() - 0.5) * 160;

        // Facial contour modeling equations
        const faceWidth = isFemale ? 55 : 65;
        const chinWidth = isFemale ? 25 : 35;
        
        if (v > 40) { // Crown / Head top
            const theta = Math.random() * Math.PI * 2;
            const r = faceWidth * (0.8 + Math.random() * 0.2);
            fx = Math.cos(theta) * r;
            fy = 60 + Math.sin(theta) * (r * 0.7);
            fz = (Math.random() - 0.5) * 50;
        } else if (v > -20 && v <= 40) { // Eyes, Nose, Cheeks
            fx = u;
            fy = v;
            fz = Math.cos(u / 40) * 35 - Math.abs(v / 8);
        } else if (v > -70 && v <= -20) { // Mouth & Jaw
            fx = u * 0.8;
            fy = v;
            fz = Math.sin(u / 30) * 25 + 10;
        } else { // Chin & Neck
            fx = (u * (chinWidth / 60));
            fy = v;
            fz = 5 + (v * 0.1);
        }

        targetPositions[i * 3] = fx;
        targetPositions[i * 3 + 1] = fy;
        targetPositions[i * 3 + 2] = fz;
    }

    geometry.setAttribute('position', new THREE.BufferAttribute(particlePositions, 3));

    const pColor = isFemale ? 0xff66cc : 0x00ffcc; // Pink/Purple for Female, Cyan/Blue for Male
    const pMaterial = new THREE.PointsMaterial({
        color: pColor,
        size: 3.8,
        map: createGlowTexture(),
        transparent: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false
    });

    particleSystem = new THREE.Points(geometry, pMaterial);
    scene.add(particleSystem);

    assemblyProgress = 0; // Trigger assembly animation
}

async function initAudioVisualizer() {
    try {
        initThreeGlowVisualizer();
        visualizeAudio();
    } catch (e) {
        console.log("Audio visualizer init error:", e);
    }
}

function visualizeAudio() {
    if (!isLiveVoiceActive) return;

    aiVoiceWaveTime += 0.05;

    if (assemblyProgress < 1.0) {
        assemblyProgress += 0.015; // Smooth assembly from stars into face
        if (assemblyProgress > 1.0) assemblyProgress = 1.0;
    }

    if (particleSystem) {
        const positions = particleSystem.geometry.attributes.position.array;
        for (let i = 0; i < numParticles; i++) {
            const idx = i * 3;
            const ox = originalPositions[idx];
            const oy = originalPositions[idx + 1];
            const oz = originalPositions[idx + 2];

            const tx = targetPositions[idx];
            const ty = targetPositions[idx + 1];
            const tz = targetPositions[idx + 2];

            // Interpolate from starfield dust to face target
            let currX = ox + (tx - ox) * assemblyProgress;
            let currY = oy + (ty - oy) * assemblyProgress;
            let currZ = oz + (tz - oz) * assemblyProgress;

            // Lip-sync & emotional reaction simulation during AI speech
            if (isAiSpeaking && ty > -50 && ty < -20 && Math.abs(tx) < 25) {
                currY += Math.sin(aiVoiceWaveTime * 15 + i) * 3.5; // Lip movement
            }

            // Blinking & gentle head rotation
            positions[idx] = currX;
            positions[idx + 1] = currY;
            positions[idx + 2] = currZ + Math.sin(aiVoiceWaveTime * 2) * 2;
        }
        particleSystem.geometry.attributes.position.needsUpdate = true;
        particleSystem.rotation.y = Math.sin(aiVoiceWaveTime * 0.5) * 0.15; // Gentle turning
    }

    if (renderer && scene && camera) {
        renderer.render(scene, camera);
    }
    
    animFrameId = requestAnimationFrame(visualizeAudio);
}

function openLiveVoiceMode() {
    isLiveVoiceActive = true;
    isRecognitionRunning = false;
    document.getElementById("liveVoiceOverlay").classList.add("active");

    const firstName = currentUser ? currentUser.first_name : "User";
    const greetingText = `ආයුබෝවන් ${firstName}, අද මම ඔබට උදව් කළ යුත්තේ කෙසේද?`;

    const statusText = document.getElementById("liveVoiceStatus");
    if (statusText) statusText.innerText = greetingText;

    connectLiveWebSocket();
    initAudioVisualizer();
    
    speakText(greetingText, () => {
        if (isLiveVoiceActive) {
            setTimeout(startLiveListening, 600);
        }
    });
}

function connectLiveWebSocket() {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/live`;

    try {
        liveSocket = new WebSocket(wsUrl);

        liveSocket.onopen = () => {
            console.log("Connected to Nexuz Live WebSocket");
        };

        liveSocket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === "ai_response") {
                const reply = data.reply || "සමාවන්න, තේරුණේ නැත.";
                const statusText = document.getElementById("liveVoiceStatus");
                if (statusText) statusText.innerText = reply;
                
                speakText(reply, () => {
                    if (isLiveVoiceActive) {
                        setTimeout(startLiveListening, 800);
                    }
                });
            }
        };

        liveSocket.onclose = () => {
            console.log("Live WebSocket Disconnected");
        };
    } catch (e) {
        console.log("WebSocket Connection Error:", e);
    }
}

function closeLiveVoiceMode() {
    isLiveVoiceActive = false;
    isAiSpeaking = false;
    isRecognitionRunning = false;
    if (recognition) {
        try { 
            recognition.onresult = null;
            recognition.onerror = null;
            recognition.onend = null;
            recognition.abort(); 
        } catch(e){}
        recognition = null;
    }
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    if (micStream) micStream.getTracks().forEach(t => t.stop());
    if (animFrameId) cancelAnimationFrame(animFrameId);
    if (liveSocket) liveSocket.close();
    
    document.getElementById("liveVoiceOverlay").classList.remove("active");
}

function cleanTextForSpeech(text) {
    if (!text) return "";
    return text
        .replace(/```([a-zA-Z0-9_+-]*)\n([\s\S]*?)```/g, ' කේතයක් සපයා ඇත. ')
        .replace(/`([^`]+)`/g, '$1')
        .replace(/\*\*(.*?)\*\*/g, '$1')
        .replace(/\*(.*?)\*/g, '$1')
        .replace(/#+/g, '')
        .replace(/\[([^\]]+)\]\([^\)]+\)/g, '$1')
        .replace(/[#_*`~>-]/g, ' ')
        .trim();
}

async function speakText(text, onCompleteCallback = null) {
    if (!text || !text.trim()) {
        if (onCompleteCallback) onCompleteCallback();
        return;
    }

    if (recognition) {
        try {
            recognition.onresult = null;
            recognition.onerror = null;
            recognition.onend = null;
            recognition.abort();
        } catch(e){}
        recognition = null;
    }
    isRecognitionRunning = false;
    isAiSpeaking = true;

    const cleanedText = cleanTextForSpeech(text);
    const selectedGender = (currentUser && currentUser.voice_preference) ? currentUser.voice_preference : "male";

    try {
        const response = await fetch("/api/tts", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text: cleanedText, voice: selectedGender })
        });

        if (!response.ok) throw new Error("TTS generation failed");

        const blob = await response.blob();
        const audioUrl = URL.createObjectURL(blob);
        const audio = new Audio(audioUrl);

        audio.onended = () => {
            isAiSpeaking = false;
            if (onCompleteCallback) onCompleteCallback();
        };

        audio.onerror = () => {
            isAiSpeaking = false;
            if (onCompleteCallback) onCompleteCallback();
        };

        await audio.play();
    } catch (e) {
        console.error("Edge TTS playback error, falling back to Web Speech API:", e);
        if ('speechSynthesis' in window) {
            window.speechSynthesis.cancel();
            const utterance = new SpeechSynthesisUtterance(cleanedText);
            utterance.rate = 1.0;
            utterance.lang = "si-LK";
            utterance.onend = utterance.onerror = () => {
                isAiSpeaking = false;
                if (onCompleteCallback) onCompleteCallback();
            };
            window.speechSynthesis.speak(utterance);
        } else {
            isAiSpeaking = false;
            if (onCompleteCallback) onCompleteCallback();
        }
    }
}

function startLiveListening() {
    if (!isLiveVoiceActive || !SpeechRecognition || isRecognitionRunning) return;

    if ('speechSynthesis' in window && window.speechSynthesis.speaking) {
        window.speechSynthesis.cancel();
        isAiSpeaking = false;
    }

    const statusText = document.getElementById("liveVoiceStatus");
    const transcriptText = document.getElementById("liveTranscript");

    if (statusText) statusText.innerText = "සවන්දෙමින් පවතී... කතා කරන්න...";

    if (recognition) {
        try { 
            recognition.onresult = null;
            recognition.onerror = null;
            recognition.onend = null;
            recognition.abort(); 
        } catch(e){}
        recognition = null;
    }

    try {
        isRecognitionRunning = true;
        recognition = new SpeechRecognition();
        recognition.lang = "si-LK";
        recognition.interimResults = true;
        recognition.continuous = false;

        recognition.start();

        recognition.onresult = (e) => {
            let text = "";
            for (let i = e.resultIndex; i < e.results.length; i++) {
                text += e.results[i][0].transcript;
            }
            if (transcriptText) transcriptText.innerText = text;

            if (silenceTimer) clearTimeout(silenceTimer);
            silenceTimer = setTimeout(() => {
                if (text.trim().length > 0 && isLiveVoiceActive && isRecognitionRunning) {
                    isRecognitionRunning = false;
                    try { recognition.abort(); } catch(err){}
                    recognition = null;
                    processLiveVoiceInput(text);
                }
            }, 1000);

            if (e.results[0].isFinal) {
                if (silenceTimer) clearTimeout(silenceTimer);
                isRecognitionRunning = false;
                try { recognition.abort(); } catch(err){}
                recognition = null;
                processLiveVoiceInput(text);
            }
        };

        recognition.onerror = (e) => {
            console.log("Speech recognition error:", e.error);
            isRecognitionRunning = false;
            if (recognition) {
                try { recognition.abort(); } catch(err){}
                recognition = null;
            }
            if (isLiveVoiceActive && !isAiSpeaking && e.error !== 'not-allowed' && e.error !== 'aborted') {
                setTimeout(startLiveListening, 1500);
            } else if (e.error === 'not-allowed') {
                if (statusText) statusText.innerText = "මයික්‍රෆෝන අවසරය ලබා දෙන්න.";
            }
        };

        recognition.onend = () => {
            isRecognitionRunning = false;
            recognition = null;
            if (isLiveVoiceActive && !isAiSpeaking && transcriptText && !transcriptText.innerText.trim()) {
                setTimeout(startLiveListening, 1000);
            }
        };
    } catch (err) {
        console.log("Speech recognition start error:", err);
        isRecognitionRunning = false;
        recognition = null;
        if (isLiveVoiceActive && !isAiSpeaking) {
            setTimeout(startLiveListening, 2000);
        }
    }
}

async function processLiveVoiceInput(userText) {
    if (!userText || !userText.trim()) {
        if (isLiveVoiceActive) setTimeout(startLiveListening, 500);
        return;
    }

    const statusText = document.getElementById("liveVoiceStatus");
    const transcriptText = document.getElementById("liveTranscript");
    if (statusText) statusText.innerText = "Nexuz සිතමින් පවතී...";
    if (transcriptText) transcriptText.innerText = "";

    const firstName = currentUser ? currentUser.first_name : "User";
    const userEmail = currentUser ? currentUser.email : "";

    if (liveSocket && liveSocket.readyState === WebSocket.OPEN) {
        liveSocket.send(JSON.stringify({
            type: "user_speech",
            text: userText,
            first_name: firstName,
            email: userEmail
        }));
    } else {
        try {
            const res = await fetch("/api/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    user_id: currentUser ? currentUser.id : "guest",
                    first_name: firstName,
                    full_name: currentUser ? (currentUser.full_name || `${currentUser.first_name || ''} ${currentUser.last_name || ''}`.trim()) : "User",
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
                if (isLiveVoiceActive) {
                    setTimeout(startLiveListening, 800);
                }
            });

        } catch (err) {
            if (statusText) statusText.innerText = "සන්නිවේදන දෝෂයක් සිදු විය.";
            setTimeout(startLiveListening, 2000);
        }
    }
}

function toggleLiveMic() {
    const btn = document.getElementById("liveMicToggle");
    if (btn && btn.classList.contains("active")) {
        btn.classList.remove("active");
        isRecognitionRunning = false;
        if (recognition) {
            try { 
                recognition.onresult = null;
                recognition.onerror = null;
                recognition.onend = null;
                recognition.abort(); 
            } catch(e){}
            recognition = null;
        }
        document.getElementById("liveVoiceStatus").innerText = "Mic අක්‍රියයි";
    } else if (btn) {
        btn.classList.add("active");
        startLiveListening();
    }
}