/**
 * app.js — ContextAI frontend application
 *
 * Vanilla JavaScript, Fetch API, no frameworks.
 * All user-supplied text is inserted via textContent / createTextNode
 * to prevent XSS — never via innerHTML with untrusted content.
 */

"use strict";

// ============================================================
// State
// ============================================================

const state = {
    currentConvId: null,
    isLoading: false,
    conversations: [],
    contextWindowSize: 20,
};

// ============================================================
// DOM references
// ============================================================

const els = {
    // Sidebar
    newChatBtn:          document.getElementById("newChatBtn"),
    conversationsList:   document.getElementById("conversationsList"),
    apiStatusDot:        document.getElementById("apiStatusDot"),
    apiStatusText:       document.getElementById("apiStatusText"),
    sidebarToggle:       document.getElementById("sidebarToggle"),
    sidebar:             document.getElementById("sidebar"),

    // Welcome
    welcomeScreen:       document.getElementById("welcomeScreen"),
    welcomeNewChatBtn:   document.getElementById("welcomeNewChatBtn"),

    // Chat interface
    chatInterface:       document.getElementById("chatInterface"),
    currentConvTitle:    document.getElementById("currentConvTitle"),
    renameBtn:           document.getElementById("renameBtn"),
    deleteConvBtn:       document.getElementById("deleteConvBtn"),
    contextBadge:        document.getElementById("contextBadge"),
    messagesArea:        document.getElementById("messagesArea"),
    messagesContainer:   document.getElementById("messagesContainer"),
    errorBanner:         document.getElementById("errorBanner"),
    errorText:           document.getElementById("errorText"),
    errorDismiss:        document.getElementById("errorDismiss"),
    chatInput:           document.getElementById("chatInput"),
    sendBtn:             document.getElementById("sendBtn"),
    contextWindowSize:   document.getElementById("contextWindowSize"),

    // Modals
    renameModal:         document.getElementById("renameModal"),
    renameInput:         document.getElementById("renameInput"),
    renameCancelBtn:     document.getElementById("renameCancelBtn"),
    renameConfirmBtn:    document.getElementById("renameConfirmBtn"),
    deleteModal:         document.getElementById("deleteModal"),
    deleteCancelBtn:     document.getElementById("deleteCancelBtn"),
    deleteConfirmBtn:    document.getElementById("deleteConfirmBtn"),
};

// ============================================================
// API helpers
// ============================================================

async function apiFetch(path, options = {}) {
    const defaults = {
        headers: { "Content-Type": "application/json" },
    };
    const config = { ...defaults, ...options };
    if (config.body && typeof config.body === "object") {
        config.body = JSON.stringify(config.body);
    }
    const response = await fetch(path, config);
    const data = await response.json();
    return { ok: response.ok, status: response.status, data };
}

// ============================================================
// Health check
// ============================================================

async function checkHealth() {
    try {
        const { ok, data } = await apiFetch("/api/health");
        if (ok && data.healthy) {
            if (data.api_key_configured) {
                setStatus("ok", `Model: ${data.model}`);
            } else {
                setStatus("warn", "API key not configured");
            }
            state.contextWindowSize = data.max_context_messages ?? 20;
            els.contextWindowSize.textContent = state.contextWindowSize;
        } else {
            setStatus("error", "Service unavailable");
        }
    } catch {
        setStatus("error", "Cannot reach server");
    }
}

function setStatus(level, text) {
    els.apiStatusDot.className = `info-dot ${level}`;
    els.apiStatusText.textContent = text;
}

// ============================================================
// Conversations — list / load / create
// ============================================================

async function loadConversations() {
    try {
        const { ok, data } = await apiFetch("/api/conversations");
        if (ok) {
            state.conversations = data.conversations;
            renderConversationList();
        }
    } catch (err) {
        console.error("Failed to load conversations:", err);
    }
}

function renderConversationList() {
    const list = els.conversationsList;
    list.innerHTML = "";

    if (state.conversations.length === 0) {
        const msg = document.createElement("div");
        msg.className = "empty-sidebar-msg";
        msg.textContent = "No conversations yet.";
        list.appendChild(msg);
        return;
    }

    for (const conv of state.conversations) {
        list.appendChild(createConvItem(conv));
    }
}

function createConvItem(conv) {
    const item = document.createElement("div");
    item.className = "conv-item" + (conv.id === state.currentConvId ? " active" : "");
    item.dataset.id = conv.id;

    const title = document.createElement("span");
    title.className = "conv-title";
    title.textContent = conv.title || "Untitled";

    const delBtn = document.createElement("button");
    delBtn.className = "conv-delete-btn";
    delBtn.textContent = "✕";
    delBtn.title = "Delete conversation";
    delBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        openDeleteModal(conv.id);
    });

    item.addEventListener("click", () => openConversation(conv.id));
    item.appendChild(title);
    item.appendChild(delBtn);
    return item;
}

async function openConversation(convId) {
    if (state.isLoading) return;
    state.currentConvId = convId;

    try {
        const { ok, data } = await apiFetch(`/api/conversations/${convId}`);
        if (!ok) {
            showError(data.message || "Failed to load conversation.");
            return;
        }
        const conv = data.conversation;
        showChatInterface();
        els.currentConvTitle.textContent = conv.title || "Untitled";
        renderMessages(conv.messages || []);
        updateActiveConvItem();
        closeSidebar();
    } catch (err) {
        showError("Failed to load conversation. Please try again.");
    }
}

async function createNewConversation() {
    if (state.isLoading) return;
    state.currentConvId = null;
    showChatInterface();
    clearMessages();
    els.currentConvTitle.textContent = "New Conversation";
    els.contextBadge.textContent = "context: —";
    updateActiveConvItem();
    hideError();
    closeSidebar();
    // Focus input
    els.chatInput.focus();
}

// ============================================================
// Message rendering
// ============================================================

function renderMessages(messages) {
    clearMessages();
    for (const msg of messages) {
        appendMessage(msg.role, msg.content, msg.created_at);
    }
    scrollToBottom();
}

function appendMessage(role, content, timestamp) {
    const wrapper = document.createElement("div");
    wrapper.className = `message ${role}`;

    const avatar = document.createElement("div");
    avatar.className = "message-avatar";
    avatar.textContent = role === "user" ? "🧑" : "🤖";

    const body = document.createElement("div");
    body.className = "message-body";

    const bubble = document.createElement("div");
    bubble.className = "message-bubble";
    // Safe text insertion — no innerHTML with untrusted content
    bubble.textContent = content;

    const timeEl = document.createElement("div");
    timeEl.className = "message-time";
    timeEl.textContent = formatTime(timestamp);

    body.appendChild(bubble);
    body.appendChild(timeEl);
    wrapper.appendChild(avatar);
    wrapper.appendChild(body);
    els.messagesContainer.appendChild(wrapper);
}

function showLoadingIndicator() {
    const wrapper = document.createElement("div");
    wrapper.className = "loading-message message assistant";
    wrapper.id = "loadingIndicator";

    const avatar = document.createElement("div");
    avatar.className = "message-avatar";
    avatar.textContent = "🤖";

    const bubble = document.createElement("div");
    bubble.className = "loading-bubble";
    bubble.innerHTML = '<div class="dot"></div><div class="dot"></div><div class="dot"></div>';

    wrapper.appendChild(avatar);
    wrapper.appendChild(bubble);
    els.messagesContainer.appendChild(wrapper);
    scrollToBottom();
}

function hideLoadingIndicator() {
    const el = document.getElementById("loadingIndicator");
    if (el) el.remove();
}

function clearMessages() {
    els.messagesContainer.innerHTML = "";
}

function scrollToBottom() {
    requestAnimationFrame(() => {
        els.messagesArea.scrollTop = els.messagesArea.scrollHeight;
    });
}

function formatTime(isoString) {
    if (!isoString) return "";
    try {
        const d = new Date(isoString.endsWith("Z") ? isoString : isoString + "Z");
        return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    } catch {
        return "";
    }
}

// ============================================================
// Sending messages
// ============================================================

async function sendMessage() {
    const rawText = els.chatInput.value;
    const text = rawText.trim();
    if (!text || state.isLoading) return;

    setLoading(true);
    hideError();

    // Optimistically render the user's message
    appendMessage("user", text, new Date().toISOString());
    els.chatInput.value = "";
    autoResizeInput();
    scrollToBottom();
    showLoadingIndicator();

    try {
        const payload = { message: text };
        if (state.currentConvId) {
            payload.conversation_id = state.currentConvId;
        }

        const { ok, status, data } = await apiFetch("/api/chat", {
            method: "POST",
            body: payload,
        });

        hideLoadingIndicator();

        if (!ok) {
            showError(data.message || "An error occurred. Please try again.");
            // Remove the optimistic user bubble since the message was not saved
            const userMsgs = els.messagesContainer.querySelectorAll(".message.user");
            if (userMsgs.length > 0) {
                userMsgs[userMsgs.length - 1].remove();
            }
            setLoading(false);
            return;
        }

        // Update conversation ID (may be new)
        if (!state.currentConvId || state.currentConvId !== data.conversation_id) {
            state.currentConvId = data.conversation_id;
            updateActiveConvItem();
            await loadConversations();
        }

        // Update context badge
        els.contextBadge.textContent = `context: ${data.context_messages_used} msgs`;

        // Append assistant reply
        appendMessage("assistant", data.reply, new Date().toISOString());
        scrollToBottom();

        // Update conversation title in header (may have been auto-titled)
        await refreshCurrentConvTitle();

    } catch (err) {
        hideLoadingIndicator();
        // Remove optimistic user bubble
        const userMsgs = els.messagesContainer.querySelectorAll(".message.user");
        if (userMsgs.length > 0) {
            userMsgs[userMsgs.length - 1].remove();
        }
        showError("Network error — could not reach the server. Check your connection.");
        console.error("sendMessage error:", err);
    }

    setLoading(false);
}

async function refreshCurrentConvTitle() {
    if (!state.currentConvId) return;
    try {
        const { ok, data } = await apiFetch(`/api/conversations/${state.currentConvId}`);
        if (ok) {
            els.currentConvTitle.textContent = data.conversation.title || "Untitled";
        }
    } catch {}
}

// ============================================================
// Rename conversation
// ============================================================

function openRenameModal() {
    if (!state.currentConvId) return;
    els.renameInput.value = els.currentConvTitle.textContent || "";
    els.renameModal.style.display = "flex";
    els.renameInput.focus();
    els.renameInput.select();
}

function closeRenameModal() {
    els.renameModal.style.display = "none";
}

async function confirmRename() {
    const newTitle = els.renameInput.value.trim();
    if (!newTitle || !state.currentConvId) {
        closeRenameModal();
        return;
    }

    try {
        const { ok, data } = await apiFetch(
            `/api/conversations/${state.currentConvId}`,
            { method: "PATCH", body: { title: newTitle } }
        );
        if (ok) {
            els.currentConvTitle.textContent = data.conversation.title;
            await loadConversations();
        } else {
            showError(data.message || "Failed to rename conversation.");
        }
    } catch {
        showError("Could not rename conversation.");
    }

    closeRenameModal();
}

// ============================================================
// Delete conversation
// ============================================================

let _pendingDeleteId = null;

function openDeleteModal(convId) {
    _pendingDeleteId = convId || state.currentConvId;
    if (!_pendingDeleteId) return;
    els.deleteModal.style.display = "flex";
}

function closeDeleteModal() {
    els.deleteModal.style.display = "none";
    _pendingDeleteId = null;
}

async function confirmDelete() {
    const convId = _pendingDeleteId;
    closeDeleteModal();
    if (!convId) return;

    try {
        const { ok, data } = await apiFetch(`/api/conversations/${convId}`, {
            method: "DELETE",
        });
        if (!ok) {
            showError(data.message || "Failed to delete conversation.");
            return;
        }

        // If deleting the active conversation, go back to welcome
        if (convId === state.currentConvId) {
            state.currentConvId = null;
            showWelcomeScreen();
        }

        await loadConversations();
    } catch {
        showError("Could not delete conversation.");
    }
}

// ============================================================
// UI helpers
// ============================================================

function showChatInterface() {
    els.welcomeScreen.style.display = "none";
    els.chatInterface.style.display = "flex";
}

function showWelcomeScreen() {
    els.chatInterface.style.display = "none";
    els.welcomeScreen.style.display = "flex";
}

function updateActiveConvItem() {
    document.querySelectorAll(".conv-item").forEach((el) => {
        el.classList.toggle("active", el.dataset.id === state.currentConvId);
    });
}

function setLoading(loading) {
    state.isLoading = loading;
    els.sendBtn.disabled = loading;
    els.chatInput.disabled = loading;
}

function showError(message) {
    els.errorText.textContent = message;
    els.errorBanner.style.display = "flex";
}

function hideError() {
    els.errorBanner.style.display = "none";
    els.errorText.textContent = "";
}

function autoResizeInput() {
    const el = els.chatInput;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 160) + "px";
}

function closeSidebar() {
    els.sidebar.classList.remove("open");
}

// ============================================================
// Event listeners
// ============================================================

// New chat
els.newChatBtn.addEventListener("click", createNewConversation);
els.welcomeNewChatBtn.addEventListener("click", createNewConversation);

// Send message
els.sendBtn.addEventListener("click", sendMessage);

els.chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

els.chatInput.addEventListener("input", autoResizeInput);

// Error dismiss
els.errorDismiss.addEventListener("click", hideError);

// Rename
els.renameBtn.addEventListener("click", openRenameModal);
els.renameCancelBtn.addEventListener("click", closeRenameModal);
els.renameConfirmBtn.addEventListener("click", confirmRename);
els.renameInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") confirmRename();
    if (e.key === "Escape") closeRenameModal();
});

// Delete (from header button)
els.deleteConvBtn.addEventListener("click", () => openDeleteModal(state.currentConvId));
els.deleteCancelBtn.addEventListener("click", closeDeleteModal);
els.deleteConfirmBtn.addEventListener("click", confirmDelete);

// Close modals on overlay click
els.renameModal.addEventListener("click", (e) => {
    if (e.target === els.renameModal) closeRenameModal();
});
els.deleteModal.addEventListener("click", (e) => {
    if (e.target === els.deleteModal) closeDeleteModal();
});

// Mobile sidebar toggle
els.sidebarToggle.addEventListener("click", () => {
    els.sidebar.classList.toggle("open");
});

// Close sidebar when clicking outside on mobile
document.addEventListener("click", (e) => {
    if (
        window.innerWidth <= 700 &&
        els.sidebar.classList.contains("open") &&
        !els.sidebar.contains(e.target) &&
        e.target !== els.sidebarToggle
    ) {
        closeSidebar();
    }
});

// ============================================================
// Keyboard shortcuts
// ============================================================

document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
        closeRenameModal();
        closeDeleteModal();
    }
});

// ============================================================
// Initialise
// ============================================================

(async function init() {
    await checkHealth();
    await loadConversations();
    // Show welcome screen by default
    showWelcomeScreen();
})();

