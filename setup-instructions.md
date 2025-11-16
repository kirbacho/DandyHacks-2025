# 🦥 LazySyllabus - Setup Instructions

## Quick Start for Judges/Hackathon

### 1. Get API Keys

**Google Gemini API:**
1. Go to [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Create a new API key
3. Copy the API key

**Google OAuth Credentials:**
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable Google Calendar API
4. Create OAuth 2.0 credentials (Web application)
5. Add `http://localhost:5001/oauth2callback` as authorized redirect URI
6. Copy Client ID and Client Secret

### 2. Setup Backend

```bash
# Clone the repository
git clone <your-repo-url>
cd lazzzy-syllabus/backend

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env
# Edit .env with your API keys

# Run the backend
python app.py
