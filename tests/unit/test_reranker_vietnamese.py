from app.domain.services.rag.reranker import KeywordOverlapReranker


def test_vietnamese_compound_word_tokenization():
    reranker = KeywordOverlapReranker()
    # Test query with compound Vietnamese terms
    query = "hãy kể về vòng cổ"
    tokens = reranker.tokenize(query)
    
    # Assert that it contains unigrams, bigrams and trigrams
    assert "vòng" in tokens
    assert "cổ" in tokens
    assert "vòng cổ" in tokens
    assert "kể về" in tokens
    assert "về vòng cổ" in tokens

def test_vietnamese_reranker_scoring():
    reranker = KeywordOverlapReranker()
    # High value terms include "vòng cổ", "nhật ký"
    query = "hãy kể về vòng cổ"
    query_tokens = reranker.tokenize(query)
    
    # Candidate text matches the high value term "vòng cổ"
    candidate_1 = "Chisa đeo một chiếc vòng cổ rất đẹp."
    score_1 = reranker.calculate_score(query_tokens, candidate_1)
    
    # Candidate text does NOT match the high value term
    candidate_2 = "Chisa đang đi dạo ở công viên."
    score_2 = reranker.calculate_score(query_tokens, candidate_2)
    
    assert score_1 > score_2
    assert score_1 > 0.0  # High-value compound term must produce a positive score.
    assert score_2 == 0.0
