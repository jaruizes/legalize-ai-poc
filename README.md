# Legalize ES - RAG API

PoC de un sistema RAG (Retrieval-Augmented Generation) para consultar la legislación española utilizando Qdrant como base de datos vectorial y FastAPI como framework web.

## 📋 Descripción

Este proyecto indexa documentos legales españoles en formato markdown (de la carpeta `legalize-es`) en una base de datos vectorial Qdrant y proporciona un API REST para realizar consultas sobre leyes españolas utilizando técnicas de RAG.

### Características

- **Indexación automática**: Al arrancar, el sistema indexa todos los documentos markdown de `legalize-es`
- **Búsqueda semántica**: Utiliza embeddings multilingües para búsqueda por similitud
- **Generación de respuestas**: Integración con OpenAI para generar respuestas contextualizadas
- **API REST**: Endpoint `/ask` para realizar preguntas sobre leyes españolas
- **Multi-región**: Soporta leyes estatales (es) y autonómicas (es-cm, es-an, etc.)

## 🏗️ Arquitectura

- **FastAPI**: Framework web para el API REST
- **Qdrant**: Base de datos vectorial para almacenamiento y búsqueda de embeddings
- **Sentence Transformers**: Modelo de embeddings multilingüe
- **LangChain**: Chunking y procesamiento de textos
- **OpenAI**: Generación de respuestas (opcional)

## 🚀 Instalación y Uso

### Prerrequisitos

- Docker y Docker Compose
- (Opcional) Clave de API de OpenAI para generación de respuestas mejoradas

### Configuración

1. Copia el archivo de ejemplo de variables de entorno:
   ```bash
   cp .env.example .env
   ```

2. Edita el archivo `.env` y configura las variables necesarias:
   ```env
   OPENAI_API_KEY=tu_clave_openai_aqui
   REINDEX_ON_STARTUP=true
   ```

### Ejecución con Docker Compose

```bash
# Levantar todos los servicios (Qdrant + API)
docker-compose up --build

# En modo detached (segundo plano)
docker-compose up -d --build
```

La API estará disponible en: `http://localhost:8000`

### Instalación local (sin Docker)

```bash
# Crear entorno virtual
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt

# Asegúrate de que Qdrant esté corriendo
docker run -p 6333:6333 qdrant/qdrant

# Ejecutar la aplicación
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## 📡 Endpoints del API

### `GET /`
Información general del API

### `GET /health`
Verificar estado del servicio

### `POST /ask`
Realizar una pregunta sobre leyes españolas

**Request:**
```json
{
  "question": "¿Qué dice la constitución sobre la educación?",
  "top_k": 5
}
```

**Response:**
```json
{
  "question": "¿Qué dice la constitución sobre la educación?",
  "answer": "Según la legislación española...",
  "sources": [
    {
      "titulo": "Constitución Española",
      "identificador": "BOE-A-1978-31229",
      "region": "es",
      "fuente": "https://www.boe.es/...",
      "score": 0.89
    }
  ]
}
```

### `POST /reindex`
Forzar reindexación manual de todos los documentos

## 🔧 Configuración Avanzada

### Variables de Entorno

| Variable | Descripción | Default |
|----------|-------------|---------|
| `QDRANT_HOST` | Host de Qdrant | `qdrant` |
| `QDRANT_PORT` | Puerto de Qdrant | `6333` |
| `QDRANT_COLLECTION_NAME` | Nombre de la colección | `legalize_es` |
| `OPENAI_API_KEY` | Clave API de OpenAI | - |
| `EMBEDDING_MODEL` | Modelo de embeddings | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` |
| `CHUNK_SIZE` | Tamaño de chunks de texto | `1000` |
| `CHUNK_OVERLAP` | Solapamiento entre chunks | `200` |
| `REINDEX_ON_STARTUP` | Reindexar al iniciar | `true` |

### Modo sin OpenAI

Si no proporcionas una clave de OpenAI, el sistema funcionará en modo "contexto únicamente", devolviendo los documentos relevantes sin generar una respuesta sintetizada.

## 📁 Estructura del Proyecto

```
.
├── app/
│   ├── __init__.py
│   ├── config.py          # Configuración y settings
│   ├── indexer.py         # Indexación de documentos
│   ├── rag.py             # Sistema RAG
│   └── main.py            # FastAPI application
├── legalize-es/           # Documentos legales en markdown
│   ├── es/                # Leyes estatales
│   ├── es-cm/             # Castilla La Mancha
│   ├── es-an/             # Andalucía
│   └── ...
├── docker-compose.yaml
├── Dockerfile
├── requirements.txt
├── .env.example
└── README.md
```

## 🧪 Ejemplos de Uso

### Con curl

```bash
# Realizar una pregunta
curl -X POST "http://localhost:8000/ask" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "¿Cuáles son los derechos fundamentales en España?",
    "top_k": 3
  }'

# Health check
curl http://localhost:8000/health

# Forzar reindexación
curl -X POST http://localhost:8000/reindex
```

### Con Python

```python
import requests

response = requests.post(
    "http://localhost:8000/ask",
    json={
        "question": "¿Qué normativa regula el teletrabajo?",
        "top_k": 5
    }
)

result = response.json()
print(f"Respuesta: {result['answer']}")
print(f"Fuentes: {len(result['sources'])} documentos")
```

## 📝 Notas

- La primera indexación puede tardar varios minutos dependiendo del número de documentos
- Los embeddings se generan usando CPU por defecto. Para mejor rendimiento, considera usar GPU
- El modelo de embeddings descarga automáticamente al primer uso (~400MB)

## 🤝 Contribuciones

Este es un proyecto PoC (Proof of Concept) para demostrar capacidades de AI sobre datos legales españoles.
