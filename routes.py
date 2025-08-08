# routes.py
from flask import render_template, request, session, jsonify
from flask_socketio import emit, join_room
from app import app, socketio, db
from models import User, ChatMessage, DocumentAnalysis
from document_processor import DocumentProcessor
import uuid
import json
import logging
import os
from werkzeug.utils import secure_filename

# -----------------------------
# Config & helpers
# -----------------------------
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'txt'}
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB

def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_or_make_session_id() -> str:
    sid = session.get('user_session')
    if not sid:
        sid = str(uuid.uuid4())
        session['user_session'] = sid
    return sid

# socket session mapping:
# HTTP session (stable) -> room name (stable)
SESSION_TO_ROOM = {}
# HTTP session (stable) -> current socket SID (volatile, per connection)
SESSION_TO_SID = {}

# single instance
document_processor = DocumentProcessor()

# -----------------------------
# Pages
# -----------------------------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat')
def chat():
    # ensure HTTP session exists before socket connects
    get_or_make_session_id()
    return render_template('chat.html')

@app.route('/document-analysis')
def document_analysis():
    return render_template('document_analysis.html')

@app.route('/legal-disclaimer')
def legal_disclaimer():
    return render_template('legal_disclaimer.html')

# -----------------------------
# REST: Chat History
# -----------------------------
@app.route('/api/chat-history', methods=['GET'])
def api_chat_history():
    try:
        session_id = session.get('user_session')
        if not session_id:
            return jsonify([])

        user = User.query.filter_by(session_id=session_id).first()
        if not user:
            return jsonify([])

        # adjust field name if your model uses created_at instead of timestamp
        messages = ChatMessage.query.filter_by(user_id=user.id).order_by(ChatMessage.created_at.asc()).all()

        history = []
        for m in messages:
            item = {
                "message": m.message or "",
                "response": m.response or "",
                "legal_category": getattr(m, "legal_category", "general"),
                "created_at": getattr(m, "created_at", None).isoformat() if getattr(m, "created_at", None) else None,
                "citations": []
            }
            # citations may be a JSON string in your model
            if hasattr(m, "citations") and m.citations:
                try:
                    item["citations"] = json.loads(m.citations)
                except Exception:
                    item["citations"] = []
            history.append(item)

        return jsonify(history)
    except Exception as e:
        logging.error(f"/api/chat-history error: {e}")
        return jsonify([])

# -----------------------------
# REST: Upload & analyze document
# -----------------------------
@app.route('/api/upload-document', methods=['POST'])
def upload_document():
    try:
        if 'document' not in request.files:
            return jsonify({'success': False, 'error': 'No file uploaded.', 'type': 'error'})

        file = request.files['document']
        if not file or file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected.', 'type': 'error'})

        if not allowed_file(file.filename):
            return jsonify({'success': False, 'error': 'Unsupported file type. Use PDF, DOCX, or TXT.', 'type': 'error'})

        # ensure http session & user
        session_id = get_or_make_session_id()
        user = User.query.filter_by(session_id=session_id).first()
        if not user:
            user = User(session_id=session_id)
            db.session.add(user)
            db.session.commit()

        # read file content (no need to save to disk if you don't want)
        file_content = file.read()
        if not file_content:
            return jsonify({'success': False, 'error': 'Empty file.', 'type': 'error'})

        filename = secure_filename(file.filename)

        # extract text
        try:
            document_text = document_processor.extract_text_from_file(file_content, filename)
        except Exception as e:
            logging.error(f"extract_text_from_file error: {e}")
            return jsonify({'success': False, 'error': 'Could not read the document.', 'type': 'error'})

        if not document_text or len(document_text.strip()) < 50:
            return jsonify({'success': False, 'error': 'Document contains insufficient text.', 'type': 'error'})

        # analyze
        try:
            analysis_result = document_processor.analyze_skeleton_argument(document_text)
        except Exception as e:
            logging.error(f"analyze_skeleton_argument error: {e}")
            return jsonify({'success': False, 'error': 'Unable to analyze the document.', 'type': 'error'})

        formatted_response = document_processor.format_defence_response(analysis_result)

        # persist
        doc_analysis = DocumentAnalysis(
            user_id=user.id,
            filename=filename,
            document_text=document_text[:10000],
            analysis_summary=analysis_result.get('document_summary', ''),
            legal_arguments=json.dumps(analysis_result.get('enriched_arguments', [])),
            track_type=analysis_result.get('track_assessment', 'small_claims'),
            legal_categories=json.dumps(analysis_result.get('legal_categories', []))
        )
        db.session.add(doc_analysis)
        db.session.commit()

        # also store a chat message so it appears in history
        chat_message = ChatMessage(
            user_id=user.id,
            message=f"Document Analysis: {filename}",
            response=formatted_response,
            legal_category=(analysis_result.get('legal_categories', ['document_analysis']) or ['document_analysis'])[0]
        )
        db.session.add(chat_message)
        db.session.commit()

        # emit to the user's room if a socket is connected
        room = SESSION_TO_ROOM.get(session_id)
        if room:
            socketio.emit('document_uploaded', {
                'filename': filename,
                'summary': formatted_response
            }, to=room)

        return jsonify({
            'success': True,
            'analysis': analysis_result,
            'formatted_response': formatted_response,
            'document_id': doc_analysis.id,
            'filename': filename,
            'enriched_arguments': analysis_result.get('enriched_arguments', []),
            'type': 'success'
        })
    except Exception as e:
        logging.error(f"Unexpected /api/upload-document error: {e}")
        # best-effort socket notify
        room = SESSION_TO_ROOM.get(session.get('user_session'))
        if room:
            socketio.emit('document_error', {'error': 'Unexpected error processing document.'}, to=room)
        return jsonify({'success': False, 'error': 'Unexpected server error.', 'type': 'error'})

# -----------------------------
# Socket.IO: connect / disconnect / streaming chat
# -----------------------------
@socketio.on('connect')
def socket_connect():
    try:
        session_id = get_or_make_session_id()
        room = SESSION_TO_ROOM.get(session_id) or f"user:{session_id}"
        SESSION_TO_ROOM[session_id] = room
        # track current socket sid for this session (not used for emits, but handy for debug)
        SESSION_TO_SID[session_id] = request.sid  # type: ignore[attr-defined]
        join_room(room)
        emit('status', {'msg': 'connected', 'room': room})
    except Exception as e:
        logging.error(f"socket connect error: {e}")

@socketio.on('disconnect')
def socket_disconnect():
    try:
        session_id = session.get('user_session')
        if session_id in SESSION_TO_SID:
            SESSION_TO_SID.pop(session_id, None)
    except Exception as e:
        logging.warning(f"socket disconnect cleanup error: {e}")

@socketio.on('user_message')
def socket_user_message(data):
    try:
        session_id = get_or_make_session_id()
        room = SESSION_TO_ROOM.get(session_id) or f"user:{session_id}"
        SESSION_TO_ROOM[session_id] = room

        user = User.query.filter_by(session_id=session_id).first()
        if not user:
            user = User(session_id=session_id)
            db.session.add(user)
            db.session.commit()

        message = (data or {}).get('message', '').strip()
        if not message:
            emit('bot_response_end', {'message': 'No message provided.'}, to=room)
            return

        # stream response chunks
        full = ""
        try:
            for chunk in document_processor.generate_chat_response_streaming(message):
                emit('bot_response_chunk', {'chunk': chunk}, to=room)
                full += chunk
        except Exception as e:
            logging.error(f"streaming error: {e}")
            emit('bot_response_end', {'message': 'An error occurred while processing your message.'}, to=room)
            return

        emit('bot_response_end', {
            'message': full,
            'track_type': 'small_claims',
            'citations': [],
            'referral_info': {}
        }, to=room)

        # persist chat
        msg = ChatMessage(
            user_id=user.id,
            message=message,
            response=full,
            legal_category='general'
        )
        db.session.add(msg)
        db.session.commit()

    except Exception as e:
        logging.error(f"user_message error: {e}")
        emit('bot_response_end', {'message': 'Server error.'}, to=SESSION_TO_ROOM.get(session.get('user_session'), None))
