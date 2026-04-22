import json
import os

import boto3

bedrock_agent_runtime = boto3.client("bedrock-agent-runtime")

KNOWLEDGE_BASE_ID = os.environ["KNOWLEDGE_BASE_ID"]
INFERENCE_PROFILE_ARN = os.environ["INFERENCE_PROFILE_ARN"]
SYSTEM_PROMPT = os.environ["SYSTEM_PROMPT"]

DEFAULT_TEMPERATURE = float(os.environ.get("DEFAULT_TEMPERATURE", "0.5"))
DEFAULT_MAX_TOKENS = int(os.environ.get("DEFAULT_MAX_TOKENS", "512"))
DEFAULT_TOP_P = float(os.environ.get("DEFAULT_TOP_P", "0.9"))
DEFAULT_TOP_K = int(os.environ.get("DEFAULT_TOP_K", "250"))
DEFAULT_NUM_RESULTS = int(os.environ.get("DEFAULT_NUM_RESULTS", "5"))

RESPONSE_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
}


def _error(status_code: int, message: str) -> dict:
    return {
        "statusCode": status_code,
        "headers": RESPONSE_HEADERS,
        "body": json.dumps({"error": message}),
    }


def handler(event, context):
    # Parse request body
    try:
        body = json.loads(event.get("body") or "{}")
    except (json.JSONDecodeError, TypeError):
        return _error(400, "Invalid JSON body")

    question = body.get("question", "").strip()
    if not question:
        return _error(400, "'question' field is required")

    # Inference parameters (caller-provided or defaults)
    temperature = float(body.get("temperature", DEFAULT_TEMPERATURE))
    max_tokens = int(body.get("max_tokens", DEFAULT_MAX_TOKENS))
    top_p = float(body.get("top_p", DEFAULT_TOP_P))
    num_results = int(body.get("num_results", DEFAULT_NUM_RESULTS))
    model_arn = INFERENCE_PROFILE_ARN

    # Build prompt template
    prompt_template = (
        f"{SYSTEM_PROMPT}\n\n"
        "Relevant legal documents:\n$search_results$\n\n"
        "Question: $query$"
    )

    # Prepare generation configuration
    generation_config = {
        "promptTemplate": {
            "textPromptTemplate": prompt_template,
        },
        "inferenceConfig": {
            "textInferenceConfig": {
                "temperature": temperature,
                "maxTokens": max_tokens,
                "topP": top_p
            }
        }
    }

    try:
        response = bedrock_agent_runtime.retrieve_and_generate(
            input={"text": question},
            retrieveAndGenerateConfiguration={
                "type": "KNOWLEDGE_BASE",
                "knowledgeBaseConfiguration": {
                    "knowledgeBaseId": KNOWLEDGE_BASE_ID,
                    "modelArn": model_arn,
                    "retrievalConfiguration": {
                        "vectorSearchConfiguration": {
                            "numberOfResults": num_results,
                        }
                    },
                    "generationConfiguration": generation_config,
                },
            },
        )
    except Exception as exc:
        return _error(500, str(exc))

    answer = response.get("output", {}).get("text", "")

    citations = []
    for citation in response.get("citations", []):
        for ref in citation.get("retrievedReferences", []):
            s3_uri = (
                ref.get("location", {}).get("s3Location", {}).get("uri", "")
            )
            citations.append(
                {
                    "source": s3_uri,
                    "text": ref.get("content", {}).get("text", ""),
                    "metadata": ref.get("metadata", {}),
                }
            )

    return {
        "statusCode": 200,
        "headers": RESPONSE_HEADERS,
        "body": json.dumps({"answer": answer, "citations": citations}),
    }
