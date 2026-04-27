import json
import logging
import os

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

bedrock_agent_runtime = boto3.client("bedrock-agent-runtime")

KNOWLEDGE_BASE_ID = os.environ["KNOWLEDGE_BASE_ID"]
INFERENCE_PROFILE_ARN = os.environ["INFERENCE_PROFILE_ARN"]
INFERENCE_PROFILE_ARN_BASE = os.environ.get("INFERENCE_PROFILE_ARN_BASE", "")
FOUNDATION_MODEL_ARN_BASE = os.environ.get("FOUNDATION_MODEL_ARN_BASE", "")
SYSTEM_PROMPT = os.environ["SYSTEM_PROMPT"]

DEFAULT_TEMPERATURE = float(os.environ.get("DEFAULT_TEMPERATURE", "0.5"))
DEFAULT_MAX_TOKENS = int(os.environ.get("DEFAULT_MAX_TOKENS", "2048"))
DEFAULT_TOP_P = float(os.environ.get("DEFAULT_TOP_P", "0.9"))
DEFAULT_NUM_RESULTS = int(os.environ.get("DEFAULT_NUM_RESULTS", "5"))

RESPONSE_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
}

_INFERENCE_PROFILE_PREFIXES = ("eu.", "us.", "ap.", "us-gov.")


def _is_inference_profile(model_id: str) -> bool:
    return any(model_id.startswith(p) for p in _INFERENCE_PROFILE_PREFIXES)


def _is_meaningful_chunk(text: str) -> bool:
    if not text or len(text.strip()) < 40:
        return False
    tokens = text.split()
    if not tokens:
        return False
    numeric = sum(1 for t in tokens if t.strip(".,;:").isdigit())
    if numeric / len(tokens) > 0.4:
        return False
    return True


def _build_metadata_filter(filters: dict) -> dict | None:
    """Convert caller-provided filters into a Bedrock KB metadata filter expression.

    Supported keys:
      ring      (str)  — exact match: Adopt | Trial | Assess | Hold
      quadrant  (str)  — exact match: Techniques | Tools | Platforms | Languages and Frameworks
      editions  (list) — one or more edition strings, OR-combined
    Returns None when no valid filter is present.
    """
    conditions = []

    ring = (filters.get("ring") or "").strip()
    if ring:
        conditions.append({"equals": {"key": "ring", "value": ring}})

    quadrant = (filters.get("quadrant") or "").strip()
    if quadrant:
        conditions.append({"equals": {"key": "quadrant", "value": quadrant}})

    editions = filters.get("editions") or []
    if isinstance(editions, list):
        valid = [e for e in editions if isinstance(e, str) and e.strip()]
        if len(valid) == 1:
            conditions.append({"equals": {"key": "edition", "value": valid[0]}})
        elif len(valid) > 1:
            conditions.append({"in": {"key": "edition", "value": valid}})

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"andAll": conditions}


def _error(status_code: int, message: str) -> dict:
    return {
        "statusCode": status_code,
        "headers": RESPONSE_HEADERS,
        "body": json.dumps({"error": message}),
    }


def handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
    except (json.JSONDecodeError, TypeError):
        return _error(400, "Invalid JSON body")

    question = body.get("question", "").strip()
    if not question:
        return _error(400, "'question' field is required")

    temperature = float(body.get("temperature", DEFAULT_TEMPERATURE))
    max_tokens = int(body.get("max_tokens", DEFAULT_MAX_TOKENS))
    top_p = float(body.get("top_p", DEFAULT_TOP_P))
    num_results = int(body.get("num_results", DEFAULT_NUM_RESULTS))

    raw_filters = body.get("filters") or {}
    metadata_filter = _build_metadata_filter(raw_filters) if raw_filters else None

    model_id = body.get("model_id", "").strip()
    if model_id:
        if _is_inference_profile(model_id) and INFERENCE_PROFILE_ARN_BASE:
            model_arn = INFERENCE_PROFILE_ARN_BASE + model_id
        elif FOUNDATION_MODEL_ARN_BASE:
            model_arn = FOUNDATION_MODEL_ARN_BASE + model_id
        else:
            model_arn = INFERENCE_PROFILE_ARN
    else:
        model_arn = INFERENCE_PROFILE_ARN

    prompt_template = (
        f"{SYSTEM_PROMPT}\n\n"
        "Context from retrieved documents:\n$search_results$\n\n"
        "Question: $query$"
    )

    # Claude models reject requests that specify both temperature and top_p.
    is_anthropic = "anthropic" in model_id or "claude" in model_id
    text_inference_config: dict = {
        "temperature": temperature,
        "maxTokens": max_tokens,
    }
    if not is_anthropic:
        text_inference_config["topP"] = top_p

    generation_config = {
        "promptTemplate": {"textPromptTemplate": prompt_template},
        "inferenceConfig": {"textInferenceConfig": text_inference_config},
    }

    vector_search_config: dict = {"numberOfResults": num_results}
    if metadata_filter:
        vector_search_config["filter"] = metadata_filter

    # NOTE: Bedrock's contextual grounding guardrail is intentionally NOT applied here.
    # It evaluates whether the response text can be traced back to retrieved passages by
    # semantic similarity. For factual Q&A this works; for multi-document synthesis it
    # always fails: the model draws conclusions and inferences that are correct but are
    # not literally present in any single chunk, so the grounding score stays below any
    # useful threshold regardless of how low it is set.

    try:
        response = bedrock_agent_runtime.retrieve_and_generate(
            input={"text": question},
            retrieveAndGenerateConfiguration={
                "type": "KNOWLEDGE_BASE",
                "knowledgeBaseConfiguration": {
                    "knowledgeBaseId": KNOWLEDGE_BASE_ID,
                    "modelArn": model_arn,
                    "retrievalConfiguration": {
                        "vectorSearchConfiguration": vector_search_config,
                    },
                    "generationConfiguration": generation_config,
                },
            },
        )
    except ClientError as exc:
        logger.error("BEDROCK_ERROR | %s", exc.response["Error"]["Message"])
        return _error(500, str(exc))
    except Exception as exc:
        logger.error("UNEXPECTED_ERROR | %s", exc)
        return _error(500, str(exc))

    answer = response.get("output", {}).get("text", "")

    citations = []
    for citation in response.get("citations", []):
        for ref in citation.get("retrievedReferences", []):
            s3_uri = ref.get("location", {}).get("s3Location", {}).get("uri", "")
            text = ref.get("content", {}).get("text", "")
            if not _is_meaningful_chunk(text):
                continue
            citations.append(
                {
                    "source": s3_uri,
                    "text": text,
                    "metadata": ref.get("metadata", {}),
                }
            )

    return {
        "statusCode": 200,
        "headers": RESPONSE_HEADERS,
        "body": json.dumps({"answer": answer, "citations": citations}),
    }
