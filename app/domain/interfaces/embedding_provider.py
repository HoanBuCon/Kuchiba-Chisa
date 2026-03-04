from typing import Protocol, List


class IEmbeddingProvider(Protocol):
    """
    Domain adapter port for Vector Embeddings generation.
    All embedding implementations (OpenAI, FastEmbed, Cohere) must satisfy this interface.
    """

    async def embed_text(self, text: str) -> List[float]:
        """
        Embed a single string text into a vector of floats.
        """
        ...

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Embed a batch of strings into a list of vectors.
        """
        ...
