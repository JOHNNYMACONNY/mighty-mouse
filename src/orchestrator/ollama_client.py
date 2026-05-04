import json
import os
import time
import urllib.request
import urllib.error

class OllamaClient:
    def __init__(self, config=None):
        self.config = config or {}
        self.host = self.config.get("ollama_host", "http://localhost:11434")
        self.model_name = self.config.get("model", "gemma4:e4b")
        self.last_metadata = {}

    def generate_content(self, sys_instr, user_prompt):
        url = f"{self.host}/api/generate"
        
        # Combine system instruction and user prompt if the model doesn't support system field natively
        # For simplicity in this harness, we prepending sys_instr
        full_prompt = f"System: {sys_instr}\n\nUser: {user_prompt}"
        
        payload = {
            "model": self.model_name,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": self.config.get("temperature", 0.2),
                "num_predict": self.config.get("max_tokens", 4000)
            }
        }
        
        headers = {"Content-Type": "application/json"}
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
        
        start_time = time.time()
        try:
            with urllib.request.urlopen(req) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                content = res_data.get("response", "")
                
                latency = time.time() - start_time
                self.last_metadata = {
                    "provider": "ollama",
                    "model": self.model_name,
                    "latency_seconds": latency,
                    "usage": {
                        "prompt_tokens": res_data.get("prompt_eval_count", 0),
                        "completion_tokens": res_data.get("eval_count", 0),
                        "total_tokens": res_data.get("prompt_eval_count", 0) + res_data.get("eval_count", 0)
                    }
                }
                return content
        except urllib.error.URLError as e:
            print(f"[ollama] Connection error: {e}")
            raise
        except Exception as e:
            print(f"[ollama] Error: {e}")
            raise
