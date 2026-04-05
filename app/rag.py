import logging
from typing import List, Dict, Any
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from openai import OpenAI

from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RAGSystem:
    def __init__(self):
        self.client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
        self.embedding_model = SentenceTransformer(settings.embedding_model)
        self.collection_name = settings.qdrant_collection_name
        self.openai_client = OpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None
        
    def search_documents(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search for relevant documents in Qdrant."""
        try:
            # Generate query embedding
            query_embedding = self.embedding_model.encode(query).tolist()
            
            # Search in Qdrant
            search_results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                limit=limit
            )
            
            # Format results
            results = []
            for result in search_results:
                results.append({
                    "score": result.score,
                    "text": result.payload.get("text", ""),
                    "titulo": result.payload.get("titulo", ""),
                    "identificador": result.payload.get("identificador", ""),
                    "region": result.payload.get("region", ""),
                    "rango": result.payload.get("rango", ""),
                    "fecha_publicacion": result.payload.get("fecha_publicacion", ""),
                    "estado": result.payload.get("estado", ""),
                    "fuente": result.payload.get("fuente", ""),
                    "chunk_index": result.payload.get("chunk_index", 0),
                    "total_chunks": result.payload.get("total_chunks", 1)
                })
            
            return results
        except Exception as e:
            logger.error(f"Error searching documents: {e}")
            raise
    
    def generate_answer(self, query: str, context_docs: List[Dict[str, Any]]) -> str:
        """Generate an answer using OpenAI based on retrieved context."""
        if not self.openai_client:
            # If no OpenAI key, return the context
            return self._format_context_only(context_docs)
        
        try:
            # Build context from retrieved documents
            context = self._build_context(context_docs)
            
            # Create prompt
            system_prompt = """Eres un asistente legal experto en legislación española. 
Tu tarea es responder preguntas sobre leyes españolas basándote únicamente en el contexto proporcionado.
Si la información no está en el contexto, indícalo claramente.
Proporciona respuestas precisas, citando los artículos o secciones relevantes cuando sea posible."""

            user_prompt = f"""Contexto de leyes españolas:

{context}

Pregunta: {query}

Por favor, responde la pregunta basándote en el contexto proporcionado. Si la información no está disponible, indícalo claramente."""

            # Call OpenAI API
            response = self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=1000
            )
            
            answer = response.choices[0].message.content
            return answer
            
        except Exception as e:
            logger.error(f"Error generating answer: {e}")
            return self._format_context_only(context_docs)
    
    def _build_context(self, docs: List[Dict[str, Any]]) -> str:
        """Build context string from retrieved documents."""
        context_parts = []
        
        for i, doc in enumerate(docs, 1):
            context_parts.append(
                f"[{i}] {doc['titulo']} ({doc['identificador']})\n"
                f"Región: {doc['region']}, Rango: {doc['rango']}, "
                f"Fecha: {doc['fecha_publicacion']}, Estado: {doc['estado']}\n"
                f"Contenido: {doc['text']}\n"
                f"Fuente: {doc['fuente']}\n"
            )
        
        return "\n---\n".join(context_parts)
    
    def _format_context_only(self, docs: List[Dict[str, Any]]) -> str:
        """Format retrieved documents when OpenAI is not available."""
        if not docs:
            return "No se encontraron documentos relevantes para tu pregunta."
        
        response = "Documentos relevantes encontrados:\n\n"
        
        for i, doc in enumerate(docs, 1):
            response += f"{i}. **{doc['titulo']}** ({doc['identificador']})\n"
            response += f"   - Región: {doc['region']}\n"
            response += f"   - Rango: {doc['rango']}\n"
            response += f"   - Fecha de publicación: {doc['fecha_publicacion']}\n"
            response += f"   - Estado: {doc['estado']}\n"
            response += f"   - Relevancia: {doc['score']:.3f}\n"
            response += f"   - Extracto: {doc['text'][:300]}...\n"
            response += f"   - Fuente: {doc['fuente']}\n\n"
        
        return response
    
    def ask(self, question: str, top_k: int = 5) -> Dict[str, Any]:
        """Main method to answer a question using RAG."""
        logger.info(f"Processing question: {question}")
        
        # Search for relevant documents
        relevant_docs = self.search_documents(question, limit=top_k)
        
        if not relevant_docs:
            return {
                "question": question,
                "answer": "No se encontró información relevante en la base de datos de leyes españolas.",
                "sources": []
            }
        
        # Generate answer
        answer = self.generate_answer(question, relevant_docs)
        
        # Format sources
        sources = [
            {
                "titulo": doc["titulo"],
                "identificador": doc["identificador"],
                "region": doc["region"],
                "fuente": doc["fuente"],
                "score": doc["score"]
            }
            for doc in relevant_docs
        ]
        
        return {
            "question": question,
            "answer": answer,
            "sources": sources
        }
