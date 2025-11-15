import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv('GEMINI_API_KEY')
print(f"API Key: {api_key[:20]}...")

if api_key and api_key != 'your_actual_gemini_key_here':
    try:
        genai.configure(api_key=api_key)
        
        print("\n🔍 Available Gemini models:")
        print("=" * 50)
        
        models = genai.list_models()
        for model in models:
            if 'generateContent' in model.supported_generation_methods:
                print(f"✅ {model.name}")
                print(f"   Description: {model.description}")
                print(f"   Methods: {model.supported_generation_methods}")
                print()
                
    except Exception as e:
        print(f"❌ Error: {e}")
else:
    print("❌ No valid API key found")