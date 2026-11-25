"""Service container: builds every long-lived service exactly once per process."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.db.session import Database
from app.services.chat_service import ChatService
from app.services.document_service import DocumentService
from app.services.embeddings import Embedder, SentenceTransformerEmbedder
from app.services.ingestion import IngestionService
from app.services.llm import LLMClient, OllamaClient
from app.services.rag import RagService
from app.services.retrieval import Retriever
from app.services.settings_service import SettingsService
from app.services.vector_store import ChromaVectorStore


@dataclass
class Container:
    settings: Settings
    db: Database
    embedder: Embedder
    store: ChromaVectorStore
    llm: LLMClient
    settings_service: SettingsService
    ingestion: IngestionService
    documents: DocumentService
    rag: RagService
    chat: ChatService

    async def aclose(self) -> None:
        self.ingestion.shutdown()
        await self.llm.aclose()
        self.db.dispose()


def build_container(
    settings: Settings,
    *,
    embedder: Embedder | None = None,
    llm: LLMClient | None = None,
    store: ChromaVectorStore | None = None,
) -> Container:
    """Wire services together. Tests inject fakes for the embedder / LLM / store."""
    settings.ensure_directories()
    db = Database(settings.resolved_database_url)
    db.create_all()

    embedder = embedder or SentenceTransformerEmbedder(
        settings.embedding_model,
        batch_size=settings.embedding_batch_size,
        query_instruction=settings.embedding_query_instruction,
        num_threads=settings.torch_num_threads,
    )
    store = store or ChromaVectorStore(settings.chroma_dir, settings.chroma_collection)
    llm = llm or OllamaClient(settings.ollama_base_url, timeout_s=settings.ollama_timeout_s)
    settings_service = SettingsService(settings)
    ingestion = IngestionService(
        db=db,
        settings=settings,
        settings_service=settings_service,
        embedder=embedder,
        store=store,
    )
    documents = DocumentService(db=db, settings=settings, store=store, ingestion=ingestion)
    rag = RagService(
        Retriever(embedder, store),
        llm,
        num_ctx=settings.ollama_num_ctx,
        num_thread=settings.ollama_num_thread,
        keep_alive=settings.ollama_keep_alive,
    )
    chat = ChatService(db=db, rag=rag, settings_service=settings_service)
    return Container(
        settings=settings,
        db=db,
        embedder=embedder,
        store=store,
        llm=llm,
        settings_service=settings_service,
        ingestion=ingestion,
        documents=documents,
        rag=rag,
        chat=chat,
    )
