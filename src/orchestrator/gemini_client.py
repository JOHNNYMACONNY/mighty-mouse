import os
import json
import requests
from dotenv import load_dotenv

class GeminiClient:
    def __init__(self, model_name="gemini-1.5-flash"):
        load_dotenv()
        self.api_key = os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY not found in environment. Please set it in .env")
        
        # Mapping gemini-3-flash to 1.5 if 3 is not public in REST yet, 
        # but 1.5-flash is the stable target for REST.
        self.model = model_name if "gemini" in model_name else "gemini-1.5-flash"
        self.url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"

    def generate(self, prompt, system_instruction=None):
        headers = {'Content-Type': 'application/json'}
        
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "temperature": float(os.getenv("TEMPERATURE", 0.0)),
                "maxOutputTokens": 8192
            }
        }
        
        if system_instruction:
            payload["system_instruction"] = {
                "parts": [{"text": system_instruction}]
            }
            
        try:
            response = requests.post(self.url, headers=headers, json=payload, timeout=60)
            res_json = response.json()
            
            if response.status_code != 200:
                return f"ERROR: API returned {response.status_code}: {json.dumps(res_json)}"
            
            # Extract text from response
            # Path: candidates[0].content.parts[0].text
            return res_json['candidates'][0]['content']['parts'][0]['text']
            
        except Exception as e:
            return f"ERROR: {str(e)}"

if __name__ == "__main__":
    try:
        client = GeminiClient()
        print("REST GeminiClient initialized.")
    except Exception as e:
        print(f"Init Failed: {e}")
