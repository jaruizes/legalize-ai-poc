# Advanced RAG Explorer on AWS

A **production-grade Proof of Concept** for an **Advanced Retrieval-Augmented Generation (RAG)** system built entirely on AWS serverless infrastructure. While the architecture is domain-agnostic, it ships pre-configured to analyse the **Thoughtworks Technology Radar** corpus, enabling deep cross-volume trend analysis across multiple editions.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Ingestion Pipeline](#ingestion-pipeline)
4. [Query Pipeline](#query-pipeline)
5. [Design Decisions](#design-decisions)
   - [Chunking Strategy: Hierarchical](#1-chunking-strategy-hierarchical)
   - [Metadata Enrichment via Custom Transformation Lambda](#2-metadata-enrichment-via-custom-transformation-lambda)
   - [Metadata Extracted and Why](#3-metadata-extracted-and-why)
   - [Citation Filtering at Query Time](#4-citation-filtering-at-query-time)
   - [Model Flexibility: Inference Profiles vs Foundation Models](#5-model-flexibility-inference-profiles-vs-foundation-models)
   - [Embedding Model: Amazon Titan Embed Text v2](#6-embedding-model-amazon-titan-embed-text-v2)
   - [Generation Token Budget: 2048](#7-generation-token-budget-2048)
   - [Metadata-Aware Retrieval Filters](#8-metadata-aware-retrieval-filters)
   - [Hybrid Search: Vector + BM25](#9-hybrid-search-vector--bm25)
   - [Bedrock Guardrails: Contextual Grounding](#10-bedrock-guardrails-contextual-grounding--built-but-not-applied)
6. [Infrastructure](#infrastructure)
7. [Getting Started](#getting-started)
8. [Configuration Reference](#configuration-reference)
9. [Project Structure](#project-structure)
10. [Testing](#testing)
11. [Roadmap](#roadmap)

---

## Overview

This project implements an **Advanced RAG** pattern on top of Amazon Bedrock Knowledge Bases with several enhancements beyond the standard out-of-the-box setup:

- **Hierarchical chunking** for precision retrieval with broad context generation.
- **Pre-indexing metadata enrichment** via a custom transformation Lambda that extracts structured metadata (volume number, publication date, ring classification, blip name, quadrant) from raw PDF content before vectors are stored.
- **Citation quality filtering** to suppress structurally-extracted garbage chunks (e.g., PDF index pages with dense number grids) from appearing in responses.
- **Runtime model switching** supporting both AWS cross-region inference profiles (Amazon Nova family) and Anthropic foundation models (Claude family) without requiring infrastructure changes.
- **Metadata-aware retrieval filters** that narrow the vector search to a specific ring, quadrant, or set of editions, reducing noise for scoped analytical queries.
- **Hybrid search (vector + BM25)** using Bedrock's `HYBRID` retrieval mode, which combines dense embedding similarity with BM25 keyword scoring to improve exact-term recall for tool names, acronyms, and version strings.
- **Bedrock Guardrails** infrastructure provisioned (contextual grounding + relevance checks) but intentionally not applied at runtime — see §10 for why contextual grounding is the wrong control for synthesis RAG.

The reference dataset is the [Thoughtworks Technology Radar](https://github.com/jaruizes/thoughtworks-radar-vols), a bi-annual publication that classifies hundreds of technologies into four rings (Adopt, Trial, Assess, Hold) and four quadrants (Techniques, Platforms, Tools, Languages & Frameworks). Indexing multiple volumes enables queries like:

- *"How has LangGraph evolved across the last four radar editions?"*
- *"Which technologies moved from Trial to Adopt between Oct 2024 and Apr 2026?"*
- *"What are the emerging trends in the AI tools quadrant?"*

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  INGESTION                                                                  │
│                                                                             │
│  GitHub Repo ──git clone──► S3 Source Bucket                               │
│                                    │                                        │
│                                    ▼                                        │
│                          Bedrock KB Ingestion Job                           │
│                                    │                                        │
│                         ┌──────────┴──────────┐                             │
│                         │  Chunking           │  HIERARCHICAL               │
│                         │  (POST_CHUNKING)    │  parent=1500t / child=400t  │
│                         └──────────┬──────────┘                             │
│                                    │                                        │
│                         ┌──────────▼──────────┐                             │
│                         │  Enricher Lambda    │  Adds: volume, year,        │
│                         │  (Custom Transform) │  edition, ring, blip_name,  │
│                         │  reads/writes S3    │  quadrant per chunk         │
│                         └──────────┬──────────┘                             │
│                                    │                                        │
│                         ┌──────────▼──────────┐                             │
│                         │  Amazon Titan        │  1024-dim embeddings        │
│                         │  Embed Text v2       │                            │
│                         └──────────┬──────────┘                             │
│                                    │                                        │
│                         ┌──────────▼──────────┐                             │
│                         │  OpenSearch          │  Vectors + metadata         │
│                         │  Serverless          │  (filterable attributes)    │
│                         └─────────────────────┘                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│  QUERY                                                                      │
│                                                                             │
│  Angular UI ──/ask──► CloudFront ──► Lambda Function URL ──► Ask Lambda    │
│   { question, model_id?,                       │                            │
│     max_tokens?, num_results?,          ┌──────▼──────────────────────┐    │
│     filters? }                          │ retrieve_and_generate        │    │
│                                         │  Bedrock KB API              │    │
│                                         │  + HYBRID search (vec+BM25)  │    │
│                                         │  + optional metadata filter  │    │
│                                         └──────┬───────────────────────┘    │
│                         ┌───────────────────────┴──────────────┐            │
│                         │                                       │            │
│               ┌─────────▼──────────┐               ┌───────────▼────────┐  │
│               │  Hybrid Search      │               │  LLM Generation    │  │
│               │  OpenSearch         │               │  Nova / Claude     │  │
│               │  vector + BM25      │               │  (parent context)  │  │
│               │  (child chunks)     │               └────────────────────┘  │
│               │  + filter by        │                                        │
│               │  ring/quadrant/     │                                        │
│               │  edition            │                                        │
│               └─────────────────────┘                                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

### AWS Services Used

| Service | Role |
|---|---|
| Amazon S3 | Source document storage, intermediate chunking bucket, frontend hosting |
| Amazon Bedrock Knowledge Bases | Orchestrates ingestion, chunking, embedding, and retrieval |
| AWS Lambda (Enricher) | Custom POST_CHUNKING transformation: metadata extraction and enrichment |
| AWS Lambda (Ask) | API handler: receives questions, calls `retrieve_and_generate`, filters citations |
| Amazon OpenSearch Serverless | Vector store with hybrid search (vector + BM25) and metadata filtering |
| Amazon Titan Embed Text v2 | Embedding model (1024 dimensions) |
| Amazon Nova / Anthropic Claude | Generative models for answer synthesis |
| Amazon Bedrock Guardrails | Contextual grounding + relevance checks (provisioned, not applied — see §10) |
| AWS Lambda Function URL | HTTP endpoint for the Ask Lambda (replaces API Gateway; no 29s timeout) |
| Amazon CloudFront + S3 | CDN for frontend; proxies `/ask` to Lambda Function URL |
| AWS IAM | Least-privilege roles for each component |

---

## Ingestion Pipeline

```
1. git clone <datasource_repo_url>
      │
      ▼
2. aws s3 sync → S3 Source Bucket
      │   (triggered by Terraform on repo HEAD change)
      ▼
3. Bedrock KB Ingestion Job
      │
      ├─► PDF parsing (Bedrock built-in)
      │
      ├─► Hierarchical Chunking
      │     · Parent chunks: 1500 tokens  → broad context (3-5 blips)
      │     · Child chunks:   400 tokens  → single blip description
      │     · Overlap:         60 tokens  → continuity at boundaries
      │
      ├─► Custom Transformation: Enricher Lambda (POST_CHUNKING)
      │     · Bedrock writes batch JSON files to temp S3 bucket
      │     · Lambda reads each batch, enriches chunk metadata in-place
      │     · Lambda writes enriched batch back to S3
      │     · Returns output file locations to Bedrock
      │
      ├─► Embedding: Amazon Titan Embed Text v2
      │     · 1024-dimensional dense vectors
      │
      └─► Indexing: OpenSearch Serverless
            · Vector + metadata stored as filterable attributes
```

The ingestion is triggered automatically by `./start.sh` or manually via:

```bash
aws bedrock-agent start-ingestion-job \
  --knowledge-base-id <KB_ID> \
  --data-source-id <DS_ID> \
  --region eu-west-1
```

> **Important**: any change to the chunking strategy or enricher logic requires a full re-ingestion. The existing vectors are **not** updated incrementally for structural changes.

---

## Query Pipeline

```
1. User question → Angular UI
      │
      ▼
2. POST /ask → CloudFront → Lambda Function URL → Ask Lambda
      │  { question, model_id?, max_tokens?, num_results?,
      │    temperature?, filters?: { ring?, quadrant?, editions? } }
      ▼
3. bedrock_agent_runtime.retrieve_and_generate()
      │
      ├─► Hybrid search on OpenSearch (child chunks, top-N)
      │     · HYBRID mode: dense vector (cosine) + BM25 keyword, fused with RRF
      │     · Default num_results = 20, user-configurable up to 100 via UI slider
      │     · Optional metadata filter applied when filters.* are present:
      │       e.g. ring=Adopt AND quadrant=Tools AND edition IN [Oct 2024, Apr 2025]
      │
      ├─► Parent chunk retrieval (full 1500-token context for each matched child)
      │
      └─► LLM Generation with prompt template:
            SYSTEM_PROMPT + retrieved parent contexts + user question
            │
            ▼
4. Response: { answer, citations[] }
      │
      ▼
5. Citation filtering (Ask Lambda)
      · Suppress chunks with >40% bare-number tokens (PDF diagram pages)
      · Suppress chunks shorter than 40 characters
      │
      ▼
6. Typewriter rendering (Angular UI)
      · Full response received; text revealed word-by-word (typewriter animation)
      · Bedrock citation markers (Passage %[N]%) → superscript refs
      · Raw markdown (**, ##) → HTML
```

---

## Design Decisions

This section documents the key architectural choices, the alternatives considered, and the reasoning behind each decision.

---

### 1. Chunking Strategy: Hierarchical

**Decision**: Use `HIERARCHICAL` chunking with parent=1500 tokens, child=400 tokens, overlap=60 tokens.

**Context**: The Technology Radar PDFs have a very consistent structure. Each technology entry (called a "blip") occupies roughly one printed page, which yields approximately 170–440 tokens of text after PDF extraction:

```
© Thoughtworks, Inc. All Rights Reserved.
13
4. Retrieval-augmented generation (RAG)
Adopt
Retrieval-augmented generation (RAG) is the preferred pattern for our teams...
[~300 tokens of description]
```

**Alternatives considered**:

| Strategy | Problem for this use case |
|---|---|
| `FIXED_SIZE` (512t) | Ignores natural content boundaries. A 512-token budget frequently splits a blip's description mid-sentence, separating the ring name ("Adopt") from the body. Metadata extraction in the enricher Lambda breaks completely. |
| `SEMANTIC` (512t) | Respects natural sentence boundaries but creates many small, isolated chunks. For cross-volume evolution queries, the LLM receives N independent fragments without the surrounding context that explains which technologies appear alongside a given blip in the same section. |
| `SEMANTIC` (800t) | Better coverage of a single blip, but still no multi-blip context for broad queries and still risks merging two adjacent blips into one chunk when their embeddings are close. |
| `HIERARCHICAL` | Retrieval uses child chunks (~1 blip) for precision. Generation uses parent chunks (~3-5 blips) for context. This combination enables both "tell me about LangGraph" (precise, child-level) and "what is happening in AI tools" (contextual, parent-level) queries. ✓ |

**How the child/parent sizes were chosen**:

- `child_max_tokens = 400`: A single blip page is 170–440 tokens. 400 tokens is the upper bound that reliably captures one blip without merging two.
- `parent_max_tokens = 1500`: A section like "Tools – Adopt" typically lists 3–5 blips. 1500 tokens covers a semantically coherent cluster, giving the LLM enough context to synthesise patterns across related technologies.
- `overlap_tokens = 60`: Roughly one sentence. Ensures the LLM can follow references that span a chunk boundary.

**Implication**: changing the chunking strategy requires a full re-ingestion job.

---

### 2. Metadata Enrichment via Custom Transformation Lambda

**Decision**: Use a Bedrock KB `POST_CHUNKING` custom transformation Lambda to enrich chunk metadata before vectorisation.

**Context**: The PDFs contain richly structured information (volume number, publication date, technology classification) that is not captured by default Bedrock ingestion. Without this metadata, it is impossible to filter or weight retrieved chunks by edition, ring, or quadrant.

**How it works at the infrastructure level**:

Bedrock's custom transformation protocol is S3-mediated:
1. After chunking, Bedrock writes batch JSON files to a temp S3 bucket.
2. It invokes the enricher Lambda with the bucket name and batch file keys.
3. The Lambda reads each batch from S3, enriches chunk metadata in-place (preserving the exact input structure to avoid schema mismatches), and writes the result back to S3.
4. The Lambda returns the output file locations to Bedrock.
5. Bedrock reads the enriched batches, generates embeddings, and indexes the result.

**Why not pre-process outside Bedrock?**

An alternative would be to run a separate pre-processing step before syncing documents to S3: parse PDFs, extract metadata, generate a companion `metadata.json` file, and rely on Bedrock's native metadata file support.

This was ruled out because:
- It adds a separate pipeline step with its own infra, IAM, and failure modes.
- The enricher Lambda approach integrates cleanly with Bedrock's ingestion lifecycle.
- Chunk-level metadata (ring, blip_name) can only be extracted *after* chunking, because the enricher can read the actual chunk text.

**Critical implementation constraint**: The output batch files must preserve the exact top-level structure of the input batch (pass-through). Any attempt to reformat the JSON causes a `Failed to deserialize the output file` error from Bedrock. Enrichment is strictly additive: new attributes are appended to `metadata.attributes`, the rest of the document is untouched.

---

### 3. Metadata Extracted and Why

Each chunk is enriched with the following attributes, stored as filterable metadata in OpenSearch:

| Attribute | Source | Example | Why |
|---|---|---|---|
| `volume` | Filename regex `vol_(\d+)` | `"33"` | Core temporal identifier; enables "filter by edition" |
| `year` | Lookup table by volume number | `"2025"` | Filenames do not contain the year; PDF first-page text does, but the lookup table is more reliable |
| `month` | Lookup table by volume number | `"11"` | Sub-year granularity for two editions per year |
| `edition` | Lookup table by volume number | `"Nov 2025"` | Human-readable; useful in LLM prompt context and citations |
| `ring` | Chunk text pattern (`Adopt\|Trial\|Assess\|Hold\|Caution`) | `"Adopt"` | Enables ring-based filtering: "what moved to Adopt?" |
| `blip_name` | Chunk text pattern (`^\d+\. (.+)$`) | `"LangGraph"` | Enables blip-tracking across volumes: "how has X evolved?" |
| `quadrant` | Chunk text pattern (`Techniques\|Platforms\|Tools\|Languages and Frameworks`) | `"Tools"` | Enables quadrant filtering: "what's new in AI tools?" |
| `processed_by` | Hardcoded | `"advanced-rag-enricher"` | Audit trail; confirms enrichment ran |

**Known limitation**: `quadrant` is only present in the chunk text for the *first* blip page of each section (the one that immediately follows the section header). For subsequent blips in the same section, `quadrant` is `"unknown"`. This is a PDF layout constraint: Thoughtworks only prints the section name on the first content page after the diagram.

**Why year is a lookup table, not filename regex**:

The PDF filenames follow the pattern `tr_technology_radar_vol_33_en.pdf` — they contain the volume number but not the year. Bedrock's enricher Lambda does receive the original S3 URI, so the filename is available, but extracting the year requires cross-referencing the volume number to a publication date. The lookup table (`VOLUME_EDITIONS` dict in the Lambda) is updated once when a new volume is published:

```python
VOLUME_EDITIONS = {
    "31": {"year": "2024", "month": "10", "edition": "Oct 2024"},
    "32": {"year": "2025", "month": "04", "edition": "Apr 2025"},
    "33": {"year": "2025", "month": "11", "edition": "Nov 2025"},
    "34": {"year": "2026", "month": "04", "edition": "Apr 2026"},
}
```

---

### 4. Citation filtering at Query Time

**Decision**: The Ask Lambda filters out citations whose text is predominantly numeric before returning them to the frontend.

**Context**: PDF extraction often produces structurally garbage chunks from radar diagram pages — pages that visually show a quadrant grid with blip numbers but whose extracted text is essentially a sequence of integers:

```
Hold HoldAssess AssessTrial TrialAdopt Adopt
4 13 1621 25 30 31 32 34 35 36 37 38 39 40 41 26 29 2 6 5 ...
```

These chunks have high semantic similarity to any technology-related query (they contain technology category terms like "Adopt", "Tools") and are frequently retrieved by the vector store. However, they provide zero informational value in a citation.

**Filter logic** (`_is_meaningful_chunk` in `lambda/ask/handler.py`):
- Chunks shorter than 40 characters → rejected (too short to carry information).
- Chunks where more than 40% of whitespace-tokenised terms are bare integers → rejected (PDF diagram pages).

**Why at query time and not at ingestion time?**

Filtering at ingestion time (in the enricher) would require either deleting chunks from the batch or marking them `skip: true`, neither of which is officially supported by the custom transformation schema. Filtering at query time keeps the index complete and the filter logic easy to tune without re-ingesting the entire corpus.

---

### 5. Model Flexibility: Inference Profiles vs Foundation Models

**Decision**: The Ask Lambda supports both AWS cross-region inference profiles (Amazon Nova family) and direct foundation model invocation (Anthropic Claude family) via runtime ARN construction.

**Context**: AWS Bedrock uses different ARN formats depending on how a model is accessed:

| Model type | ARN format | Example |
|---|---|---|
| Cross-region inference profile | `arn:aws:bedrock:REGION:ACCOUNT:inference-profile/ID` | `eu.amazon.nova-lite-v1:0` |
| Foundation model | `arn:aws:bedrock:REGION::foundation-model/ID` | `anthropic.claude-sonnet-4-6` |

The first format includes the account ID; the second does not (note the double `::` — no account component). Using the wrong format results in an `AccessDeniedException` or `ResourceNotFoundException`.

**Implementation**: the Lambda detects the model type by checking if the `model_id` starts with a known regional prefix (`eu.`, `us.`, `ap.`, `us-gov.`). If yes, it constructs an inference profile ARN; otherwise it constructs a foundation model ARN:

```python
_INFERENCE_PROFILE_PREFIXES = ("eu.", "us.", "ap.", "us-gov.")

if _is_inference_profile(model_id):
    model_arn = INFERENCE_PROFILE_ARN_BASE + model_id
    # e.g. arn:aws:bedrock:eu-west-1:123456789:inference-profile/eu.amazon.nova-lite-v1:0
else:
    model_arn = FOUNDATION_MODEL_ARN_BASE + model_id
    # e.g. arn:aws:bedrock:eu-west-1::foundation-model/anthropic.claude-sonnet-4-6
```

Both ARN base URLs are injected as Lambda environment variables from Terraform, avoiding any hardcoded account IDs or regions.

**IAM**: the Lambda role's `BedrockInvokeModel` policy covers both resource patterns:
```json
"Resource": [
  "arn:aws:bedrock:*:ACCOUNT:inference-profile/*",
  "arn:aws:bedrock:*::foundation-model/*"
]
```

---

### 6. Embedding Model: Amazon Titan Embed Text v2

**Decision**: Use `amazon.titan-embed-text-v2:0` with 1024-dimensional vectors.

**Rationale**:
- Native to Amazon Bedrock — no cross-service latency or additional IAM complexity.
- 1024 dimensions offer a good balance between recall quality and OpenSearch storage/query cost.
- Supports multilingual content (the Radar PDFs are in English but queries may arrive in Spanish or other languages).
- `v2` provides significantly better semantic fidelity than `v1` for technical vocabulary.

**Trade-off**: switching embedding models requires a full re-ingestion because the existing vectors in OpenSearch become incompatible (different dimensionality and semantic space).

---

### 7. Generation Token Budget: 2048

**Decision**: `DEFAULT_MAX_TOKENS = 2048` for generation, configurable up to 4096 via the UI slider.

**Context**: The previous default was 512. At 512 tokens (~400 words), a complex comparative analysis across four radar volumes is physically impossible — the model would truncate after barely covering two editions.

**Guidelines for this use case**:
- Simple factual queries ("what ring is LangGraph in vol 33?") → 256–512 tokens is sufficient.
- Trend analysis across two editions → 1024 tokens.
- Full cross-volume evolution report → 2048–4096 tokens.

Increasing max tokens increases cost per query linearly. The UI slider lets users tune this per query without requiring a redeployment.

---

### 8. Metadata-Aware Retrieval Filters

**Decision**: Expose `ring`, `quadrant`, and `editions` as optional hard filters on the vector search, applied via the Bedrock KB `vectorSearchConfiguration.filter` parameter.

**Context**: The enricher Lambda tags every chunk with structured metadata (`ring`, `quadrant`, `edition`). Without query-time filters, a question like *"what entered Adopt in Oct 2024?"* returns chunks from all four editions — the model then has to infer temporal scope from the text, which it may do incorrectly. Hard filters eliminate irrelevant chunks before the vector similarity ranking, improving both accuracy and response quality.

**How filters are built** (`_build_metadata_filter` in `lambda/ask/handler.py`):

Filters from the request body are converted into Bedrock KB filter expressions:

```python
# Single field:  { "equals": { "key": "ring", "value": "Adopt" } }
# Multiple fields are AND-ed:
{
  "andAll": [
    { "equals": { "key": "ring",     "value": "Adopt" } },
    { "equals": { "key": "quadrant", "value": "Tools" } },
    { "in":     { "key": "edition",  "value": ["Oct 2024", "Apr 2025"] } }
  ]
}
```

When no filters are provided the expression is omitted entirely — behaviour is identical to the pre-filter version.

**UI**: the settings panel exposes three filter controls:
- **Anillo** — dropdown (Adopt / Trial / Assess / Hold / Todos)
- **Cuadrante** — dropdown (Techniques / Tools / Platforms / Languages and Frameworks / Todos)
- **Ediciones** — multi-select chips (one per radar volume); any number can be combined

Active filters are visually indicated on the settings button and can be cleared in one click.

**Trade-off**: hard filters reduce recall. If a user selects `quadrant=Tools` but the relevant chunk has `quadrant=unknown` (which occurs for non-first-page blips — see §3), the filter will exclude it. For exploratory queries, using no filter is better.

---

### 9. Hybrid Search: Vector + BM25

**Decision**: The retrieval strategy uses `overrideSearchType: "HYBRID"` in `vectorSearchConfiguration`, combining dense vector similarity search with BM25 keyword scoring.

**Why vector-only search is not enough**:

Standard RAG pipelines rely exclusively on **dense vector retrieval**: the query and each document chunk are encoded as high-dimensional embeddings and the closest chunks by cosine similarity are returned. This works well for paraphrased or conceptually similar queries, but has a well-known failure mode: **exact-term recall**.

Embedding models compress meaning into a fixed-size vector. In doing so, specific surface tokens — proper nouns, acronyms, version strings, niche tool names — are merged into a broader semantic neighbourhood. Searching for *"eBPF"* or *"Rust 2024 edition"* may return chunks about systems observability or memory-safe languages in general, rather than the chunk that contains those exact strings.

In a technology radar corpus this matters a lot:

| Query contains | Vector search may miss | BM25 would catch |
|---|---|---|
| Exact tool name (`"Temporal"`, `"Buf"`) | Chunks where that name appears once | Chunks with exact token match |
| Acronyms (`"DORA"`, `"eBPF"`, `"WASM"`) | Semantically distant from description | Exact token match regardless |
| Version / edition strings (`"Vol. 32"`) | Not meaningful in embedding space | Direct keyword hit |
| Ring transitions (`"moved to Adopt"`) | Lost in paraphrase compression | Phrase proximity scoring |

**What BM25 adds**:

BM25 (Best Match 25) is a classic probabilistic keyword-ranking function. It scores chunks by the frequency of query tokens relative to the average chunk length (TF-IDF family, with length normalisation). Its strengths are the exact opposite of dense retrieval:

- **Exact-term recall**: if the query token is present in the chunk, BM25 scores it — regardless of how different the surrounding semantics are.
- **Rare-term boost**: tokens that appear in few chunks (specific tool names) get a high IDF weight, surfacing the most specific passages.
- **Transparent scoring**: scores are derived directly from token overlap, making the retrieval easier to reason about.

**Hybrid mode in Bedrock Knowledge Base**:

Bedrock's hybrid search mode runs both retrievers in parallel on the same OpenSearch Serverless collection and fuses the result lists using **Reciprocal Rank Fusion (RRF)**: each chunk's combined score is `1/(k + rank_vector) + 1/(k + rank_bm25)` where `k` is a small constant (typically 60). Chunks that rank highly in both lists are boosted strongly; chunks that appear in only one list are still surfaced if their single-list rank is high enough.

This means neither approach dominates — a semantically relevant chunk that doesn't contain the exact query tokens still gets retrieved, and a chunk containing the exact tokens that is semantically distant still gets a chance.

**When hybrid search helps most in this system**:

- Questions about a specific named technology: *"¿Qué dice el radar sobre Temporal?"*
- Cross-volume evolution queries: the model needs chunks from all three volumes — hybrid search widens the net.
- Synthesis queries with 20–40 `num_results`: at higher chunk counts the diversity from two retrieval signals prevents the result set from being dominated by a single semantic cluster.

**When it makes little difference**:

- Broad thematic queries without exact-match signals (*"¿Cuáles son las tendencias en plataformas?"*) — both retrievers return conceptually similar chunks.
- Queries covered by a strong metadata filter — the filter pre-narrows the corpus before ranking.

---

### 10. Bedrock Guardrails: Contextual Grounding — Built but Not Applied

**Decision**: The contextual grounding guardrail infrastructure is provisioned in Terraform but is **intentionally not attached** to the `retrieve_and_generate` call.

**Why it was not applied**:

Bedrock's contextual grounding guardrail works by scoring how closely the generated response text can be traced back to the retrieved source passages using semantic similarity. This is appropriate for **factual Q&A** ("what ring is X in vol 33?"), where the response should be a near-verbatim extraction from a chunk.

For the primary use case of this system — **multi-document synthesis and trend analysis** — the guardrail produces only false positives:

- The model generates conclusions like *"LangGraph moved from Trial to Adopt between Oct 2024 and Apr 2025"*
- This claim is fully correct and is derivable from the indexed volumes
- However, it does not appear verbatim in any single chunk; it is an inference across two chunks from different volumes
- The grounding score for this kind of synthesis is low regardless of the threshold, causing valid analytical responses to be blocked

Testing confirmed that even at a threshold of 0.4 (the lowest that still filters clear hallucinations), broad synthesis queries such as *"How have AI tools evolved over the last two years?"* are blocked.

**What the guardrail infrastructure provides**:

The Terraform resources (`aws_bedrock_guardrail`, `aws_bedrock_guardrail_version`) and the IAM `bedrock:ApplyGuardrail` permission remain in place. The Lambda receives `GUARDRAIL_ID` and `GUARDRAIL_VERSION` as environment variables. Applying the guardrail to specific factual queries in the future requires only adding `guardrailConfiguration` to `generationConfiguration` — no infrastructure change is needed.

**Better alternatives for hallucination control in synthesis RAG**:

| Approach | Suitable for |
|---|---|
| Contextual grounding guardrail | Factual Q&A, extraction queries |
| Topic restriction guardrail | Blocking questions outside the corpus domain |
| Careful system prompt design | Instructing the model to cite sources and flag uncertainty |
| Citation display in the UI | Letting the user verify claims against source chunks |

The citation display approach (already implemented) is the most appropriate control for this use case: the user can expand the source references and verify any claim the model makes.

---

## Infrastructure

All infrastructure is defined in Terraform under `infrastructure/terraform/`. The stack is modular:

```
infrastructure/terraform/
├── main.tf                    # Root: wires modules together, document sync
├── variables.tf               # All tunable parameters with defaults
├── outputs.tf                 # Exported values (KB ID, CF URL, etc.)
└── modules/
    ├── s3_source/             # Source document bucket
    ├── opensearch/            # OpenSearch Serverless collection + index
    ├── bedrock_kb/            # Knowledge Base, Data Source, Enricher Lambda, IAM
    │   ├── main.tf
    │   └── variables.tf
    ├── api/                   # Ask Lambda, Lambda Function URL, Guardrail, IAM
    │   ├── main.tf
    │   └── variables.tf
    └── frontend/              # CloudFront distribution + S3 frontend bucket
```

### IAM Design

The project follows least-privilege IAM:

- **Bedrock KB role**: `InvokeModel` (embedding model only), `s3:GetObject/ListBucket` (source bucket), `aoss:APIAccessAll` (OpenSearch collection), `lambda:InvokeFunction` (enricher), `s3:GetObject/PutObject/ListBucket` (temp bucket).
- **Enricher Lambda role**: `s3:GetObject/PutObject` (temp bucket only), `s3:ListBucket` (temp bucket).
- **Ask Lambda role**: `bedrock:RetrieveAndGenerate` + `bedrock:Retrieve` (specific KB), `bedrock:InvokeModel` (all inference profiles + foundation models in account), `bedrock:GetInferenceProfile`, `bedrock:ApplyGuardrail` (specific guardrail ARN).

---

## Getting Started

### Prerequisites

- AWS account with Bedrock model access enabled for:
  - `amazon.titan-embed-text-v2:0` (embeddings)
  - At least one generative model: `eu.amazon.nova-lite-v1:0` or similar
- Terraform ≥ 1.5.0
- AWS CLI configured with credentials
- Node.js ≥ 18 + npm
- Python 3.11+

### One-Command Deployment

```bash
chmod +x start.sh
./start.sh
```

This script:
1. Verifies prerequisites (terraform, aws, node, npm).
2. Runs `terraform init` + `terraform apply` (provisions OpenSearch Serverless, Bedrock KB, Lambda + Function URL, CloudFront). First run takes 10–15 minutes.
3. Builds the Angular app and deploys it to S3 + CloudFront.
4. Removes temporary Lambda ZIP files.
5. Starts a Bedrock KB ingestion job (clones the radar volumes repo → S3 → chunks → enriches → embeds → indexes).

**Flags**:
```bash
./start.sh --skip-frontend    # Re-deploy infra only, skip Angular build
./start.sh --skip-ingestion   # Re-deploy infra + frontend, skip KB ingestion
```

### Re-indexing After Enricher or Chunking Changes

Any change to the enricher Lambda or the chunking configuration requires a full re-ingestion:

```bash
./start.sh --skip-frontend
```

Terraform detects the Lambda code change (via `source_code_hash`), updates the function, and `start.sh` triggers a new ingestion job.

### Cleanup

```bash
cd infrastructure/terraform
terraform destroy
```

> OpenSearch Serverless has a minimum billing unit. Destroy the stack when not in use to avoid charges.

---

## Configuration Reference

All parameters are in `infrastructure/terraform/variables.tf`. The most relevant ones:

### Chunking

| Variable | Default | Description |
|---|---|---|
| `chunking_strategy` | `HIERARCHICAL` | `DEFAULT`, `FIXED_SIZE`, `HIERARCHICAL`, `SEMANTIC`, `NONE` |
| `hierarchical_parent_max_tokens` | `1500` | Parent chunk size. Covers 3–5 blips for broad context. |
| `hierarchical_child_max_tokens` | `400` | Child chunk size. Sized for one blip description. |
| `hierarchical_overlap_tokens` | `60` | Token overlap between consecutive chunks. |

### Models

| Variable | Default | Description |
|---|---|---|
| `kb_model_id` | `amazon.titan-embed-text-v2:0` | Embedding model. Changing this requires full re-ingestion. |
| `inference_profile_id` | `eu.amazon.nova-lite-v1:0` | Default generative model (cross-region inference profile). |
| `vector_dimension` | `1024` | Must match the embedding model's output dimension. |

### Generation

| Variable | Default | Description |
|---|---|---|
| `default_max_tokens` | `2048` | Default output token budget. Users can override via UI (up to 4096). |
| `default_num_results` | `20` | Default number of chunks retrieved per query. Users can override via UI (5–100). |
| `api_system_prompt` | (see file) | System prompt injected on every `/ask` call. |

### UI

| Variable | Default | Description |
|---|---|---|
| `ui_title` | `Tech Radar Explorer` | App title (header + welcome screen). |
| `ui_subtitle` | (see file) | Subtitle on the welcome screen. |
| `ui_icon` | `🔍` | Emoji icon in header and assistant avatar. |
| `ui_examples` | (see file) | Example queries shown before the first message. |
| `ui_disclaimer` | (see file) | Footer disclaimer text. |

### Guardrails

| Variable | Default | Description |
|---|---|---|
| `guardrail_grounding_threshold` | `0.4` | Minimum grounding score (0–1). Answers with lower score are blocked. (Guardrail provisioned but not applied — see §10.) |
| `guardrail_relevance_threshold` | `0.4` | Minimum relevance score (0–1). Answers with lower score are blocked. (Guardrail provisioned but not applied — see §10.) |

### Data Source

| Variable | Default | Description |
|---|---|---|
| `datasource_repo_url` | Radar volumes repo | Git URL cloned and synced to S3 on `terraform apply`. |

---

## Project Structure

```
.
├── app/                            # Angular 19 frontend
│   └── src/
│       ├── app/
│       │   └── app.component.ts    # Chat UI: signals, markdown rendering, model picker, filters
│       └── environments/
│           └── environment.ts      # UI config + filter options injected by deploy-frontend.sh
│
├── infrastructure/
│   └── terraform/
│       ├── main.tf                 # Root module
│       ├── variables.tf            # All tunable parameters
│       └── modules/
│           ├── s3_source/          # Source document bucket
│           ├── opensearch/         # Vector store
│           ├── bedrock_kb/         # KB + enricher Lambda
│           └── api/                # Ask Lambda + Lambda Function URL + Guardrail
│
├── lambda/
│   ├── ask/
│   │   ├── handler.py              # /ask endpoint: retrieve_and_generate + citation filter
│   │   └── test_handler.py
│   └── enricher/
│       ├── handler.py              # POST_CHUNKING enricher: extracts ring, blip, edition…
│       └── test_handler.py         # 44 unit + integration tests (moto S3 mock)
│
├── scripts/
│   └── deploy-frontend.sh          # Angular build + S3 sync + CloudFront invalidation
│       # Injects Terraform outputs into environment.ts using per-field regex replacement
│       # (block replacement was abandoned after it silently corrupted models/defaultMaxTokens)
│
├── radar-example-files/            # Local copies of radar PDFs for testing
│
└── start.sh                        # Bootstrap: tf apply + frontend deploy + ingestion
```

---

## Testing

### Enricher Lambda

```bash
cd lambda/enricher

# Create virtualenv and run tests
python3 -m venv venv && source venv/bin/activate
pip install boto3 moto pytest
pytest test_handler.py -v
```

The test suite (44 tests) uses `moto` to mock S3, covering:
- Lambda response schema (Bedrock contract: `outputFiles` only, no top-level `version`)
- Output key naming convention
- Pass-through structure preservation
- Core metadata enrichment (`volume`, `year`, `edition`)
- Text-derived metadata (`ring`, `blip_name`, `quadrant`)
- Edge cases: unknown volumes, duplicate attribute prevention, empty batches, `chunkList` key variant

### Ask Lambda

```bash
cd lambda/ask
python3 -m venv venv && source venv/bin/activate
pip install boto3 moto pytest
pytest test_handler.py -v
```

---

## Roadmap

Potential next steps to evolve this PoC into a production-grade system:

1. ✅ **Metadata-aware retrieval filters** — `ring`, `quadrant`, and `edition` hard filters applied in the Bedrock vector search configuration via the UI settings panel. See [§8](#8-metadata-aware-retrieval-filters).
2. **Evaluation framework** — integrate [RAGAS](https://github.com/explodinggradients/ragas) or [DeepEval](https://github.com/confident-ai/deepeval) to measure retrieval precision, answer faithfulness, and context recall across query types.
3. ~~**Bedrock Guardrails**~~ — the contextual grounding guardrail was built and tested but is **intentionally not applied** to synthesis queries: it evaluates direct textual traceability, which always fails for multi-document inference and analysis. See [§10](#10-bedrock-guardrails-contextual-grounding--built-but-not-applied).
4. **Semantic cache** — cache frequent query embeddings and their responses (Amazon ElastiCache or a Lambda-local LRU) to reduce latency and Bedrock costs for repeated questions.
5. **Conversation memory** — pass prior turns to `retrieve_and_generate` using Bedrock's session management to enable multi-turn conversations.
6. **Query decomposition** — for complex analysis questions, decompose them into sub-queries (one per volume), run them in parallel, and synthesise the results. This would significantly improve cross-volume evolution reports.
7. **Automatic volume ingestion** — watch the upstream radar repository for new commits and trigger an incremental ingestion job automatically via EventBridge + Lambda.
