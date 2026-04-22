#!/usr/bin/env python3
"""Script para probar la Lambda localmente sin subirla a AWS (con mock de Bedrock)"""

import json
import os
from unittest.mock import patch, MagicMock

# Configurar variables de entorno de prueba ANTES de importar handler
os.environ["KNOWLEDGE_BASE_ID"] = "test-kb-id"
os.environ["GENERATIVE_MODEL_ID"] = "test-model-id"
os.environ["INFERENCE_PROFILE_ARN"] = "test-inference-profile-arn"
os.environ["SYSTEM_PROMPT"] = "You are a test assistant"

from handler import handler

# Cargar evento de prueba
with open("test_event.json") as f:
    event = json.load(f)

print("🧪 Testing Lambda handler locally (with mocked Bedrock)...\n")
print(f"Event: {json.dumps(event, indent=2)}\n")

# Mock de la respuesta de Bedrock
mock_bedrock_response = {
    "output": {"text": "Esta es una respuesta simulada sobre legislación española."},
    "citations": [
        {
            "retrievedReferences": [
                {
                    "location": {"s3Location": {"uri": "s3://bucket/BOE-A-2015-11430.md"}},
                    "content": {"text": "Artículo 38. El período de vacaciones anuales retribuidas..."},
                    "metadata": {"titulo": "Real Decreto Legislativo 2/2015 - Estatuto de los Trabajadores"}
                }
            ]
        }
    ]
}

# Ejecutar handler con Bedrock mockeado
with patch("handler.bedrock_agent_runtime") as mock_bedrock:
    mock_bedrock.retrieve_and_generate.return_value = mock_bedrock_response

    try:
        result = handler(event, None)
        print(f"✅ Status: {result['statusCode']}")
        print(f"📄 Response:\n{json.dumps(json.loads(result['body']), indent=2)}")
    except Exception as e:
        print(f"❌ Error: {e}")
