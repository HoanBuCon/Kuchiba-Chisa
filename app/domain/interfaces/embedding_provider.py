from typing import Protocol, List


class IEmbeddingProvider(Protocol):
    """
    Domain adapter port for Vector Embeddings generation.
    All embedding implementations (OpenAI, FastEmbed, Cohere) must satisfy this interface.
    """

    @property
    def model_name(self) -> str:
        """The name of the embedding model (e.g., 'bge-small-en-v1.5')."""
        ...
        
    @property
    def dimension(self) -> int:
        """The output dimension of the embeddings (e.g., 384)."""
        ...
        
    @property
    def version(self) -> str:
        """The current version of this embedding implementation."""
        ...

    async def embed_text(self, text: str, prefix: str = "query: ") -> List[float]:
        """
        Embed a single string text into a vector of floats with optional E5 prefix ('query: ' or 'passage: ').
        """
        ...

    async def embed_batch(self, texts: List[str], prefix: str = "query: ") -> List[List[float]]:
        """
        Embed a batch of strings into a list of vectors with optional E5 prefix ('query: ' or 'passage: ').
        """
        ...
