from flask import Flask, request, jsonify, send_from_directory, redirect, session
from flask_cors import CORS
import google.generativeai as genai
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import Flow
import base64
import os
from datetime import datetime, timedelta
import json
from dotenv import load_dotenv
import hashlib
import traceback
from collections import OrderedDict

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key-123')

# Enable CORS for all routes
CORS(app)

# Configure Gemini API
try:
    genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
    print("✅ Gemini API configured")
except Exception as e:
    print(f"❌ Gemini API config failed: {e}")

# Try to import faster text extraction libraries
try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
    print("✅ PyMuPDF available for fast PDF processing")
except ImportError:
    HAS_PYMUPDF = False
    print("❌ PyMuPDF not available - install with: pip install PyMuPDF")

# Create global model objects ONCE (huge speed boost)
GEMINI_TEXT_MODEL = genai.GenerativeModel("gemini-2.5-flash")
GEMINI_VISION_MODEL = genai.GenerativeModel("gemini-2.5-flash")

# SMARTER PROMPT - IDENTIFY RECURRING EVENTS
SMART_EVENT_EXTRACTION_PROMPT = """
Extract academic events from the syllabus. Identify which events are recurring weekly.

For SINGLE events (exams, major deadlines, assignments, homework):
{"title":"","date":"YYYY-MM-DD","start_time":"","end_time":"","recurring":false,"recurrence_pattern":"","description":"","type":"exam/assignment/homework"}

For RECURRING weekly events (classes, labs, office hours):
{"title":"","date":"YYYY-MM-DD","start_time":"","end_time":"","recurring":true,"recurrence_pattern":"weekly","description":"","type":"class/lab/office_hours"}

Return ONLY valid JSON in this form:
{"events":[
  // single events
  {"title":"Midterm Exam","date":"2025-03-15","start_time":"14:00","end_time":"16:00","recurring":false,"recurrence_pattern":"","description":"","type":"exam"},
  {"title":"Homework 1 Due","date":"2025-02-10","start_time":"23:59","end_time":"","recurring":false,"recurrence_pattern":"","description":"","type":"assignment"},
  // recurring events  
  {"title":"CS101 Lecture","date":"2025-01-20","start_time":"10:00","end_time":"11:30","recurring":true,"recurrence_pattern":"weekly","description":"","type":"class"}
]}
Focus on major events and weekly recurring schedules.
"""

# File Cache (LRU)
MAX_CACHE_ITEMS = 20
file_cache = OrderedDict()

def cache_put(key, value):
    if key in file_cache:
        file_cache.move_to_end(key)
    file_cache[key] = value
    if len(file_cache) > MAX_CACHE_ITEMS:
        file_cache.popitem(last=False)

# OAuth Configuration
def get_client_config():
    """Load OAuth client configuration from environment variables"""
    client_id = os.getenv('GOOGLE_CLIENT_ID')
    client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
    
    if not client_id or not client_secret:
        print("❌ OAuth configuration incomplete!")
        return None
    
    config = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost:5001/oauth2callback"]
        }
    }
    return config

# OAuth setup
SCOPES = ['https://www.googleapis.com/auth/calendar']
client_config = get_client_config()

# ---------------------------------------------------------
# Fast PDF text extraction using PyMuPDF
# ---------------------------------------------------------
def extract_text_fast(file_content, mime_type):
    """Fast text extraction using specialized libraries"""
    try:
        # For PDFs - use PyMuPDF (fastest)
        if mime_type == 'application/pdf' and HAS_PYMUPDF:
            print("🔍 Using PyMuPDF for fast text extraction")
            import fitz
            with fitz.open(stream=file_content, filetype="pdf") as doc:
                text = "\n".join(page.get_text() for page in doc)
                return text.strip()
        
        # For text files
        elif mime_type.startswith('text/'):
            return file_content.decode('utf-8', errors='ignore').strip()
        
        return None
        
    except Exception as e:
        print(f"❌ Fast text extraction failed: {e}")
        return None

# ---------------------------------------------------------
# Gemini TEXT processing - WITH RECURRING EVENTS
# ---------------------------------------------------------
def extract_dates_with_gemini_text(text_content, mime_type):
    try:
        truncated_text = text_content[:6000]

        response = GEMINI_TEXT_MODEL.generate_content(
            [SMART_EVENT_EXTRACTION_PROMPT, truncated_text]
        )

        response_text = (
            response.text.replace("```json", "").replace("```", "").strip()
        )
        events_json = json.loads(response_text)

        events = events_json.get("events", [])
        
        print(f"✅ Extracted {len(events)} events ({sum(1 for e in events if e.get('recurring'))} recurring)")
        return events[:25]  # Reasonable limit

    except Exception as e:
        print("Text-only extraction error:", e)
        return []

# ---------------------------------------------------------
# Gemini VISION processing - WITH RECURRING EVENTS
# ---------------------------------------------------------
def extract_dates_with_gemini_vision(file_content, mime_type):
    try:
        file_part = {
            "mime_type": mime_type,
            "data": base64.b64encode(file_content).decode("utf-8")
        }

        response = GEMINI_VISION_MODEL.generate_content(
            [SMART_EVENT_EXTRACTION_PROMPT, file_part]
        )

        response_text = (
            response.text.replace("```json", "").replace("```", "").strip()
        )
        events_json = json.loads(response_text)

        events = events_json.get("events", [])
        print(f"✅ Extracted {len(events)} events using vision processing")
        return events[:25]  # Reasonable limit

    except Exception as e:
        print("Vision extraction error:", e)
        return get_sample_events()

def get_sample_events():
    """Return sample events with recurring classes"""
    return [
        # Single events
        {
            "title": "Midterm Exam",
            "date": "2025-03-15",
            "start_time": "14:00",
            "end_time": "16:00",
            "recurring": False,
            "recurrence_pattern": "",
            "description": "Midterm examination covering chapters 1-5",
            "type": "exam"
        },
        {
            "title": "Homework 1 Due",
            "date": "2025-02-10",
            "start_time": "20:00",
            "end_time": "21:00",
            "recurring": False,
            "recurrence_pattern": "",
            "description": "Submit homework assignment 1",
            "type": "assignment"
        },
        # Recurring events
        {
            "title": "CS101 Lecture",
            "date": "2025-01-20",
            "start_time": "10:00",
            "end_time": "11:30",
            "recurring": True,
            "recurrence_pattern": "weekly",
            "description": "Weekly class lecture",
            "type": "class"
        }
    ]

def generate_ai_study_tips(event):
    """Generate smart study tips using Gemini AI"""
    try:
        prompt = f"""
        Generate 3 specific, actionable study tips for this academic event:
        
        Event: {event.get('title')}
        Description: {event.get('description', 'No description provided')}
        Type: {event.get('type', 'general')}
        
        Provide ONLY a JSON array with 3 study tips as strings. No explanations, no markdown, just the array.
        
        Example: ["Review key concepts from chapters 1-5", "Practice with past exam questions", "Create summary sheets for quick review"]
        """
        
        response = GEMINI_TEXT_MODEL.generate_content(prompt)
        response_text = response.text.strip()
        
        # Clean the response
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        
        tips = json.loads(response_text)
        print(f"🤖 Generated AI study tips: {tips}")
        return tips[:3]  # Ensure we only return 3 tips
        
    except Exception as e:
        print(f"AI tips generation failed: {e}")
        # Fallback tips
        return [
            "Review key concepts and materials",
            "Practice with relevant exercises",
            "Create study notes and summaries"
        ]

# Debug route
@app.route('/debug')
def debug():
    """Debug endpoint to check configuration"""
    client_config = get_client_config()
    return jsonify({
        'gemini_configured': bool(os.getenv('GEMINI_API_KEY')),
        'client_id_set': bool(os.getenv('GOOGLE_CLIENT_ID')),
        'client_secret_set': bool(os.getenv('GOOGLE_CLIENT_SECRET')),
        'client_config_available': bool(client_config),
        'cache_items': len(file_cache),
        'env_keys': [k for k in os.environ.keys() if 'GOOGLE' in k or 'GEMINI' in k or 'SECRET' in k]
    })

# Serve frontend files
@app.route('/')
def serve_index():
    return send_from_directory('../frontend', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('../frontend', path)

# OAuth routes
@app.route('/auth/google')
def google_auth():
    """Start Google OAuth flow"""
    print("🔑 OAuth flow initiated")
    
    client_config = get_client_config()
    if not client_config:
        error_msg = "OAuth not configured. Check your .env file."
        print(f"❌ {error_msg}")
        return jsonify({'error': error_msg}), 500
    
    try:
        flow = Flow.from_client_config(client_config, scopes=SCOPES)
        flow.redirect_uri = 'http://localhost:5001/oauth2callback'
        
        auth_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )
        session['state'] = state
        print(f"✅ Redirecting to: {auth_url}")
        return redirect(auth_url)
    except Exception as e:
        error_msg = f"OAuth setup failed: {str(e)}"
        print(f"❌ {error_msg}")
        return jsonify({'error': error_msg}), 500

@app.route('/oauth2callback')
def oauth_callback():
    """OAuth callback handler"""
    if not client_config:
        return jsonify({'error': 'OAuth not configured'}), 500
    
    try:
        flow = Flow.from_client_config(client_config, scopes=SCOPES)
        flow.redirect_uri = 'http://localhost:5001/oauth2callback'
        flow.fetch_token(authorization_response=request.url)
        
        creds = flow.credentials
        session['credentials'] = {
            'token': creds.token,
            'refresh_token': creds.refresh_token,
            'token_uri': creds.token_uri,
            'client_id': creds.client_id,
            'client_secret': creds.client_secret,
            'scopes': creds.scopes
        }
        return redirect('/?auth=success')
    except Exception as e:
        print(f"OAuth callback error: {e}")
        return redirect('/?auth=error')

def get_calendar_service():
    """Get Google Calendar service from session credentials"""
    if 'credentials' not in session:
        return None
    
    creds_info = session['credentials']
    credentials = Credentials(
        token=creds_info['token'],
        refresh_token=creds_info['refresh_token'],
        token_uri=creds_info['token_uri'],
        client_id=creds_info['client_id'],
        client_secret=creds_info['client_secret'],
        scopes=creds_info['scopes']
    )
    
    # Refresh token if expired
    if credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(Request())
            session['credentials']['token'] = credentials.token
        except Exception as e:
            print(f"Token refresh failed: {e}")
            return None
    
    return build('calendar', 'v3', credentials=credentials)

# API routes
@app.route('/upload', methods=['POST'])
def upload_syllabus():
    """Upload and process syllabus file - WITH RECURRING EVENTS"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        print(f"📁 Processing file: {file.filename}")
        
        # Read file content directly
        file_content = file.read()
        
        # Check cache first
        file_hash = hashlib.md5(file_content).hexdigest()
        if file_hash in file_cache:
            print("✅ Serving from cache")
            events = file_cache[file_hash]
        else:
            # OPTIMIZED PROCESSING FLOW:
            extracted_text = extract_text_fast(file_content, file.content_type)
            
            if extracted_text and len(extracted_text) > 100:
                print(f"📝 Extracted {len(extracted_text)} characters of text")
                events = extract_dates_with_gemini_text(extracted_text, file.content_type)
            else:
                print("📝 Using vision processing")
                events = extract_dates_with_gemini_vision(file_content, file.content_type)
            
            # Cache the result
            cache_put(file_hash, events)
        
        return jsonify({'success': True, 'events': events})
        
    except Exception as e:
        print(f"Upload error: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/generate-study-sessions', methods=['POST'])
def generate_study_sessions():
    """Generate study sessions with AI-powered tips"""
    try:
        data = request.json
        exam_event = data.get('exam_event')
        days_before = data.get('days_before', [5, 2])  # 2 sessions only
        
        print(f"🎯 Generating study sessions for: {exam_event.get('title')}")
        
        # ONLY generate for actual exams, not review sessions
        event_title = exam_event.get('title', '').lower()
        if 'review' in event_title:
            print("⏭️  Skipping study sessions for review session")
            return jsonify({'success': True, 'study_sessions': []})
        
        # Generate AI-powered study tips - ACTUALLY CALL THE FUNCTION
        study_tips = generate_ai_study_tips(exam_event)
        
        # Create study sessions
        study_sessions = []
        exam_date = datetime.strptime(exam_event['date'], '%Y-%m-%d')
        
        for i, days in enumerate(days_before):
            study_date = exam_date - timedelta(days=days)
            
            # Different focus for each session
            if i == 0:
                session_title = f"📚 Review: {exam_event['title']}"
                tips = study_tips
            else:
                session_title = f"💪 Practice: {exam_event['title']}"
                # Generate separate AI tips for practice session
                practice_event = exam_event.copy()
                practice_event['title'] = f"Practice for {exam_event['title']}"
                practice_tips = generate_ai_study_tips(practice_event)
                tips = practice_tips
            
            study_sessions.append({
                "title": session_title,
                "date": study_date.strftime('%Y-%m-%d'),
                "start_time": "19:00",
                "end_time": "21:00", 
                "recurring": False,
                "recurrence_pattern": "",
                "description": f"Study session for {exam_event['title']}",
                "type": "study-session",
                "study_tips": tips  # SIMPLE ARRAY OF STRINGS from AI
            })
        
        return jsonify({'success': True, 'study_sessions': study_sessions})
        
    except Exception as e:
        print(f"Study session generation error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/add-to-calendar', methods=['POST'])
def add_to_calendar():
    """Add events to Google Calendar - SUPPORTS RECURRING EVENTS"""
    try:
        data = request.json
        events = data.get('events', [])
        
        service = get_calendar_service()
        if not service:
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
        
        added_count = 0
        for event_data in events:
            try:
                # Handle different event types properly
                start_time = event_data.get('start_time', '10:00')
                end_time = event_data.get('end_time', '11:00')  # Default 1 hour duration
                
                # Validate and clean times
                if not start_time or start_time == '':
                    if event_data.get('type') in ['assignment', 'homework']:
                        start_time = '20:00'
                        end_time = '21:00'  # 1 hour for homework
                    else:
                        start_time = '10:00'
                        end_time = '11:00'  # 1 hour default
                
                # If end_time is empty or invalid, set a reasonable duration
                if not end_time or end_time == '':
                    if event_data.get('type') in ['assignment', 'homework']:
                        end_time = '21:00'  # 1 hour after start
                    elif 'exam' in event_data.get('type', ''):
                        end_time = '12:00'  # 2 hours for exams (if start is 10:00)
                    else:
                        # Calculate end time as 1 hour after start
                        start_dt = datetime.strptime(start_time, '%H:%M')
                        end_dt = start_dt + timedelta(hours=1)
                        end_time = end_dt.strftime('%H:%M')
                
                # Ensure end time is after start time
                start_dt = datetime.strptime(start_time, '%H:%M')
                end_dt = datetime.strptime(end_time, '%H:%M')
                if end_dt <= start_dt:
                    # If end time is before or equal to start, add 1 hour
                    end_dt = start_dt + timedelta(hours=1)
                    end_time = end_dt.strftime('%H:%M')
                
                # For assignments due at midnight, use a reasonable time
                if start_time == '23:59' or end_time == '23:59':
                    start_time = '20:00'
                    end_time = '21:00'
                
                # Base event structure
                event = {
                    'summary': event_data['title'],
                    'description': event_data.get('description', ''),
                    'start': {
                        'dateTime': f"{event_data['date']}T{start_time}:00",
                        'timeZone': 'America/New_York',
                    },
                    'end': {
                        'dateTime': f"{event_data['date']}T{end_time}:00", 
                        'timeZone': 'America/New_York',
                    }
                }
                
                # ADD RECURRENCE FOR WEEKLY EVENTS
                if event_data.get('recurring') and event_data.get('recurrence_pattern') == 'weekly':
                    # Set end date for semester (approx 16 weeks from start)
                    start_date = datetime.strptime(event_data['date'], '%Y-%m-%d')
                    end_date = start_date + timedelta(weeks=16)
                    
                    event['recurrence'] = [
                        f"RRULE:FREQ=WEEKLY;UNTIL={end_date.strftime('%Y%m%dT%H%M%SZ')}"
                    ]
                    print(f"🔄 Adding recurring event: {event_data['title']}")
                
                # Add study tips to description for study sessions
                if event_data.get('type') == 'study-session' and event_data.get('study_tips'):
                    tips_text = "\n\nStudy Tips:\n• " + "\n• ".join(event_data['study_tips'])
                    event['description'] += tips_text
                
                # Debug print to see what we're sending
                print(f"📅 Creating event: {event_data['title']} on {event_data['date']} from {start_time} to {end_time}")
                
                service.events().insert(calendarId='primary', body=event).execute()
                added_count += 1
                print(f"✅ Added event: {event_data['title']}")
                
            except Exception as e:
                print(f"❌ Failed to add event '{event_data['title']}': {str(e)}")
                print(f"   Event data: {event_data}")
                continue
        
        # Count recurring vs single events
        recurring_count = sum(1 for e in events if e.get('recurring'))
        single_count = len(events) - recurring_count
        
        return jsonify({
            'success': True, 
            'added_events': added_count,
            'recurring_events': recurring_count,
            'single_events': single_count,
            'message': f'Added {added_count} events ({recurring_count} recurring, {single_count} single) to calendar'
        })
        
    except Exception as e:
        print(f"Calendar error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/auth-status')
def auth_status():
    """Check if user is authenticated"""
    service = get_calendar_service()
    return jsonify({'authenticated': service is not None})

@app.route('/health')
def health_check():
    return jsonify({'status': 'healthy', 'message': 'Server is running'})

@app.route('/logout')
def logout():
    """Clear session"""
    session.clear()
    return jsonify({'success': True, 'message': 'Logged out'})

if __name__ == '__main__':
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    print("🚀 Starting Flask server on http://localhost:5001")
    print("📁 Serving frontend from ../frontend")
    app.run(debug=True, host='0.0.0.0', port=5001)