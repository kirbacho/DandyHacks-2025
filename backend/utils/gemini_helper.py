import google.generativeai as genai
import base64
import json
import os

def initialize_gemini():
    """Initialize the Gemini API with the API key"""
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in environment variables")
    
    genai.configure(api_key=api_key)

def extract_syllabus_info(file_content, mime_type):
    """
    Extract syllabus information using Gemini API
    
    Args:
        file_content: The file content as bytes
        mime_type: The MIME type of the file
    
    Returns:
        List of extracted events
    """
    try:
        # Initialize the model
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        # Prepare the prompt
        prompt = """
        Analyze this syllabus document and extract all important academic dates including:
        - Class meeting times and schedules
        - Exam dates and times
        - Assignment due dates
        - Project deadlines
        - Holiday breaks
        - Other important academic events
        
        Return the information in JSON format with this exact structure:
        {
            "events": [
                {
                    "title": "Event name (e.g., 'Midterm Exam', 'Weekly Lecture')",
                    "date": "YYYY-MM-DD",
                    "start_time": "HH:MM (24-hour format, optional)",
                    "end_time": "HH:MM (24-hour format, optional)",
                    "recurring": false,
                    "recurrence_pattern": "weekly/daily/monthly (if recurring)",
                    "description": "Brief description or details about the event"
                }
            ]
        }
        
        For recurring events like weekly classes, set recurring to true and specify the pattern.
        Make sure all dates are in the correct academic semester/year.
        """
        
        # Prepare the file part
        file_part = {
            "mime_type": mime_type,
            "data": base64.b64encode(file_content).decode('utf-8')
        }
        
        # Generate content
        response = model.generate_content([prompt, file_part])
        
        # Parse the response
        try:
            # Extract JSON from the response
            response_text = response.text
            # Remove markdown code blocks if present
            response_text = response_text.replace('```json', '').replace('```', '').strip()
            
            events_data = json.loads(response_text)
            return events_data.get('events', [])
            
        except json.JSONDecodeError as e:
            print(f"Failed to parse Gemini response as JSON: {e}")
            print(f"Response was: {response.text}")
            return []
            
    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        return []