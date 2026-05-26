"""
app/services/rag_service.py — Bloque 3.1 / actualizado Bloque 3.3

Bloque 3.3 — Cambios:
  - Ya no instancia ChatOpenAI directamente.
  - Usa get_llm() de app.core.llm_provider.
  - Los embeddings siguen usando OpenAIEmbeddings por ahora (FAISS requiere
    vectores compatibles; en un futuro bloque se puede agregar soporte
    multi-embedding).
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_openai import OpenAIEmbeddings

from app.config import settings
from app.core.llm_provider import get_llm   # ← Bloque 3.3

logger = logging.getLogger(__name__)

# ── Configuración ─────────────────────────────────────────────────────────────
CHUNK_SIZE = 1000          # caracteres por chunk
CHUNK_OVERLAP = 150        # solapamiento entre chunks
TOP_K = 4                  # chunks recuperados por pregunta
HISTORY_WINDOW = 6         # últimos N turnos de historial (N mensajes user+asistente)
VECTOR_STORE_DIR = Path(os.getenv("VECTOR_STORE_DIR", "./vector_stores"))

SYSTEM_PROMPT = """Sos un asistente experto en análisis de documentos.
Respondés preguntas basándote ÚNICAMENTE en el contenido del documento proporcionado.
Si la información no está en el documento, decí "No encontré esa información en el documento."
Respondé en el mismo idioma de la pregunta del usuario.
Sé preciso, conciso y cita los fragmentos relevantes cuando sea útil."""


class RAGService:
    """
    Servicio stateless de RAG. Cada método recibe todos los datos necesarios.
    Los índices FAISS se cargan/crean bajo demanda y se cachean en memoria
    durante la vida del proceso (diccionario de clase).
    """

    _index_cache: Dict[int, FAISS] = {}   # doc_id → FAISS index (cache en memoria)

    def __init__(self):
        self.embeddings = OpenAIEmbeddings(
            api_key=settings.OPENAI_API_KEY,
            model="text-embedding-3-small",   # más barato y suficientemente preciso
        )
        # Bloque 3.3: LLM resuelto desde .env
        self.llm = get_llm(temperature=0.2, max_tokens=1000)
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    # ─── Índice FAISS ─────────────────────────────────────────────────────────

    def _index_path(self, doc_id: int) -> Path:
        return VECTOR_STORE_DIR / str(doc_id)

    def _index_exists(self, doc_id: int) -> bool:
        p = self._index_path(doc_id)
        return (p / "index.faiss").exists() and (p / "index.pkl").exists()

    def _load_index(self, doc_id: int) -> Optional[FAISS]:
        """Carga índice desde disco. Retorna None si no existe."""
        if doc_id in self._index_cache:
            return self._index_cache[doc_id]

        if not self._index_exists(doc_id):
            return None

        try:
            index = FAISS.load_local(
                str(self._index_path(doc_id)),
                self.embeddings,
                allow_dangerous_deserialization=True,  # archivos propios, es seguro
            )
            self._index_cache[doc_id] = index
            logger.info(f"FAISS index cargado desde disco — doc_id={doc_id}")
            return index
        except Exception as e:
            logger.error(f"Error cargando FAISS index para doc_id={doc_id}: {e}")
            return None

    def _build_index(self, doc_id: int, text: str) -> FAISS:
        """
        Divide el texto en chunks, genera embeddings y construye el índice FAISS.
        Persiste el índice en disco para no reconstruirlo en cada sesión.
        """
        logger.info(f"Construyendo FAISS index — doc_id={doc_id} ({len(text)} chars)")

        chunks = self.splitter.split_text(text)
        if not chunks:
            raise ValueError(f"El documento {doc_id} no tiene texto para indexar.")

        # Metadata por chunk (número de chunk para tracing)
        metadatas = [{"chunk": i, "doc_id": doc_id} for i in range(len(chunks))]

        index = FAISS.from_texts(chunks, self.embeddings, metadatas=metadatas)

        # Persistir en disco
        index_dir = self._index_path(doc_id)
        index_dir.mkdir(parents=True, exist_ok=True)
        index.save_local(str(index_dir))

        self._index_cache[doc_id] = index
        logger.info(f"FAISS index guardado — doc_id={doc_id} | chunks={len(chunks)}")
        return index

    def get_or_build_index(self, doc_id: int, text: str) -> FAISS:
        """
        Retorna el índice existente (memoria o disco) o lo construye si no existe.
        """
        index = self._load_index(doc_id)
        if index is None:
            index = self._build_index(doc_id, text)
        return index

    def invalidate_index(self, doc_id: int) -> None:
        """
        Elimina el índice de memoria y disco.
        Llamar al eliminar o re-procesar un documento.
        """
        self._index_cache.pop(doc_id, None)
        index_dir = self._index_path(doc_id)
        if index_dir.exists():
            import shutil
            shutil.rmtree(index_dir)
            logger.info(f"FAISS index eliminado — doc_id={doc_id}")

    # ─── Chat ─────────────────────────────────────────────────────────────────

    def _build_history_messages(
        self, history: List[Dict[str, str]]
    ) -> List:
        """
        Convierte historial [{role, content}] a mensajes LangChain.
        Limita a los últimos HISTORY_WINDOW mensajes para no saturar el contexto.
        """
        messages = []
        # Tomar solo los últimos N mensajes
        recent = history[-HISTORY_WINDOW:] if len(history) > HISTORY_WINDOW else history
        for msg in recent:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                messages.append(AIMessage(content=msg["content"]))
        return messages

    def _retrieve_chunks(
        self, index: FAISS, question: str
    ) -> Tuple[str, List[Dict]]:
        """
        Recupera los TOP_K chunks más relevantes para la pregunta.
        Retorna (contexto_concatenado, lista_de_sources).
        """
        docs = index.similarity_search(question, k=TOP_K)
        context_parts = []
        sources = []

        for i, doc in enumerate(docs):
            context_parts.append(f"[Fragmento {i+1}]\n{doc.page_content}")
            sources.append({
                "content": doc.page_content[:300],   # snippet para la UI
                "page": doc.metadata.get("chunk"),
            })

        context = "\n\n".join(context_parts)
        return context, sources

    async def chat(
        self,
        doc_id: int,
        doc_text: str,
        question: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """
        Genera una respuesta a `question` basándose en el documento indexado.

        Args:
            doc_id:   ID del documento.
            doc_text: Texto completo extraído del documento.
            question: Pregunta del usuario.
            history:  Lista de mensajes previos [{role, content}].

        Returns:
            Dict con keys: answer (str), sources (list).
        """
        history = history or []

        # 1. Obtener / construir índice FAISS
        index = self.get_or_build_index(doc_id, doc_text)

        # 2. Recuperar chunks relevantes
        context, sources = self._retrieve_chunks(index, question)

        # 3. Construir prompt con contexto + historial
        messages = [SystemMessage(content=SYSTEM_PROMPT)]
        messages.extend(self._build_history_messages(history))
        messages.append(
            HumanMessage(
                content=(
                    f"Contexto del documento:\n{context}\n\n"
                    f"Pregunta: {question}"
                )
            )
        )

        # 4. Invocar LLM
        response = await self.llm.ainvoke(messages)
        answer = response.content.strip()

        logger.info(
            f"RAG chat — doc_id={doc_id} | "
            f"chunks_usados={len(sources)} | "
            f"respuesta_len={len(answer)}"
        )

        return {"answer": answer, "sources": sources}


# Singleton — se reutiliza el mismo objeto (y su cache en memoria) por proceso
rag_service = RAGService()
