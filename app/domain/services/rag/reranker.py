import math
import re
from pathlib import Path

import yaml

from app.shared.utils.logger import get_logger

log = get_logger(__name__)

class KeywordOverlapReranker:
    """
    Reranks candidate chunks by matching overlapping keyword tokens with synonym expansion.
    """
    def __init__(self):
        config_path = Path(__file__).parent / "reranker_config.yaml"
        self.high_value_terms = set()
        self.synonyms = {}
        try:
            if config_path.exists():
                with open(config_path, encoding="utf-8") as f:
                    config = yaml.safe_load(f)
                    if config:
                        self.high_value_terms = set(config.get("high_value_terms", []))
                        self.synonyms = config.get("synonyms", {})
            else:
                log.warning("reranker_config.yaml not found, using empty config", path=str(config_path))
        except Exception as e:
            log.error("Failed to load reranker config", error=str(e))

    def tokenize(self, text: str) -> list[str]:
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

    VI_STOP_WORDS = {
        "là", "gì", "trong", "và", "của", "nó", "như", "thế", "nào", "có",
        "được", "ra", "sao", "với", "cho", "em", "anh", "senpai", "vậy",
        "chisa", "hãy", "biết", "về", "các", "những", "một", "này", "đó",
        "ở", "tại", "tạo", "đến", "khi", "đang", "đã", "sẽ", "để", "thì"
    }

    def calculate_score(self, query_tokens: list[str], candidate_text: str) -> float:
        if not query_tokens or not candidate_text:
            return 0.0

        candidate_lower = candidate_text.lower()
        candidate_words = re.findall(r"[\wÀ-ỹ]+", candidate_lower)
        hits = 0
        weighted_hits = 0.0

        # Separate content tokens to use as a fair normalized denominator base
        content_tokens = [t for t in query_tokens if t not in self.VI_STOP_WORDS]
        if not content_tokens:
            return 0.0

        # Calculate dynamic max possible score based on query token weights
        max_possible = sum(
            2.0 if (t in self.high_value_terms or any(s in self.high_value_terms for s in self.synonyms.get(t, [])))
            else (1.5 if " " in t else 1.0)
            for t in content_tokens
        )
        denom = max(2.0, max_possible)

        for token in query_tokens:
            matched = False
            # 1. Direct match: check whole word/phrase to prevent short word substring collision
            if token in candidate_lower:
                if " " in token or len(token) > 3:
                    matched = True
                elif token in candidate_words:
                    matched = True

            # 2. Synonym match
            if not matched and token in self.synonyms:
                for syn in self.synonyms[token]:
                    if syn in candidate_lower:
                        if " " in syn or len(syn) > 3:
                            matched = True
                            break
                        elif syn in candidate_words:
                            matched = True
                            break
            
            if matched:
                hits += 1
                is_stop = token in self.VI_STOP_WORDS
                if not is_stop:
                    # Check if token or any of its matched synonyms is a high value term
                    is_high_value = token in self.high_value_terms
                    if not is_high_value and token in self.synonyms:
                        for syn in self.synonyms[token]:
                            if syn in self.high_value_terms and syn in candidate_lower:
                                if " " in syn or len(syn) > 3 or syn in candidate_words:
                                    is_high_value = True
                                    break
                    
                    if is_high_value:
                        weighted_hits += 2.0
                    elif " " in token:
                        weighted_hits += 1.5
                    else:
                        weighted_hits += 1.0

        if not hits or weighted_hits <= 0.0:
            return 0.0

        return min(1.0, weighted_hits / denom)


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

    def calculate_recency(
        self,
        created_at: int,
        now: int,
        importance: float = 0.7,
        memory_type: str = "user_fact",
        last_accessed_at: int | None = None
    ) -> float:
        """
        Adaptive Ebbinghaus Time-Decay Scoring:
        - Core permanent facts & nicknames (importance >= 0.85 or shared_story) decay very slowly (~140 days half-life).
        - Standard preferences/habits (0.65 <= importance < 0.85) decay moderately (~28 days half-life).
        - Fleeting/casual memories (importance < 0.65) decay quickly (~7 days half-life).
        - Spaced repetition: uses max(created_at, last_accessed_at) to reinforce recalled memories.
        """
        ref_time = max(created_at, last_accessed_at or created_at)
        age_seconds = max(0, now - ref_time)
        age_days = age_seconds / 86400.0

        if importance >= 0.85 or memory_type == "shared_story":
            adaptive_lambda = 0.005  # Half-life: ~138 days
        elif importance >= 0.65:
            adaptive_lambda = 0.025  # Half-life: ~28 days
        else:
            adaptive_lambda = 0.10   # Half-life: ~7 days

        return max(0.01, min(1.0, math.exp(-adaptive_lambda * age_days)))

    def calculate_emotion_match(
        self, memory_emotion: dict[str, float], current_emotion: dict[str, float]
    ) -> float:
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
