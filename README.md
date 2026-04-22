# Legalize ES - RAG PoC on AWS

A foundational Proof of Concept (PoC) for a **Retrieval-Augmented Generation (RAG)** system designed to query Spanish legislation. This project leverages AWS managed services to provide a scalable, serverless, and production-ready architecture.

## 📋 Overview

This project serves as the baseline for a series of implementations exploring the evolution of RAG systems. It indexes Spanish legal documents (in Markdown) into a vector database and provides a web interface to perform natural language queries against the law.

### 🏗️ Target Use Case
The current implementation focuses on a **Foundational RAG** pattern, which will be evolved in future iterations to include:
- 🧠 **Semantic Cache**: To reduce latency and costs for redundant queries.
- 🛡️ **Guardrails**: To ensure safe and relevant model responses.
- 🔍 **Hybrid Search**: Combining semantic vector search with keyword-based BM25 search.
- 🔄 **Advanced Re-ranking**: To improve the relevance of retrieved context.

## 🏗️ Architecture

The system is built entirely on AWS using a serverless approach:

- **Frontend**: Angular 19 application hosted on **Amazon S3** and distributed via **Amazon CloudFront**.
- **API**: **AWS Lambda** (Python) triggered by **Amazon API Gateway**.
- **Orchestration**: **Amazon Bedrock Knowledge Bases** handles the RAG workflow (Retrieval + Generation).
- **Vector Store**: **Amazon OpenSearch Serverless (OSS)** stores the document embeddings.
- **LLMs**: 
    - **Embeddings**: `amazon.titan-embed-text-v2:0`
    - **Generation**: `amazon.nova-lite-v1:0` (via Bedrock)
- **Infrastructure as Code**: **Terraform**.

## 🚀 Getting Started

### Prerequisites

- **AWS Account** with Bedrock model access enabled (Titan Embeddings and Nova/Claude).
- **Terraform** (>= 1.5.0)
- **AWS CLI** configured with appropriate credentials.
- **Node.js & npm** (for the Angular frontend).
- **Python 3.12+** (for local Lambda testing).

### One-Click Deployment

The project includes a bootstrap script that handles infrastructure provisioning, frontend building, and data ingestion.

```bash
chmod +x start.sh
./start.sh
```

This script will:
1. Initialize and apply the **Terraform** configuration.
2. Build the **Angular** application.
3. Deploy the frontend assets to **S3** and invalidate **CloudFront**.
4. Synchronize the legal documents from `legalize-es/` to the source S3 bucket.
5. Trigger an **Ingestion Job** in the Bedrock Knowledge Base.

### Manual Setup

1. **Infrastructure**:
   ```bash
   cd infrastructure/terraform
   terraform init
   terraform apply
   ```

2. **Frontend**:
   ```bash
   cd app
   npm install
   npm run build
   # Sync with S3 (see scripts/deploy-frontend.sh for details)
   ```

## 📂 Project Structure

- `app/`: Angular 19 frontend.
- `infrastructure/terraform/`: AWS infrastructure definitions.
    - `modules/`: Reusable modules for OpenSearch, Bedrock KB, API, and Frontend.
- `lambda/`: Python backend logic for the `/ask` endpoint.
- `legalize-es/`: The "Knowledge Base" — Spanish laws in Markdown format.
- `scripts/`: Utility scripts for deployment and maintenance.
- `posts/`: Technical articles and documentation related to the project's evolution.

## 🔧 Configuration

You can customize the RAG behavior in `infrastructure/terraform/variables.tf`:

| Variable | Description | Default |
|----------|-------------|---------|
| `chunking_strategy` | Strategy for splitting text (`SEMANTIC`, `HIERARCHICAL`, `FIXED_SIZE`) | `SEMANTIC` |
| `kb_model_id` | Bedrock Embedding model ID | `amazon.titan-embed-text-v2:0` |
| `generative_model_id` | Bedrock Foundation Model for answering | `amazon.nova-lite-v1:0` |
| `api_system_prompt` | The personality and constraints of the assistant | (Legal expert) |

## 🧪 Testing

### Local Lambda Testing
The `lambda/` directory contains scripts to test the handler logic without deploying to AWS:
```bash
cd lambda
pip install -r requirements.txt
python test_local.py
```

## 🗑️ Cleanup

To avoid ongoing AWS costs (especially for OpenSearch Serverless), destroy the infrastructure when finished:

```bash
./destroy.sh
```

## 🤝 Evolution Roadmap

This PoC is designed to be modified. Future posts will cover:
1. **Implementing Guardrails** to prevent hallucinations about non-Spanish laws.
2. **Adding a Semantic Cache** using Amazon ElastiCache or a local Redis.
3. **Evaluating Retrieval Quality** using RAGAS or similar frameworks.
