import math
import uuid
from collections.abc import Callable
from typing import Any

from app.domain.interfaces.repositories import ILoreParentRepository
from app.domain.interfaces.reranker import (
    ICrossEncoderReranker,
    RerankerDataBoundary,
    RerankerFailureKind,
    RerankerUnavailableError,
)
from app.domain.interfaces.vector_store import IVectorStore
from app.domain.services.rag.deterministic_reranker_fallback import (
    DeterministicRerankerFallback,
)
from app.domain.services.rag.reranker import KeywordOverlapReranker
from app.domain.tuning.rag import RAGTuning
from app.shared.utils.logger import get_logger
from app.shared.utils.token_estimator import TokenEstimator

log = get_logger(__name__)


class LoreRetriever:
    """
    Retrieves Chisa lore chunks from Qdrant using vector search,
    boosted by keyword overlap re-ranking and Windowed Parent Resolution.
    """
    def __init__(
        self, 
        vector_store: IVectorStore, 
        reranker: KeywordOverlapReranker | None = None,
        lore_parent_repo_factory: Callable[[Any], ILoreParentRepository] | None = None,
        cross_encoder_reranker: ICrossEncoderReranker | None = None,
    ):
        self.vector_store = vector_store
        self.reranker = reranker or KeywordOverlapReranker()
        self.lore_parent_repo_factory = lore_parent_repo_factory
        self.cross_encoder_reranker = cross_encoder_reranker
        self._cross_encoder_fallback = DeterministicRerankerFallback()

    @staticmethod
    def resolve_windowed_parent(
        parent_markdown: str | None, child_text: str, window_chars: int = 1200
    ) -> str:
        """
        Extracts a localized context window around child_text instead of loading the entire parent markdown.
        Preserves Markdown Section Headers and prevents Parent Document Bloat.
        """
        if not parent_markdown:
            return child_text
        if not child_text:
            return parent_markdown[:window_chars].strip()

        # Extract top-level section header if present
        header_line = ""
        for line in parent_markdown.splitlines():
            s_line = line.strip()
            if s_line.startswith("#"):
                header_line = s_line
                break

        # If parent markdown is already compact, use it directly
        if len(parent_markdown) <= window_chars:
            return parent_markdown.strip()

        # Clean child text by stripping metadata prefixes if present
        clean_child = child_text.strip()
        if clean_child.startswith("[") and "\n" in clean_child:
            clean_child = clean_child.split("\n", 1)[-1].strip()

        # Multi-resolution substring search
        pos = -1
        for sample_len in (80, 50, 30, 20):
            if len(clean_child) >= sample_len:
                pos = parent_markdown.find(clean_child[:sample_len])
                if pos != -1:
                    break

        if pos == -1:
            # Fallback: return child text prefixed with section header if missing
            if header_line and header_line not in child_text:
                return f"{header_line}\n{child_text}".strip()
            return child_text

        # Calculate balanced window without blowing up size
        child_len = min(len(clean_child), len(parent_markdown) - pos)
        extra_budget = max(0, window_chars - child_len)
        half_extra = extra_budget // 2

        start = max(0, pos - half_extra)
        end = min(len(parent_markdown), pos + child_len + half_extra)

        # Align start boundary to newline or sentence if close
        if start > 0:
            prev_nl = parent_markdown.rfind("\n", 0, start)
            if prev_nl != -1 and (start - prev_nl) < 150:
                start = prev_nl + 1

        # Align end boundary to newline if close
        if end < len(parent_markdown):
            next_nl = parent_markdown.find("\n", end)
            if next_nl != -1 and (next_nl - end) < 150:
                end = next_nl

        snippet = parent_markdown[start:end].strip()

        prefix = "... " if start > 0 else ""
        suffix = " ..." if end < len(parent_markdown) else ""

        # Ensure section header is always attached if window starts mid-document
        if start > 0 and header_line and header_line not in snippet:
            return f"{header_line}\n{prefix}{snippet}{suffix}"
        return f"{prefix}{snippet}{suffix}"

    async def retrieve_lore_parent_child(
        self,
        collection: str,
        query_vector: list[float],
        session: Any = None,
        query_text: str = "",
        top_k: int = RAGTuning.TOP_K,
        score_threshold: float = RAGTuning.SCORE_THRESHOLD,
        entities_filter: list[str] | None = None,
        requester_subject_id: str | None = None,
        requester_tenant_id: str | None = None,
        requester_channel_id: str | None = None,
        max_token_budget: int | None = None,
        enable_cross_encoder_rerank: bool = True,
    ) -> list[tuple[str, float, dict[str, Any]]]:
        try:
            if not self.vector_store:
                return []
                
            candidates = await self.vector_store.search_lore(
                collection=collection,
                query_vector=query_vector,
                query_text=query_text,
                limit=15,
                score_threshold=score_threshold,
                entities_filter=entities_filter,
                requester_subject_id=requester_subject_id,
                requester_tenant_id=requester_tenant_id,
                requester_channel_id=requester_channel_id,
            )
        except Exception as e:
            log.warning("Lore parent-child retrieval failed", collection=collection, error=str(e))
            return []

        query_tokens = self.reranker.tokenize(query_text)
        filter_set = set(entities_filter) if entities_filter else set()
        scored_candidates = []
        
        for cand in candidates:
            payload = cand.get("payload", {})
            child_text = payload.get("text_content", "")
            score = cand.get("score", 0.0)
            if child_text:
                # 1. Text Keyword Overlap Score
                keyword_score = self.reranker.calculate_score(query_tokens, child_text)
                
                # 2. Metadata Overlap & Entity Alignment Score
                canon_name = payload.get("canonical_name") or ""
                heading = payload.get("heading_path") or ""
                meta_text = f"{canon_name} {heading}".strip()
                heading_score = self.reranker.calculate_score(query_tokens, meta_text) if meta_text else 0.0
                
                chunk_entities = payload.get("entities") or []
                entity_hit = 1.0 if (filter_set and (any(e in filter_set for e in chunk_entities) or canon_name in filter_set)) else 0.0
                metadata_score = (heading_score * 0.5) + (entity_hit * 0.5)
                
                # 3. Unified Multi-Signal Hybrid Score
                hybrid_score = (
                    (score * RAGTuning.WEIGHT_VECTOR) +
                    (keyword_score * RAGTuning.WEIGHT_KEYWORD) +
                    (metadata_score * RAGTuning.WEIGHT_METADATA)
                )
                
                dense_score = cand.get("dense_score")
                sparse_score = cand.get("sparse_score")
                scoring_meta = {
                    "collection": collection,
                    "point_id": str(cand.get("id", "")),
                    "source_type": payload.get("source_type", "wiki"),
                    "parent_id": payload.get("parent_id"),
                    "page_id": payload.get("page_id"),
                    "section_id": payload.get("section_id"),
                    "chunk_index": payload.get("chunk_index"),
                    "chunk_start_offset": payload.get("chunk_start_offset"),
                    "chunk_end_offset": payload.get("chunk_end_offset"),
                    "revision_id": payload.get("revision_id"),
                    "access_scope": payload.get("access_scope"),
                    "access_subject_id": payload.get("access_subject_id"),
                    "access_tenant_id": payload.get("access_tenant_id"),
                    "access_channel_id": payload.get("access_channel_id"),
                    "vector_score": round(
                        float(dense_score if dense_score is not None else score), 4
                    ),
                    "dense_score": (
                        round(float(dense_score), 4) if dense_score is not None else None
                    ),
                    "sparse_score": (
                        round(float(sparse_score), 4) if sparse_score is not None else None
                    ),
                    "dense_sparse_rrf_score": round(score, 6),
                    "retrieval_mode": cand.get("retrieval_mode", "dense_legacy"),
                    "keyword_score": round(keyword_score, 4),
                    "metadata_score": round(metadata_score, 4),
                    "hybrid_score": round(hybrid_score, 4),
                    "canonical_name": canon_name,
                    "heading_path": heading,
                    "entities": chunk_entities,
                    "entity_hit": bool(entity_hit)
                }
                cand["scoring_meta"] = scoring_meta
                scored_candidates.append((cand, hybrid_score))

        scored_candidates.sort(key=lambda x: x[1], reverse=True)
        scored_candidates = await self._cross_encoder_rerank(
            query_text=query_text,
            scored_candidates=scored_candidates,
            enabled=enable_cross_encoder_rerank,
        )

        seen_parents = set()
        lore_chunks: list[tuple[str, float, dict[str, Any]]] = []
        accumulated_tokens = 0
        
        # Collect parent IDs to fetch from DB
        parent_ids_to_fetch = set()
        for cand, score in scored_candidates:
            payload = cand.get("payload", {})
            parent_id_str = payload.get("parent_id")
            if parent_id_str:
                try:
                    parent_ids_to_fetch.add(uuid.UUID(parent_id_str))
                except ValueError:
                    pass

        # Fetch parents if repo factory and session are provided
        parent_docs: dict[str, str] = {}
        if self.lore_parent_repo_factory and session and parent_ids_to_fetch:
            try:
                repo = self.lore_parent_repo_factory(session)
                parents = await repo.get_parents_batch(list(parent_ids_to_fetch))
                for p in parents:
                    # Store full parent section markdown
                    parent_docs[str(p.id)] = p.markdown
            except Exception as pe:
                log.warning("Failed to fetch parent markdown from database, using chunk fallback", error=str(pe))

        for cand, score in scored_candidates:
            payload = cand.get("payload", {})
            parent_id = payload.get("parent_id")
            
            # 1. Try to get section parent markdown from DB
            parent_text = parent_docs.get(parent_id) if parent_id else None
            child_text = payload.get("text_content", "")
            
            # 2. Windowed Parent Resolution (mitigate parent bloat)
            resolved_text = self.resolve_windowed_parent(parent_text, child_text, window_chars=1200) if parent_text else child_text
            
            if not resolved_text:
                continue
                
            chunk_tokens = TokenEstimator.estimate(resolved_text)
            
            # Check dynamic context token budget if provided
            if max_token_budget is not None and accumulated_tokens + chunk_tokens > max_token_budget and lore_chunks:
                log.info("Lore retrieval reached max token budget limit", current_tokens=accumulated_tokens, budget=max_token_budget)
                break
                
            scoring_meta = cand.get("scoring_meta", {})
            if parent_id:
                if parent_id not in seen_parents:
                    seen_parents.add(parent_id)
                    lore_chunks.append((resolved_text, score, scoring_meta))
                    accumulated_tokens += chunk_tokens
            else:
                lore_chunks.append((resolved_text, score, scoring_meta))
                accumulated_tokens += chunk_tokens
                
            if len(lore_chunks) >= top_k:
                break
                
        return lore_chunks

    async def _cross_encoder_rerank(
        self,
        *,
        query_text: str,
        scored_candidates: list[tuple[dict[str, Any], float]],
        enabled: bool,
    ) -> list[tuple[dict[str, Any], float]]:
        """Rerank top candidates with the configured cross encoder or expose fallback.

        Lexical/vector scores remain provenance features only when a cross encoder
        succeeds. A missing, invalid, or late model never blocks chat retrieval;
        callers can observe the deterministic fallback through evidence metadata.
        """
        if not scored_candidates:
            return scored_candidates
        if not enabled:
            return self._apply_cross_encoder_fallback(
                scored_candidates,
                "not_applicable",
                degraded=False,
            )
        if self.cross_encoder_reranker is None or not query_text.strip():
            return self._apply_cross_encoder_fallback(scored_candidates, "not_configured")

        rerankable = scored_candidates[: RAGTuning.CROSS_ENCODER_CANDIDATE_LIMIT]
        if self._reranker_requires_public_evidence() and not self._all_public(rerankable):
            log.warning(
                "Remote reranker denied non-public evidence; using deterministic fallback"
            )
            return self._apply_cross_encoder_fallback(scored_candidates, "remote_policy")
        documents = [
            str(candidate.get("payload", {}).get("text_content", ""))
            for candidate, _ in rerankable
        ]
        if not all(documents):
            return self._apply_cross_encoder_fallback(scored_candidates, "invalid_candidate")
        try:
            cross_encoder_scores = await self.cross_encoder_reranker.rerank(
                query_text, documents
            )
        except RerankerUnavailableError as error:
            log.warning(
                "Cross-encoder reranking unavailable; using deterministic fallback",
                error_type=type(error).__name__,
                failure_kind=error.failure_kind.value,
            )
            return self._apply_cross_encoder_fallback(
                scored_candidates,
                self._provider_failure_reason(error.failure_kind),
            )
        except TimeoutError as error:
            log.warning(
                "Cross-encoder reranking unavailable; using deterministic fallback",
                error_type=type(error).__name__,
                failure_kind="timeout",
            )
            return self._apply_cross_encoder_fallback(
                scored_candidates,
                "provider_timeout",
            )
        if len(cross_encoder_scores) != len(rerankable) or not all(
            math.isfinite(score) for score in cross_encoder_scores
        ):
            log.warning("Cross-encoder returned an invalid score set; using deterministic fallback")
            return self._apply_cross_encoder_fallback(scored_candidates, "invalid_score_set")

        reranked: list[tuple[dict[str, Any], float]] = []
        for (candidate, _), raw_score in zip(rerankable, cross_encoder_scores, strict=True):
            calibrated_score = self._calibrate_cross_encoder_score(raw_score)
            scoring_meta = candidate["scoring_meta"]
            scoring_meta["cross_encoder_score"] = round(float(raw_score), 6)
            scoring_meta["reranker_score"] = round(calibrated_score, 6)
            scoring_meta["reranker_mode"] = "cross_encoder"
            scoring_meta["reranker_fallback"] = False
            scoring_meta["reranker_degraded"] = False
            reranked.append((candidate, calibrated_score))
        for candidate, score in scored_candidates[RAGTuning.CROSS_ENCODER_CANDIDATE_LIMIT :]:
            scoring_meta = candidate["scoring_meta"]
            scoring_meta["reranker_mode"] = "candidate_limit_fallback"
            scoring_meta["reranker_fallback"] = True
            scoring_meta["reranker_degraded"] = True
            reranked.append((candidate, score))
        reranked.sort(key=lambda item: item[1], reverse=True)
        return reranked

    def _apply_cross_encoder_fallback(
        self,
        scored_candidates: list[tuple[dict[str, Any], float]],
        reason: str,
        degraded: bool = True,
    ) -> list[tuple[dict[str, Any], float]]:
        return self._cross_encoder_fallback.apply(
            scored_candidates,
            reason=reason,
            degraded=degraded,
        )

    @staticmethod
    def _provider_failure_reason(failure_kind: RerankerFailureKind) -> str:
        return {
            RerankerFailureKind.TIMEOUT: "provider_timeout",
            RerankerFailureKind.RATE_LIMIT: "provider_rate_limit",
            RerankerFailureKind.PROVIDER: "provider_unavailable",
            RerankerFailureKind.INVALID_RESPONSE: "provider_invalid_response",
            RerankerFailureKind.UNAVAILABLE: "provider_unavailable",
        }[failure_kind]

    def _reranker_requires_public_evidence(self) -> bool:
        """Treat an unlabelled adapter as remote until it proves otherwise."""
        return (
            getattr(self.cross_encoder_reranker, "data_boundary", None)
            is not RerankerDataBoundary.LOCAL
        )

    @staticmethod
    def _all_public(scored_candidates: list[tuple[dict[str, Any], float]]) -> bool:
        return all(
            candidate.get("payload", {}).get("access_scope") == "public"
            for candidate, _ in scored_candidates
        )

    @staticmethod
    def _calibrate_cross_encoder_score(raw_score: float) -> float:
        """Map model logits to a bounded score for existing RAG fusion consumers."""
        bounded_logit = max(-20.0, min(20.0, float(raw_score)))
        return 1.0 / (1.0 + math.exp(-bounded_logit))
