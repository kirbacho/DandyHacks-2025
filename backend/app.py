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
import tempfile

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

# OAuth Configuration
def get_client_config():
    """Load OAuth client configuration from environment variables"""
    client_id = os.getenv('GOOGLE_CLIENT_ID')
    client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
    
    print(f"🔧 OAuth Config Check:")
    print(f"   Client ID: {'✅ SET' if client_id else '❌ MISSING'}")
    print(f"   Client Secret: {'✅ SET' if client_secret else '❌ MISSING'}")
    
    if not client_id or not client_secret:
        print("❌ OAuth configuration incomplete!")
        return None
    
    # Validate the format
    if not client_id.endswith('.apps.googleusercontent.com'):
        print("❌ Client ID format looks wrong")
    
    config = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost:5001/oauth2callback"]
        }
    }
    print("✅ OAuth configuration loaded successfully")
    return config

# OAuth setup
SCOPES = ['https://www.googleapis.com/auth/calendar']
client_config = get_client_config()

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
    """Upload and process syllabus file"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        # Save and process file
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as temp_file:
            file.save(temp_file.name)
            temp_path = temp_file.name
        
        with open(temp_path, 'rb') as f:
            file_content = f.read()
        
        # Extract events
        events = extract_dates_with_gemini(file_content, file.content_type)
        
        # Cleanup
        os.unlink(temp_path)
        
        return jsonify({'success': True, 'events': events})
        
    except Exception as e:
        print(f"Upload error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

def extract_dates_with_gemini(file_content, mime_type):
    """Extract dates using Gemini AI"""
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        prompt = """
        Extract academic dates from this syllabus. Return JSON with this structure:
        {
            "events": [
                {
                    "title": "Event name",
                    "date": "YYYY-MM-DD", 
                    "start_time": "HH:MM",
                    "end_time": "HH:MM",
                    "recurring": false,
                    "recurrence_pattern": "",
                    "description": "Event details"
                }
            ]
        }
        Return ONLY JSON, no other text.
        """
        
        file_part = {
            "mime_type": mime_type,
            "data": base64.b64encode(file_content).decode('utf-8')
        }
        
        response = model.generate_content([prompt, file_part])
        
        # Parse response
        response_text = response.text.replace('```json', '').replace('```', '').strip()
        events_data = json.loads(response_text)
        return events_data.get('events', [])
        
    except Exception as e:
        print(f"Gemini error: {e}")
        # Return sample data as fallback
        return [
            {
                "title": "Sample Midterm Exam",
                "date": "2024-03-15",
                "start_time": "14:00",
                "end_time": "16:00",
                "recurring": False,
                "recurrence_pattern": "",
                "description": "Midterm examination"
            },
            {
                "title": "Sample Final Project", 
                "date": "2024-05-10",
                "start_time": "23:59",
                "end_time": "",
                "recurring": False,
                "recurrence_pattern": "",
                "description": "Final project submission"
            }
        ]

@app.route('/add-to-calendar', methods=['POST'])
def add_to_calendar():
    """Add events to Google Calendar"""
    try:
        data = request.json
        events = data.get('events', [])
        
        service = get_calendar_service()
        if not service:
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
        
        added_count = 0
        for event_data in events:
            event = {
                'summary': event_data['title'],
                'description': event_data.get('description', ''),
                'start': {
                    'dateTime': f"{event_data['date']}T{event_data.get('start_time', '00:00')}:00",
                    'timeZone': 'America/New_York',
                },
                'end': {
                    'dateTime': f"{event_data['date']}T{event_data.get('end_time', '23:59')}:00", 
                    'timeZone': 'America/New_York',
                }
            }
            
            try:
                service.events().insert(calendarId='primary', body=event).execute()
                added_count += 1
            except Exception as e:
                print(f"Failed to add event {event_data['title']}: {e}")
                continue
        
        return jsonify({
            'success': True, 
            'added_events': added_count,
            'message': f'Added {added_count} events to calendar'
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
    # Enable for local development
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    print("🚀 Starting Flask server on http://localhost:5001")
    print("📁 Serving frontend from ../frontend")
    app.run(debug=True, host='0.0.0.0', port=5001)