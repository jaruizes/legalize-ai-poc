import os
import logging
from pathlib import Path
from typing import List, Dict, Any
import frontmatter
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer
from langchain.text_splitter import RecursiveCharacterTextSplitter

from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DocumentIndexer:
    def __init__(self):
        self.client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
        self.embedding_model = SentenceTransformer(settings.embedding_model)
        self.collection_name = settings.qdrant_collection_name
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
        
    def initialize_collection(self):
        """Create or recreate the Qdrant collection."""
        try:
            # Get embedding dimension
            sample_embedding = self.embedding_model.encode(["test"])
            vector_size = len(sample_embedding[0])
            
            # Check if collection exists
            collections = self.client.get_collections().collections
            collection_names = [col.name for col in collections]
            
            if self.collection_name in collection_names:
                logger.info(f"Collection '{self.collection_name}' already exists. Deleting...")
                self.client.delete_collection(self.collection_name)
            
            # Create collection
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE)
            )
            logger.info(f"Collection '{self.collection_name}' created successfully.")
        except Exception as e:
            logger.error(f"Error initializing collection: {e}")
            raise
    
    def read_markdown_files(self, base_path: str) -> List[Dict[str, Any]]:
        """Read all markdown files from legalize-es directory."""
        documents = []
        base_path = Path(base_path)
        
        if not base_path.exists():
            logger.error(f"Path {base_path} does not exist")
            return documents
        
        # Iterate through all subdirectories (es, es-cm, es-an, etc.)
        for region_dir in base_path.iterdir():
            if region_dir.is_dir():
                logger.info(f"Processing directory: {region_dir.name}")
                md_files = list(region_dir.glob("*.md"))
                
                for md_file in md_files:
                    try:
                        with open(md_file, 'r', encoding='utf-8') as f:
                            post = frontmatter.load(f)
                            
                        documents.append({
                            "content": post.content,
                            "metadata": {
                                "titulo": post.get("titulo", ""),
                                "identificador": post.get("identificador", ""),
                                "pais": post.get("pais", ""),
                                "region": region_dir.name,
                                "rango": post.get("rango", ""),
                                "fecha_publicacion": post.get("fecha_publicacion", ""),
                                "ultima_actualizacion": post.get("ultima_actualizacion", ""),
                                "estado": post.get("estado", ""),
                                "fuente": post.get("fuente", ""),
                                "file_path": str(md_file)
                            }
                        })
                    except Exception as e:
                        logger.error(f"Error reading file {md_file}: {e}")
                
                logger.info(f"Processed {len(md_files)} files from {region_dir.name}")
        
        logger.info(f"Total documents read: {len(documents)}")
        return documents
    
    def chunk_and_index_documents(self, documents: List[Dict[str, Any]]):
        """Chunk documents and index them in Qdrant."""
        logger.info("Starting document chunking and indexing...")
        
        points = []
        point_id = 0
        
        for doc in documents:
            # Chunk the document content
            chunks = self.text_splitter.split_text(doc["content"])
            
            for chunk_idx, chunk in enumerate(chunks):
                # Create enhanced text for embedding (includes title for better context)
                enhanced_text = f"{doc['metadata']['titulo']}\n\n{chunk}"
                
                # Generate embedding
                embedding = self.embedding_model.encode(enhanced_text).tolist()
                
                # Prepare metadata for this chunk
                chunk_metadata = doc["metadata"].copy()
                chunk_metadata["chunk_index"] = chunk_idx
                chunk_metadata["total_chunks"] = len(chunks)
                chunk_metadata["text"] = chunk
                
                # Create point
                point = PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload=chunk_metadata
                )
                points.append(point)
                point_id += 1
                
                # Upload in batches of 100
                if len(points) >= 100:
                    self.client.upsert(
                        collection_name=self.collection_name,
                        points=points
                    )
                    logger.info(f"Uploaded batch of {len(points)} points. Total: {point_id}")
                    points = []
        
        # Upload remaining points
        if points:
            self.client.upsert(
                collection_name=self.collection_name,
                points=points
            )
            logger.info(f"Uploaded final batch of {len(points)} points. Total: {point_id}")
        
        logger.info(f"Indexing complete! Total chunks indexed: {point_id}")
    
    def index_all(self):
        """Main method to index all documents."""
        logger.info("Starting indexing process...")
        
        # Initialize collection
        self.initialize_collection()
        
        # Read all markdown files
        documents = self.read_markdown_files("legalize-es")
        
        if not documents:
            logger.warning("No documents found to index!")
            return
        
        # Chunk and index
        self.chunk_and_index_documents(documents)
        
        logger.info("Indexing process completed successfully!")


if __name__ == "__main__":
    indexer = DocumentIndexer()
    indexer.index_all()
