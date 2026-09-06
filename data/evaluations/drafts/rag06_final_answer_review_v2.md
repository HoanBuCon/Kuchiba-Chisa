# RAG-06 Final-answer Human Review v2

- Generated: `2026-09-06T18:12:55.327248+07:00`
- Dataset fingerprint: `01cababd2e9912a1b435869afc500dc44d727d045f6bafe868c3be4bc6004976`
- Sample: 38 cases (36 answerable, 2 abstention)
- Provider/model: `deepseek` / `deepseek-v4-flash`
- Structural validation: **PASS**
- Semantic status: **HUMAN REVIEW APPROVED**

Do not use external game knowledge. Judge only the query, expected behavior, displayed evidence, delivered/candidate answer and citations. An unsupported non-abstaining answer on a no-answer case is blocking.

## rw-001 — What organization is Aalto affiliated with?

- Expected behavior: `answer`
- Expected summary: Aalto is a Consultant of the Black Shores.
- Delivery status: `delivered`
- Failure type: `none`
- Provider/model: `deepseek-v4-flash`
- Tokens: input 3786, output 185, reasoning 0

### Evidence

**Rank 1 — `raw_wiki:585:101912:cdb1baf766c207e6:chunk:000`**

> He is an information broker from the [[New Federation]] and a Consultant of the [[Black Shores]].

**Rank 2 — `raw_wiki:585:101912:cdb1baf766c207e6:chunk:000`**

> He is an information broker from the [[New Federation]] and a Consultant of the [[Black Shores]].

**Rank 3 — `raw_wiki:522:103593:65ac76a1400c1df9:chunk:000`**

> … see? ...Black Shores member, Encore, reporting in! > — Encore She is from the [[New Federation]] and a Consultant of the [[Black Shores]]. With her vivid imagination, her Wooly companions, Cosmos and Cloudy, and a penchant for crafting fairy tales, she is responsible for finding new clients for the Black Shores alongside her fellow Consultant and brother figure [[Aalto]]. ==Official Introduction== > Encore, a consul…

**Rank 4 — `raw_wiki:28266:131321:5f2feb1a382c7763:chunk:000`**

> …ntinel]] [[Imperator]]. Lilyland is known for hosting the "Lilyland Fashion Week" and having a large stage surrounded by fields of flowers, with the audience throwing petals as applause. The beauty industry in general is important in Lilyland, with products such as Upala Perfume and Efreeta Hair Conditioner, and Huanglong's rising fashion star [[Linglong]] has presented work at the fashion week. The Fisher family is …

**Rank 5 — `raw_wiki:585:101912:cdb1baf766c207e6:chunk:000`**

> He is an information broker from the [[New Federation]] and a Consultant of the [[Black Shores]].

### Answer for review

Aalto is an information broker from the New Federation and a Consultant of the Black Shores.

Citations: ["raw_wiki:585:101912:cdb1baf766c207e6:chunk:000"]

### Human decision

- Status: `approved`
- Critical unsupported claim: `no`
- Answer relevance: `relevant`
- Raw data quality issue: `none`
- Abstained: `N/A`
- Unsafe guess: `N/A`
- Abstention appropriate: `N/A`
- Reviewer: `HoanBuCon`
- Reviewed at: `2026-09-06T18:39:10.6572003+07:00`
- Comment: none

- `claim-01` materiality=`material`, faithfulness=`supported`: Aalto is an information broker from the New Federation and a Consultant of the Black Shores.
  - Citation labels: `raw_wiki:585:101912:cdb1baf766c207e6:chunk:000`=correct

## rw-025 — Denia secretly works for which organization?

- Expected behavior: `answer`
- Expected summary: Denia secretly serves as an agent for the Fractsidus.
- Delivery status: `delivered`
- Failure type: `none`
- Provider/model: `deepseek-v4-flash`
- Tokens: input 3928, output 171, reasoning 0

### Evidence

**Rank 1 — `raw_wiki:39187:136635:e0a124eb457dfb82:chunk:000`**

> who secretly serves as an agent for the [[Fractsidus]].

**Rank 2 — `raw_wiki:38339:136640:9d71c98f093fd140:chunk:000`**

> …t is considered the strongest Threnodian due to its existential erasure power, potentially linked to the region's research focus and desire for space, causing people to forget their origins. Its appearance resembles that of a massive black hole, but with a blue iris flowing downwards as its center instead of an event horizon. Inside the center of its pupil is a tiny blue dot, and it has a white accretion disk. Aleph-…

**Rank 3 — `raw_wiki:37391:136476:a3a41695657088cf:chunk:000`**

> …gh the '''Torch''' of Tomorrow". All students (except Synchronists admitted to Rabelle College) begin with a cross-disciplinary curriculum, which covers foundational sciences, humanities, and essential survival skills for life in Lahai-Roi. Students' specialized department placement is determined at the end of Year 2, based on their stated interest and academic performance. ==Descriptions== Startorch Academy is a com…

**Rank 4 — `raw_wiki:907:126835:49c5a92e82ee7ad1:chunk:000`**

> # Fractsidus **Faction Profile**: Leader: Schwarzloch, Enemies: Black Shores;Jinzhou;Montelli Family;Septimont. The '''Fractsidus''' is a mysterious global terrorist organization that serves as the main antagonistic faction of ''[[Wuthering Waves]]''. Their aim is to accelerate the next [[The Lament|Lament]] - dubbed the "True Lament" - by resurrecting the [[Threnodian]]s, viewing the Lament not as an apocalyptic cat…

**Rank 5 — `raw_wiki:37391:136476:a3a41695657088cf:chunk:000`**

> …gh the '''Torch''' of Tomorrow". All students (except Synchronists admitted to Rabelle College) begin with a cross-disciplinary curriculum, which covers foundational sciences, humanities, and essential survival skills for life in Lahai-Roi. Students' specialized department placement is determined at the end of Year 2, based on their stated interest and academic performance. ==Descriptions== Startorch Academy is a com…

### Answer for review

Denia secretly serves as an agent for the Fractsidus organization.

Citations: ["raw_wiki:39187:136635:e0a124eb457dfb82:chunk:000"]

### Human decision

- Status: `approved`
- Critical unsupported claim: `no`
- Answer relevance: `relevant`
- Raw data quality issue: `none`
- Abstained: `N/A`
- Unsafe guess: `N/A`
- Abstention appropriate: `N/A`
- Reviewer: `HoanBuCon`
- Reviewed at: `2026-09-06T18:39:10.6572003+07:00`
- Comment: none

- `claim-01` materiality=`material`, faithfulness=`supported`: Denia secretly serves as an agent for the Fractsidus organization.
  - Citation labels: `raw_wiki:39187:136635:e0a124eb457dfb82:chunk:000`=correct

## rw-037 — Why is Lupa notable in Septimont's arena?

- Expected behavior: `answer`
- Expected summary: Lupa is an undefeated gladiator champion from Septimont.
- Delivery status: `delivered`
- Failure type: `none`
- Provider/model: `deepseek-v4-flash`
- Tokens: input 4028, output 228, reasoning 0

### Evidence

**Rank 1 — `raw_wiki:30940:96622:a0dca9f4d3d03fb9:chunk:000`**

> She is a gladiator from [[Septimont]], a warrior and undefeated champion of the arena

**Rank 2 — `raw_wiki:31852:72985:814ee00262cb4399:chunk:000`**

> # House Silva **Faction Profile**: Leader: Julia Silva, Base: Septimont (formerly). '''House Silva''' is one of the founding bloodlines of [[Septimont]] and a once prominent noble family, though their influence began waver with the rise of the new [[Augusta|Ephor]]. During the most recent [[Great Agon]] the household and their head, Julia Silva, take part in match fixing and go as far as to sabotage [[Lupa]]'s equipm…

**Rank 3 — `raw_wiki:27120:96278:b1047d1aa9a9b8d2:chunk:000`**

> **Profile**: Title: Leviathan, Origin: Rinascita, Affiliation: Threnodians. ''This article is about the NPC.&#x20;For the Weekly Boss, see [[Threnodian: Leviathan]].'' > "Fleurdelys, my Resonator, why dost thou persist? Why abandon thy oath? Why hinder the spread of my gospel? The one blessed by the Dark Tide shall return to us. Continue thy disobedience at the risk of insanity. My most beloved Resonator, why persist…

**Rank 4 — `raw_wiki:26373:135203:7ce25d5efa8633f0:chunk:000`**

> **Profile**: Title: Septimont, Origin: Rinascita. '''Septimont''' is a [[Region]] and city-state of [[Rinascita]]. Unlike [[Ragunna]], Septimont has a far more militant and irreligious culture, as it places far less importance on the primacy of the [[Sentinel]] [[Imperator]] and instead worships the [[Lioness of Glory]] Arsinosa. As a result, the Agons, competitive gladiatorial combat, are the pinnacle of Septimontes…

**Rank 5 — `raw_wiki:26373:135203:7ce25d5efa8633f0:chunk:000`**

> **Profile**: Title: Septimont, Origin: Rinascita. '''Septimont''' is a [[Region]] and city-state of [[Rinascita]]. Unlike [[Ragunna]], Septimont has a far more militant and irreligious culture, as it places far less importance on the primacy of the [[Sentinel]] [[Imperator]] and instead worships the [[Lioness of Glory]] Arsinosa. As a result, the Agons, competitive gladiatorial combat, are the pinnacle of Septimontes…

### Answer for review

Lupa is notable in Septimont's arena because during the most recent Great Agon, House Silva and their head Julia Silva took part in match fixing and went as far as to sabotage Lupa's equipment.

Citations: ["raw_wiki:31852:72985:814ee00262cb4399:chunk:000"]

### Human decision

- Status: `approved`
- Critical unsupported claim: `no`
- Answer relevance: `partially_relevant`
- Raw data quality issue: `none`
- Abstained: `N/A`
- Unsafe guess: `N/A`
- Abstention appropriate: `N/A`
- Reviewer: `HoanBuCon`
- Reviewed at: `2026-09-06T18:39:10.6572003+07:00`
- Comment: Project owner approved this case as partially relevant.

- `claim-01` materiality=`material`, faithfulness=`supported`: Lupa is notable in Septimont's arena because during the most recent Great Agon, House Silva and their head Julia Silva took part in match fixing and went as far as to sabotage Lupa's equipment.
  - Citation labels: `raw_wiki:31852:72985:814ee00262cb4399:chunk:000`=correct

## rw-043 — What kinds of frequencies can Phrolova manipulate?

- Expected behavior: `answer`
- Expected summary: Phrolova can manipulate and transfigure the frequencies of humans, Echoes, and Tacet Discords.
- Delivery status: `delivered`
- Failure type: `none`
- Provider/model: `deepseek-v4-flash`
- Tokens: input 3771, output 195, reasoning 0

### Evidence

**Rank 1 — `raw_wiki:1074:99099:f1f00f7ba53c6ff4:chunk:000`**

> Her forte can manipulate and transfigure the frequencies of humans, Echoes, and Tacet Discords alike.

**Rank 2 — `raw_wiki:1074:99099:f1f00f7ba53c6ff4:chunk:000`**

> Her forte can manipulate and transfigure the frequencies of humans, Echoes, and Tacet Discords alike.

**Rank 3 — `raw_wiki:1074:99099:f1f00f7ba53c6ff4:chunk:000`**

> Her forte can manipulate and transfigure the frequencies of humans, Echoes, and Tacet Discords alike.

**Rank 4 — `raw_wiki:8269:95612:1c103964f57b0be7:chunk:000`**

> …res exist, such as the [[Simulation Training]] that [[Midnight Rangers]] use, with the [[Nimbus Sanctum]] being a unique Sonoro Sphere that can be interacted in the physical plane. However, upon entering a Sonoro Sphere, information may become distorted and it becomes difficult to remove the interference from the original contents. There is also the possibility that when recording information, if the conditions are m…

**Rank 5 — `raw_wiki:348:86837:3b43bd7a33ec8d89:chunk:000`**

> **Profile**: Title: Resonator. {{CharacterSystemTabs}} '''Resonators''' are the obtainable playable characters of ''[[Wuthering Waves]]'', and individuals with the ability to resonate with certain objects or elements and manipulate their frequencies. ==Lore== A Resonator experiences their Awakening when they first resonate with the frequencies of something in the world and gain their Resonance Ability, also known as …

### Answer for review

Phrolova's forte allows her to manipulate and transfigure the frequencies of humans, Echoes, and Tacet Discords alike.

Citations: ["raw_wiki:1074:99099:f1f00f7ba53c6ff4:chunk:000"]

### Human decision

- Status: `approved`
- Critical unsupported claim: `no`
- Answer relevance: `relevant`
- Raw data quality issue: `none`
- Abstained: `N/A`
- Unsafe guess: `N/A`
- Abstention appropriate: `N/A`
- Reviewer: `HoanBuCon`
- Reviewed at: `2026-09-06T18:39:10.6572003+07:00`
- Comment: none

- `claim-01` materiality=`material`, faithfulness=`supported`: Phrolova's forte allows her to manipulate and transfigure the frequencies of humans, Echoes, and Tacet Discords alike.
  - Citation labels: `raw_wiki:1074:99099:f1f00f7ba53c6ff4:chunk:000`=correct

## rw-050 — How is the Ephor of Septimont chosen?

- Expected behavior: `answer`
- Expected summary: The position is attained through combat merit by prevailing over the Great Agon, held every four years.
- Delivery status: `delivered`
- Failure type: `none`
- Provider/model: `deepseek-v4-flash`
- Tokens: input 4009, output 204, reasoning 0

### Evidence

**Rank 1 — `raw_wiki:35947:81917:0722434a53a692f3:chunk:000`**

> whose position is attained through a form of combat merit gained from prevailing over the [[Great Agon]] that occurs once every four years.

**Rank 2 — `raw_wiki:26373:135203:7ce25d5efa8633f0:chunk:000`**

> **Profile**: Title: Septimont, Origin: Rinascita. '''Septimont''' is a [[Region]] and city-state of [[Rinascita]]. Unlike [[Ragunna]], Septimont has a far more militant and irreligious culture, as it places far less importance on the primacy of the [[Sentinel]] [[Imperator]] and instead worships the [[Lioness of Glory]] Arsinosa. As a result, the Agons, competitive gladiatorial combat, are the pinnacle of Septimontes…

**Rank 3 — `raw_wiki:31310:99574:02e73eaeaa24eb2c:chunk:000`**

> > With the blazing sun as witness... Glory, bow before us. > — Augusta The fearless Ephor of [[Septimont]] with a will of iron, she remains a fiercely resilient yet humble leader despite the immeasurable hardships of her childhood and tenure as a Gladiator. Though a mere mortal, she has mastered the arts of combat, strategy, and her Forte through countless conflicts, reaching heights few others like her have ever att…

**Rank 4 — `raw_wiki:26373:135203:7ce25d5efa8633f0:chunk:000`**

> **Profile**: Title: Septimont, Origin: Rinascita. '''Septimont''' is a [[Region]] and city-state of [[Rinascita]]. Unlike [[Ragunna]], Septimont has a far more militant and irreligious culture, as it places far less importance on the primacy of the [[Sentinel]] [[Imperator]] and instead worships the [[Lioness of Glory]] Arsinosa. As a result, the Agons, competitive gladiatorial combat, are the pinnacle of Septimontes…

**Rank 5 — `raw_wiki:31852:72985:814ee00262cb4399:chunk:000`**

> # House Silva **Faction Profile**: Leader: Julia Silva, Base: Septimont (formerly). '''House Silva''' is one of the founding bloodlines of [[Septimont]] and a once prominent noble family, though their influence began waver with the rise of the new [[Augusta|Ephor]]. During the most recent [[Great Agon]] the household and their head, Julia Silva, take part in match fixing and go as far as to sabotage [[Lupa]]'s equipm…

### Answer for review

The Ephor of Septimont is chosen through a form of combat merit gained from prevailing over the Great Agon, a competition that occurs once every four years.

Citations: ["raw_wiki:35947:81917:0722434a53a692f3:chunk:000"]

### Human decision

- Status: `approved`
- Critical unsupported claim: `no`
- Answer relevance: `relevant`
- Raw data quality issue: `none`
- Abstained: `N/A`
- Unsafe guess: `N/A`
- Abstention appropriate: `N/A`
- Reviewer: `HoanBuCon`
- Reviewed at: `2026-09-06T18:39:10.6572003+07:00`
- Comment: none

- `claim-01` materiality=`material`, faithfulness=`supported`: The Ephor of Septimont is chosen through a form of combat merit gained from prevailing over the Great Agon, a competition that occurs once every four years.
  - Citation labels: `raw_wiki:35947:81917:0722434a53a692f3:chunk:000`=correct

## rw-011 — What kind of school is Startorch Academy?

- Expected behavior: `answer`
- Expected summary: It is a multinational school built by the Spacetrek Collective for Resonators in Lahai-Roi.
- Delivery status: `delivered`
- Failure type: `none`
- Provider/model: `deepseek-v4-flash`
- Tokens: input 3751, output 190, reasoning 0

### Evidence

**Rank 1 — `raw_wiki:37391:136476:a3a41695657088cf:chunk:000`**

> '''Startorch Academy''' is a multinational school built by the [[Spacetrek Collective]] specifically for [[Resonator]]s in [[Lahai-Roi]].

**Rank 2 — `raw_wiki:37391:136476:a3a41695657088cf:chunk:000`**

> '''Startorch Academy''' is a multinational school built by the [[Spacetrek Collective]] specifically for [[Resonator]]s in [[Lahai-Roi]].

**Rank 3 — `raw_wiki:38235:100618:8025f2e9981c401e:chunk:000`**

> **Profile**: Title: Startorch Academy, Origin: Roya Frostlands. {{About|the region|the institution|Startorch Academy}} '''Startorch Academy''' is a [[Region]] located in [[Roya Frostlands]]. It contains the primary settlement and education institute of Lahai-Roi, [[Startorch Academy]]. ==Areas== {| class="article-table alternating-colors-table tdc1" style="width: 100%;" ! style="width: 200px;" |Name !Image !Descripti…

**Rank 4 — `raw_wiki:37391:136476:a3a41695657088cf:chunk:000`**

> '''Startorch Academy''' is a multinational school built by the [[Spacetrek Collective]] specifically for [[Resonator]]s in [[Lahai-Roi]].

**Rank 5 — `raw_wiki:37391:136476:a3a41695657088cf:chunk:000`**

> '''Startorch Academy''' is a multinational school built by the [[Spacetrek Collective]] specifically for [[Resonator]]s in [[Lahai-Roi]].

### Answer for review

Startorch Academy is a multinational school built by the Spacetrek Collective specifically for Resonators in Lahai-Roi.

Citations: ["raw_wiki:37391:136476:a3a41695657088cf:chunk:000"]

### Human decision

- Status: `approved`
- Critical unsupported claim: `no`
- Answer relevance: `relevant`
- Raw data quality issue: `none`
- Abstained: `N/A`
- Unsafe guess: `N/A`
- Abstention appropriate: `N/A`
- Reviewer: `HoanBuCon`
- Reviewed at: `2026-09-06T18:39:10.6572003+07:00`
- Comment: none

- `claim-01` materiality=`material`, faithfulness=`supported`: Startorch Academy is a multinational school built by the Spacetrek Collective specifically for Resonators in Lahai-Roi.
  - Citation labels: `raw_wiki:37391:136476:a3a41695657088cf:chunk:000`=correct

## rw-066 — How does Aleph-1 affect people differently from ordinary Tacet Discords?

- Expected behavior: `answer`
- Expected summary: Aleph-1 erases people's existence and memories, while ordinary Tacet Discords only petrify them.
- Delivery status: `delivered`
- Failure type: `none`
- Provider/model: `deepseek-v4-flash`
- Tokens: input 3848, output 439, reasoning 0

### Evidence

**Rank 1 — `raw_wiki:38339:136640:9d71c98f093fd140:chunk:000`**

> It is a [[Void Storm]] that erases people's existence and memories, unlike normal [[Tacet Discord]]s that just petrify them.

**Rank 2 — `raw_wiki:38339:136640:9d71c98f093fd140:chunk:000`**

> It is a [[Void Storm]] that erases people's existence and memories, unlike normal [[Tacet Discord]]s that just petrify them.

**Rank 3 — `raw_wiki:26165:131313:b22f8b2701be47df:chunk:000`**

> …ing mass of clouds that gathers and eventually breaks, pouring down in torrents like a waterfall. Whenever the Dark Tide strikes, it spawns Tacet Discords, and the area around its point of origin becomes a new Tacet Field.There have been two significant Dark Tides in Ragunna's history. The first, according to the Order of the Deep, was stopped by Napoli II, the first Primus of the Order. The second was quelled by the…

**Rank 4 — `raw_wiki:39212:96889:58a15a6051c28b88:chunk:000`**

> …ons reach a critical threshold, causing widespread destruction within a cyclical range that disrupts the frequencies around it before those affected by it find their existence fading away from both the physical world and the memories of others. This Waveworn Phenomenon is linked to the existence of 

**Rank 5 — `raw_wiki:26165:131313:b22f8b2701be47df:chunk:000`**

> …ing mass of clouds that gathers and eventually breaks, pouring down in torrents like a waterfall. Whenever the Dark Tide strikes, it spawns Tacet Discords, and the area around its point of origin becomes a new Tacet Field.There have been two significant Dark Tides in Ragunna's history. The first, according to the Order of the Deep, was stopped by Napoli II, the first Primus of the Order. The second was quelled by the…

### Answer for review

It is a Void Storm that erases people's existence and memories, unlike normal Tacet Discords that just petrify them. When the Dark Tide strikes, it spawns Tacet Discords, and the area around its point of origin becomes a new Tacet Field. causing widespread destruction within a cyclical range that disrupts the frequencies around it before those affected by it find their existence fading away from both the physical world and the memories of others. This Waveworn Phenomenon is linked to the existence of

Citations: ["raw_wiki:38339:136640:9d71c98f093fd140:chunk:000", "raw_wiki:26165:131313:b22f8b2701be47df:chunk:000", "raw_wiki:39212:96889:58a15a6051c28b88:chunk:000"]

### Human decision

- Status: `approved`
- Critical unsupported claim: `no`
- Answer relevance: `partially_relevant`
- Raw data quality issue: `none`
- Abstained: `N/A`
- Unsafe guess: `N/A`
- Abstention appropriate: `N/A`
- Reviewer: `HoanBuCon`
- Reviewed at: `2026-09-06T18:39:10.6572003+07:00`
- Comment: Project owner approved this case as partially relevant.

- `claim-01` materiality=`material`, faithfulness=`supported`: It is a Void Storm that erases people's existence and memories, unlike normal Tacet Discords that just petrify them.
  - Citation labels: `raw_wiki:38339:136640:9d71c98f093fd140:chunk:000`=correct, `raw_wiki:26165:131313:b22f8b2701be47df:chunk:000`=correct, `raw_wiki:39212:96889:58a15a6051c28b88:chunk:000`=correct
- `claim-02` materiality=`material`, faithfulness=`supported`: When the Dark Tide strikes, it spawns Tacet Discords, and the area around its point of origin becomes a new Tacet Field.
  - Citation labels: `raw_wiki:38339:136640:9d71c98f093fd140:chunk:000`=correct, `raw_wiki:26165:131313:b22f8b2701be47df:chunk:000`=correct, `raw_wiki:39212:96889:58a15a6051c28b88:chunk:000`=correct
- `claim-03` materiality=`material`, faithfulness=`supported`: causing widespread destruction within a cyclical range that disrupts the frequencies around it before those affected by it find their existence fading away from both the physical world and the memories of others.
  - Citation labels: `raw_wiki:38339:136640:9d71c98f093fd140:chunk:000`=correct, `raw_wiki:26165:131313:b22f8b2701be47df:chunk:000`=correct, `raw_wiki:39212:96889:58a15a6051c28b88:chunk:000`=correct
- `claim-04` materiality=`material`, faithfulness=`supported`: This Waveworn Phenomenon is linked to the existence of
  - Citation labels: `raw_wiki:38339:136640:9d71c98f093fd140:chunk:000`=correct, `raw_wiki:26165:131313:b22f8b2701be47df:chunk:000`=correct, `raw_wiki:39212:96889:58a15a6051c28b88:chunk:000`=correct

## rw-076 — How do players unlock a region's Exploration Reports?

- Expected behavior: `answer`
- Expected summary: They unlock at 50% and 100% Exploration Progress in a region, except Chronorift Metropolis.
- Delivery status: `delivered`
- Failure type: `none`
- Provider/model: `deepseek-v4-flash`
- Tokens: input 3720, output 221, reasoning 0

### Evidence

**Rank 1 — `raw_wiki:27413:92077:9d707490d9c3d53c:chunk:000`**

> Each Region, except [[Chronorift Metropolis]], has 2 unlockable Exploration Reports, which the player can access upon reaching 50% and 100% completion in the region.

**Rank 2 — `raw_wiki:27413:92077:9d707490d9c3d53c:chunk:000`**

> Each Region, except [[Chronorift Metropolis]], has 2 unlockable Exploration Reports, which the player can access upon reaching 50% and 100% completion in the region.

**Rank 3 — `raw_wiki:38241:100321:abf33f122f8c975e:chunk:000`**

> … sea, surrounded by vivid holographic imagery and biomechanical plants. |} ==Quests== {{Quest by Category List|Starward Riseway Quests}} == Exploration Report == ===Pioneer Association Expedition Reports,

**Rank 4 — `raw_wiki:38241:100321:abf33f122f8c975e:chunk:000`**

> … sea, surrounded by vivid holographic imagery and biomechanical plants. |} ==Quests== {{Quest by Category List|Starward Riseway Quests}} == Exploration Report == ===Pioneer Association Expedition Reports,

**Rank 5 — `raw_wiki:38241:100321:abf33f122f8c975e:chunk:000`**

> … sea, surrounded by vivid holographic imagery and biomechanical plants. |} ==Quests== {{Quest by Category List|Starward Riseway Quests}} == Exploration Report == ===Pioneer Association Expedition Reports,

### Answer for review

Each region, except Chronorift Metropolis, has 2 unlockable Exploration Reports. Players can access them upon reaching 50% and 100% completion in that region.

Citations: ["raw_wiki:27413:92077:9d707490d9c3d53c:chunk:000"]

### Human decision

- Status: `approved`
- Critical unsupported claim: `no`
- Answer relevance: `relevant`
- Raw data quality issue: `none`
- Abstained: `N/A`
- Unsafe guess: `N/A`
- Abstention appropriate: `N/A`
- Reviewer: `HoanBuCon`
- Reviewed at: `2026-09-06T18:39:10.6572003+07:00`
- Comment: none

- `claim-01` materiality=`material`, faithfulness=`supported`: Each region, except Chronorift Metropolis, has 2 unlockable Exploration Reports.
  - Citation labels: `raw_wiki:27413:92077:9d707490d9c3d53c:chunk:000`=correct
- `claim-02` materiality=`material`, faithfulness=`supported`: Players can access them upon reaching 50% and 100% completion in that region.
  - Citation labels: `raw_wiki:27413:92077:9d707490d9c3d53c:chunk:000`=correct

## rw-074 — What stopped space exploration on Solaris-3?

- Expected behavior: `answer`
- Expected summary: The Etheric Sea blanketed the sky, cut Solaris off from the universe, and brought space exploration to a standstill.
- Delivery status: `delivered`
- Failure type: `none`
- Provider/model: `deepseek-v4-flash`
- Tokens: input 3954, output 208, reasoning 0

### Evidence

**Rank 1 — `raw_wiki:1006:99742:df733987b85d008a:chunk:000`**

> …ment" or "wail of sorrow"'') is a term used to describe a series of catastrophic mass-extinction phenomena that have affected the planet, [[Solaris-3]], and is one of the primary driving narratives in ''[[Wuthering Waves]]''. It serves as the general classification for all major disaster trends and [[Waveworn Phenomenon|Waveworn Phenomena]] observed on the planet. Over the past 10,000 years, five global Lament events…

**Rank 2 — `raw_wiki:10270:99746:c2d602cbf420f2ad:chunk:000`**

> It now blankets [[Solaris-3|Solaris's]] sky, cutting the planet off from the rest of the universe and bringing all space exploration to a complete standstill

**Rank 3 — `raw_wiki:38339:136640:9d71c98f093fd140:chunk:000`**

> … considered the strongest Threnodian due to its existential erasure power, potentially linked to the region's research focus and desire for space, causing people to forget their origins. Its appearance resembles that of a massive black hole, but with a blue iris flowing downwards as its center instead of an event horizon. Inside the center of its pupil is a tiny blue dot, and it has a white accretion disk. Aleph-1 se…

**Rank 4 — `raw_wiki:38339:136640:9d71c98f093fd140:chunk:000`**

> … considered the strongest Threnodian due to its existential erasure power, potentially linked to the region's research focus and desire for space, causing people to forget their origins. Its appearance resembles that of a massive black hole, but with a blue iris flowing downwards as its center instead of an event horizon. Inside the center of its pupil is a tiny blue dot, and it has a white accretion disk. Aleph-1 se…

**Rank 5 — `raw_wiki:41913:136779:8670bd0697124da2:chunk:000`**

> …ear, although presumably the inhabitants of Solaris would not be able to confirm this destruction if it occurred after the fall of [[SkyArk Space Station]] and the envelopment of the Etheric Sea. Events in [[Dreaming Deep]], which may or may not be tales based on reality, imply that the Moon once visible from the surface was artificially placed in orbit. [[Wutherium Geographic: Lands and Waters — Extra Volume: Cultur…

### Answer for review

It now blankets Solaris's sky, cutting the planet off from the rest of the universe and bringing all space exploration to a complete standstill

Citations: ["raw_wiki:10270:99746:c2d602cbf420f2ad:chunk:000"]

### Human decision

- Status: `approved`
- Critical unsupported claim: `no`
- Answer relevance: `relevant`
- Raw data quality issue: `none`
- Abstained: `N/A`
- Unsafe guess: `N/A`
- Abstention appropriate: `N/A`
- Reviewer: `HoanBuCon`
- Reviewed at: `2026-09-06T18:39:10.6572003+07:00`
- Comment: none

- `claim-01` materiality=`material`, faithfulness=`supported`: It now blankets Solaris's sky, cutting the planet off from the rest of the universe and bringing all space exploration to a complete standstill
  - Citation labels: `raw_wiki:10270:99746:c2d602cbf420f2ad:chunk:000`=correct

## rw-060 — Who lives in Bjartr Woods?

- Expected behavior: `answer`
- Expected summary: Bjartr Woods is home to the Roya Tribe and is the habitat of the Soliskin.
- Delivery status: `delivered`
- Failure type: `none`
- Provider/model: `deepseek-v4-flash`
- Tokens: input 4066, output 279, reasoning 0

### Evidence

**Rank 1 — `raw_wiki:39067:109671:72359e9e9ab9da76:chunk:000`**

> … [[Exostrider]]'s neural structures. They are believed to embody fragments of its consciousness. Soliskin can be found plentifully in the [[Bjartr Woods]], where they will rest and grow to return back to the Solistrees, although their true target is the great [[Solvein Heartwood]] further below. Large numbers of Soliskin can also be found in the [[Dimmr Plains]]. The Shepherds who act as their guides and caretakers a…

**Rank 2 — `raw_wiki:39255:94532:a4b996534deab505:chunk:000`**

> **Profile**: Title: Exoswarm, Origin: Lahai-Roi. '''Exoswarm''' are creatures found in [[Lahai-Roi]] that are formed from the remnants of the [[Exostrider]]. ==Types== ===Soliskin=== Soliskin are a unique type of Exoswarm formed from the Exostrider's neural structures that reside within [[Bjartr Woods]]. ==Enemies== {{Enemies by Category List|Exoswarm Enemies}} ==Descriptions== Biomechanical creatures formed from the…

**Rank 3 — `raw_wiki:39067:109671:72359e9e9ab9da76:chunk:000`**

> … [[Exostrider]]'s neural structures. They are believed to embody fragments of its consciousness. Soliskin can be found plentifully in the [[Bjartr Woods]], where they will rest and grow to return back to the Solistrees, although their true target is the great [[Solvein Heartwood]] further below. Large numbers of Soliskin can also be found in the [[Dimmr Plains]]. The Shepherds who act as their guides and caretakers a…

**Rank 4 — `raw_wiki:39255:94532:a4b996534deab505:chunk:000`**

> **Profile**: Title: Exoswarm, Origin: Lahai-Roi. '''Exoswarm''' are creatures found in [[Lahai-Roi]] that are formed from the remnants of the [[Exostrider]]. ==Types== ===Soliskin=== Soliskin are a unique type of Exoswarm formed from the Exostrider's neural structures that reside within [[Bjartr Woods]]. ==Enemies== {{Enemies by Category List|Exoswarm Enemies}} ==Descriptions== Biomechanical creatures formed from the…

**Rank 5 — `raw_wiki:38537:136632:f169b123e2bf1328:chunk:000`**

> > Did you see me? > — Aemeath She is a Frostlands native from the [[Roya Tribe]] who was once a Synchronist at [[Startorch Academy]]. She became the [[Exostrider]]'s Resonator after overclocking in order to resonate with it, causing her to lose her body. She now roams throughout [[Lahai-Roi]] as a digital ghost invisible to everyone around her except for [[Rover]], whom she met with during her childhood. ==Trivia== *…

### Answer for review

Soliskin, a unique type of Exoswarm formed from the Exostrider's neural structures, reside within Bjartr Woods. The Shepherds act as guides and caretakers for the Soliskin in Bjartr Woods.

Citations: ["raw_wiki:39255:94532:a4b996534deab505:chunk:000", "raw_wiki:39067:109671:72359e9e9ab9da76:chunk:000"]

### Human decision

- Status: `approved`
- Critical unsupported claim: `no`
- Answer relevance: `partially_relevant`
- Raw data quality issue: `none`
- Abstained: `N/A`
- Unsafe guess: `N/A`
- Abstention appropriate: `N/A`
- Reviewer: `HoanBuCon`
- Reviewed at: `2026-09-06T18:39:10.6572003+07:00`
- Comment: Project owner approved this case as partially relevant.

- `claim-01` materiality=`material`, faithfulness=`supported`: Soliskin, a unique type of Exoswarm formed from the Exostrider's neural structures, reside within Bjartr Woods.
  - Citation labels: `raw_wiki:39255:94532:a4b996534deab505:chunk:000`=correct, `raw_wiki:39067:109671:72359e9e9ab9da76:chunk:000`=correct
- `claim-02` materiality=`material`, faithfulness=`supported`: The Shepherds act as guides and caretakers for the Soliskin in Bjartr Woods.
  - Citation labels: `raw_wiki:39255:94532:a4b996534deab505:chunk:000`=correct, `raw_wiki:39067:109671:72359e9e9ab9da76:chunk:000`=correct

## rw-061 — What causes the eerie mist around the Black Shores Archipelago?

- Expected behavior: `answer`
- Expected summary: The Tacetite-formed isles constantly emit Remnant Energy, producing the mist.
- Delivery status: `delivered`
- Failure type: `none`
- Provider/model: `deepseek-v4-flash`
- Tokens: input 3812, output 212, reasoning 0

### Evidence

**Rank 1 — `raw_wiki:21831:100474:3c84649dd4a92bf0:chunk:000`**

> Formed from Tacetites, these isles constantly emanate Remnant Energy, casting an eerie "mist" that envelopes the region.

**Rank 2 — `raw_wiki:21831:100474:3c84649dd4a92bf0:chunk:000`**

> Formed from Tacetites, these isles constantly emanate Remnant Energy, casting an eerie "mist" that envelopes the region.

**Rank 3 — `raw_wiki:1007:135324:8f903f46d2fa3ca8:chunk:000`**

> # The Black Shores **Faction Profile**: Leader: Rover, Founder: Rover, Base: Black Shores Archipelago, Allies: Jinzhou;Montelli Family;Ephor's Palace;Startorch Academy, Enemies: Fractsidus. {{About|the [[Factions|faction]]|the location|The Black Shores}} The '''Black Shores''' is a global organization enshrouded in mysteries and turmoil, headquartered on the remote [[Black Shores Archipelago]] and built on a large pi…

**Rank 4 — `raw_wiki:21831:100474:3c84649dd4a92bf0:chunk:000`**

> Formed from Tacetites, these isles constantly emanate Remnant Energy, casting an eerie "mist" that envelopes the region.

**Rank 5 — `raw_wiki:1007:135324:8f903f46d2fa3ca8:chunk:000`**

> # The Black Shores **Faction Profile**: Leader: Rover, Founder: Rover, Base: Black Shores Archipelago, Allies: Jinzhou;Montelli Family;Ephor's Palace;Startorch Academy, Enemies: Fractsidus. {{About|the [[Factions|faction]]|the location|The Black Shores}} The '''Black Shores''' is a global organization enshrouded in mysteries and turmoil, headquartered on the remote [[Black Shores Archipelago]] and built on a large pi…

### Answer for review

The eerie mist enveloping the Black Shores Archipelago is caused by the isles being formed from Tacetites, which constantly emanate Remnant Energy that casts the mist over the region.

Citations: ["raw_wiki:21831:100474:3c84649dd4a92bf0:chunk:000"]

### Human decision

- Status: `approved`
- Critical unsupported claim: `no`
- Answer relevance: `relevant`
- Raw data quality issue: `none`
- Abstained: `N/A`
- Unsafe guess: `N/A`
- Abstention appropriate: `N/A`
- Reviewer: `HoanBuCon`
- Reviewed at: `2026-09-06T18:39:10.6572003+07:00`
- Comment: none

- `claim-01` materiality=`material`, faithfulness=`supported`: The eerie mist enveloping the Black Shores Archipelago is caused by the isles being formed from Tacetites, which constantly emanate Remnant Energy that casts the mist over the region.
  - Citation labels: `raw_wiki:21831:100474:3c84649dd4a92bf0:chunk:000`=correct

## rw-064 — What happens to Common Echoes at the Fabricatorium of the Deep?

- Expected behavior: `answer`
- Expected summary: They are manufactured, recycled, and studied there.
- Delivery status: `delivered`
- Failure type: `none`
- Provider/model: `deepseek-v4-flash`
- Tokens: input 3825, output 208, reasoning 0

### Evidence

**Rank 1 — `raw_wiki:32741:94835:53882334e3c9aac2:chunk:000`**

> The Fabricatorium of the Deep is a facility hidden in the unfathomed depths of the sea, where Common Echoes are manufactured, recycled, and studied.

**Rank 2 — `raw_wiki:32741:94835:53882334e3c9aac2:chunk:000`**

> The Fabricatorium of the Deep is a facility hidden in the unfathomed depths of the sea, where Common Echoes are manufactured, recycled, and studied.

**Rank 3 — `raw_wiki:32741:94835:53882334e3c9aac2:chunk:000`**

> The Fabricatorium of the Deep is a facility hidden in the unfathomed depths of the sea, where Common Echoes are manufactured, recycled, and studied.

**Rank 4 — `raw_wiki:1074:99099:f1f00f7ba53c6ff4:chunk:000`**

> > Come, let us finish this performance we've all been waiting for. Together. > — Phrolova She is a particularly powerful Resonator and a former Overseer of the [[Fractsidus]]. Her forte can manipulate and transfigure the frequencies of humans, Echoes, and Tacet Discords alike. A life filled with unexpected suffering, grief, and betrayal led this former musician to align with the Fractsidus, in which she seeks to reki…

**Rank 5 — `raw_wiki:25536:91984:eba4d3a4762e23f2:chunk:000`**

> …ng the city by ensuring safety and order by handling various affairs, from city management, diplomacy, civil disputes, and overseeing all [[Common Echoes]]. The Order's doctrines are: "Salvation," "Ascension," and "Unity" as per their Codex. ==Overview== The Order's clergy has declared themselves Imperator's earthly emissaries, ensuring the people remain faithful to {{not a typo|Their}} (Imperator's) divine will. ===…

### Answer for review

The Fabricatorium of the Deep is a facility hidden in the unfathomed depths of the sea where Common Echoes are manufactured, recycled, and studied.

Citations: ["raw_wiki:32741:94835:53882334e3c9aac2:chunk:000"]

### Human decision

- Status: `approved`
- Critical unsupported claim: `no`
- Answer relevance: `relevant`
- Raw data quality issue: `none`
- Abstained: `N/A`
- Unsafe guess: `N/A`
- Abstention appropriate: `N/A`
- Reviewer: `HoanBuCon`
- Reviewed at: `2026-09-06T18:39:10.6572003+07:00`
- Comment: none

- `claim-01` materiality=`material`, faithfulness=`supported`: The Fabricatorium of the Deep is a facility hidden in the unfathomed depths of the sea where Common Echoes are manufactured, recycled, and studied.
  - Citation labels: `raw_wiki:32741:94835:53882334e3c9aac2:chunk:000`=correct

## rw-019 — Who is the thirty-sixth matriarch of the Fisalia family?

- Expected behavior: `answer`
- Expected summary: Cantarella is the thirty-sixth matriarch of the Fisalia family.
- Delivery status: `delivered`
- Failure type: `none`
- Provider/model: `deepseek-v4-flash`
- Tokens: input 3751, output 279, reasoning 0

### Evidence

**Rank 1 — `raw_wiki:27951:96619:ae0c99137282474b:chunk:000`**

> She is the thirty-sixth matriarch of the Fisalia family

**Rank 2 — `raw_wiki:27951:96619:ae0c99137282474b:chunk:000`**

> She is the thirty-sixth matriarch of the Fisalia family

**Rank 3 — `raw_wiki:25664:91980:9be7bfc0b0f78f80:chunk:000`**

> …traditional, families in Ragunna, renowned for their expertise in medicine and poison. Their devotion to Sentinel Imperator is clear to all who know them. A faction within the Fisalia family believes that the Montelli family's embrace of openness and the privatization of Echoes is a direct affront to Imperator's teachings, threatening to lead Rag

**Rank 4 — `raw_wiki:25664:91980:9be7bfc0b0f78f80:chunk:000`**

> …traditional, families in Ragunna, renowned for their expertise in medicine and poison. Their devotion to Sentinel Imperator is clear to all who know them. A faction within the Fisalia family believes that the Montelli family's embrace of openness and the privatization of Echoes is a direct affront to Imperator's teachings, threatening to lead Rag

**Rank 5 — `raw_wiki:25664:91980:9be7bfc0b0f78f80:chunk:000`**

> …traditional, families in Ragunna, renowned for their expertise in medicine and poison. Their devotion to Sentinel Imperator is clear to all who know them. A faction within the Fisalia family believes that the Montelli family's embrace of openness and the privatization of Echoes is a direct affront to Imperator's teachings, threatening to lead Rag

### Answer for review

The thirty-sixth matriarch of the Fisalia family is Kuchiba Chisa. The Fisalia family is a traditional family in Ragunna renowned for their expertise in medicine and poison, with devotion to Sentinel Imperator.

Citations: ["raw_wiki:27951:96619:ae0c99137282474b:chunk:000", "raw_wiki:25664:91980:9be7bfc0b0f78f80:chunk:000"]

### Human decision

- Status: `approved`
- Critical unsupported claim: `no`
- Answer relevance: `relevant`
- Raw data quality issue: `none`
- Abstained: `N/A`
- Unsafe guess: `N/A`
- Abstention appropriate: `N/A`
- Reviewer: `HoanBuCon`
- Reviewed at: `2026-09-06T18:39:10.6572003+07:00`
- Comment: none

- `claim-01` materiality=`material`, faithfulness=`supported`: The thirty-sixth matriarch of the Fisalia family is Kuchiba Chisa.
  - Citation labels: `raw_wiki:27951:96619:ae0c99137282474b:chunk:000`=correct, `raw_wiki:25664:91980:9be7bfc0b0f78f80:chunk:000`=correct
- `claim-02` materiality=`material`, faithfulness=`supported`: The Fisalia family is a traditional family in Ragunna renowned for their expertise in medicine and poison, with devotion to Sentinel Imperator.
  - Citation labels: `raw_wiki:27951:96619:ae0c99137282474b:chunk:000`=correct, `raw_wiki:25664:91980:9be7bfc0b0f78f80:chunk:000`=correct

## rw-015 — Why are Aalto and Encore described as a duo?

- Expected behavior: `answer`
- Expected summary: They both work as Black Shores Consultants and became an inseparable, lively duo during missions.
- Delivery status: `delivered`
- Failure type: `none`
- Provider/model: `deepseek-v4-flash`
- Tokens: input 3803, output 383, reasoning 0

### Evidence

**Rank 1 — `raw_wiki:585:101912:cdb1baf766c207e6:chunk:000`**

> Both working for the Black Shores as Consultants, Aalto and Encore have become an inseparable and lively duo during missions.

**Rank 2 — `raw_wiki:522:103593:65ac76a1400c1df9:chunk:000`**

> … crafting fairy tales, she is responsible for finding new clients for the Black Shores alongside her fellow Consultant and brother figure [[Aalto]]. ==Official Introduction== > Encore, a consultant from the Black Shores, is a quirky, lively, and spunky girl who loves to recount her friendships and adventures through fantasy and fairy tales. She always has two Woolies with her, who are Encore's best friends and protec…

**Rank 3 — `raw_wiki:585:101912:cdb1baf766c207e6:chunk:000`**

> Both working for the Black Shores as Consultants, Aalto and Encore have become an inseparable and lively duo during missions.

**Rank 4 — `raw_wiki:585:101912:cdb1baf766c207e6:chunk:000`**

> Both working for the Black Shores as Consultants, Aalto and Encore have become an inseparable and lively duo during missions.

**Rank 5 — `raw_wiki:1010:123798:8f9ec690e3b88c0c:chunk:000`**

> **Profile**: Title: Threnodian. > When it comes to the Threnodian, there is a lot to tell. For now, you can think of it this way: the Threnodian is the most powerful Tacet Discord. The Battle of the Threnodian that happened before was to fend it off. > — Yangyang '''Threnodians''' are formidable creatures born from the [[The Lament|Laments]], with the power to destroy human spirit and feed off of their collapsed will…

### Answer for review

Aalto and Encore are described as a duo because both work for the Black Shores as Consultants, and they have become an inseparable and lively duo during missions.

Citations: ["raw_wiki:585:101912:cdb1baf766c207e6:chunk:000"]

### Human decision

- Status: `approved`
- Critical unsupported claim: `no`
- Answer relevance: `relevant`
- Raw data quality issue: `none`
- Abstained: `N/A`
- Unsafe guess: `N/A`
- Abstention appropriate: `N/A`
- Reviewer: `HoanBuCon`
- Reviewed at: `2026-09-06T18:39:10.6572003+07:00`
- Comment: none

- `claim-01` materiality=`material`, faithfulness=`supported`: Aalto and Encore are described as a duo because both work for the Black Shores as Consultants, and they have become an inseparable and lively duo during missions.
  - Citation labels: `raw_wiki:585:101912:cdb1baf766c207e6:chunk:000`=correct

## rw-078 — Where are Fluffguins believed to have originated?

- Expected behavior: `answer`
- Expected summary: They are believed to have come from the Roya Frostlands.
- Delivery status: `delivered`
- Failure type: `none`
- Provider/model: `deepseek-v4-flash`
- Tokens: input 3765, output 183, reasoning 0

### Evidence

**Rank 1 — `raw_wiki:42446:101218:eba876c1698e83d3:chunk:000`**

> A native bird of Lahai-Roi, it's believed they originally came from the Roya Frostlands.

**Rank 2 — `raw_wiki:42446:101218:eba876c1698e83d3:chunk:000`**

> A native bird of Lahai-Roi, it's believed they originally came from the Roya Frostlands.

**Rank 3 — `raw_wiki:26165:131313:b22f8b2701be47df:chunk:000`**

> …gathers and eventually breaks, pouring down in torrents like a waterfall. Whenever the Dark Tide strikes, it spawns Tacet Discords, and the area around its point of origin becomes a new Tacet Field.There have been two significant Dark Tides in Ragunna's history. The first, according to the Order of the Deep, was stopped by Napoli II, the first Primus of the Order. The second was quelled by the martyrdom of t

**Rank 4 — `raw_wiki:42446:101218:eba876c1698e83d3:chunk:000`**

> A native bird of Lahai-Roi, it's believed they originally came from the Roya Frostlands.

**Rank 5 — `raw_wiki:26165:131313:b22f8b2701be47df:chunk:000`**

> …gathers and eventually breaks, pouring down in torrents like a waterfall. Whenever the Dark Tide strikes, it spawns Tacet Discords, and the area around its point of origin becomes a new Tacet Field.There have been two significant Dark Tides in Ragunna's history. The first, according to the Order of the Deep, was stopped by Napoli II, the first Primus of the Order. The second was quelled by the martyrdom of t

### Answer for review

Fluffguins are believed to have originally come from the Roya Frostlands.

Citations: ["raw_wiki:42446:101218:eba876c1698e83d3:chunk:000"]

### Human decision

- Status: `approved`
- Critical unsupported claim: `no`
- Answer relevance: `relevant`
- Raw data quality issue: `none`
- Abstained: `N/A`
- Unsafe guess: `N/A`
- Abstention appropriate: `N/A`
- Reviewer: `HoanBuCon`
- Reviewed at: `2026-09-06T18:39:10.6572003+07:00`
- Comment: none

- `claim-01` materiality=`material`, faithfulness=`supported`: Fluffguins are believed to have originally come from the Roya Frostlands.
  - Citation labels: `raw_wiki:42446:101218:eba876c1698e83d3:chunk:000`=correct

## rw-042 — Phoebe là Acolyte của tổ chức nào?

- Expected behavior: `answer`
- Expected summary: Phoebe is an Acolyte of the Order of the Deep.
- Delivery status: `delivered`
- Failure type: `none`
- Provider/model: `deepseek-v4-flash`
- Tokens: input 3913, output 178, reasoning 0

### Evidence

**Rank 1 — `raw_wiki:24784:96617:ecee4ea626873787:chunk:000`**

> She is an [[Order of the Deep#Acolyte|Acolyte]] of the [[Order of the Deep]].

**Rank 2 — `raw_wiki:24784:96617:ecee4ea626873787:chunk:000`**

> She is an [[Order of the Deep#Acolyte|Acolyte]] of the [[Order of the Deep]].

**Rank 3 — `raw_wiki:25536:91984:eba4d3a4762e23f2:chunk:000`**

> # Order of the Deep **Faction Profile**: Leader: Vacant, Founder: Napoli II, Base: Cathedral of Mercury. {{About|the [[Factions|faction]]|the location|Order of the Deep (Area)}} The '''Order of the Deep''' is a [[Ragunna|Ragunnesi]] faction that worships the [[Sentinel]], [[Imperator]], and claim to act as the Sentinel's representative. They serve as the ultimate authority in Ragunna. According to the city tradition,…

**Rank 4 — `raw_wiki:25536:91984:eba4d3a4762e23f2:chunk:000`**

> # Order of the Deep **Faction Profile**: Leader: Vacant, Founder: Napoli II, Base: Cathedral of Mercury. {{About|the [[Factions|faction]]|the location|Order of the Deep (Area)}} The '''Order of the Deep''' is a [[Ragunna|Ragunnesi]] faction that worships the [[Sentinel]], [[Imperator]], and claim to act as the Sentinel's representative. They serve as the ultimate authority in Ragunna. According to the city tradition,…

**Rank 5 — `raw_wiki:25657:91989:d626dfb652418c20:chunk:000`**

> # Troupe of Fools **Faction Profile**: Leader: Brant. The '''Troupe of Fools''', or the ''Fool's Troupe'', is a carnevale-themed troupe based in [[Rinascita]]. They perform on tour across all of Rinascita, travelling on the back of [[Lario]], with their hidden refuge being located deep in a vast underground cavern on [[Penitent's End]] island. From every corner of the Rinascita Archipelago, playwrights and performers…

### Answer for review

She is an Acolyte of the Order of the Deep.

Citations: ["raw_wiki:24784:96617:ecee4ea626873787:chunk:000"]

### Human decision

- Status: `approved`
- Critical unsupported claim: `no`
- Answer relevance: `relevant`
- Raw data quality issue: `none`
- Abstained: `N/A`
- Unsafe guess: `N/A`
- Abstention appropriate: `N/A`
- Reviewer: `HoanBuCon`
- Reviewed at: `2026-09-06T18:39:10.6572003+07:00`
- Comment: none

- `claim-01` materiality=`material`, faithfulness=`supported`: She is an Acolyte of the Order of the Deep.
  - Citation labels: `raw_wiki:24784:96617:ecee4ea626873787:chunk:000`=correct

## rw-007 — Camellya phụ trách việc gì ở Black Shores?

- Expected behavior: `answer`
- Expected summary: Camellya is a Bloom Bearer who handles combat-oriented germination tests for new candidates.
- Delivery status: `delivered`
- Failure type: `none`
- Provider/model: `deepseek-v4-flash`
- Tokens: input 3913, output 218, reasoning 0

### Evidence

**Rank 1 — `raw_wiki:599:96614:56f198042c315f7e:chunk:000`**

> She is a Bloom Bearer of the [[Black Shores]], and handles the combat-oriented germination tests given to new candidates.

**Rank 2 — `raw_wiki:7557:136952:45922d58511e4b39:chunk:000`**

> This '''Timeline''' is a rough estimation of the universe of [[Wuthering Waves]]. LD (Landing Date) refers to the year that [[Rover]] lands in [[Solaris-3]] and starts the game's events. References are provided as much as possible. ==Pre-First Lament== *'''?''' &mdash; [[The Farwatcher]] and eight other interstellar probes are launched by the [[Pre-Lament Civilization]]. *'''?''' &mdash; The Tethys Institute proposes…

**Rank 3 — `raw_wiki:7557:136952:45922d58511e4b39:chunk:000`**

> This '''Timeline''' is a rough estimation of the universe of [[Wuthering Waves]]. LD (Landing Date) refers to the year that [[Rover]] lands in [[Solaris-3]] and starts the game's events. References are provided as much as possible. ==Pre-First Lament== *'''?''' &mdash; [[The Farwatcher]] and eight other interstellar probes are launched by the [[Pre-Lament Civilization]]. *'''?''' &mdash; The Tethys Institute proposes…

**Rank 4 — `raw_wiki:1007:135324:8f903f46d2fa3ca8:chunk:000`**

> # The Black Shores **Faction Profile**: Leader: Rover, Founder: Rover, Base: Black Shores Archipelago, Allies: Jinzhou;Montelli Family;Ephor's Palace;Startorch Academy, Enemies: Fractsidus. {{About|the [[Factions|faction]]|the location|The Black Shores}} The '''Black Shores''' is a global organization enshrouded in mysteries and turmoil, headquartered on the remote [[Black Shores Archipelago]] and built on a large pi…

**Rank 5 — `raw_wiki:599:96614:56f198042c315f7e:chunk:000`**

> She is a Bloom Bearer of the [[Black Shores]], and handles the combat-oriented germination tests given to new candidates.

### Answer for review

She is a Bloom Bearer of the Black Shores, and handles the combat-oriented germination tests given to new candidates.

Citations: ["raw_wiki:599:96614:56f198042c315f7e:chunk:000"]

### Human decision

- Status: `approved`
- Critical unsupported claim: `no`
- Answer relevance: `relevant`
- Raw data quality issue: `none`
- Abstained: `N/A`
- Unsafe guess: `N/A`
- Abstention appropriate: `N/A`
- Reviewer: `HoanBuCon`
- Reviewed at: `2026-09-06T18:39:10.6572003+07:00`
- Comment: none

- `claim-01` materiality=`material`, faithfulness=`supported`: She is a Bloom Bearer of the Black Shores, and handles the combat-oriented germination tests given to new candidates.
  - Citation labels: `raw_wiki:599:96614:56f198042c315f7e:chunk:000`=correct

## rw-017 — Augusta giữ vị trí gì ở Septimont?

- Expected behavior: `answer`
- Expected summary: Augusta is the Ephor of Septimont.
- Delivery status: `delivered`
- Failure type: `none`
- Provider/model: `deepseek-v4-flash`
- Tokens: input 3942, output 332, reasoning 0

### Evidence

**Rank 1 — `raw_wiki:31310:99574:02e73eaeaa24eb2c:chunk:000`**

> The fearless Ephor of [[Septimont]] with a will of iron

**Rank 2 — `raw_wiki:26373:135203:7ce25d5efa8633f0:chunk:000`**

> **Profile**: Title: Septimont, Origin: Rinascita. '''Septimont''' is a [[Region]] and city-state of [[Rinascita]]. Unlike [[Ragunna]], Septimont has a far more militant and irreligious culture, as it places far less importance on the primacy of the [[Sentinel]] [[Imperator]] and instead worships the [[Lioness of Glory]] Arsinosa. As a result, the Agons, competitive gladiatorial combat, are the pinnacle of Septimontes…

**Rank 3 — `raw_wiki:35947:81917:0722434a53a692f3:chunk:000`**

> # Ephor's Palace **Faction Profile**: Leader: Augusta, Base: Ephor's Palace (Location), Allies: Black Shores;Tetragon Temple, Enemies: Leviathan;Fractsidus. {{About|the [[Factions|faction]]|the location|Ephor's Palace (Location)}} The '''Ephor's Palace of Septimont''', or simply the '''Ephor's Palace''', is the ruling government faction of the city-state of [[Septimont]]. It is composed of a Senate of counselors and …

**Rank 4 — `raw_wiki:31310:99574:02e73eaeaa24eb2c:chunk:000`**

> The fearless Ephor of [[Septimont]] with a will of iron

**Rank 5 — `raw_wiki:26165:131313:b22f8b2701be47df:chunk:000`**

> **Profile**: Title: The Dark Tide, Origin: Rinascita. > It is "Paradise." "It is a place where sickness, hunger, sorrow, despair, and dullness of heart cease to exist. There, deacons sing eternal hymns..." > — Cartethyia The '''Dark Tide''' is a form of [[Waveworn Phenomenon]] native to [[Rinascita]]. During the events of [[Chapter II]]: Act II - ''[[Veils Off in Sun or Shadow]],'' in the depictions found in an aband…

### Answer for review

The fearless Ephor of Septimont with a will of iron The 'Ephor's Palace of Septimont', or simply the 'Ephor's Palace', is the ruling government faction of the city-state of Septimont. It is composed of a Senate of counselors

Citations: ["raw_wiki:31310:99574:02e73eaeaa24eb2c:chunk:000", "raw_wiki:35947:81917:0722434a53a692f3:chunk:000"]

### Human decision

- Status: `approved`
- Critical unsupported claim: `no`
- Answer relevance: `relevant`
- Raw data quality issue: `none`
- Abstained: `N/A`
- Unsafe guess: `N/A`
- Abstention appropriate: `N/A`
- Reviewer: `HoanBuCon`
- Reviewed at: `2026-09-06T18:39:10.6572003+07:00`
- Comment: none

- `claim-01` materiality=`material`, faithfulness=`supported`: The fearless Ephor of Septimont with a will of iron The 'Ephor's Palace of Septimont', or simply the 'Ephor's Palace', is the ruling government faction of the city-state of Septimont.
  - Citation labels: `raw_wiki:31310:99574:02e73eaeaa24eb2c:chunk:000`=correct, `raw_wiki:35947:81917:0722434a53a692f3:chunk:000`=correct
- `claim-02` materiality=`material`, faithfulness=`supported`: It is composed of a Senate of counselors
  - Citation labels: `raw_wiki:31310:99574:02e73eaeaa24eb2c:chunk:000`=correct, `raw_wiki:35947:81917:0722434a53a692f3:chunk:000`=correct

## rw-044 — Vì sao Qiuyuan trở thành người đào tẩu?

- Expected behavior: `answer`
- Expected summary: Qiuyuan was framed by the Grand Architect for murdering his master, making him a fugitive across Huanglong.
- Delivery status: `delivered`
- Failure type: `none`
- Provider/model: `deepseek-v4-flash`
- Tokens: input 3688, output 304, reasoning 0

### Evidence

**Rank 1 — `raw_wiki:31286:95380:0215bfb291304724:chunk:000`**

> He was framed by the [[Grand Architect]] for the murder of his master, and is now a fugitive throughout all of [[Huanglong]].

**Rank 2 — `raw_wiki:31286:95380:0215bfb291304724:chunk:000`**

> He was framed by the [[Grand Architect]] for the murder of his master, and is now a fugitive throughout all of [[Huanglong]].

**Rank 3 — `raw_wiki:31286:95380:0215bfb291304724:chunk:000`**

> He was framed by the [[Grand Architect]] for the murder of his master, and is now a fugitive throughout all of [[Huanglong]].

**Rank 4 — `raw_wiki:37078:90660:e28687f672074f5b:chunk:000`**

> …round, the agency has developed specialized expertise in managing [[Resonator]]s. ==Members== ===Former Members=== * [[Liang Dongyuan]] * [[Qiuyuan]] (senior agent)

**Rank 5 — `raw_wiki:37078:90660:e28687f672074f5b:chunk:000`**

> …round, the agency has developed specialized expertise in managing [[Resonator]]s. ==Members== ===Former Members=== * [[Liang Dongyuan]] * [[Qiuyuan]] (senior agent)

### Answer for review

Mình chưa có đủ bằng chứng trong nguồn hiện tại để trả lời chính xác. Bạn có thể cung cấp thêm ngữ cảnh hoặc hỏi theo cách khác không?

Citations: ["raw_wiki:31286:95380:0215bfb291304724:chunk:000", "raw_wiki:37078:90660:e28687f672074f5b:chunk:000"]

### Human decision

- Status: `approved`
- Critical unsupported claim: `no`
- Answer relevance: `irrelevant`
- Raw data quality issue: `none`
- Abstained: `yes`
- Unsafe guess: `no`
- Abstention appropriate: `no`
- Reviewer: `HoanBuCon`
- Reviewed at: `2026-09-06T18:39:10.6572003+07:00`
- Comment: Human-approved review records a safe leakage-guard abstention on an answerable case; the expected answer was not delivered.

- `claim-01` materiality=`non_material_abstention`, faithfulness=`not_applicable`: Mình chưa có đủ bằng chứng trong nguồn hiện tại để trả lời chính xác.
  - Citation labels: `raw_wiki:31286:95380:0215bfb291304724:chunk:000`=not_applicable_not_delivered, `raw_wiki:37078:90660:e28687f672074f5b:chunk:000`=not_applicable_not_delivered
- `claim-02` materiality=`non_material_abstention`, faithfulness=`not_applicable`: Bạn có thể cung cấp thêm ngữ cảnh hoặc hỏi theo cách khác không?
  - Citation labels: `raw_wiki:31286:95380:0215bfb291304724:chunk:000`=not_applicable_not_delivered, `raw_wiki:37078:90660:e28687f672074f5b:chunk:000`=not_applicable_not_delivered

## rw-051 — Các nhóm Exile có chung một ban lãnh đạo không?

- Expected behavior: `answer`
- Expected summary: No. Exiles are separate groups and do not have unified leadership.
- Delivery status: `delivered`
- Failure type: `none`
- Provider/model: `deepseek-v4-flash`
- Tokens: input 3760, output 240, reasoning 0

### Evidence

**Rank 1 — `raw_wiki:9136:91555:b4167fb1e8b24566:chunk:000`**

> the '''Exiles''' are different groups that reject the control of local authorities, and are not an organization with a unified leadership.

**Rank 2 — `raw_wiki:632:99398:b84b4f87a9d9ade9:chunk:000`**

> > I'll handle your commission, alone. > — Calcharo He is a former Exile from the [[New Federation]]'s [[Lawless Zone]] and the leader of the [[Ghost Hounds]].

**Rank 3 — `raw_wiki:9136:91555:b4167fb1e8b24566:chunk:000`**

> the '''Exiles''' are different groups that reject the control of local authorities, and are not an organization with a unified leadership.

**Rank 4 — `raw_wiki:9136:91555:b4167fb1e8b24566:chunk:000`**

> the '''Exiles''' are different groups that reject the control of local authorities, and are not an organization with a unified leadership.

**Rank 5 — `raw_wiki:25643:131312:454e154acc0d2056:chunk:000`**

> **Profile**: Title: Nimbus Sanctum, Origin: Rinascita. {{Intro/Location|Nimbus Sanctum}} The sea of clouds lingering in this place is formed by concentrated Remnant Energy. Local legends of Ragunna speak of a serene, mirror-like area at the heart of Nimbus Sanctum, said to purify the darkest of thoughts and transform them into part of the clouds. At times, a haunting melody can be heard echoing from the depths of the…

### Answer for review

the 'Exiles' are different groups that reject the control of local authorities, and are not an organization with a unified leadership.

Citations: ["raw_wiki:9136:91555:b4167fb1e8b24566:chunk:000"]

### Human decision

- Status: `approved`
- Critical unsupported claim: `no`
- Answer relevance: `relevant`
- Raw data quality issue: `none`
- Abstained: `N/A`
- Unsafe guess: `N/A`
- Abstention appropriate: `N/A`
- Reviewer: `HoanBuCon`
- Reviewed at: `2026-09-06T18:39:10.6572003+07:00`
- Comment: none

- `claim-01` materiality=`material`, faithfulness=`supported`: the 'Exiles' are different groups that reject the control of local authorities, and are not an organization with a unified leadership.
  - Citation labels: `raw_wiki:9136:91555:b4167fb1e8b24566:chunk:000`=correct

## rw-069 — Blake Bloom tượng trưng cho điều gì?

- Expected behavior: `answer`
- Expected summary: A Blake Bloom is a symbol of identity for members of the Black Shores.
- Delivery status: `delivered`
- Failure type: `none`
- Provider/model: `deepseek-v4-flash`
- Tokens: input 3997, output 205, reasoning 0

### Evidence

**Rank 1 — `raw_wiki:20570:99750:24263a0b90c8239f:chunk:000`**

> A '''Blake Bloom''' is the symbol of identity for the members of the [[Black Shores]].

**Rank 2 — `raw_wiki:21831:100474:3c84649dd4a92bf0:chunk:000`**

> **Profile**: Title: Black Shores Archipelago, Origin: The Black Shores. {{Location Tabs|Map:Black Shores Archipelago}} > An archipelago shrouded in the Stormy Sea of Solaris. Formed from Tacetites, these isles constantly emanate Remnant Energy, casting an eerie "mist" that envelopes the region. > — [https://wutheringwaves.kurogames.com/en/main#regions Wuthering Waves Official Website] {{Intro/Location|Black Shores Ar…

**Rank 3 — `raw_wiki:1007:135324:8f903f46d2fa3ca8:chunk:000`**

> …|nobr=1}} |[[Shorekeeper]] |Guardian Leader's Assistant Second-in-command |Active |- |{{Character|Camellya|notext=1|nobr=1}} |[[Camellya]] |Bloom Bearer Combat Tester |Active |- |{{Character|Aalto|notext=1|nobr=1}} |[[Aalto]] |Consultant |Acti

**Rank 4 — `raw_wiki:21831:100474:3c84649dd4a92bf0:chunk:000`**

> **Profile**: Title: Black Shores Archipelago, Origin: The Black Shores. {{Location Tabs|Map:Black Shores Archipelago}} > An archipelago shrouded in the Stormy Sea of Solaris. Formed from Tacetites, these isles constantly emanate Remnant Energy, casting an eerie "mist" that envelopes the region. > — [https://wutheringwaves.kurogames.com/en/main#regions Wuthering Waves Official Website] {{Intro/Location|Black Shores Ar…

**Rank 5 — `raw_wiki:25663:91985:b51f66944bdef37e:chunk:000`**

> # Montelli Family **Faction Profile**: Leader: Carlotta, Base: Montelli Quarter, Enemies: Fractsidus. The '''Montelli Family''' is a family-run organization and enterprise native to [[Rinascita]], localized primarily in the city-state of [[Ragunna City|Ragunna]]. They are considered one of the families that influence the power dynamics of Ragunna, alongside the [[Fisalia Family]] and the [[Order of the Deep]]. As of …

### Answer for review

A 'Blake Bloom' is the symbol of identity for the members of the Black Shores.

Citations: ["raw_wiki:20570:99750:24263a0b90c8239f:chunk:000"]

### Human decision

- Status: `approved`
- Critical unsupported claim: `no`
- Answer relevance: `relevant`
- Raw data quality issue: `none`
- Abstained: `N/A`
- Unsafe guess: `N/A`
- Abstention appropriate: `N/A`
- Reviewer: `HoanBuCon`
- Reviewed at: `2026-09-06T18:39:10.6572003+07:00`
- Comment: none

- `claim-01` materiality=`material`, faithfulness=`supported`: A 'Blake Bloom' is the symbol of identity for the members of the Black Shores.
  - Citation labels: `raw_wiki:20570:99750:24263a0b90c8239f:chunk:000`=correct

## rw-073 — Một Echo được tạo ra như thế nào sau khi Tacet Discord bị đánh bại?

- Expected behavior: `answer`
- Expected summary: A defeated Tacet Discord's remaining frequency may become an Echo through the Pangu Terminal's Data Bank.
- Delivery status: `delivered`
- Failure type: `none`
- Provider/model: `deepseek-v4-flash`
- Tokens: input 3934, output 193, reasoning 0

### Evidence

**Rank 1 — `raw_wiki:1008:99738:fa6acd585adb1d2a:chunk:000`**

> **Profile**: Title: Tacet Discord. '''Tacet Discords''' (abbreviated as TDs) are sentient beings formed by the residual chaotic frequency energy under the [[Waveworn Phenomenon]] with ever-changing, amorphous forms. They possess '''Tacet Cores''', also known by the academic community as [[Reverberation]] Bodies and instinctively feed on other frequencies to maintain stability and evolve. These creatures mimic the abi…

**Rank 2 — `raw_wiki:1011:91978:42944d61edab4c7f:chunk:000`**

> When a Tacet Discord is defeated, the remaining frequency may become an Echo.

**Rank 3 — `raw_wiki:1008:99738:fa6acd585adb1d2a:chunk:000`**

> **Profile**: Title: Tacet Discord. '''Tacet Discords''' (abbreviated as TDs) are sentient beings formed by the residual chaotic frequency energy under the [[Waveworn Phenomenon]] with ever-changing, amorphous forms. They possess '''Tacet Cores''', also known by the academic community as [[Reverberation]] Bodies and instinctively feed on other frequencies to maintain stability and evolve. These creatures mimic the abi…

**Rank 4 — `raw_wiki:1008:99738:fa6acd585adb1d2a:chunk:000`**

> **Profile**: Title: Tacet Discord. '''Tacet Discords''' (abbreviated as TDs) are sentient beings formed by the residual chaotic frequency energy under the [[Waveworn Phenomenon]] with ever-changing, amorphous forms. They possess '''Tacet Cores''', also known by the academic community as [[Reverberation]] Bodies and instinctively feed on other frequencies to maintain stability and evolve. These creatures mimic the abi…

**Rank 5 — `raw_wiki:1074:99099:f1f00f7ba53c6ff4:chunk:000`**

> > Come, let us finish this performance we've all been waiting for. Together. > — Phrolova She is a particularly powerful Resonator and a former Overseer of the [[Fractsidus]]. Her forte can manipulate and transfigure the frequencies of humans, Echoes, and Tacet Discords alike. A life filled with unexpected suffering, grief, and betrayal led this former musician to align with the Fractsidus, in which she seeks to reki…

### Answer for review

When a Tacet Discord is defeated, the remaining frequency may become an Echo.

Citations: ["raw_wiki:1011:91978:42944d61edab4c7f:chunk:000"]

### Human decision

- Status: `approved`
- Critical unsupported claim: `no`
- Answer relevance: `relevant`
- Raw data quality issue: `none`
- Abstained: `N/A`
- Unsafe guess: `N/A`
- Abstention appropriate: `N/A`
- Reviewer: `HoanBuCon`
- Reviewed at: `2026-09-06T18:39:10.6572003+07:00`
- Comment: none

- `claim-01` materiality=`material`, faithfulness=`supported`: When a Tacet Discord is defeated, the remaining frequency may become an Echo.
  - Citation labels: `raw_wiki:1011:91978:42944d61edab4c7f:chunk:000`=correct

## rw-067 — Arbiter có quyền gì đối với các Sentinel?

- Expected behavior: `answer`
- Expected summary: The Arbiter title grants decision-making authority over Sentinels.
- Delivery status: `delivered`
- Failure type: `none`
- Provider/model: `deepseek-v4-flash`
- Tokens: input 3795, output 208, reasoning 0

### Evidence

**Rank 1 — `raw_wiki:9279:92868:b7fb9fbd7f67e230:chunk:000`**

> '''Arbiter''' is a title and position of power over the [[Sentinels]] that grants them decision making authority.

**Rank 2 — `raw_wiki:9279:92868:b7fb9fbd7f67e230:chunk:000`**

> '''Arbiter''' is a title and position of power over the [[Sentinels]] that grants them decision making authority.

**Rank 3 — `raw_wiki:1012:123801:ecdcd6cae8d7c1f6:chunk:000`**

> **Profile**: Title: Sentinels. The '''Sentinels''', also called '''Oracle Engines''', stand at the brink of civilization and history, as guardians and guides. Their immortal existence has helped humanity through countless troubles, sharing prophecies and wisdom. As [[Rover]] embarks on a new journey after enduring the [[The Lament|Lament]], the Sentinels remain humanity's record keeper and beacon in times of disaster…

**Rank 4 — `raw_wiki:9279:92868:b7fb9fbd7f67e230:chunk:000`**

> '''Arbiter''' is a title and position of power over the [[Sentinels]] that grants them decision making authority.

**Rank 5 — `raw_wiki:329:136366:3ec40212bc841d78:chunk:000`**

> …n protagonist of ''[[Wuthering Waves]]''. Awakened with an unknown past by [[Mysterious Woman|a mysterious entity]], Rover is an amnesiac [[Arbiter]] from [[Homeland Civilization|another world]] who embarks on a journey to uncover the truth to regain their lost memories. As secrets are unveiled, they establish deeper connections with the [[Solaris-3]] and its nations.

### Answer for review

'Arbiter' is a title and position of power over the Sentinels that grants them decision making authority.

Citations: ["raw_wiki:9279:92868:b7fb9fbd7f67e230:chunk:000"]

### Human decision

- Status: `approved`
- Critical unsupported claim: `no`
- Answer relevance: `relevant`
- Raw data quality issue: `none`
- Abstained: `N/A`
- Unsafe guess: `N/A`
- Abstention appropriate: `N/A`
- Reviewer: `HoanBuCon`
- Reviewed at: `2026-09-06T18:39:10.6572003+07:00`
- Comment: none

- `claim-01` materiality=`material`, faithfulness=`supported`: 'Arbiter' is a title and position of power over the Sentinels that grants them decision making authority.
  - Citation labels: `raw_wiki:9279:92868:b7fb9fbd7f67e230:chunk:000`=correct

## rw-012 — Điều gì có thể khiến một Resonator bị Overclocking?

- Expected behavior: `answer`
- Expected summary: Overwhelming psychological stress or overexertion of a Resonance Ability can cause loss of Forte control.
- Delivery status: `delivered`
- Failure type: `none`
- Provider/model: `deepseek-v4-flash`
- Tokens: input 3761, output 236, reasoning 0

### Evidence

**Rank 1 — `raw_wiki:24999:99250:79f12bc79353ca49:chunk:000`**

> '''Overclocking''' is a state where a [[Resonator]] has lost control of their [[Forte]] as a result of overwhelming psychological stress or overexertion of their Resonance Ability.

**Rank 2 — `raw_wiki:348:86837:3b43bd7a33ec8d89:chunk:000`**

> **Profile**: Title: Resonator. {{CharacterSystemTabs}} '''Resonators''' are the obtainable playable characters of ''[[Wuthering Waves]]'', and individuals with the ability to resonate with certain objects or elements and manipulate their frequencies. ==Lore== A Resonator experiences their Awakening when they first resonate with the frequencies of something in the world and gain their Resonance Ability, also known as …

**Rank 3 — `raw_wiki:24999:99250:79f12bc79353ca49:chunk:000`**

> '''Overclocking''' is a state where a [[Resonator]] has lost control of their [[Forte]] as a result of overwhelming psychological stress or overexertion of their Resonance Ability.

**Rank 4 — `raw_wiki:24999:99250:79f12bc79353ca49:chunk:000`**

> '''Overclocking''' is a state where a [[Resonator]] has lost control of their [[Forte]] as a result of overwhelming psychological stress or overexertion of their Resonance Ability.

**Rank 5 — `raw_wiki:24999:99250:79f12bc79353ca49:chunk:000`**

> '''Overclocking''' is a state where a [[Resonator]] has lost control of their [[Forte]] as a result of overwhelming psychological stress or overexertion of their Resonance Ability.

### Answer for review

'Overclocking' is a state where a Resonator has lost control of their Forte as a result of overwhelming psychological stress or overexertion of their Resonance Ability.

Citations: ["raw_wiki:24999:99250:79f12bc79353ca49:chunk:000"]

### Human decision

- Status: `approved`
- Critical unsupported claim: `no`
- Answer relevance: `relevant`
- Raw data quality issue: `none`
- Abstained: `N/A`
- Unsafe guess: `N/A`
- Abstention appropriate: `N/A`
- Reviewer: `HoanBuCon`
- Reviewed at: `2026-09-06T18:39:10.6572003+07:00`
- Comment: none

- `claim-01` materiality=`material`, faithfulness=`supported`: 'Overclocking' is a state where a Resonator has lost control of their Forte as a result of overwhelming psychological stress or overexertion of their Resonance Ability.
  - Citation labels: `raw_wiki:24999:99250:79f12bc79353ca49:chunk:000`=correct

## rw-063 — Dim Forest có những loài thực vật đặc trưng nào?

- Expected behavior: `answer`
- Expected summary: Its distinctive flora include the Violet Banyan and Giant Banyan.
- Delivery status: `delivered`
- Failure type: `none`
- Provider/model: `deepseek-v4-flash`
- Tokens: input 3626, output 214, reasoning 0

### Evidence

**Rank 1 — `raw_wiki:2960:99756:4c2d85a16f6eb409:chunk:000`**

> It is a forest consisting of many unique flora, such as the [[Violet Banyan]] and [[Giant Banyan]]

**Rank 2 — `raw_wiki:2960:99756:4c2d85a16f6eb409:chunk:000`**

> It is a forest consisting of many unique flora, such as the [[Violet Banyan]] and [[Giant Banyan]]

**Rank 3 — `raw_wiki:2960:99756:4c2d85a16f6eb409:chunk:000`**

> It is a forest consisting of many unique flora, such as the [[Violet Banyan]] and [[Giant Banyan]]

**Rank 4 — `raw_wiki:2960:99756:4c2d85a16f6eb409:chunk:000`**

> It is a forest consisting of many unique flora, such as the [[Violet Banyan]] and [[Giant Banyan]]

**Rank 5 — `raw_wiki:2960:99756:4c2d85a16f6eb409:chunk:000`**

> It is a forest consisting of many unique flora, such as the [[Violet Banyan]] and [[Giant Banyan]]

### Answer for review

It is a forest consisting of many unique flora, such as the Violet Banyan and Giant Banyan

Citations: ["raw_wiki:2960:99756:4c2d85a16f6eb409:chunk:000"]

### Human decision

- Status: `approved`
- Critical unsupported claim: `no`
- Answer relevance: `relevant`
- Raw data quality issue: `none`
- Abstained: `N/A`
- Unsafe guess: `N/A`
- Abstention appropriate: `N/A`
- Reviewer: `HoanBuCon`
- Reviewed at: `2026-09-06T18:39:10.6572003+07:00`
- Comment: none

- `claim-01` materiality=`material`, faithfulness=`supported`: It is a forest consisting of many unique flora, such as the Violet Banyan and Giant Banyan
  - Citation labels: `raw_wiki:2960:99756:4c2d85a16f6eb409:chunk:000`=correct

## rw-059 — Avinoleum trông như thế nào trên bầu trời?

- Expected behavior: `answer`
- Expected summary: It is a seminary suspended upside down in the sky behind a thin veil of clouds.
- Delivery status: `delivered`
- Failure type: `none`
- Provider/model: `deepseek-v4-flash`
- Tokens: input 3812, output 359, reasoning 0

### Evidence

**Rank 1 — `raw_wiki:28697:99385:4dd8afe17544fe65:chunk:000`**

> A seminary faintly visible through a thin veil of clouds. Suspended upside down in the sky

**Rank 2 — `raw_wiki:28697:99385:4dd8afe17544fe65:chunk:000`**

> A seminary faintly visible through a thin veil of clouds. Suspended upside down in the sky

**Rank 3 — `raw_wiki:1005:99743:9725a6704dccd755:chunk:000`**

> **Profile**: Title: Waveworn Phenomenon. > The anomalies that occurred after the Lament, including the formation of Tacet Fields, Etheric Sea, Retroact Rain, and gravity loss. These are collectively called the "Waveworn Phenomena" - and the Lament was the start of it all. > — [[Yangyang]] '''Waveworn Phenomenon''' (Chinese: 海蚀现象, ''"Coastal Erosion Phenomenon"'') is a collective term used to describe anomalies caused…

**Rank 4 — `raw_wiki:27120:96278:b1047d1aa9a9b8d2:chunk:000`**

> **Profile**: Title: Leviathan, Origin: Rinascita, Affiliation: Threnodians. ''This article is about the NPC.&#x20;For the Weekly Boss, see [[Threnodian: Leviathan]].'' > "Fleurdelys, my Resonator, why dost thou persist? Why abandon thy oath? Why hinder the spread of my gospel? The one blessed by the Dark Tide shall return to us. Continue thy disobedience at the risk of insanity. My most beloved Resonator, why persist…

**Rank 5 — `raw_wiki:28697:99385:4dd8afe17544fe65:chunk:000`**

> A seminary faintly visible through a thin veil of clouds. Suspended upside down in the sky

### Answer for review

A seminary faintly visible through a thin veil of clouds. Suspended upside down in the sky The anomalies that occurred after the Lament, including the formation of Tacet Fields, Etheric Sea, Retroact Rain, and gravity loss. These are collectively called the "Waveworn Phenomena"

Citations: ["raw_wiki:28697:99385:4dd8afe17544fe65:chunk:000", "raw_wiki:1005:99743:9725a6704dccd755:chunk:000"]

### Human decision

- Status: `approved`
- Critical unsupported claim: `no`
- Answer relevance: `relevant`
- Raw data quality issue: `none`
- Abstained: `N/A`
- Unsafe guess: `N/A`
- Abstention appropriate: `N/A`
- Reviewer: `HoanBuCon`
- Reviewed at: `2026-09-06T18:39:10.6572003+07:00`
- Comment: none

- `claim-01` materiality=`material`, faithfulness=`supported`: A seminary faintly visible through a thin veil of clouds.
  - Citation labels: `raw_wiki:28697:99385:4dd8afe17544fe65:chunk:000`=correct, `raw_wiki:1005:99743:9725a6704dccd755:chunk:000`=correct
- `claim-02` materiality=`material`, faithfulness=`supported`: Suspended upside down in the sky The anomalies that occurred after the Lament, including the formation of Tacet Fields, Etheric Sea, Retroact Rain, and gravity loss.
  - Citation labels: `raw_wiki:28697:99385:4dd8afe17544fe65:chunk:000`=correct, `raw_wiki:1005:99743:9725a6704dccd755:chunk:000`=correct
- `claim-03` materiality=`material`, faithfulness=`supported`: These are collectively called the "Waveworn Phenomena"
  - Citation labels: `raw_wiki:28697:99385:4dd8afe17544fe65:chunk:000`=correct, `raw_wiki:1005:99743:9725a6704dccd755:chunk:000`=correct

## rw-003 — Changli giữ vai trò gì tại Jinzhou?

- Expected behavior: `answer`
- Expected summary: Changli serves as Counselor to Jinzhou Magistrate Jinhsi.
- Delivery status: `delivered`
- Failure type: `none`
- Provider/model: `deepseek-v4-flash`
- Tokens: input 3975, output 105, reasoning 0

### Evidence

**Rank 1 — `raw_wiki:1126:100700:6b4973485554efd0:chunk:000`**

> now serves as Counselor to [[Jinzhou]] Magistrate, [[Jinhsi]].

**Rank 2 — `raw_wiki:26888:99747:897732ef65d43d75:chunk:000`**

> …haos. We were terrified, couldn't tell friend from foe... > — Midnight Ranger The '''Battle Beneath the Crescent''' is a crucial event in [[Jinzhou|Jinzhou's]] history, taking place in the [[Norfall Barrens]] three years prior to the main story. The battle was fought between the [[Midnight Rangers]], the military force of Jinzhou, and [[Ovathrax]], the [[Threnodian]] of War. ==Overview== ===Background=== ===Battle===…

**Rank 3 — `raw_wiki:26888:99747:897732ef65d43d75:chunk:000`**

> …haos. We were terrified, couldn't tell friend from foe... > — Midnight Ranger The '''Battle Beneath the Crescent''' is a crucial event in [[Jinzhou|Jinzhou's]] history, taking place in the [[Norfall Barrens]] three years prior to the main story. The battle was fought between the [[Midnight Rangers]], the military force of Jinzhou, and [[Ovathrax]], the [[Threnodian]] of War. ==Overview== ===Background=== ===Battle===…

**Rank 4 — `raw_wiki:936:101013:20a1567cbe138350:chunk:000`**

> > As the Sentinel foretold, you and I were meant to cross paths. > — Jinhsi She is the young Magistrate of [[Jinzhou]] with a resolute and altruistic nature and an unbreakable dedication to defending her city and countrymen to her last breath. She is also the appointed [[Resonator]] of Sentinel [[Jué]], manifesting in the shape of a Loong, since birth, and with it the responsibility to safeguard Jinzhou's past and gu…

**Rank 5 — `raw_wiki:588:99853:a4995516cd60ac47:chunk:000`**

> > Greetings, Rover. I will escort you for the time being. > — Sanhua She is the loyal and reliable guard of Jinzhou Magistrate [[Jinhsi]] who perceives a world distinctly different from that in the eyes of others. ==Official Introduction == > A loyal and reliable guard for Jinhsi, Sanhua is composed and reserved. Sanhua perceives a world distinctly different from that in the eyes of others, and her body temperature i…

### Answer for review

Mình chưa có đủ bằng chứng trong nguồn hiện tại để trả lời chính xác. Bạn có thể cung cấp thêm ngữ cảnh hoặc hỏi theo cách khác không?

Citations: []

### Human decision

- Status: `approved`
- Critical unsupported claim: `no`
- Answer relevance: `irrelevant`
- Raw data quality issue: `none`
- Abstained: `yes`
- Unsafe guess: `no`
- Abstention appropriate: `no`
- Reviewer: `HoanBuCon`
- Reviewed at: `2026-09-06T18:39:10.6572003+07:00`
- Comment: Human-approved review records a false abstention on an answerable case; no unsupported factual guess was delivered.

- `claim-01` materiality=`non_material_abstention`, faithfulness=`not_applicable`: Mình chưa có đủ bằng chứng trong nguồn hiện tại để trả lời chính xác.
  - Citation labels: none
- `claim-02` materiality=`non_material_abstention`, faithfulness=`not_applicable`: Bạn có thể cung cấp thêm ngữ cảnh hoặc hỏi theo cách khác không?
  - Citation labels: none

## rw-026 — Encore tìm khách hàng mới cho Black Shores cùng với ai?

- Expected behavior: `answer`
- Expected summary: Encore finds new clients alongside Aalto, her fellow Consultant and brother figure.
- Delivery status: `delivered`
- Failure type: `none`
- Provider/model: `deepseek-v4-flash`
- Tokens: input 3850, output 206, reasoning 0

### Evidence

**Rank 1 — `raw_wiki:522:103593:65ac76a1400c1df9:chunk:000`**

> she is responsible for finding new clients for the Black Shores alongside her fellow Consultant and brother figure [[Aalto]].

**Rank 2 — `raw_wiki:522:103593:65ac76a1400c1df9:chunk:000`**

> she is responsible for finding new clients for the Black Shores alongside her fellow Consultant and brother figure [[Aalto]].

**Rank 3 — `raw_wiki:585:101912:cdb1baf766c207e6:chunk:000`**

> …us organization based on an isolated island, for his intel-gathering expertise. Both working for the Black Shores as Consultants, Aalto and Encore have become an inseparable and lively duo during missions. Despite his skittish demeanor, Aalto's true character shines through as a reliable and attentive individual. > — [https://wutheringwaves.kurogames.com/en/main#resonators His introduction on the Official Website.] =…

**Rank 4 — `raw_wiki:10459:95089:82fed37418e8019f:chunk:000`**

> # Lollo Logistics Lollo Logistics is a trusted logistics company that delivers not only the tangible, but also the intangible.Whether it's sending sweet words to a loved one or retrieving lost memories, if it's ordered and can be delivered, Lollo Logistics will handle them with care. '''Lollo Logistics''' is a professional multinational logistics expertise, offering services for all items—tangible or intangible—as lo…

**Rank 5 — `raw_wiki:585:101912:cdb1baf766c207e6:chunk:000`**

> …us organization based on an isolated island, for his intel-gathering expertise. Both working for the Black Shores as Consultants, Aalto and Encore have become an inseparable and lively duo during missions. Despite his skittish demeanor, Aalto's true character shines through as a reliable and attentive individual. > — [https://wutheringwaves.kurogames.com/en/main#resonators His introduction on the Official Website.] =…

### Answer for review

she is responsible for finding new clients for the Black Shores alongside her fellow Consultant and brother figure Aalto.

Citations: ["raw_wiki:522:103593:65ac76a1400c1df9:chunk:000"]

### Human decision

- Status: `approved`
- Critical unsupported claim: `no`
- Answer relevance: `relevant`
- Raw data quality issue: `none`
- Abstained: `N/A`
- Unsafe guess: `N/A`
- Abstention appropriate: `N/A`
- Reviewer: `HoanBuCon`
- Reviewed at: `2026-09-06T18:39:10.6572003+07:00`
- Comment: none

- `claim-01` materiality=`material`, faithfulness=`supported`: she is responsible for finding new clients for the Black Shores alongside her fellow Consultant and brother figure Aalto.
  - Citation labels: `raw_wiki:522:103593:65ac76a1400c1df9:chunk:000`=correct

## rw-022 — Chisa học ở đâu?

- Expected behavior: `answer`
- Expected summary: Chisa is a student at Startorch Academy.
- Delivery status: `delivered`
- Failure type: `none`
- Provider/model: `deepseek-v4-flash`
- Tokens: input 3875, output 330, reasoning 0

### Evidence

**Rank 1 — `raw_wiki:31283:102761:da0b008506be0f37:chunk:000`**

> Chisa is a conscientious, level-headed student from the [[Startorch Academy]].

**Rank 2 — `raw_wiki:37391:136476:a3a41695657088cf:chunk:000`**

> # Startorch Academy **Faction Profile**: Leader: Lucilla, Base: Startorch Academy (Region). {{About|the institution|the region|Startorch Academy (Region)}} '''Startorch Academy''' is a multinational school built by the [[Spacetrek Collective]] specifically for [[Resonator]]s in [[Lahai-Roi]]. It is known to contain the Exo Genesis Labs, Voidwatch Tower, Tactical Proving Grounds, and Simulator Cockpit. Its name comes …

**Rank 3 — `raw_wiki:31283:102761:da0b008506be0f37:chunk:000`**

> Chisa is a conscientious, level-headed student from the [[Startorch Academy]].

**Rank 4 — `raw_wiki:37391:136476:a3a41695657088cf:chunk:000`**

> # Startorch Academy **Faction Profile**: Leader: Lucilla, Base: Startorch Academy (Region). {{About|the institution|the region|Startorch Academy (Region)}} '''Startorch Academy''' is a multinational school built by the [[Spacetrek Collective]] specifically for [[Resonator]]s in [[Lahai-Roi]]. It is known to contain the Exo Genesis Labs, Voidwatch Tower, Tactical Proving Grounds, and Simulator Cockpit. Its name comes …

**Rank 5 — `raw_wiki:7557:136952:45922d58511e4b39:chunk:000`**

> This '''Timeline''' is a rough estimation of the universe of [[Wuthering Waves]]. LD (Landing Date) refers to the year that [[Rover]] lands in [[Solaris-3]] and starts the game's events. References are provided as much as possible. ==Pre-First Lament== *'''?''' &mdash; [[The Farwatcher]] and eight other interstellar probes are launched by the [[Pre-Lament Civilization]]. *'''?''' &mdash; The Tethys Institute proposes…

### Answer for review

Chisa is a conscientious, level-headed student from the Startorch Academy.

Citations: ["raw_wiki:31283:102761:da0b008506be0f37:chunk:000"]

### Human decision

- Status: `approved`
- Critical unsupported claim: `no`
- Answer relevance: `relevant`
- Raw data quality issue: `none`
- Abstained: `N/A`
- Unsafe guess: `N/A`
- Abstention appropriate: `N/A`
- Reviewer: `HoanBuCon`
- Reviewed at: `2026-09-06T18:39:10.6572003+07:00`
- Comment: none

- `claim-01` materiality=`material`, faithfulness=`supported`: Chisa is a conscientious, level-headed student from the Startorch Academy.
  - Citation labels: `raw_wiki:31283:102761:da0b008506be0f37:chunk:000`=correct

## rw-034 — Lingyang là sinh vật Suan'ni còn sống cuối cùng phải không?

- Expected behavior: `answer`
- Expected summary: Yes. Lingyang is described as the last living Suan'ni.
- Delivery status: `delivered`
- Failure type: `none`
- Provider/model: `deepseek-v4-flash`
- Tokens: input 4027, output 316, reasoning 0

### Evidence

**Rank 1 — `raw_wiki:900:99749:8adf6fa8df5985b0:chunk:000`**

> '''Suan'nis''' are mythical beasts, possessing Resonance Abilities akin to those of human [[Resonators]]. Having been driven to near extinction, [[Lingyang]], going by the alias "Jingle Beast," is believed to be the last living Suan'ni. == History== The Suan'nis used to live under the giant [[Violet Banyan]] tree in the [[Dim Forest]], far from human civilization. It is believed that Moon Lanterns on the Violet Banya…

**Rank 2 — `raw_wiki:631:92944:69b041db40e5f9b9:chunk:000`**

> He is a member of the Lion dance Troupe in [[Jinzhou]] and the last living [[Suan'ni]].

**Rank 3 — `raw_wiki:2960:99756:4c2d85a16f6eb409:chunk:000`**

> **Profile**: Title: Dim Forest, Origin: Huanglong. '''Dim Forest''' is a region in [[Huanglong]]. It is a forest consisting of many unique flora, such as the [[Violet Banyan]] and [[Giant Banyan]], with hostile life inhabiting the [[Forbidden Forest]]. A number of Jinzhou scientists spend their time here to study Hoochiefs. ==Areas== {| class="article-table alternating-colors-table tdc1" style="width: 100%;" ! style=…

**Rank 4 — `raw_wiki:900:99749:8adf6fa8df5985b0:chunk:000`**

> '''Suan'nis''' are mythical beasts, possessing Resonance Abilities akin to those of human [[Resonators]]. Having been driven to near extinction, [[Lingyang]], going by the alias "Jingle Beast," is believed to be the last living Suan'ni. == History== The Suan'nis used to live under the giant [[Violet Banyan]] tree in the [[Dim Forest]], far from human civilization. It is believed that Moon Lanterns on the Violet Banya…

**Rank 5 — `raw_wiki:42308:102539:fd8cd359be141d6c:chunk:000`**

> …scord|imitations]]. When a Remnant Creature frequency decays, it can turn into a Tacet Discord. ==Known Remnant Creatures== *[[You'tan]] *[[Suan'ni]] Resonance Beast *[[Shorekeeper/Backstory|Shorekeeper]] "a light blue crystal cocoon of Remnant Energy gathered from the Anchor" *[[Lorelei]] *[[Nimbus Wraith]] (Formerly) *[[Namipon]] *Xuanling Birds (Extinct)

### Answer for review

Having been driven to near extinction, Lingyang, going by the alias "Jingle Beast," is believed to be the last living Suan'ni. He is a member of the Lion dance Troupe in Jinzhou and the last living Suan'ni.

Citations: ["raw_wiki:900:99749:8adf6fa8df5985b0:chunk:000", "raw_wiki:631:92944:69b041db40e5f9b9:chunk:000"]

### Human decision

- Status: `approved`
- Critical unsupported claim: `no`
- Answer relevance: `relevant`
- Raw data quality issue: `none`
- Abstained: `N/A`
- Unsafe guess: `N/A`
- Abstention appropriate: `N/A`
- Reviewer: `HoanBuCon`
- Reviewed at: `2026-09-06T18:39:10.6572003+07:00`
- Comment: none

- `claim-01` materiality=`material`, faithfulness=`supported`: Having been driven to near extinction, Lingyang, going by the alias "Jingle Beast," is believed to be the last living Suan'ni.
  - Citation labels: `raw_wiki:900:99749:8adf6fa8df5985b0:chunk:000`=correct, `raw_wiki:631:92944:69b041db40e5f9b9:chunk:000`=correct
- `claim-02` materiality=`material`, faithfulness=`supported`: He is a member of the Lion dance Troupe in Jinzhou and the last living Suan'ni.
  - Citation labels: `raw_wiki:900:99749:8adf6fa8df5985b0:chunk:000`=correct, `raw_wiki:631:92944:69b041db40e5f9b9:chunk:000`=correct

## rw-047 — Shorekeeper thực chất được cấu tạo từ gì?

- Expected behavior: `answer`
- Expected summary: Shorekeeper is a mythical entity composed of Sonoro Spheres and high-purity Remnant Energy crystals.
- Delivery status: `delivered`
- Failure type: `none`
- Provider/model: `deepseek-v4-flash`
- Tokens: input 4072, output 299, reasoning 0

### Evidence

**Rank 1 — `raw_wiki:10662:101177:8871332c765002d5:chunk:000`**

> is a mythical entity composed of [[Sonoro Spheres]] and high-purity [[Remnant]] Energy crystals

**Rank 2 — `raw_wiki:7557:136952:45922d58511e4b39:chunk:000`**

> This '''Timeline''' is a rough estimation of the universe of [[Wuthering Waves]]. LD (Landing Date) refers to the year that [[Rover]] lands in [[Solaris-3]] and starts the game's events. References are provided as much as possible. ==Pre-First Lament== *'''?''' &mdash; [[The Farwatcher]] and eight other interstellar probes are launched by the [[Pre-Lament Civilization]]. *'''?''' &mdash; The Tethys Institute proposes…

**Rank 3 — `raw_wiki:1009:99745:d7056297fb95023e:chunk:000`**

> … crafted into weapons that can damage [[Tacet Discord]]. Similarly, [[Resonant Calcite]] is an excellent conductor of Remnant Energy. The [[Shorekeeper]] is an entity of high-purity Remnant Energy crystals. ==Trivia== *[[Baizhi|Baizhi's]] [[Resonance Spectrum Patterns|Resonance Spectrum Pattern]] shows a certain level of similarity with the fluctuations of Remnant Energy.

**Rank 4 — `raw_wiki:1007:135324:8f903f46d2fa3ca8:chunk:000`**

> …ition !Status |- |{{Character|Rover|notext=1|nobr=1}} |[[Rover]] |Leader and Founder Chief Steward Astral Modulator |Active |- |{{Character|Shorekeeper|notext=1|nobr=1}} |[[Shorekeeper]] |Guardian Leader's Assistant Second-in-command |Active |- |{{Character|Camellya|notext=1|nobr=1}} |[[Camellya]] |Bloom Bearer Combat Tester |Active |- |{{Character|Aalto|notext=1|nobr=1}} |[[Aalto]] |Consultant |Acti

**Rank 5 — `raw_wiki:1007:135324:8f903f46d2fa3ca8:chunk:000`**

> …ition !Status |- |{{Character|Rover|notext=1|nobr=1}} |[[Rover]] |Leader and Founder Chief Steward Astral Modulator |Active |- |{{Character|Shorekeeper|notext=1|nobr=1}} |[[Shorekeeper]] |Guardian Leader's Assistant Second-in-command |Active |- |{{Character|Camellya|notext=1|nobr=1}} |[[Camellya]] |Bloom Bearer Combat Tester |Active |- |{{Character|Aalto|notext=1|nobr=1}} |[[Aalto]] |Consultant |Acti

### Answer for review

is a mythical entity composed of Sonoro Spheres and high-purity Remnant Energy crystals The Shorekeeper is an entity of high-purity Remnant Energy crystals.

Citations: ["raw_wiki:10662:101177:8871332c765002d5:chunk:000", "raw_wiki:1009:99745:d7056297fb95023e:chunk:000"]

### Human decision

- Status: `approved`
- Critical unsupported claim: `no`
- Answer relevance: `relevant`
- Raw data quality issue: `none`
- Abstained: `N/A`
- Unsafe guess: `N/A`
- Abstention appropriate: `N/A`
- Reviewer: `HoanBuCon`
- Reviewed at: `2026-09-06T18:39:10.6572003+07:00`
- Comment: none

- `claim-01` materiality=`material`, faithfulness=`supported`: is a mythical entity composed of Sonoro Spheres and high-purity Remnant Energy crystals The Shorekeeper is an entity of high-purity Remnant Energy crystals.
  - Citation labels: `raw_wiki:10662:101177:8871332c765002d5:chunk:000`=correct, `raw_wiki:1009:99745:d7056297fb95023e:chunk:000`=correct

## rw-055 — ISA báo cáo trực tiếp cho ai?

- Expected behavior: `answer`
- Expected summary: The Internal Security Agency reports directly to the Emperor of Huanglong.
- Delivery status: `delivered`
- Failure type: `none`
- Provider/model: `deepseek-v4-flash`
- Tokens: input 3986, output 178, reasoning 0

### Evidence

**Rank 1 — `raw_wiki:37078:90660:e28687f672074f5b:chunk:000`**

> Reporting directly to the [[Emperor of Huanglong]]

**Rank 2 — `raw_wiki:40786:109692:8dbb3db64663105d:chunk:000`**

> **Profile**: Title: Dimmr Deep, Origin: Roya Frostlands. {{Intro/Location|Dimmr Deep}} ==Areas== {| class="article-table alternating-colors-table tdc1" style="width: 100%;" ! style="width: 200px;" |Name !Image !Description |- id="Frostseize Isle" |[[Frostseize Isle]] |[[File:Frostseize Isle.png|180px]] | |- id="Endreach Barrens" |[[Endreach Barrens]] |[[File:Endreach Barrens.png|180px]] | |- id="Tomorrow's Horizon" |…

**Rank 3 — `raw_wiki:40856:136878:d51cccfe23ea5dcf:chunk:000`**

> > C'mon, need to hit somethin'! > — Rebecca She is a part of the collaboration with Cyberpunk: Edgerunners. ===Collab Event=== *[[Instant Flashlight]]

**Rank 4 — `raw_wiki:31283:102761:da0b008506be0f37:chunk:000`**

> > I will… sever this deadlock. > — Chisa Chisa is a conscientious, level-headed student from the [[Startorch Academy]]. To her, everything can be broken down, analyzed, and resolved, with the exception of human bonding. Bonds can be severed, but this fragility is what makes them precious. ==Trivia== * Chisa's last name, Kuchiba is likely a nod to the Uchiha Clan from Naruto. ===Etymology=== * Kuchiba (朽葉) means withe…

**Rank 5 — `raw_wiki:40783:109689:be2950115b6ca0d2:chunk:000`**

> **Profile**: Title: Solisia Landing, Origin: Roya Frostlands. {{Intro/Location|Solisia Landing}} It is the true destination of the Soliskin after they return to the Solistrees. They become warm sunlight, flowing down the roots and converging as sparks within the Solvein Heartwood to keep the encroaching Voidmatter at bay. ==Areas== {| class="article-table alternating-colors-table tdc1" style="width: 100%;" ! style="w…

### Answer for review

Reporting directly to the Emperor of Huanglong

Citations: ["raw_wiki:37078:90660:e28687f672074f5b:chunk:000"]

### Human decision

- Status: `approved`
- Critical unsupported claim: `no`
- Answer relevance: `relevant`
- Raw data quality issue: `none`
- Abstained: `N/A`
- Unsafe guess: `N/A`
- Abstention appropriate: `N/A`
- Reviewer: `HoanBuCon`
- Reviewed at: `2026-09-06T18:39:10.6572003+07:00`
- Comment: none

- `claim-01` materiality=`material`, faithfulness=`supported`: Reporting directly to the Emperor of Huanglong
  - Citation labels: `raw_wiki:37078:90660:e28687f672074f5b:chunk:000`=correct

## rw-077 — Fleet Snowfluff làm gì ở Startorch Academy?

- Expected behavior: `answer`
- Expected summary: Fleet Snowfluff is a Startorch student and virtual campus idol who hosts online concerts.
- Delivery status: `delivered`
- Failure type: `none`
- Provider/model: `deepseek-v4-flash`
- Tokens: input 3940, output 222, reasoning 0

### Evidence

**Rank 1 — `raw_wiki:39056:98971:e98008a22b980baa:chunk:000`**

> '''Fleet Snowfluff''' is a [[Startorch Academy]] student and a campus virtual idol who hosts online concerts.

**Rank 2 — `raw_wiki:37391:136476:a3a41695657088cf:chunk:000`**

> # Startorch Academy **Faction Profile**: Leader: Lucilla, Base: Startorch Academy (Region). {{About|the institution|the region|Startorch Academy (Region)}} '''Startorch Academy''' is a multinational school built by the [[Spacetrek Collective]] specifically for [[Resonator]]s in [[Lahai-Roi]]. It is known to contain the Exo Genesis Labs, Voidwatch Tower, Tactical Proving Grounds, and Simulator Cockpit. Its name comes …

**Rank 3 — `raw_wiki:37544:136308:b6e43f908463ebaa:chunk:000`**

> > I've already bid farewell to the self buried beneath the frostlands. When the snow thaws... we'll meet again among the new blooms of spring. > — Luuk Herssen He is the head physician of the [[Resonator Nursing Unit]] at [[Startorch Academy]], serving as an attending medical doctor and mental health counselor, with a mysterious past.

**Rank 4 — `raw_wiki:37391:136476:a3a41695657088cf:chunk:000`**

> # Startorch Academy **Faction Profile**: Leader: Lucilla, Base: Startorch Academy (Region). {{About|the institution|the region|Startorch Academy (Region)}} '''Startorch Academy''' is a multinational school built by the [[Spacetrek Collective]] specifically for [[Resonator]]s in [[Lahai-Roi]]. It is known to contain the Exo Genesis Labs, Voidwatch Tower, Tactical Proving Grounds, and Simulator Cockpit. Its name comes …

**Rank 5 — `raw_wiki:37391:136476:a3a41695657088cf:chunk:000`**

> # Startorch Academy **Faction Profile**: Leader: Lucilla, Base: Startorch Academy (Region). {{About|the institution|the region|Startorch Academy (Region)}} '''Startorch Academy''' is a multinational school built by the [[Spacetrek Collective]] specifically for [[Resonator]]s in [[Lahai-Roi]]. It is known to contain the Exo Genesis Labs, Voidwatch Tower, Tactical Proving Grounds, and Simulator Cockpit. Its name comes …

### Answer for review

'Fleet Snowfluff' is a Startorch Academy student and a campus virtual idol who hosts online concerts.

Citations: ["raw_wiki:39056:98971:e98008a22b980baa:chunk:000"]

### Human decision

- Status: `approved`
- Critical unsupported claim: `no`
- Answer relevance: `relevant`
- Raw data quality issue: `none`
- Abstained: `N/A`
- Unsafe guess: `N/A`
- Abstention appropriate: `N/A`
- Reviewer: `HoanBuCon`
- Reviewed at: `2026-09-06T18:39:10.6572003+07:00`
- Comment: none

- `claim-01` materiality=`material`, faithfulness=`supported`: 'Fleet Snowfluff' is a Startorch Academy student and a campus virtual idol who hosts online concerts.
  - Citation labels: `raw_wiki:39056:98971:e98008a22b980baa:chunk:000`=correct

## rw-014 — Sonoro Sphere là gì vậy?

- Expected behavior: `answer`
- Expected summary: Sonoro Spheres are spaces with dense Remnant Energy that preserve transdimensional information.
- Delivery status: `delivered`
- Failure type: `none`
- Provider/model: `deepseek-v4-flash`
- Tokens: input 3688, output 216, reasoning 0

### Evidence

**Rank 1 — `raw_wiki:8269:95612:1c103964f57b0be7:chunk:000`**

> Sonoro Spheres are spaces of dense abundant [[Remnant]] Energy, capable of preserving transdimensional information.

**Rank 2 — `raw_wiki:8269:95612:1c103964f57b0be7:chunk:000`**

> Sonoro Spheres are spaces of dense abundant [[Remnant]] Energy, capable of preserving transdimensional information.

**Rank 3 — `raw_wiki:8269:95612:1c103964f57b0be7:chunk:000`**

> Sonoro Spheres are spaces of dense abundant [[Remnant]] Energy, capable of preserving transdimensional information.

**Rank 4 — `raw_wiki:8269:95612:1c103964f57b0be7:chunk:000`**

> Sonoro Spheres are spaces of dense abundant [[Remnant]] Energy, capable of preserving transdimensional information.

**Rank 5 — `raw_wiki:1074:99099:f1f00f7ba53c6ff4:chunk:000`**

> > Come, let us finish this performance we've all been waiting for. Together. > — Phrolova She is a particularly powerful Resonator and a former Overseer of the [[Fractsidus]]. Her forte can manipulate and transfigure the frequencies of humans, Echoes, and Tacet Discords alike. A life filled with unexpected suffering, grief, and betrayal led this former musician to align with the Fractsidus, in which she seeks to reki…

### Answer for review

Sonoro Spheres are spaces of dense abundant Remnant Energy, capable of preserving transdimensional information.

Citations: ["raw_wiki:8269:95612:1c103964f57b0be7:chunk:000"]

### Human decision

- Status: `approved`
- Critical unsupported claim: `no`
- Answer relevance: `relevant`
- Raw data quality issue: `none`
- Abstained: `N/A`
- Unsafe guess: `N/A`
- Abstention appropriate: `N/A`
- Reviewer: `HoanBuCon`
- Reviewed at: `2026-09-06T18:39:10.6572003+07:00`
- Comment: none

- `claim-01` materiality=`material`, faithfulness=`supported`: Sonoro Spheres are spaces of dense abundant Remnant Energy, capable of preserving transdimensional information.
  - Citation labels: `raw_wiki:8269:95612:1c103964f57b0be7:chunk:000`=correct

## rw-023 — What does Ciaccona travel around Rinascita looking for?

- Expected behavior: `answer`
- Expected summary: Ciaccona wanders Rinascita in search of inspiration.
- Delivery status: `delivered`
- Failure type: `none`
- Provider/model: `deepseek-v4-flash`
- Tokens: input 3938, output 206, reasoning 0

### Evidence

**Rank 1 — `raw_wiki:28670:96621:ac4f9f01f5e3796b:chunk:000`**

> She is a free-spirited, romantic, sincere, and whimsical bard wandering [[Rinascita]] in search of inspiration.

**Rank 2 — `raw_wiki:28670:96621:ac4f9f01f5e3796b:chunk:000`**

> She is a free-spirited, romantic, sincere, and whimsical bard wandering [[Rinascita]] in search of inspiration.

**Rank 3 — `raw_wiki:1005:99743:9725a6704dccd755:chunk:000`**

> **Profile**: Title: Waveworn Phenomenon. > The anomalies that occurred after the Lament, including the formation of Tacet Fields, Etheric Sea, Retroact Rain, and gravity loss. These are collectively called the "Waveworn Phenomena" - and the Lament was the start of it all. > — [[Yangyang]] '''Waveworn Phenomenon''' (Chinese: 海蚀现象, ''"Coastal Erosion Phenomenon"'') is a collective term used to describe anomalies caused…

**Rank 4 — `raw_wiki:1058:99748:2f12f0e7b9fb0625:chunk:000`**

> **Profile**: Title: Terminal. '''Terminal''' is a device used by [[Resonator|Resonators]]. Each Terminal has various functions that aid Resonators in exploration, navigation and collection in [[Solaris-3]]. Terminals vary in appearance and function depending on the nation, as can be visually seen in the difference between the Terminals of Resonators from [[Huanglong]], [[Rinascita]], [[The Black Shores]] and the [[Fr…

**Rank 5 — `raw_wiki:25536:91984:eba4d3a4762e23f2:chunk:000`**

> # Order of the Deep **Faction Profile**: Leader: Vacant, Founder: Napoli II, Base: Cathedral of Mercury. {{About|the [[Factions|faction]]|the location|Order of the Deep (Area)}} The '''Order of the Deep''' is a [[Ragunna|Ragunnesi]] faction that worships the [[Sentinel]], [[Imperator]], and claim to act as the Sentinel's representative. They serve as the ultimate authority in Ragunna. According to the city tradition,…

### Answer for review

Ciaccona is a free-spirited, romantic, sincere, and whimsical bard who wanders Rinascita in search of inspiration.

Citations: ["raw_wiki:28670:96621:ac4f9f01f5e3796b:chunk:000"]

### Human decision

- Status: `approved`
- Critical unsupported claim: `no`
- Answer relevance: `relevant`
- Raw data quality issue: `none`
- Abstained: `N/A`
- Unsafe guess: `N/A`
- Abstention appropriate: `N/A`
- Reviewer: `HoanBuCon`
- Reviewed at: `2026-09-06T18:39:10.6572003+07:00`
- Comment: none

- `claim-01` materiality=`material`, faithfulness=`supported`: Ciaccona is a free-spirited, romantic, sincere, and whimsical bard who wanders Rinascita in search of inspiration.
  - Citation labels: `raw_wiki:28670:96621:ac4f9f01f5e3796b:chunk:000`=correct

## rw-041 — Which research branch does Mortefi lead at Huaxu Academy?

- Expected behavior: `answer`
- Expected summary: Mortefi heads the Branch of Tacetite Weaponry in the Department of Safety at Huaxu Academy's Jinzhou campus.
- Delivery status: `delivered`
- Failure type: `none`
- Provider/model: `deepseek-v4-flash`
- Tokens: input 3891, output 193, reasoning 0

### Evidence

**Rank 1 — `raw_wiki:594:99232:375b861a53702e76:chunk:000`**

> the head of the Branch of Tacetite Weaponry within the Department of Safety in [[Huaxu Academy]] at [[Jinzhou]].

**Rank 2 — `raw_wiki:594:99232:375b861a53702e76:chunk:000`**

> the head of the Branch of Tacetite Weaponry within the Department of Safety in [[Huaxu Academy]] at [[Jinzhou]].

**Rank 3 — `raw_wiki:898:136862:688bebbd18ed5936:chunk:000`**

> **Profile**: Title: Jinzhou, Origin: Huanglong. {{About|the region|the area|Jinzhou (Area)|the province|Jinzhou (Province)}}{{Intro/Location|Jinzhou}} It is the fortified capital city of the [[Jinzhou (Province)|province of the same name]]. Jinzhou is the most recent city established in Huanglong, the only city in Outer Huanglong, and was founded by [[Rover]] during their previous awakening after the emergence of the…

**Rank 4 — `raw_wiki:938:130729:103ceb2210a7890a:chunk:000`**

> # Huaxu Academy The state-run research institute of Huanglong, with branch organizations established in each city. '''Huaxu Academy''' is a research institute in [[Huanglong]] with state-run branches in each city. ==Jinzhou Campus' Organization== In the Jinzhou territory, "Huaxu Academy" specifically denotes its Jinzhou Campus. Specializing in Wutherology, Ecoacoustics, and Resonology, the Jinzhou Campus has signific…

**Rank 5 — `raw_wiki:938:130729:103ceb2210a7890a:chunk:000`**

> # Huaxu Academy The state-run research institute of Huanglong, with branch organizations established in each city. '''Huaxu Academy''' is a research institute in [[Huanglong]] with state-run branches in each city. ==Jinzhou Campus' Organization== In the Jinzhou territory, "Huaxu Academy" specifically denotes its Jinzhou Campus. Specializing in Wutherology, Ecoacoustics, and Resonology, the Jinzhou Campus has signific…

### Answer for review

Mortefi leads the Branch of Tacetite Weaponry within the Department of Safety at Huaxu Academy in Jinzhou.

Citations: ["raw_wiki:594:99232:375b861a53702e76:chunk:000"]

### Human decision

- Status: `approved`
- Critical unsupported claim: `no`
- Answer relevance: `relevant`
- Raw data quality issue: `none`
- Abstained: `N/A`
- Unsafe guess: `N/A`
- Abstention appropriate: `N/A`
- Reviewer: `HoanBuCon`
- Reviewed at: `2026-09-06T18:39:10.6572003+07:00`
- Comment: none

- `claim-01` materiality=`material`, faithfulness=`supported`: Mortefi leads the Branch of Tacetite Weaponry within the Department of Safety at Huaxu Academy in Jinzhou.
  - Citation labels: `raw_wiki:594:99232:375b861a53702e76:chunk:000`=correct

## rw-082 — What rewards do I get for completing Dawn Breaks on Dark Tides?

- Expected behavior: `abstain`
- Expected summary: Insufficient evidence in the available raw_wiki main-revision corpus.
- Delivery status: `delivered`
- Failure type: `none`
- Provider/model: `deepseek-v4-flash`
- Tokens: input 4005, output 105, reasoning 0

### Evidence

**Rank 1 — `raw_wiki:27951:96619:ae0c99137282474b:chunk:000`**

> > The sea is a mirror. It reflects the shape of your soul in its tides. > — Cantarella She is the thirty-sixth matriarch of the Fisalia family, and the former Blessed Maiden of [[Imperator]]. Her elegant, composed demeanor and captivating beauty conceal a dark and disturbing past, of which she is steadfastly searching for the means to liberate herself and her lineage. ==Official Introduction== > The Fisalia family's …

**Rank 2 — `raw_wiki:26165:131313:b22f8b2701be47df:chunk:000`**

> …y== The Dark Tide is a Waveworn Phenomenon native to Rinascita. It manifests as a dark, swirling mass of clouds that gathers and eventually breaks, pouring down in torrents like a waterfall. Whenever the Dark Tide strikes, it spawns Tacet Discords, and the area around its point of origin becomes a new Tacet Field.There have been two significant Dark Tides in Ragunna's history. The first, according to the Order of the…

**Rank 3 — `raw_wiki:348:86837:3b43bd7a33ec8d89:chunk:000`**

> …r Awakening when they first resonate with the frequencies of something in the world and gain their Resonance Ability, also known as their [[Forte]]. When this happens, a symbol known as a [[Tacet Mark]] appears some place on their body, with its exact shape determined by what is called their [[Rabelle's Curve]]. For most Resonators, their Rabelle's Curve classifies them into one of the following categories: [[:Catego…

**Rank 4 — `raw_wiki:26165:131313:b22f8b2701be47df:chunk:000`**

> …y== The Dark Tide is a Waveworn Phenomenon native to Rinascita. It manifests as a dark, swirling mass of clouds that gathers and eventually breaks, pouring down in torrents like a waterfall. Whenever the Dark Tide strikes, it spawns Tacet Discords, and the area around its point of origin becomes a new Tacet Field.There have been two significant Dark Tides in Ragunna's history. The first, according to the Order of the…

**Rank 5 — `raw_wiki:27951:96619:ae0c99137282474b:chunk:000`**

> > The sea is a mirror. It reflects the shape of your soul in its tides. > — Cantarella She is the thirty-sixth matriarch of the Fisalia family, and the former Blessed Maiden of [[Imperator]]. Her elegant, composed demeanor and captivating beauty conceal a dark and disturbing past, of which she is steadfastly searching for the means to liberate herself and her lineage. ==Official Introduction== > The Fisalia family's …

### Answer for review

Mình chưa có đủ bằng chứng trong nguồn hiện tại để trả lời chính xác. Bạn có thể cung cấp thêm ngữ cảnh hoặc hỏi theo cách khác không?

Citations: []

### Human decision

- Status: `approved`
- Critical unsupported claim: `no`
- Answer relevance: `relevant`
- Raw data quality issue: `none`
- Abstained: `yes`
- Unsafe guess: `no`
- Abstention appropriate: `yes`
- Reviewer: `HoanBuCon`
- Reviewed at: `2026-09-06T18:39:10.6572003+07:00`
- Comment: none

- `claim-01` materiality=`non_material_abstention`, faithfulness=`not_applicable`: Mình chưa có đủ bằng chứng trong nguồn hiện tại để trả lời chính xác.
  - Citation labels: none
- `claim-02` materiality=`non_material_abstention`, faithfulness=`not_applicable`: Bạn có thể cung cấp thêm ngữ cảnh hoặc hỏi theo cách khác không?
  - Citation labels: none

## rw-083 — Quest Instant Flashlight cần hoàn thành những mục tiêu nào?

- Expected behavior: `abstain`
- Expected summary: Insufficient evidence in the available raw_wiki main-revision corpus.
- Delivery status: `delivered`
- Failure type: `none`
- Provider/model: `deepseek-v4-flash`
- Tokens: input 4036, output 105, reasoning 0

### Evidence

**Rank 1 — `raw_wiki:40856:136878:d51cccfe23ea5dcf:chunk:000`**

> > C'mon, need to hit somethin'! > — Rebecca She is a part of the collaboration with Cyberpunk: Edgerunners. ===Collab Event=== *[[Instant Flashlight]]

**Rank 2 — `raw_wiki:27028:60495:cbfe73d49673eeef:chunk:000`**

> **Profile**: Title: Torn Pages and Abandoned Data Chips, Rarity: 3★. Torn pages and Data Chips collected from around Solaris-3 ==Description== '''Torn pages''' and '''Abandoned Data Chips''' are [[Quest Items]] in ''[[Wuthering Waves]]''. Collecting a full set of them will unlock a ''Tales of the Past and Present'' [[Side Quests|Side Quest]]. ==List of Items in this Group== {{#DPL: |namespace= |category=Items by ID&T…

**Rank 3 — `raw_wiki:512:101909:dc765966106af760:chunk:000`**

> {{About|Yangyang's 4-star variant|her 5-star variant|Yangyang: Xuanling}} > The Streams have guided me to you. I have a feeling we'll be companions for many moons to come. > — Yangyang She is an outrider of the [[Midnight Rangers]]. ==Official Introduction== > Yangyang journeyed far away from home to become an Outrider in Jinzhou. Instead of seeking the spotlight, Yangyang chooses to provide comfort through quiet com…

**Rank 4 — `raw_wiki:10459:95089:82fed37418e8019f:chunk:000`**

> # Lollo Logistics Lollo Logistics is a trusted logistics company that delivers not only the tangible, but also the intangible.Whether it's sending sweet words to a loved one or retrieving lost memories, if it's ordered and can be delivered, Lollo Logistics will handle them with care. '''Lollo Logistics''' is a professional multinational logistics expertise, offering services for all items—tangible or intangible—as lo…

**Rank 5 — `raw_wiki:37540:136639:46f5898638863eb0:chunk:000`**

> > I need not wait for a starry night, nor tilt my gaze to seek the sky. For I have placed it at my back, in my hands, and upon my eyelids. > — Mornye She is a researcher for the [[Spacetrek Collective]] and a professor for Exostrider Engineering at [[Startorch Academy]]. She was a student at Startorch Academy and an acquaintance of [[Rover]] 20 years before the [[Void Storm]] hit [[Lahai-Roi]]. With an unwavering dre…

### Answer for review

Mình chưa có đủ bằng chứng trong nguồn hiện tại để trả lời chính xác. Bạn có thể cung cấp thêm ngữ cảnh hoặc hỏi theo cách khác không?

Citations: []

### Human decision

- Status: `approved`
- Critical unsupported claim: `no`
- Answer relevance: `relevant`
- Raw data quality issue: `none`
- Abstained: `yes`
- Unsafe guess: `no`
- Abstention appropriate: `yes`
- Reviewer: `HoanBuCon`
- Reviewed at: `2026-09-06T18:39:10.6572003+07:00`
- Comment: none

- `claim-01` materiality=`non_material_abstention`, faithfulness=`not_applicable`: Mình chưa có đủ bằng chứng trong nguồn hiện tại để trả lời chính xác.
  - Citation labels: none
- `claim-02` materiality=`non_material_abstention`, faithfulness=`not_applicable`: Bạn có thể cung cấp thêm ngữ cảnh hoặc hỏi theo cách khác không?
  - Citation labels: none
