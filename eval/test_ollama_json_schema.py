import json
from unittest.mock import MagicMock, patch
from src.mighty_mouse.orchestrator.ollama_client import OllamaClient

def test_ollama_json_format_payload():
    config = {
        "ollama_host": "http://localhost:11434",
        "model": "gemma4:e4b",
        "format": "json"
    }
    client = OllamaClient(config=config)
    
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({
        "response": '{"status": "ok"}',
        "prompt_eval_count": 10,
        "eval_count": 5
    }).encode("utf-8")
    mock_response.__enter__.return_value = mock_response

    with patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
        res = client.generate_content("System prompt", "User prompt")
        assert res == '{"status": "ok"}'
        
        # Verify format parameter in request payload
        args, kwargs = mock_urlopen.call_args
        req = args[0]
        payload = json.loads(req.data.decode("utf-8"))
        assert payload.get("format") == "json"
        assert payload.get("model") == "gemma4:e4b"
