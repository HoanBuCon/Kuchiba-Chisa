import asyncio
import uuid
from typing import Any

import pytest

from app.application.dependencies import container
from app.domain.entities.lore import LoreParent, LorePayload
from app.domain.services.rag.entity_resolver import EntityResolver
from app.domain.services.rag.entity_sync import sync_entities_dictionary
from app.domain.services.rag.retriever_lore import LoreRetriever
from app.domain.tuning.rag import RAGTuning
from app.infrastructure.database.engine import AsyncSessionFactory
from app.infrastructure.database.models.lore_parent import LoreParentModel
from app.infrastructure.database.repositories.lore_parent import LoreParentRepository

pytestmark = pytest.mark.asyncio(loop_scope="session")

LORE_TEST_CASES = [
    # ── Group 1: Character Identity & Background (4 cases) ───────────────────
    {
        "id": "TC01",
        "category": "Character Identity",
        "query": "Chisa là ai và cô ấy có nguồn gốc xuất thân như thế nào?",
        "expected_entities": ["Kuchiba Chisa"],
        "expected_keywords": ["Kuchiba Chisa", "Mutant Resonator", "Resonator"],
    },
    {
        "id": "TC02",
        "category": "Character Personality",
        "query": "Tính cách của Chisa và sở thích ăn uống, điểm yếu ẩm thực của em là gì?",
        "expected_entities": ["Kuchiba Chisa"],
        "expected_keywords": ["Kuudere", "socola", "Pocky", "ớt"],
    },
    {
        "id": "TC03",
        "category": "Character Profile",
        "query": "Sở thích lúc rảnh rỗi của Chisa và tình cảm của cô ấy đối với loài mèo ra sao?",
        "expected_entities": ["Kuchiba Chisa"],
        "expected_keywords": ["mèo", "trà", "nấu ăn", "bánh ngọt"],
    },
    {
        "id": "TC04",
        "category": "Character Overclock",
        "query": "Hiện tượng Overclocking và nguy cơ quá tải tần số của Chisa diễn ra như thế nào?",
        "expected_entities": ["Kuchiba Chisa", "Overclocking"],
        "expected_keywords": ["quá tải", "tần số", "thực tại", "biến dị"],
    },
    # ── Group 2: Forte, Combat & Weapon Mechanics (4 cases) ───────────────────
    {
        "id": "TC05",
        "category": "Forte Mechanics",
        "query": "Năng lực Forte đặc trưng Thread Perception của Chisa hoạt động như thế nào?",
        "expected_entities": ["Thread Perception", "Kuchiba Chisa"],
        "expected_keywords": ["Thread Perception", "sợi tơ", "cấu trúc", "phân tích"],
    },
    {
        "id": "TC06",
        "category": "Weapon Mechanics",
        "query": "Vũ khí Broadblade của Chisa có hình dạng chiếc kéo khổng lồ có ý nghĩa gì?",
        "expected_entities": ["Broadblade", "Kuchiba Chisa"],
        "expected_keywords": ["kéo", "Broadblade", "cắt", "sợi tơ"],
    },
    {
        "id": "TC07",
        "category": "Combat Ability",
        "query": "Kỹ năng Resonance Liberation của Chisa tác động lên liên kết năng lượng mục tiêu ra sao?",
        "expected_entities": ["Kuchiba Chisa", "Resonator"],
        "expected_keywords": ["Resonance Liberation", "giải phóng", "cấu trúc", "sụp đổ"],
    },
    {
        "id": "TC08",
        "category": "Structural Analysis",
        "query": "Thế giới quan và tư duy phân tích logic về cấu trúc vạn vật của Chisa là gì?",
        "expected_entities": ["Kuchiba Chisa"],
        "expected_keywords": ["logic", "cấu trúc", "phân tích", "vạn vật"],
    },
    # ── Group 3: Relationships & Emotional Bonds (4 cases) ────────────────────
    {
        "id": "TC09",
        "category": "Relationship - Rover",
        "query": "Mối quan hệ gắn kết giữa Chisa và Senpai Rover có ý nghĩa đặc biệt thế nào?",
        "expected_entities": ["Rover", "Kuchiba Chisa"],
        "expected_keywords": ["Senpai", "Rover", "đồng hành", "ấm áp"],
    },
    {
        "id": "TC10",
        "category": "Relationship - Sumika",
        "query": "Người tiền bối quá cố Sumika có ảnh hưởng sâu đậm gì đến cuộc đời của Chisa?",
        "expected_entities": ["Sumika", "Kuchiba Chisa"],
        "expected_keywords": ["Sumika", "tiền bối", "dấu ấn", "hành trình"],
    },
    {
        "id": "TC11",
        "category": "Companion Quest",
        "query": "Kỷ niệm lễ hội học viện Startorch và khoảnh khắc uống trà dưới ánh pháo hoa cùng Rover ra sao?",
        "expected_entities": ["Startorch Academy", "Rover", "Kuchiba Chisa"],
        "expected_keywords": ["pháo hoa", "Startorch", "trà", "lễ hội"],
    },
    {
        "id": "TC12",
        "category": "Relationship Dynamics",
        "query": "Trạng thái cảm xúc Tsundere ngầm và sự thẹn thùng của Chisa khi bên cạnh Rover biểu hiện thế nào?",
        "expected_entities": ["Kuchiba Chisa", "Rover"],
        "expected_keywords": ["Tsundere", "dịu dàng", "lễ phép", "Senpai"],
    },
    # ── Group 4: Storyline, Quests & The Loop (4 cases) ───────────────────────
    {
        "id": "TC13",
        "category": "Story - Honami Loop",
        "query": "Chuyện gì đã xảy ra trong vòng lặp thời gian Honami Loop khiến Chisa bị giam cầm 20 năm?",
        "expected_entities": ["Honami Loop", "Kuchiba Chisa"],
        "expected_keywords": ["Honami", "vòng lặp", "20 năm", "ngưng đọng"],
    },
    {
        "id": "TC14",
        "category": "Story - Breaking The Loop",
        "query": "Làm thế nào Chisa và Rover có thể phá vỡ vòng lặp và giải phóng Honami?",
        "expected_entities": ["Honami Loop", "Rover", "Kuchiba Chisa"],
        "expected_keywords": ["phá vỡ", "vòng lặp", "lõi", "giải phóng"],
    },
    {
        "id": "TC15",
        "category": "Story - Sumika's Diary",
        "query": "Nội dung cuốn nhật ký của Sumika ghi lại những điều gì về những ngày tháng sinh tồn?",
        "expected_entities": ["Sumika", "Honami Loop"],
        "expected_keywords": ["nhật ký", "Sumika", "sinh tồn", "bạn bè"],
    },
    {
        "id": "TC16",
        "category": "Story - Sonoro Sphere Isolation",
        "query": "Không gian Sonoro Sphere Honami được tạo thành từ những nỗi sợ và ký ức đau buồn nào?",
        "expected_entities": ["Sonoro Sphere", "Kuchiba Chisa"],
        "expected_keywords": ["Sonoro Sphere", "Honami", "cô độc", "ký ức"],
    },
    # ── Group 5: World Lore, Factions & Environment (4 cases) ─────────────────
    {
        "id": "TC17",
        "category": "World - Solaris-3 & Lament",
        "query": "Hành tinh Solaris-3 và thảm họa tần số The Lament đã tàn phá nền văn minh như thế nào?",
        "expected_entities": ["Solaris-3", "Lament"],
        "expected_keywords": ["Solaris-3", "Lament", "tần số", "thảm họa"],
    },
    {
        "id": "TC18",
        "category": "World - Factions & Academy",
        "query": "Học viện Startorch thuộc thành phố Jinzhou, Hoàng Long Huanglong đào tạo những ai?",
        "expected_entities": ["Startorch Academy", "Jinzhou", "Huanglong"],
        "expected_keywords": ["Startorch", "Jinzhou", "Huanglong", "Resonator"],
    },
    {
        "id": "TC19",
        "category": "World - Monsters & Fields",
        "query": "Quái vật Dị Thể Tacet Discord và vùng Tacet Field có nguồn gốc hình thành và cơ chế tái sinh ra sao?",
        "expected_entities": ["Tacet Discord", "Tacet Field"],
        "expected_keywords": ["Tacet Discord", "Tacet Field", "năng lượng", "tái sinh"],
    },
    {
        "id": "TC20",
        "category": "World - Geography & Regions",
        "query": "Vùng đất băng giá Lahai-Roi và các Sonoro Spheres trên khắp Solaris-3 có đặc điểm gì?",
        "expected_entities": ["Lahai-Roi", "Sonoro Sphere", "Solaris-3"],
        "expected_keywords": ["Lahai-Roi", "Sonoro Sphere", "Solaris-3", "không gian"],
    },
]


@pytest.fixture(scope="module", autouse=True)
async def isolated_lore_corpus(isolated_postgres, isolated_vector_store, test_embedder):
    """Seed a real PostgreSQL parent corpus and Qdrant child corpus in the isolated stack."""
    del isolated_postgres
    fixture_namespace = uuid.UUID("00000000-0000-0000-0000-000000000901")

    async with AsyncSessionFactory() as session:
        for index, test_case in enumerate(LORE_TEST_CASES, start=1):
            parent_id = uuid.uuid5(fixture_namespace, test_case["id"])
            text_content = f"{test_case['query']}\n{' | '.join(test_case['expected_keywords'])}"
            parent = LoreParent(
                id=parent_id,
                page_id=90000 + index,
                page_title=f"OPS-01 {test_case['id']}",
                heading=test_case["category"],
                markdown=f"# {test_case['category']}\n\n{text_content}",
                source_file="ops01-isolated-lore-fixture.md",
                revision_id=1,
                section_id=f"ops01-{test_case['id']}",
                heading_path=test_case["category"],
                section_depth=2,
            )
            await session.merge(LoreParentModel.from_domain(parent))

            collection = (
                "character_lore" if index <= 8 else "story_lore" if index <= 16 else "world_lore"
            )
            payload = LorePayload(
                parent_id=str(parent_id),
                section_id=parent.section_id,
                page_id=parent.page_id,
                source_file=parent.source_file or "ops01-isolated-lore-fixture.md",
                chunk_index=0,
                text_content=text_content,
                heading_path=parent.heading_path,
                section_depth=parent.section_depth,
                canonical_name=test_case["expected_entities"][0],
                entities=test_case["expected_entities"],
            )
            vector = await test_embedder.embed_text(text_content, prefix="passage: ")
            await isolated_vector_store.upsert_lore(
                collection=collection,
                point_id=str(uuid.uuid5(fixture_namespace, f"point-{test_case['id']}")),
                vector=vector,
                payload=payload,
            )
        await session.commit()


@pytest.fixture
def isolated_lore_retriever(isolated_vector_store):
    return LoreRetriever(
        vector_store=isolated_vector_store,
        lore_parent_repo_factory=LoreParentRepository,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("tc", LORE_TEST_CASES, ids=[tc["id"] for tc in LORE_TEST_CASES])
async def test_lore_metadata_retrieval_case(
    tc: dict[str, Any],
    isolated_entity_resolver: EntityResolver,
    isolated_lore_corpus: None,
    isolated_lore_retriever: LoreRetriever,
    test_embedder: Any,
):
    """
    Tests that each of the 20 Lore test cases:
    1. Triggers Entity Extraction & Graph Expansion from query.
    2. Performs Multi-Signal Hybrid Vector & Metadata retrieval across collections.
    3. Retrieves at least 1 relevant Lore chunk with score >= SCORE_THRESHOLD.
    4. Matches key expected lore topics in retrieved chunks.
    """
    query = tc["query"]
    expected_ents = set(tc["expected_entities"])
    expected_kw = tc["expected_keywords"]

    # 1. Entity Resolver Verification
    del isolated_lore_corpus
    resolver = isolated_entity_resolver
    extracted = resolver.extract_entities(query)
    expanded = resolver.expand_entities(extracted)

    # Verify that at least one expected entity is recognized/expanded
    assert bool(extracted & expected_ents) or bool(expanded & expected_ents), (
        f"[{tc['id']}] Failed to recognize expected entities {expected_ents}. "
        f"Extracted: {extracted}, Expanded: {expanded}"
    )

    # 2. Multi-Signal RAG Metadata-Hybrid Retrieval across lore collections
    q_vec = await test_embedder.embed_text(query)

    retrieved_lore_chunks = []
    async with AsyncSessionFactory() as session:
        for col in ["character_lore", "world_lore", "story_lore"]:
            chunks = await isolated_lore_retriever.retrieve_lore_parent_child(
                collection=col,
                query_vector=q_vec,
                session=session,
                query_text=query,
                top_k=RAGTuning.TOP_K,
                score_threshold=RAGTuning.SCORE_THRESHOLD,
                entities_filter=list(expanded) if expanded else None,
            )
            for item in chunks:
                retrieved_lore_chunks.append(item[0])

    # 3. Assertions on Retrieved Lore
    assert (
        len(retrieved_lore_chunks) > 0
    ), f"[{tc['id']}] No lore chunks retrieved for query: '{query}'"

    all_retrieved_text = " ".join(retrieved_lore_chunks).lower()

    # Verify that at least one expected topic keyword is contained in retrieved text
    matched_kws = [kw for kw in expected_kw if kw.lower() in all_retrieved_text]
    assert len(matched_kws) > 0, (
        f"[{tc['id']}] Retrieved lore chunks do not contain any of expected keywords {expected_kw}.\n"
        f"Retrieved Lore Sample:\n{retrieved_lore_chunks[0][:300]}..."
    )


async def run_all_tests_cli():
    """CLI runner to execute and display a rich summary table of all 20 testcases."""
    print("=" * 80)
    print("[TEST] RUNNING 20-QUESTION LORE METADATA-HYBRID RETRIEVAL TEST SUITE")
    print("=" * 80)

    sync_entities_dictionary()
    container.entity_resolver.load()
    embedder = container.embedder
    rag_stage = container.chat_engine.pipeline.stages[4]
    rag_pipeline = rag_stage.rag_pipeline
    lore_retriever = rag_pipeline.lore_retriever

    passed = 0
    failed = 0

    for i, tc in enumerate(LORE_TEST_CASES, 1):
        q = tc["query"]
        cid = tc["id"]
        cat = tc["category"]
        expected_ents = set(tc["expected_entities"])
        expected_kw = tc["expected_keywords"]

        resolver = container.entity_resolver
        extracted = resolver.extract_entities(q)
        expanded = resolver.expand_entities(extracted)

        q_vec = await embedder.embed_text(q)
        retrieved_chunks = []
        async with AsyncSessionFactory() as session:
            for col in ["character_lore", "world_lore", "story_lore"]:
                chunks = await lore_retriever.retrieve_lore_parent_child(
                    collection=col,
                    query_vector=q_vec,
                    session=session,
                    query_text=q,
                    top_k=RAGTuning.TOP_K,
                    score_threshold=RAGTuning.SCORE_THRESHOLD,
                    entities_filter=list(expanded) if expanded else None,
                )
                for item in chunks:
                    retrieved_chunks.append(item[0])

        all_text = " ".join(retrieved_chunks).lower()
        matched_kw = [k for k in expected_kw if k.lower() in all_text]
        ent_ok = bool(extracted & expected_ents) or bool(expanded & expected_ents)
        lore_ok = len(retrieved_chunks) > 0 and len(matched_kw) > 0

        status = "[PASS]" if (ent_ok and lore_ok) else "[FAIL]"
        if status == "[PASS]":
            passed += 1
        else:
            failed += 1

        print(f"[{cid}] [{cat:^28}] {status} | Chunks: {len(retrieved_chunks)}")
        print(f"     Matched KWs: {matched_kw} | Extracted: {list(extracted)}")
        if status == "[FAIL]":
            print(f"     Query: {q}")
            print(f"     Expected Ents: {expected_ents} (Extracted: {extracted})")
            print(f"     Expected KWs: {expected_kw}")

    print("=" * 80)
    print(
        f"[SUMMARY] {passed}/20 PASSED | {failed}/20 FAILED | Success Rate: {(passed/20)*100:.1f}%"
    )
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_all_tests_cli())
