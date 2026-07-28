# STRUCTURAL DIAGRAM & TAXONOMY: WUTHERING WAVES WIKI

> **Tự động trích xuất từ dữ liệu Wiki**: 20 trang đã được phân tích.  
> **Thời gian tạo**: 2026-07-26  

---

## 1. PHÂN LOẠI CẤU TRÚC WIKI (DYNAMIC WIKI TAXONOMY MINDMAP)

```mermaid
mindmap
  root((Wuthering Waves Wiki Structure))
    GENERIC[Page Type: GENERIC (19 pages)]
      Common Headings: Solaris-3, CHUNK 2 — Honami Loop and Sumika, Sumika Relationship, Resonator
    FACTION[Page Type: FACTION (1 pages)]
      Common Headings: Startorch Academy, Campus Life, Birding Fan Club, Auto Parking & Engineering Xpertise
```

---

## 2. LUỒNG XỬ LÝ DỮ LIỆU WIKI (INGESTION PIPELINE FLOWCHART)

```mermaid
flowchart TD
    subgraph RawData ["Wuthering Waves Raw Data Layer"]
        WikiPages["Wiki Pages / Wikitext"] --> Sanitizer["Sanitizer & Stripper"]
        Sanitizer --> SectionExtractor["Section & Table Parser"]
    end

    subgraph CanonicalLayer ["Canonicalization Layer (canonical.jsonl)"]
        SectionExtractor --> Classifier["PageType Classifier"]
        Classifier --> EntityRes["Entity & Alias Registry"]
        EntityRes --> GoldenCanonical[("Canonical Dataset
data/canonical/canonical.jsonl")]
    end

    subgraph Downstream ["Structure-Aware Chunking & Storage"]
        GoldenCanonical --> Router{"Content-Type Router"}
        Router -- "TABLE" --> TableInliner["TableInlinerChunker"]
        Router -- "DIALOGUE" --> DialogueChunker["DialogueChunker"]
        Router -- "PROSE / LIST" --> GenericChunker["GenericChunker"]
        Router -- "ATOMIC" --> AtomicChunker["AtomicChunker (Unsplit)"]

        TableInliner --> ContextPrefix["Context Prefix Injection"]
        DialogueChunker --> ContextPrefix
        GenericChunker --> ContextPrefix
        AtomicChunker --> ContextPrefix

        ContextPrefix --> Qdrant[("Qdrant Vector Storage
chisa_characters | chisa_lore | chisa_gameplay")]
    end
```

---

## 3. THỐNG KÊ CHI TIẾT CÁC PHÂN LOẠI TRANG (PAGE TYPE & SECTION BREAKDOWN)

| Page Type (`PageTypeEnum`) | So Luong Trang | Infobox Fields Mau | Standard Headings Mau |
| :--- | :--- | :--- | :--- |
| `GENERIC` | 19 | `None` | `Solaris-3, CHUNK 2 — Honami Loop and Sumika, Sumika Relationship` |
| `FACTION` | 1 | `None` | `Startorch Academy, Campus Life, Birding Fan Club` |

---

## 4. MA TRẬN QUAN HỆ THỰC THỂ WIKI (ENTITY RELATIONSHIP ER DIAGRAM)

```mermaid
erDiagram
    Chisa_Lore_Legacy ||--o{ Lahai_Roi : located_in
    Chisa_Lore_Legacy ||--o{ Startorch_Academy : affiliated_with
    Spacetrek_Collective ||--o{ Lahai_Roi : located_in
    Startorch_Academy ||--o{ New_Federation : located_in
    Startorch_Academy ||--o{ Spacetrek_Collective : affiliated_with
    Chisa_Overclock ||--o{ Lahai_Roi : located_in
    Companion_Quest ||--o{ Startorch_Academy : affiliated_with
    Sumika ||--o{ Startorch_Academy : affiliated_with
    Lahai_Roi ||--o{ Lahai_Roi : located_in
    Companion_Quest ||--o{ Lahai_Roi : located_in
```
