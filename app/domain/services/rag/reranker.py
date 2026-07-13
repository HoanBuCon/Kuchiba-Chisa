import re
import math
import time
from typing import Any, List, Dict

class KeywordOverlapReranker:
    """
    Reranks candidate chunks by matching overlapping keyword tokens with synonym expansion.
    """
    def __init__(self):
        self.high_value_terms = {
            "honami", "sumika", "tacet", "vòng", "cổ", "vòng cổ", "startorch",
            "học viện", "broadblade", "kéo", "havoc", "overclock", "sonoro", "sphere",
            "nhật ký", "ký ức", "trà", "pocky", "mèo", "socola", "đam mê", "sở thích", "yêu thích", 
            "đặc biệt", "đáng nhớ", "trường học", "trường", "học sinh", "nữ sinh", "lahai-roi",
            "solaris-3", "ashinohara", "mutant", "resonator", "tuổi", "18 tuổi", "38 tuổi", "tiền bối", "quê quán",
            "linh hồn", "tần số", "cộng hưởng", "biến dị", "thiết bị", "vòng giới hạn", "giám sát",
            "nguy hiểm", "sụp đổ", "không gian", "lực lượng", "chủng tộc", "remnant"
        }
        
        self.synonyms = {
            "trường": ["học viện", "startorch", "trung học", "nữ sinh", "academy", "school", "startorch academy"],
            "học": ["theo học", "học viện", "học tập", "trường học"],
            "tuổi": ["tuổi sinh học", "tuổi thực tế", "18 tuổi", "38 tuổi", "năm sinh"],
            "quê": ["quê quán", "ashinohara", "nơi sinh", "sinh ra ở"],
            "sức mạnh": ["forte", "thread perception", "năng lực", "sức mạnh", "chiến đấu", "sức mạnh cộng hưởng", "biến dị"],
            "vũ khí": ["broadblade", "chiếc kéo", "kéo khổng lồ", "kiếm"],
            "tiền bối": ["sumika", "chị sumika", "tiền bối sumika"],
            "thích": ["sở thích", "đam mê", "yêu thích", "thích ăn", "thích ngắm", "thích mèo"],
            "ăn": ["ẩm thực", "ăn vặt", "socola", "pocky", "bánh quy", "ớt cay"],
            "chữa": ["trị liệu", "healer", "hỗ trợ", "phục hồi"],
            "nhật ký": ["di thư", "cuốn sổ", "ghi chép"],
            "năng lực": ["forte", "sức mạnh cộng hưởng", "cộng hưởng dị thường", "biến dị"],
            "vòng cổ": ["thiết bị giới hạn", "vòng giới hạn", "cái vòng ở cổ", "vòng resonance"],
            "sợ": ["nỗi sợ", "lo sợ", "lo ngại", "sợ hãi", "ám ảnh"],
            "yếu": ["điểm yếu", "overclock", "quá tải", "phản ứng kém", "cay"],
            "mèo": ["mèo con", "loài mèo", "chú mèo"],
            "kỷ niệm": ["ký ức", "kỷ niệm", "quá khứ", "ngắm hoa anh đào", "đèn lồng"],
            "anh đào": ["hoa anh đào", "anh đào rơi", "lễ hội"],
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
        candidate_words = re.findall(r"[\wÀ-ỹ]+", candidate_lower)
        hits = 0
        weighted_hits = 0.0

        # Separate unigrams (single words) to use as the denominator base
        unigrams = [t for t in query_tokens if " " not in t]

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
                # Check if token or any of its matched synonyms is a high value term
                is_high_value = token in self.high_value_terms
                if not is_high_value and token in self.synonyms:
                    for syn in self.synonyms[token]:
                        if syn in self.high_value_terms and syn in candidate_lower:
                            # Verify whole word for synonym if it's short
                            if " " in syn or len(syn) > 3 or syn in candidate_words:
                                is_high_value = True
                                break
                
                weighted_hits += 2.0 if is_high_value else 1.0

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
