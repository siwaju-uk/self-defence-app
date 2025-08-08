// UK Legal Chatbot - Chat Interface JavaScript

class LegalChatBot {
    constructor() {
        this.socket = null;
        this.isConnected = false;
        this.isTyping = false;
        this.messageHistory = [];

        this.init();
    }

    init() {
        this.initializeSocket();
        this.bindEvents();
        this.loadChatHistory();
    }

    initializeSocket() {
        this.socket = io();

        this.socket.on('connect', () => {
            this.handleConnection(true);
        });

        this.socket.on('disconnect', () => {
            this.handleConnection(false);
        });

        this.socket.on('status', (data) => {
            console.log('Status:', data.msg);
        });

        this.socket.on('bot_response_chunk', (data) => {
            this.updateStreamingResponse(data.chunk);
        });

        this.socket.on('bot_response_end', (data) => {
            this.finalizeStreamingResponse(data.message, data);
        });

        this.socket.on('document_uploaded', (data) => {
            const message = `📄 Document Uploaded: <strong>${data.filename}</strong><br>${data.summary}`;
            this.addMessage(message, 'bot');
        });

        this.socket.on('document_error', (data) => {
            const message = `❌ Error processing document: ${data.error}`;
            this.addMessage(message, 'bot');
        });

        this.socket.on('typing', (data) => {
            this.handleTypingIndicator(data.typing);
        });

        this.socket.on('document_response', (data) => {
            this.setSendButtonState(true);
            this.addMessage(`Uploaded: ${data.filename}`, 'user');
            this.addMessage(data.formatted_response, 'bot', data);
        });
    }

    bindEvents() {
        const chatForm = document.getElementById('chat-form');
        const messageInput = document.getElementById('message-input');
        const sendButton = document.getElementById('send-button');
        const fileInput = document.getElementById('file-input');

        chatForm.addEventListener('submit', (e) => {
            e.preventDefault();
            this.sendMessage();
        });

        messageInput.addEventListener('input', (e) => {
            const remaining = 1000 - e.target.value.length;
            const counter = document.querySelector('.char-counter');
            if (counter) {
                counter.textContent = `${remaining} characters remaining`;
            }
        });

        if (fileInput) {
            fileInput.addEventListener('change', () => {
                this.uploadDocument(fileInput.files[0]);
            });
        }
    }



    sendMessage() {
        const messageInput = document.getElementById('message-input');
        const message = messageInput.value.trim();

        if (!message || !this.isConnected) {
            return;
        }

        if (message.length > 1000) {
            this.showError('Message too long. Please keep it under 1000 characters.');
            return;
        }

        this.addMessage(message, 'user');
        messageInput.value = '';
        this.setSendButtonState(false);

        // Begin streaming
        this.addStreamingPlaceholder();

        this.socket.emit('user_message', { message });
    }

    addStreamingPlaceholder() {
        const chatMessages = document.getElementById('chat-messages');
        const placeholder = document.createElement('div');
        placeholder.id = 'streaming-response';
        placeholder.className = 'message bot-message';
        placeholder.innerHTML = `<div class="message-content"><span id="streaming-text"></span></div>`;
        chatMessages.appendChild(placeholder);
        this.scrollToBottom();
    }

    updateStreamingResponse(chunk) {
        const textContainer = document.getElementById('streaming-text');
        if (textContainer) {
            textContainer.innerHTML += this.escapeHtml(chunk);
            this.scrollToBottom();
        }
    }

    finalizeStreamingResponse(fullMessage, data = {}) {
        const placeholder = document.getElementById('streaming-response');
        if (placeholder) {
            placeholder.remove();
        }
        this.setSendButtonState(true);
        this.addMessage(fullMessage, 'bot', data);
    }

    uploadDocument(file) {
        if (!file) return;

        this.setSendButtonState(false);

        const formData = new FormData();
        formData.append('document', file);

        fetch('/api/upload-document', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                this.socket.emit('document_uploaded', data);
            } else {
                this.socket.emit('document_error', data);
            }
        })
        .catch(error => {
            console.error('Upload error:', error);
            this.socket.emit('document_error', { error: 'An error occurred while uploading.' });
        });
    }

    addMessage(content, type, data = {}) {
        const chatMessages = document.getElementById('chat-messages');
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${type}-message`;

        const timestamp = new Date().toLocaleTimeString('en-GB', {
            hour: '2-digit',
            minute: '2-digit'
        });

        if (type === 'user') {
            messageDiv.innerHTML = `
                <div class="message-content">${this.escapeHtml(content)}</div>
                <div class="message-timestamp">${timestamp}</div>
            `;
        } else {
            let messageHTML = `
                <div class="message-content">
                    ${this.formatBotMessage(content)}
                    ${this.addTrackBadge(data.track_type)}
                    ${this.addCitations(data.citations)}
                    ${this.addReferralInfo(data.referral_info)}
                </div>
                <div class="message-timestamp">${timestamp}</div>
            `;
            messageDiv.innerHTML = messageHTML;
        }

        chatMessages.appendChild(messageDiv);
        this.scrollToBottom();
    }

    formatBotMessage(content) {
        return content
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/\n/g, '<br>')
            .replace(/•/g, '&bull;');
    }

    addTrackBadge(trackType) {
        if (!trackType) return '';
        const badges = {
            'small_claims': '<span class="badge bg-success track-badge small-claims mb-2">Small Claims Track</span>',
            'fast_track': '<span class="badge bg-warning track-badge fast-track mb-2">Fast Track</span>',
            'multi_track': '<span class="badge bg-danger track-badge multi-track mb-2">Multi-Track</span>'
        };
        return badges[trackType] || '';
    }

    addCitations(citations) {
        if (!citations || citations.length === 0) return '';
        let html = '<div class="citation mt-3"><h6 class="text-info mb-2"><i class="fas fa-quote-left me-2"></i>Sources:</h6>';
        citations.forEach(c => {
            if (c.type === 'case') {
                html += `<div class="citation-item mb-1"><strong>${c.name}</strong> ${c.citation}`;
                if (c.url) html += ` <a href="${c.url}" target="_blank" class="citation-link ms-2"><i class="fas fa-external-link-alt"></i></a>`;
                html += `</div>`;
            } else if (c.type === 'procedure') {
                html += `<div class="citation-item mb-1">${c.title}`;
                if (c.source) html += ` <a href="${c.source}" target="_blank" class="citation-link ms-2"><i class="fas fa-external-link-alt"></i></a>`;
                html += `</div>`;
            }
        });
        return html + '</div>';
    }

    addReferralInfo(info) {
        if (!info) return '';
        let html = '<div class="referral-box mt-3">';
        html += '<h6 class="text-warning mb-3"><i class="fas fa-user-tie me-2"></i>Professional Legal Advice</h6>';
        if (info.referral_advice) html += `<p class="mb-3">${info.referral_advice}</p>`;
        if (info.recommended_solicitors && info.recommended_solicitors.length > 0) {
            html += '<h6 class="mb-2">Recommended Solicitors:</h6>';
            info.recommended_solicitors.forEach(s => {
                html += `<div class="card bg-light mb-2"><div class="card-body py-2">
                    <h6 class="card-title mb-1">${s.firm_name}</h6>
                    <p class="card-text small mb-1"><strong>Contact:</strong> ${s.contact_name || 'N/A'}<br>
                    ${s.location ? `<strong>Location:</strong> ${s.location}` : ''}</p>
                    <p class="card-text small mb-1"><strong>Specialties:</strong> ${s.specialties.join(', ')}</p>
                    ${s.contact_phone ? `<small><i class="fas fa-phone me-1"></i>${s.contact_phone}</small>` : ''}
                    ${s.website ? `<small class="ms-2"><a href="${s.website}" target="_blank"><i class="fas fa-globe me-1"></i>Website</a></small>` : ''}
                </div></div>`;
            });
        }
        if (info.funding_options && info.funding_options.length > 0) {
            html += '<h6 class="mb-2 mt-3">Funding Options:</h6><div class="row">';
            info.funding_options.forEach(o => {
                html += `<div class="col-md-6 mb-2"><div class="card bg-info bg-opacity-10 border-info">
                    <div class="card-body py-2">
                        <h6 class="card-title small mb-1">${o.type}</h6>
                        <p class="card-text small mb-0">${o.description}</p>
                    </div>
                </div></div>`;
            });
            html += '</div>';
        }
        return html + '</div>';
    }

    showError(message) {
        const chatMessages = document.getElementById('chat-messages');
        const errorDiv = document.createElement('div');
        errorDiv.className = 'alert alert-danger mb-3';
        errorDiv.innerHTML = `<i class="fas fa-exclamation-triangle me-2"></i><strong>Error:</strong> ${this.escapeHtml(message)}`;
        chatMessages.appendChild(errorDiv);
        this.scrollToBottom();
        setTimeout(() => {
            if (errorDiv.parentNode) errorDiv.remove();
        }, 5000);
    }

    setSendButtonState(enabled) {
        const sendButton = document.getElementById('send-button');
        const messageInput = document.getElementById('message-input');
        sendButton.disabled = !enabled;
        messageInput.disabled = !enabled;
        sendButton.innerHTML = enabled ? '<i class="fas fa-paper-plane"></i>' : '<i class="fas fa-spinner fa-spin"></i>';
    }

    handleConnection(connected) {
        this.isConnected = connected;
        const status = document.getElementById('connection-status');
        if (connected) {
            status.className = 'badge bg-success';
            status.innerHTML = '<i class="fas fa-circle me-1"></i>Connected';
        } else {
            status.className = 'badge bg-danger';
            status.innerHTML = '<i class="fas fa-circle me-1"></i>Disconnected';
        }
    }

    handleTypingIndicator(isTyping) {
        const chatMessages = document.getElementById('chat-messages');
        let indicator = document.getElementById('typing-indicator');
        if (isTyping) {
            if (!indicator) {
                indicator = document.createElement('div');
                indicator.id = 'typing-indicator';
                indicator.className = 'message bot-message';
                indicator.innerHTML = `
                    <div class="typing-indicator">
                        <div class="typing-dots"><span></span><span></span><span></span></div>
                        <small class="ms-2">Legal assistant is typing...</small>
                    </div>
                `;
                chatMessages.appendChild(indicator);
                this.scrollToBottom();
            }
        } else if (indicator) {
            indicator.remove();
        }
    }

    loadChatHistory() {
        fetch('/api/chat-history')
            .then(response => response.json())
            .then(history => {
                history.forEach(item => {
                    this.addMessage(item.message, 'user');
                    if (item.response) {
                        this.addMessage(item.response, 'bot', {
                            legal_category: item.legal_category,
                            citations: item.citations
                        });
                    }
                });
            })
            .catch(error => {
                console.error('Error loading chat history:', error);
            });
    }

    scrollToBottom() {
        const chatContainer = document.getElementById('chat-container');
        setTimeout(() => {
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }, 100);
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Initialize chatbot
document.addEventListener('DOMContentLoaded', () => {
    new LegalChatBot();
});
