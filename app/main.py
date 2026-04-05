import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any

from app.config import settings
from app.indexer import DocumentIndexer
from app.rag import RAGSystem

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global RAG system instance
rag_system = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    global rag_system
    
    logger.info("Starting application...")
    
    # Initialize RAG system
    rag_system = RAGSystem()
    
    # Index documents on startup if configured
    if settings.reindex_on_startup:
        logger.info("Reindexing documents on startup...")
        try:
            indexer = DocumentIndexer()
            indexer.index_all()
            logger.info("Indexing completed successfully!")
        except Exception as e:
            logger.error(f"Error during indexing: {e}")
            logger.warning("Continuing without reindexing...")
    
    logger.info("Application ready!")
    
    yield
    
    # Shutdown
    logger.info("Shutting down application...")


app = FastAPI(
    title="Legalize ES RAG API",
    description="API para consultar leyes españolas usando RAG (Retrieval-Augmented Generation)",
    version="1.0.0",
    lifespan=lifespan
)


class AskRequest(BaseModel):
    question: str
    top_k: int = 5


class Source(BaseModel):
    titulo: str
    identificador: str
    region: str
    fuente: str
    score: float


class AskResponse(BaseModel):
    question: str
    answer: str
    sources: List[Source]


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "Legalize ES RAG API",
        "description": "API para consultar leyes españolas",
        "endpoints": {
            "/ask": "POST - Hacer una pregunta sobre leyes españolas",
            "/health": "GET - Verificar el estado de la API"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "qdrant_host": settings.qdrant_host,
        "qdrant_port": settings.qdrant_port,
        "collection_name": settings.qdrant_collection_name
    }


@app.post("/ask", response_model=AskResponse)
async def ask_question(request: AskRequest):
    """
    Endpoint para hacer preguntas sobre leyes españolas.
    
    Args:
        request: Objeto con la pregunta y el número de documentos a recuperar (top_k)
    
    Returns:
        Respuesta con la pregunta, respuesta generada y fuentes utilizadas
    """
    global rag_system
    
    if not rag_system:
        raise HTTPException(status_code=503, detail="RAG system not initialized")
    
    if not request.question or not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    
    try:
        result = rag_system.ask(request.question, top_k=request.top_k)
        return result
    except Exception as e:
        logger.error(f"Error processing question: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing question: {str(e)}")


@app.post("/reindex")
async def trigger_reindex():
    """
    Endpoint para forzar la reindexación de todos los documentos.
    Útil para actualizar el índice sin reiniciar la aplicación.
    """
    try:
        logger.info("Manual reindex triggered...")
        indexer = DocumentIndexer()
        indexer.index_all()
        return {"status": "success", "message": "Reindexing completed successfully"}
    except Exception as e:
        logger.error(f"Error during manual reindex: {e}")
        raise HTTPException(status_code=500, detail=f"Error during reindexing: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
