# RAG-05 Raw Wiki Fact-Reviewed Pilot v1

Status: `draft` — proposed labels only; no reranker execution is authorized.

Corpus version: `raw-wiki-sha256:19fe7942c55f43a7a793532ed0894d88e5adb2dd24329681ebb9768d4d3a6ad3`

| Case | Language | Category | Query | Evidence ID |
|---|---|---|---|---|
| p01 | en | affiliation | What organization is Aalto affiliated with? | `raw_wiki:585:101912:cdb1baf766c207e6:chunk:000` |
| p02 | vi | character background | Baizhi làm việc trong lĩnh vực nào ở Huaxu Academy? | `raw_wiki:624:92922:791b05ce14a56b51:chunk:000` |
| p03 | vi | relationship | Changli giữ vai trò gì tại Jinzhou? | `raw_wiki:1126:100700:6b4973485554efd0:chunk:000` |
| p04 | en | character background | What job does Chixia have in Jinzhou? | `raw_wiki:510:99239:2efdf295348ddd30:chunk:000` |
| p05 | vi | affiliation | Calcharo lãnh đạo nhóm nào? | `raw_wiki:632:99398:b84b4f87a9d9ade9:chunk:000` |
| p06 | en | relationship | Who leads the Troupe of Fools? | `raw_wiki:24786:99400:468ec49727209414:chunk:000` |
| p07 | vi | affiliation | Camellya phụ trách việc gì ở Black Shores? | `raw_wiki:599:96614:56f198042c315f7e:chunk:000` |
| p08 | vi | relationship | Ai là lãnh đạo và người sáng lập Black Shores? | `raw_wiki:1007:135324:8f903f46d2fa3ca8:chunk:000` |
| p09 | en | faction/lore | What fields does Huaxu Academy's Jinzhou Campus specialize in? | `raw_wiki:938:130729:103ceb2210a7890a:chunk:000` |
| p10 | vi | faction/lore | Midnight Rangers có nhiệm vụ gì ở Jinzhou? | `raw_wiki:896:99150:aa2a5187c5ebc08b:chunk:000` |
| p11 | en | faction/lore | What kind of school is Startorch Academy? | `raw_wiki:37391:136476:a3a41695657088cf:chunk:000` |
| p12 | vi | lore/event | Điều gì có thể khiến một Resonator bị Overclocking? | `raw_wiki:24999:99250:79f12bc79353ca49:chunk:000` |
| p13 | en | lore/event | What are Tacet Discords formed from? | `raw_wiki:1008:99738:fa6acd585adb1d2a:chunk:000` |
| p14 | vi informal | paraphrase | Sonoro Sphere là gì vậy? | `raw_wiki:8269:95612:1c103964f57b0be7:chunk:000` |
| p15 | en | relationship | Why are Aalto and Encore described as a duo? | `raw_wiki:585:101912:cdb1baf766c207e6:chunk:000` |

Every answer summary, exact excerpt, rationale, and evidence link is in the JSON artifact. Relationships p03, p06, p08, and p15 were manually checked against their quoted source text. No multi-evidence or hard-negative case was included because none was added without a separately verified proof.
