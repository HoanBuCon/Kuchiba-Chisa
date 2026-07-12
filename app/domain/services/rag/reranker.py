import re
import math
import time
from typing import Any, List, Dict

class KeywordOverlapReranker:
    """
    Reranks candidate chunks by matching overlapping keyword tokens.
    """
    def __init__(self):
        self.high_value_terms = {
            "honami", "sumika", "tacet", "vòng", "cổ", "vòng cổ", "startorch",
            "học viện", "broadblade", "kéo", "havoc", "overclock", "sonoro", "sphere",
            "nhật ký", "ký ức", "trà", "pocky", "mèo", "socola", "đam mê", "sở thích", "yêu thích", "đặc biệt", "đáng nhớ"
        }

    def tokenize(self, text: str) -> List[str]:
        if not text:
            return []
        words = re.findall(r"[\wÀ-ỹ]+", text.lower())
        tokens = [w for w in words if len(w) >= 2]
        
        # Generate bigrams and trigrams for compound Vietnamese words
        n = len(words)
        bigrams = [" ".join(words[i:i+2]) for i in range(n-1)]
        trigrams = [" ".join(words[i:i+3]) for i in range(n-2)]
        
        all_tokens = tokens + bigrams + trigrams
        return [t for t in all_tokens if len(t) >= 2]

    def calculate_score(self, query_tokens: List[str], candidate_text: str) -> float:
        if not query_tokens or not candidate_text:
            return 0.0

        candidate_lower = candidate_text.lower()
        hits = 0
        weighted_hits = 0.0

        # Separate unigrams (single words) to use as the denominator base
        unigrams = [t for t in query_tokens if " " not in t]

        for token in query_tokens:
            if token in candidate_lower:
                hits += 1
                weighted_hits += 2.0 if token in self.high_value_terms else 1.0

        if not hits:
            return 0.0

        # Prevent denominator inflation from bigrams/trigrams by using unigrams count
        return min(1.0, weighted_hits / max(4.0, len(unigrams)))


class HybridMemoryScorer:
    """
    Calculates unified hybrid scoring for user memories based on vector similarity, recency decay,
    importance scaling, and emotion resonance.
    """
    def __init__(
        self,
        w_similarity: float = 0.60,
        w_recency: float = 0.20,
        w_importance: float = 0.15,
        w_emotion: float = 0.05,
        decay_lambda: float = 0.05
    ):
        self.W_SIMILARITY = w_similarity
        self.W_RECENCY = w_recency
        self.W_IMPORTANCE = w_importance
        self.W_EMOTION = w_emotion
        self.DECAY_LAMBDA = decay_lambda

    def calculate_recency(self, created_at: int, now: int) -> float:
        age_seconds = max(0, now - created_at)
        age_days = age_seconds / 86400.0
        return math.exp(-self.DECAY_LAMBDA * age_days)

    def calculate_emotion_match(self, memory_emotion: Dict[str, float], current_emotion: Dict[str, float]) -> float:
        if not memory_emotion or not current_emotion:
            return 0.5

        score = 0.0
        keys = set(memory_emotion.keys()).intersection(current_emotion.keys())
        if not keys:
            return 0.5

        for k in keys:
            diff = abs(memory_emotion[k] - current_emotion.get(k, 0.0))
            score += max(0.0, 1.0 - diff)

        return score / len(keys)

    def calculate_final_score(
        self,
        similarity: float,
        recency: float,
        importance: float,
        emotion_match: float
    ) -> float:
        return (
            (similarity * self.W_SIMILARITY) +
            (recency * self.W_RECENCY) +
            (importance * self.W_IMPORTANCE) +
            (emotion_match * self.W_EMOTION)
        )
