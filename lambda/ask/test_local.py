import json
import os
import pytest
from unittest.mock import patch

os.environ["KNOWLEDGE_BASE_ID"] = "test-kb-id"
os.environ["INFERENCE_PROFILE_ARN"] = "test-inference-profile-arn"
os.environ["SYSTEM_PROMPT"] = "Test prompt"
os.environ["DEFAULT_TEMPERATURE"] = "0.5"
os.environ["DEFAULT_MAX_TOKENS"] = "512"
os.environ["DEFAULT_TOP_P"] = "0.9"
os.environ["DEFAULT_TOP_K"] = "250"
os.environ["DEFAULT_NUM_RESULTS"] = "5"

from handler import handler, _error

# Mock de variables de entorno
@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_BASE_ID", "test-kb-id")
    monkeypatch.setenv("GENERATIVE_MODEL_ID", "test-model")
    monkeypatch.setenv("SYSTEM_PROMPT", "Test prompt")
    monkeypatch.setenv("DEFAULT_TEMPERATURE", "0.5")
    monkeypatch.setenv("DEFAULT_MAX_TOKENS", "512")
    monkeypatch.setenv("DEFAULT_TOP_P", "0.9")
    monkeypatch.setenv("DEFAULT_TOP_K", "250")
    monkeypatch.setenv("DEFAULT_NUM_RESULTS", "5")


def test_error_helper():
    """Test de la función auxiliar _error"""
    result = _error(400, "Test error")
    assert result["statusCode"] == 400
    body = json.loads(result["body"])
    assert body["error"] == "Test error"


def test_handler_missing_question():
    """Test sin pregunta en el body"""
    event = {"body": "{}"}
    result = handler(event, None)
    
    assert result["statusCode"] == 400
    body = json.loads(result["body"])
    assert "required" in body["error"]


def test_handler_invalid_json():
    """Test con JSON inválido"""
    event = {"body": "invalid json"}
    result = handler(event, None)
    
    assert result["statusCode"] == 400


@patch("handler.bedrock_agent_runtime")
def test_handler_success(mock_bedrock):
    """Test de respuesta exitosa (con mock de Bedrock)"""
    # Mock de la respuesta de Bedrock
    mock_bedrock.retrieve_and_generate.return_value = {
        "output": {"text": "Respuesta de prueba"},
        "citations": [
            {
                "retrievedReferences": [
                    {
                        "location": {"s3Location": {"uri": "s3://bucket/file.md"}},
                        "content": {"text": "Contenido de referencia"},
                        "metadata": {"key": "value"}
                    }
                ]
            }
        ]
    }
    
    event = {
        "body": json.dumps({
            "question": "¿Qué dice la ley?"
        })
    }
    
    result = handler(event, None)
    
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["answer"] == "Respuesta de prueba"
    assert len(body["citations"]) == 1


def test_handler_with_file_event():
    """Test usando el archivo de evento JSON"""
    with open("test_event.json") as f:
        event = json.load(f)
    
    # Este test requiere mock de Bedrock también
    with patch("handler.bedrock_agent_runtime") as mock_bedrock:
        mock_bedrock.retrieve_and_generate.return_value = {
            "output": {"text": "Mock response"},
            "citations": []
        }
        
        result = handler(event, None)
        assert result["statusCode"] == 200
