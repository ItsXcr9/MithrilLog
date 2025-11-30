import google.generativeai as genai
import os

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    # Fallback to the key found in the user's .env file
    api_key = "AIzaSyBPVfd9gaxGvc0FWZzcruZghvWa7MCTcJQ"

genai.configure(api_key=api_key)

print("Listing available models:")
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        print(m.name)
