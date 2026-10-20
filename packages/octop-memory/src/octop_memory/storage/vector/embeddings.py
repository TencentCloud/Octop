"""Built-in EmbeddingProvider implementations, ready to use out of the box.

Supports three common embedding sources:

1. OpenAIEmbeddingProvider   -- OpenAI / any OpenAI-compatible endpoint
   Dependencies: none extra (uses stdlib urllib, consistent with LLMClient)
   Models: text-embedding-3-small (default, 1536 dims), text-embedding-3-large (3072 dims)

2. OllamaEmbeddingProvider   -- local Ollama service
   Dependencies: none extra (uses stdlib urllib)
   Models: nomic-embed-text (default, 768 dims), mxbai-embed-large (1024 dims), etc.

3. SentenceTransformerEmbeddingProvider -- local sentence-transformers
   Dependencies: pip install 'octop-memory[embeddings]'
   Models: all-MiniLM-L6-v2 (default, 384 dims), etc.

Usage example:
    from octop_memory.storage.vector.embeddings import OpenAIEmbeddingProvider
    from octop_memory.storage.vector.chroma import ChromaVectorIndex
    from octop_memory import Memory

    ep = OpenAIEmbeddingProvider(api_key="sk-...")
    idx = ChromaVectorIndex("my_agent")
    idx.ensure_collection(ep.vector_size)

    mem = Memory("my_agent", vector_index=idx, embedding_provider=ep)
    mem.store("Finished phase one of the project", topic="Project A")
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, ClassVar

try:
    from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]

    _ST_AVAILABLE = True
except ImportError:
    _ST_AVAILABLE = False


# ---------------------------------------------------------------------------
# 1. OpenAI / OpenAI-compatible endpoints
# ---------------------------------------------------------------------------


class OpenAIEmbeddingProvider:
    """OpenAI text-embedding endpoint; also supports any OpenAI-compatible embedding service.

    Args:
        api_key: OpenAI API key. Can also be set via the OPENAI_API_KEY environment variable.
        model: embedding model name.
            - "text-embedding-3-small"  -> 1536 dims (default, best cost/performance)
            - "text-embedding-3-large"  -> 3072 dims (higher accuracy)
            - "text-embedding-ada-002"  -> 1536 dims (legacy)
        base_url: API base URL. Defaults to the official OpenAI endpoint.
            Compatible-endpoint examples:
            - Azure OpenAI: "https://<resource>.openai.azure.com/openai"
            - Local proxy: "http://localhost:8080/v1"
        timeout: request timeout in seconds, default 10.

    Example:
        # Official OpenAI
        ep = OpenAIEmbeddingProvider(api_key="sk-...")

        # OpenAI-compatible endpoint (e.g. DeepSeek, Moonshot, etc.)
        ep = OpenAIEmbeddingProvider(
            api_key="your-key",
            model="your-embed-model",
            base_url="https://api.deepseek.com/v1",
        )
    """

    _VECTOR_SIZES: ClassVar[dict[str, int]] = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
    }

    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str = "text-embedding-3-small",
        base_url: str = "https://api.openai.com/v1",
        timeout: int = 10,
    ) -> None:
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "OpenAIEmbeddingProvider requires an api_key.\n"
                "Pass it explicitly: OpenAIEmbeddingProvider(api_key='sk-...')\n"
                "Or set the environment variable: export OPENAI_API_KEY=sk-..."
            )
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    @property
    def vector_size(self) -> int:
        """Return the vector dimension. Defaults to 1536 for unknown models."""
        return self._VECTOR_SIZES.get(self._model, 1536)

    def embed(self, text: str) -> list[float]:
        """Call the OpenAI embeddings API and return the vector."""
        url = f"{self._base_url}/embeddings"
        body = json.dumps({"input": text, "model": self._model}).encode()
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            data: dict[str, Any] = json.loads(resp.read())
        return list(data["data"][0]["embedding"])

    def __repr__(self) -> str:
        return f"OpenAIEmbeddingProvider(model={self._model!r}, base_url={self._base_url!r})"


# ---------------------------------------------------------------------------
# 2. Local Ollama service
# ---------------------------------------------------------------------------


class OllamaEmbeddingProvider:
    """Local Ollama embedding service, no API key needed, fully offline.

    Prerequisite: `ollama serve` is already running locally with the target model pulled.

    Args:
        model: Ollama embedding model name.
            - "nomic-embed-text"    -> 768 dims (default, good overall performance)
            - "mxbai-embed-large"   -> 1024 dims (higher accuracy)
            - "all-minilm"          -> 384 dims (fastest)
        host: Ollama service address, default http://localhost:11434.
        timeout: request timeout in seconds, default 30 (local inference can be slower).

    Example:
        # Pull the model first: ollama pull nomic-embed-text
        ep = OllamaEmbeddingProvider()
        ep = OllamaEmbeddingProvider(model="mxbai-embed-large")
    """

    _VECTOR_SIZES: ClassVar[dict[str, int]] = {
        "nomic-embed-text": 768,
        "mxbai-embed-large": 1024,
        "all-minilm": 384,
    }

    def __init__(
        self,
        model: str = "nomic-embed-text",
        *,
        host: str = "http://localhost:11434",
        timeout: int = 30,
    ) -> None:
        self._model = model
        self._host = host.rstrip("/")
        self._timeout = timeout

    @property
    def vector_size(self) -> int:
        """Return the vector dimension. Defaults to 768 for unknown models."""
        return self._VECTOR_SIZES.get(self._model, 768)

    def embed(self, text: str) -> list[float]:
        """Call the Ollama /api/embeddings endpoint and return the vector."""
        url = f"{self._host}/api/embeddings"
        body = json.dumps({"model": self._model, "prompt": text}).encode()
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            data: dict[str, Any] = json.loads(resp.read())
        return list(data["embedding"])

    def __repr__(self) -> str:
        return f"OllamaEmbeddingProvider(model={self._model!r}, host={self._host!r})"


# ---------------------------------------------------------------------------
# 3. sentence-transformers (local, no network dependency)
# ---------------------------------------------------------------------------


class SentenceTransformerEmbeddingProvider:
    """Local sentence-transformers model, fully offline, no API key needed.

    Dependency: pip install 'octop-memory[embeddings]'
    (i.e. the sentence-transformers package)

    Args:
        model: model name or local path.
            - "all-MiniLM-L6-v2"        -> 384 dims (default, fast, English-focused)
            - "paraphrase-multilingual-MiniLM-L12-v2" -> 384 dims (multilingual, incl. Chinese)
            - "BAAI/bge-small-zh-v1.5"  -> 512 dims (Chinese-specialized, good performance)
        device: device to run on, "cpu" (default) or "cuda" (GPU acceleration).

    Example:
        # English-focused
        ep = SentenceTransformerEmbeddingProvider()

        # Recommended for Chinese scenarios
        ep = SentenceTransformerEmbeddingProvider(
            model="paraphrase-multilingual-MiniLM-L12-v2"
        )
    """

    _VECTOR_SIZES: ClassVar[dict[str, int]] = {
        "all-MiniLM-L6-v2": 384,
        "paraphrase-multilingual-MiniLM-L12-v2": 384,
        "BAAI/bge-small-zh-v1.5": 512,
        "BAAI/bge-base-zh-v1.5": 768,
        "BAAI/bge-large-zh-v1.5": 1024,
    }

    def __init__(
        self,
        model: str = "all-MiniLM-L6-v2",
        *,
        device: str = "cpu",
    ) -> None:
        if not _ST_AVAILABLE:
            raise ImportError(
                "SentenceTransformerEmbeddingProvider requires sentence-transformers to be installed.\n"
                "Please run: pip install 'octop-memory[embeddings]'"
            )
        self._model_name = model
        self._model = SentenceTransformer(model, device=device)

    @property
    def vector_size(self) -> int:
        """Return the vector dimension. Looks up the table first, falls back to the model object."""
        if self._model_name in self._VECTOR_SIZES:
            return self._VECTOR_SIZES[self._model_name]
        # Fetch dynamically from the model object
        dim: int = self._model.get_sentence_embedding_dimension() or 384
        return dim

    def embed(self, text: str) -> list[float]:
        """Run local inference and return the vector."""
        vec = self._model.encode(text, convert_to_numpy=True)
        return list(vec.tolist())

    def __repr__(self) -> str:
        return f"SentenceTransformerEmbeddingProvider(model={self._model_name!r})"


__all__ = [
    "OllamaEmbeddingProvider",
    "OpenAIEmbeddingProvider",
    "SentenceTransformerEmbeddingProvider",
]
