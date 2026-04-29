import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

bedrock_agent_runtime = boto3.client("bedrock-agent-runtime")
bedrock_runtime = boto3.client("bedrock-runtime")
dynamodb = boto3.resource("dynamodb")

KNOWLEDGE_BASE_ID = os.environ["KNOWLEDGE_BASE_ID"]
INFERENCE_PROFILE_ARN = os.environ["INFERENCE_PROFILE_ARN"]
INFERENCE_PROFILE_ARN_BASE = os.environ.get("INFERENCE_PROFILE_ARN_BASE", "")
FOUNDATION_MODEL_ARN_BASE = os.environ.get("FOUNDATION_MODEL_ARN_BASE", "")
SYSTEM_PROMPT = os.environ["SYSTEM_PROMPT"]
INTERVIEWS_TABLE = os.environ.get("INTERVIEWS_TABLE", "")
SUMMARY_MODEL_ARN = os.environ.get("SUMMARY_MODEL_ARN", "amazon.nova-micro-v1:0")

DEFAULT_TEMPERATURE = float(os.environ.get("DEFAULT_TEMPERATURE", "0.5"))
DEFAULT_MAX_TOKENS = int(os.environ.get("DEFAULT_MAX_TOKENS", "2048"))
DEFAULT_TOP_P = float(os.environ.get("DEFAULT_TOP_P", "0.9"))
DEFAULT_NUM_RESULTS = int(os.environ.get("DEFAULT_NUM_RESULTS", "5"))

RESPONSE_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
}

_INFERENCE_PROFILE_PREFIXES = ("eu.", "us.", "ap.", "us-gov.")

_REFUSAL_PHRASES = (
    "sorry, i am unable",
    "i cannot assist",
    "i'm unable to assist",
    "i am unable to assist",
    "i can't help with",
    "i cannot help with",
    "i'm not able to assist",
    "i am not able to assist",
    "lo siento, no puedo",
    "no puedo ayudarte con",
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _is_inference_profile(model_id: str) -> bool:
    return any(model_id.startswith(p) for p in _INFERENCE_PROFILE_PREFIXES)


def _looks_like_refusal(text: str) -> bool:
    lowered = text.lower().strip()
    return any(phrase in lowered for phrase in _REFUSAL_PHRASES)


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
    """Convert caller-provided filters into a Bedrock KB metadata filter expression."""
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


def _resolve_model_arn(model_id: str) -> str:
    if model_id:
        if _is_inference_profile(model_id) and INFERENCE_PROFILE_ARN_BASE:
            return INFERENCE_PROFILE_ARN_BASE + model_id
        elif FOUNDATION_MODEL_ARN_BASE:
            return FOUNDATION_MODEL_ARN_BASE + model_id
    return INFERENCE_PROFILE_ARN


def _error(status_code: int, message: str) -> dict:
    return {
        "statusCode": status_code,
        "headers": RESPONSE_HEADERS,
        "body": json.dumps({"error": message}),
    }


# ─── DynamoDB helpers ─────────────────────────────────────────────────────────

def _table():
    return dynamodb.Table(INTERVIEWS_TABLE)


def _load_session(session_id: str) -> dict | None:
    if not INTERVIEWS_TABLE:
        return None
    try:
        resp = _table().get_item(Key={"pk": f"SESSION#{session_id}", "sk": "META"})
        return resp.get("Item")
    except Exception as exc:
        logger.warning("DYNAMO_LOAD_ERROR | %s", exc)
        return None


def _load_last_turn(session_id: str, turn_count: int) -> dict | None:
    if not INTERVIEWS_TABLE or turn_count == 0:
        return None
    try:
        resp = _table().get_item(
            Key={"pk": f"SESSION#{session_id}", "sk": f"TURN#{turn_count:04d}"}
        )
        return resp.get("Item")
    except Exception as exc:
        logger.warning("DYNAMO_LOAD_TURN_ERROR | %s", exc)
        return None


def _save_turn(session_id: str, turn_num: int, question: str, answer: str) -> None:
    if not INTERVIEWS_TABLE:
        return
    try:
        _table().put_item(Item={
            "pk": f"SESSION#{session_id}",
            "sk": f"TURN#{turn_num:04d}",
            "question": question,
            "answer": answer,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as exc:
        logger.warning("DYNAMO_SAVE_TURN_ERROR | %s", exc)


def _update_session_meta(
    session_id: str, turn_count: int, summary: str, created_at: str | None = None
) -> None:
    if not INTERVIEWS_TABLE:
        return
    now = datetime.now(timezone.utc).isoformat()
    try:
        _table().put_item(Item={
            "pk": f"SESSION#{session_id}",
            "sk": "META",
            "summary": summary,
            "turn_count": turn_count,
            "created_at": created_at or now,
            "updated_at": now,
        })
    except Exception as exc:
        logger.warning("DYNAMO_UPDATE_META_ERROR | %s", exc)


def _update_rolling_summary(existing_summary: str, question: str, answer: str) -> str:
    """Call Nova Micro to produce an updated rolling summary of the conversation."""
    prompt = (
        "Eres un asistente que mantiene un resumen compacto de una entrevista técnica.\n"
        "Tu tarea: integrar el nuevo intercambio en el resumen existente y devolver\n"
        "un resumen actualizado en español de máximo 500 palabras.\n"
        "Captura: temas técnicos discutidos, opiniones expresadas, tendencias identificadas.\n"
        "Solo devuelve el resumen, sin introducción ni comentarios adicionales.\n\n"
        f"RESUMEN EXISTENTE:\n{existing_summary or '(ninguno todavía)'}\n\n"
        "NUEVO INTERCAMBIO:\n"
        f"P: {question}\n"
        f"R: {answer}\n\n"
        "RESUMEN ACTUALIZADO:"
    )
    try:
        resp = bedrock_runtime.converse(
            modelId=SUMMARY_MODEL_ARN,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 700, "temperature": 0.3},
        )
        return resp["output"]["message"]["content"][0]["text"].strip()
    except Exception as exc:
        logger.warning("SUMMARY_UPDATE_ERROR | %s", exc)
        return existing_summary  # Fall back to previous summary on error


# ─── Route: POST /ask ─────────────────────────────────────────────────────────

def _handle_ask(body: dict) -> dict:
    question = body.get("question", "").strip()
    if not question:
        return _error(400, "'question' field is required")

    system_prompt_override = (body.get("system_prompt") or "").strip()
    effective_system_prompt = system_prompt_override if system_prompt_override else SYSTEM_PROMPT

    temperature = float(body.get("temperature", DEFAULT_TEMPERATURE))
    max_tokens = int(body.get("max_tokens", DEFAULT_MAX_TOKENS))
    top_p = float(body.get("top_p", DEFAULT_TOP_P))
    num_results = int(body.get("num_results", DEFAULT_NUM_RESULTS))

    raw_filters = body.get("filters") or {}
    metadata_filter = _build_metadata_filter(raw_filters) if raw_filters else None

    model_id = body.get("model_id", "").strip()
    model_arn = _resolve_model_arn(model_id)

    # ── Session / conversation context ────────────────────────────────────────
    session_id = (body.get("session_id") or "").strip()
    is_new_session = not session_id
    if is_new_session:
        session_id = str(uuid.uuid4())

    session_meta = None if is_new_session else _load_session(session_id)
    turn_count = int((session_meta or {}).get("turn_count", 0))
    summary = (session_meta or {}).get("summary", "")
    created_at = (session_meta or {}).get("created_at")
    last_turn = _load_last_turn(session_id, turn_count)

    # Build context preamble injected before the RAG results
    context_parts = []
    if summary:
        context_parts.append(f"RESUMEN DE LA ENTREVISTA HASTA AHORA:\n{summary}")
    if last_turn:
        context_parts.append(
            f"ÚLTIMO INTERCAMBIO:\nP: {last_turn['question']}\nR: {last_turn['answer']}"
        )
    context_preamble = "\n\n".join(context_parts)

    logger.info(
        "REQUEST | question_len=%d | model=%s | num_results=%d | "
        "filters=%s | prompt_src=%s | temperature=%.2f | max_tokens=%d | "
        "session=%s | turn=%d | has_context=%s",
        len(question),
        model_id or "(default)",
        num_results,
        json.dumps(raw_filters) if raw_filters else "none",
        "override" if system_prompt_override else "env",
        temperature,
        max_tokens,
        session_id[:8],
        turn_count,
        bool(context_preamble),
    )

    # Build prompt: system prompt → conversation context → RAG results → question
    prompt_parts = [effective_system_prompt]
    if context_preamble:
        prompt_parts.append(context_preamble)
    prompt_parts += [
        "Context from retrieved documents:\n$search_results$",
        "Question: $query$",
    ]
    prompt_template = "\n\n".join(prompt_parts)

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

    vector_search_config: dict = {
        "numberOfResults": num_results,
        "overrideSearchType": "HYBRID",
    }
    if metadata_filter:
        vector_search_config["filter"] = metadata_filter

    logger.info(
        "BEDROCK_CALL | model_arn=%s | kb=%s | num_results=%d | search_type=HYBRID | "
        "metadata_filter=%s | prompt_len=%d",
        model_arn,
        KNOWLEDGE_BASE_ID,
        num_results,
        json.dumps(metadata_filter) if metadata_filter else "none",
        len(prompt_template),
    )

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

    raw_ref_count = sum(
        len(c.get("retrievedReferences", [])) for c in response.get("citations", [])
    )

    citations = []
    for citation in response.get("citations", []):
        for ref in citation.get("retrievedReferences", []):
            s3_uri = ref.get("location", {}).get("s3Location", {}).get("uri", "")
            text = ref.get("content", {}).get("text", "")
            if not _is_meaningful_chunk(text):
                continue
            citations.append({
                "source": s3_uri,
                "text": text,
                "metadata": ref.get("metadata", {}),
            })

    logger.info(
        "RESPONSE | answer_len=%d | raw_refs=%d | filtered_refs=%d | answer_preview=%r",
        len(answer),
        raw_ref_count,
        len(citations),
        answer[:120],
    )

    if raw_ref_count == 0:
        logger.warning(
            "NO_CONTEXT_RETRIEVED | model=%s | kb=%s | filters=%s | question=%r",
            model_arn,
            KNOWLEDGE_BASE_ID,
            json.dumps(metadata_filter) if metadata_filter else "none",
            question[:300],
        )

    if _looks_like_refusal(answer):
        logger.warning(
            "REFUSAL_DETECTED | model=%s | raw_refs=%d | filtered_refs=%d | "
            "filters=%s | answer=%r | question=%r",
            model_arn,
            raw_ref_count,
            len(citations),
            json.dumps(metadata_filter) if metadata_filter else "none",
            answer[:500],
            question[:300],
        )

    # ── Persist turn + update rolling summary ─────────────────────────────────
    if INTERVIEWS_TABLE:
        new_turn_count = turn_count + 1
        _save_turn(session_id, new_turn_count, question, answer)
        new_summary = _update_rolling_summary(summary, question, answer)
        _update_session_meta(session_id, new_turn_count, new_summary, created_at)
        logger.info("SESSION_SAVED | session=%s | turn=%d", session_id[:8], new_turn_count)

    return {
        "statusCode": 200,
        "headers": RESPONSE_HEADERS,
        "body": json.dumps({
            "answer": answer,
            "citations": citations,
            "session_id": session_id,
        }),
    }


# ─── Route: GET /interview/{id} ───────────────────────────────────────────────

def _handle_get_interview(session_id: str) -> dict:
    if not INTERVIEWS_TABLE:
        return _error(503, "Interview history not available")

    try:
        resp = _table().query(
            KeyConditionExpression=Key("pk").eq(f"SESSION#{session_id}")
        )
        items = resp.get("Items", [])
    except Exception as exc:
        logger.error("DYNAMO_QUERY_ERROR | %s", exc)
        return _error(500, str(exc))

    meta = next((i for i in items if i["sk"] == "META"), None)
    turns = sorted(
        [i for i in items if i["sk"].startswith("TURN#")],
        key=lambda x: x["sk"],
    )

    return {
        "statusCode": 200,
        "headers": RESPONSE_HEADERS,
        "body": json.dumps({
            "session_id": session_id,
            "summary": (meta or {}).get("summary", ""),
            "turn_count": int((meta or {}).get("turn_count", 0)),
            "created_at": (meta or {}).get("created_at", ""),
            "updated_at": (meta or {}).get("updated_at", ""),
            "turns": [
                {
                    "turn_num": int(t["sk"].replace("TURN#", "")),
                    "question": t.get("question", ""),
                    "answer": t.get("answer", ""),
                    "timestamp": t.get("timestamp", ""),
                }
                for t in turns
            ],
        }),
    }


# ─── Route: POST /interview/{id}/summary ──────────────────────────────────────

def _handle_finalize_interview(session_id: str, body: dict) -> dict:
    get_resp = _handle_get_interview(session_id)
    if get_resp["statusCode"] != 200:
        return get_resp

    interview = json.loads(get_resp["body"])
    turns = interview.get("turns", [])

    if not turns:
        return _error(400, "No turns found for this session")

    transcript = "\n\n".join(
        f"P{i + 1}: {t['question']}\nR{i + 1}: {t['answer']}"
        for i, t in enumerate(turns)
    )

    model_id = (body.get("model_id") or "").strip()
    model_arn = _resolve_model_arn(model_id)

    prompt = (
        "A continuación tienes la transcripción completa de una entrevista.\n"
        "Tu única tarea es generar un INFORME EJECUTIVO basado EXCLUSIVAMENTE "
        "en las preguntas y respuestas de esa transcripción.\n"
        "No uses conocimiento externo ni información que no aparezca en la entrevista.\n\n"
        "El informe debe estructurarse en estas secciones:\n"
        "1. **Resumen ejecutivo**: qué temas se abordaron y cuáles fueron las principales conclusiones (2-3 párrafos)\n"
        "2. **Temas clave discutidos**: lista de los temas principales que surgieron en la entrevista\n"
        "3. **Tendencias y patrones identificados**: tendencias o patrones que el entrevistado destacó durante la conversación\n"
        "4. **Recomendaciones**: consejos o recomendaciones que surgieron en la entrevista\n"
        "5. **Conclusión**: cierre con los puntos más relevantes de la conversación\n\n"
        "IMPORTANTE: el informe debe reflejar lo que SE DIJO en la entrevista. "
        "Cita o parafrasea las respuestas del entrevistado. "
        "Si alguna sección no tiene contenido relevante en la transcripción, indícalo brevemente.\n\n"
        f"TRANSCRIPCIÓN:\n{transcript}\n\n"
        "INFORME EJECUTIVO:"
    )

    try:
        resp = bedrock_runtime.converse(
            modelId=model_arn,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 2048, "temperature": 0.4},
        )
        executive_summary = resp["output"]["message"]["content"][0]["text"].strip()
    except Exception as exc:
        logger.error("FINALIZE_ERROR | %s", exc)
        return _error(500, str(exc))

    logger.info(
        "FINALIZE | session=%s | turns=%d | summary_len=%d",
        session_id[:8],
        len(turns),
        len(executive_summary),
    )

    return {
        "statusCode": 200,
        "headers": RESPONSE_HEADERS,
        "body": json.dumps({
            "session_id": session_id,
            "executive_summary": executive_summary,
            "turn_count": interview["turn_count"],
        }),
    }


# ─── Main handler ─────────────────────────────────────────────────────────────

def handler(event, context):
    method = (
        event.get("requestContext", {}).get("http", {}).get("method", "POST").upper()
    )
    raw_path = event.get("rawPath", "/ask")

    # GET /interview/{id}
    m = re.match(r"^/interview/([^/]+)$", raw_path)
    if m and method == "GET":
        return _handle_get_interview(m.group(1))

    # POST /interview/{id}/summary
    m = re.match(r"^/interview/([^/]+)/summary$", raw_path)
    if m and method == "POST":
        try:
            body = json.loads(event.get("body") or "{}")
        except (json.JSONDecodeError, TypeError):
            body = {}
        return _handle_finalize_interview(m.group(1), body)

    # POST /ask (default)
    try:
        body = json.loads(event.get("body") or "{}")
    except (json.JSONDecodeError, TypeError):
        return _error(400, "Invalid JSON body")

    return _handle_ask(body)
