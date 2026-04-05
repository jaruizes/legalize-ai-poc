from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Qdrant Configuration
    qdrant_host: str = "qdrant"
    qdrant_port: int = 6333
    qdrant_collection_name: str = "legalize_es"
    
    # OpenAI Configuration
    openai_api_key: str = ""
    
    # Embedding Model Configuration
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    
    # Indexing Configuration
    chunk_size: int = 1000
    chunk_overlap: int = 200
    
    # Application Configuration
    reindex_on_startup: bool = True
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
