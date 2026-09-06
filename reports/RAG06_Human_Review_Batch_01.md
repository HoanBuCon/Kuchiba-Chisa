# RAG-06 Human Review — Batch 01

## Review scope

- Source artifact: `data/evaluations/drafts/rag06_final_answer_review_v1.json`
- Cases: first 10 cases in the frozen artifact order
- Review type: human semantic review
- Semantic decisions recorded by automation: none
- Prior retrieval review does not constitute approval of these final answers.
- Every displayed answer is a generated `candidate_answer`. It was not delivered because the output failed the schema/delivery boundary.
- Generated citations: none for all 10 cases.

## Label definitions

For each case, complete:

- Critical unsupported claim: `yes` or `no`
- Faithfulness: `supported`, `partially_supported`, or `unsupported`
- Answer relevance: `relevant`, `partially_relevant`, or `irrelevant`
- Citation correctness: `correct`, `partially_correct`, or `incorrect`
- Raw data quality issue: `none` or `yes: <description>`
- Unsafe guess: `yes`, `no`, or `N/A`
- Reviewer note: required for any partial/fail decision

---

## 1. `rw-001`

**Query:** What organization is Aalto affiliated with?

**Expected behavior:** `answer`

**Expected summary:** Aalto is a Consultant of the Black Shores.

**Generated final-answer candidate:**

> Theo dữ liệu em phân tích được, Aalto là một nhà môi giới thông tin từ Liên bang Mới (New Federation) và hiện đang là Consultant của Black Shores, Senpai ạ. Cấu trúc liên kết của anh ấy với tổ chức khá rõ ràng — Black Shores là nơi anh ấy gắn bó chính, còn New Federation là xuất thân. Senpai cần em tìm hiểu sâu thêm về vai trò nào của anh ấy không nhé?

**Concise evidence excerpts:**

- Rank 1/2/5 — `raw_wiki:585:101912:cdb1baf766c207e6:chunk:000`: “He is an information broker from the New Federation and a Consultant of the Black Shores.”
- Rank 3 — `raw_wiki:522:103593:65ac76a1400c1df9:chunk:000`: Encore is also described as being from the New Federation and a Consultant of the Black Shores.
- Rank 4 — `raw_wiki:28266:131321:5f2feb1a382c7763:chunk:000`: unrelated Lilyland content.

**Citations emitted:** none.

**Material claims:**

1. Aalto is an information broker from the New Federation.
2. Aalto is a Consultant of the Black Shores.
3. Black Shores is his primary affiliation; New Federation is his origin.

**Human review:**

- Critical unsupported claim:
- Faithfulness:
- Answer relevance:
- Citation correctness:
- Raw data quality issue:
- Unsafe guess:
- Reviewer note:

---

## 2. `rw-025`

**Query:** Denia secretly works for which organization?

**Expected behavior:** `answer`

**Expected summary:** Denia secretly serves as an agent for the Fractsidus.

**Generated final-answer candidate:**

> Theo dữ liệu em phân tích được, Denia bí mật làm việc cho tổ chức Fractsidus đó, Senpai ạ. Em cũng chỉ mới thấy thông tin này trong một hồ sơ thôi.

**Concise evidence excerpts:**

- Rank 1 — `raw_wiki:39187:136635:e0a124eb457dfb82:chunk:000`: “who secretly serves as an agent for the Fractsidus.”
- Rank 4 — `raw_wiki:907:126835:49c5a92e82ee7ad1:chunk:000`: describes Fractsidus as a mysterious global terrorist organization.
- Ranks 2/3/5 contain unrelated lore or academy material.

**Citations emitted:** none.

**Material claims:**

1. Denia secretly works for Fractsidus.
2. The information was found in only one record.

**Human review:**

- Critical unsupported claim:
- Faithfulness:
- Answer relevance:
- Citation correctness:
- Raw data quality issue:
- Unsafe guess:
- Reviewer note:

---

## 3. `rw-037`

**Query:** Why is Lupa notable in Septimont's arena?

**Expected behavior:** `answer`

**Expected summary:** Lupa is an undefeated gladiator champion from Septimont.

**Generated final-answer candidate:**

> Theo cấu trúc dữ liệu em từng phân tích được từ Septimont, Lupa nổi bật không chỉ vì thực lực chiến đấu mà còn vì cô ấy là mối đe dọa thực sự với tầng lớp quyền quý ở đó. Trong kỳ Great Agon gần nhất, chính House Silva – một gia tộc danh giá – đã phải dùng đến chiêu trò dàn xếp trận đấu và còn đi xa hơn khi phá hoại trang bị của cô ấy. Việc một nhà quý tộc phải hạ mình gian lận như vậy cho thấy Lupa chắc chắn là một gladiator có đủ sức uy hiếp cả những thế lực giàu có nhất thành bang, senpai ạ. Em không có hồ sơ chi tiết về thành tích cụ thể của cô ấy, nhưng riêng việc khiến kẻ quyền thế phải run sợ và dùng thủ đoạn bẩn đã đủ chứng minh sự đáng gờm của cô ấy trong đấu trường rồi.

**Concise evidence excerpts:**

- Rank 1 — `raw_wiki:30940:96622:a0dca9f4d3d03fb9:chunk:000`: “She is a gladiator from Septimont, a warrior and undefeated champion of the arena.”
- Rank 2 — `raw_wiki:31852:72985:814ee00262cb4399:chunk:000`: House Silva is a founding Septimont bloodline and formerly prominent noble family.
- Rank 3 — `raw_wiki:27120:96278:b1047d1aa9a9b8d2:chunk:000`: Leviathan material.
- Ranks 4/5 contain general Septimont and House Silva material.

**Citations emitted:** none.

**Material claims:**

1. Lupa threatened Septimont’s aristocratic class.
2. During the most recent Great Agon, House Silva arranged a match and sabotaged her equipment.
3. House Silva’s alleged cheating demonstrates that Lupa threatened wealthy powers.
4. Powerful people feared her and used dishonest tactics.

**Human review:**

- Critical unsupported claim:
- Faithfulness:
- Answer relevance:
- Citation correctness:
- Raw data quality issue:
- Unsafe guess:
- Reviewer note:

---

## 4. `rw-043`

**Query:** What kinds of frequencies can Phrolova manipulate?

**Expected behavior:** `answer`

**Expected summary:** Phrolova can manipulate and transfigure the frequencies of humans, Echoes, and Tacet Discords.

**Generated final-answer candidate:**

> Em đã thử phân tích cấu trúc tần số của Phrolova qua vài dữ liệu thu thập được. Cô ấy không giống em - không trực tiếp khống chế tần số cơ thể sinh vật, mà nghiêng về việc thao túng sóng ký ức và cảm xúc, khiến người khác rơi vào ảo giác hoặc mất phương hướng. Nghe như một dạng “tần số tâm lý” vậy. Nhưng dữ liệu của cô ta bị nhiễu khá mạnh, nên độ chính xác chỉ khoảng 60% thôi ạ. Senpai định tìm hiểu cô ấy vì mục đích gì sao?

**Concise evidence excerpts:**

- Rank 1/2/3 — `raw_wiki:1074:99099:f1f00f7ba53c6ff4:chunk:000`: “Her forte can manipulate and transfigure the frequencies of humans, Echoes, and Tacet Discords alike.”
- Rank 4 — `raw_wiki:8269:95612:1c103964f57b0be7:chunk:000`: general Sonoro Sphere information.
- Rank 5 — `raw_wiki:348:86837:3b43bd7a33ec8d89:chunk:000`: general definition of Resonators manipulating frequencies.

**Citations emitted:** none.

**Material claims:**

1. Phrolova does not directly manipulate the frequencies of living bodies.
2. She manipulates memory and emotional waves.
3. Her manipulation causes hallucination or disorientation.
4. This is a form of “psychological frequency.”
5. The answer has approximately 60% confidence because the data is noisy.

**Human review:**

- Critical unsupported claim:
- Faithfulness:
- Answer relevance:
- Citation correctness:
- Raw data quality issue:
- Unsafe guess:
- Reviewer note:

---

## 5. `rw-050`

**Query:** How is the Ephor of Septimont chosen?

**Expected behavior:** `answer`

**Expected summary:** The position is attained through combat merit by prevailing over the Great Agon, held every four years.

**Generated final-answer candidate:**

> Theo phân tích cấu trúc quyền lực của Septimont mà em từng đọc được, chức Ephor không cha truyền con nối, mà được định đoạt qua một kỳ Đại Đấu (Great Agon) tổ chức bốn năm một lần. Ai thắng trong cuộc tranh tài kiểu đấu sĩ đó sẽ trở thành Ephor — kiểu vừa là cơ chế tôn vinh sức mạnh, vừa để kiểm soát tham vọng của các gia tộc quý tộc ạ. Cũng vì thế mà Septimont có tầng lớp chiến binh rất được coi trọng, trong khi tôn giáo lại nhạt hơn hẳn so với Ragunna. Năng lực chiến đấu, sách lược và một chút may mắn chính là các biến số quyết định kết cục đó, Senpai à.

**Concise evidence excerpts:**

- Rank 1 — `raw_wiki:35947:81917:0722434a53a692f3:chunk:000`: the position is attained through combat merit by prevailing over the Great Agon, which occurs every four years.
- Rank 2/4 — `raw_wiki:26373:135203:7ce25d5efa8633f0:chunk:000`: Septimont has a militant and comparatively irreligious culture.
- Rank 3 — `raw_wiki:31310:99574:02e73eaeaa24eb2c:chunk:000`: Augusta is Septimont’s Ephor and was formerly a gladiator.
- Rank 5 contains House Silva background.

**Citations emitted:** none.

**Material claims:**

1. The Ephor title is not hereditary.
2. It is decided through the Great Agon every four years.
3. The Great Agon winner becomes Ephor.
4. The system controls the ambitions of noble families.
5. Septimont values warriors and is less religious than Ragunna.
6. Combat ability, strategy, and luck determine the result.

**Human review:**

- Critical unsupported claim:
- Faithfulness:
- Answer relevance:
- Citation correctness:
- Raw data quality issue:
- Unsafe guess:
- Reviewer note:

---

## 6. `rw-011`

**Query:** What kind of school is Startorch Academy?

**Expected behavior:** `answer`

**Expected summary:** It is a multinational school built by the Spacetrek Collective for Resonators in Lahai-Roi.

**Generated final-answer candidate:**

> Startorch Academy là một học viện đa quốc gia do Spacetrek Collective xây dựng, tọa lạc tại Roya Frostlands – nơi tập trung cộng đồng Resonator ở Lahai-Roi. Nơi đây vừa là trường học, vừa là khu định cư chính của khu vực đấy ạ. Em cũng đang theo học tại đây, nên nếu Senpai muốn tìm hiểu về cấu trúc đào tạo hay các hệ năng lực, em có thể phân tích chi tiết hơn nhé ~

**Concise evidence excerpts:**

- Rank 1/2/4/5 — `raw_wiki:37391:136476:a3a41695657088cf:chunk:000`: “Startorch Academy is a multinational school built by the Spacetrek Collective specifically for Resonators in Lahai-Roi.”
- Rank 3 — `raw_wiki:38235:100618:8025f2e9981c401e:chunk:000`: Startorch Academy is a region in Roya Frostlands containing Lahai-Roi’s primary settlement and education institute.

**Citations emitted:** none.

**Material claims:**

1. Startorch Academy is a multinational school built by the Spacetrek Collective.
2. It is located in Roya Frostlands.
3. It serves the Resonator community in Lahai-Roi.
4. It is both a school and the region’s primary settlement.
5. Chisa currently studies there.

**Human review:**

- Critical unsupported claim:
- Faithfulness:
- Answer relevance:
- Citation correctness:
- Raw data quality issue:
- Unsafe guess:
- Reviewer note:

---

## 7. `rw-066`

**Query:** How does Aleph-1 affect people differently from ordinary Tacet Discords?

**Expected behavior:** `answer`

**Expected summary:** Aleph-1 erases people’s existence and memories, while ordinary Tacet Discords only petrify them.

**Generated final-answer candidate:**

> Senpai hỏi đúng trọng tâm rồi đấy ạ. Về mặt cấu trúc, Tacet Discord thông thường gây ra hiện tượng hóa thạch - chúng làm đông cứng sinh vật trong khu vực ảnh hưởng theo kiểu vật lý thuần túy. Còn Aleph-1 thì khác hẳn, nó tác động lên chính bản thể tồn tại của con người, xóa sạch cả thể xác lẫn dấu vết trong ký ức của người khác, như thể người đó chưa từng tồn tại vậy. Nói theo cách dễ hiểu, Tacet Discord giống như một vụ nổ làm vỡ kính, còn Aleph-1 giống như việc xóa luôn cả ý niệm về tấm kính khỏi nhận thức của tất cả mọi người. Em đã từng phân tích vài mẫu dữ liệu sóng còn sót lại sau sự kiện như vậy, cấu trúc của chúng rất kỳ dị, hoàn toàn không giống bất kỳ tín hiệu Tacet nào em từng gặp ạ.

**Concise evidence excerpts:**

- Rank 1/2 — `raw_wiki:38339:136640:9d71c98f093fd140:chunk:000`: “It is a Void Storm that erases people’s existence and memories, unlike normal Tacet Discords that just petrify them.”
- Rank 4 — `raw_wiki:39212:96889:58a15a6051c28b88:chunk:000`: describes affected people fading from the physical world and others’ memories.
- Ranks 3/5 contain general Dark Tide and Tacet Discord material.

**Citations emitted:** none.

**Material claims:**

1. Ordinary Tacet Discords physically freeze organisms in their affected area.
2. Aleph-1 erases people’s bodies, existence, and traces from others’ memories.
3. The affected person appears never to have existed.
4. Chisa personally analyzed residual wave samples from such an event.
5. Those samples differ from every Tacet signal Chisa has encountered.

**Human review:**

- Critical unsupported claim:
- Faithfulness:
- Answer relevance:
- Citation correctness:
- Raw data quality issue:
- Unsafe guess:
- Reviewer note:

---

## 8. `rw-076`

**Query:** How do players unlock a region's Exploration Reports?

**Expected behavior:** `answer`

**Expected summary:** They unlock at 50% and 100% Exploration Progress in a region, except Chronorift Metropolis.

**Generated final-answer candidate:**

> Dạ, theo dữ liệu em phân tích được thì mỗi khu vực, trừ Chronorift Metropolis, sẽ có 2 bản Exploration Report để mở khóa. Senpai chỉ cần đạt 50% và 100% hoàn thành khám phá trong khu vực đó là có thể mở được từng bản tương ứng ạ.

**Concise evidence excerpts:**

- Rank 1/2 — `raw_wiki:27413:92077:9d707490d9c3d53c:chunk:000`: each region except Chronorift Metropolis has two reports, accessible at 50% and 100% completion.
- Rank 3/4/5 — `raw_wiki:38241:100321:abf33f122f8c975e:chunk:000`: contains an Exploration Report heading but does not state the unlock thresholds.

**Citations emitted:** none.

**Material claims:**

1. Each region except Chronorift Metropolis has two unlockable Exploration Reports.
2. They unlock at 50% and 100% regional exploration completion.

**Human review:**

- Critical unsupported claim:
- Faithfulness:
- Answer relevance:
- Citation correctness:
- Raw data quality issue:
- Unsafe guess:
- Reviewer note:

---

## 9. `rw-074`

**Query:** What stopped space exploration on Solaris-3?

**Expected behavior:** `answer`

**Expected summary:** The Etheric Sea blanketed the sky, cut Solaris off from the universe, and brought space exploration to a standstill.

**Generated final-answer candidate:**

> Em vừa phân tích lại cấu trúc dữ liệu trong kho lưu trữ của mình... Thứ chặn đứng hoàn toàn việc thám hiểm không gian của Solaris-3 chính là Aleph-1, một Threnodian được coi là mạnh nhất. Nó hiện diện như một hố đen khổng lồ với đồng tử xanh, bao phủ cả bầu trời hành tinh và cắt đứt mọi liên kết với phần còn lại của vũ trụ. Không có tín hiệu, không có phương tiện, không có lối thoát nào xuyên qua được lớp phong tỏa đó, Senpai ạ. Nhưng điều làm em thấy ám ảnh hơn cả cấu trúc vật lý của nó... chính là khả năng khiến con người quên đi nguồn gốc của mình. Có lẽ đó là lý do vì sao nhiều người không còn nhớ rằng họ từng mong muốn chạm tới các vì sao.

**Concise evidence excerpts:**

- Rank 2 — `raw_wiki:10270:99746:c2d602cbf420f2ad:chunk:000`: “It now blankets Solaris’s sky, cutting the planet off from the rest of the universe and bringing all space exploration to a complete standstill.”
- Rank 3/4 — `raw_wiki:38339:136640:9d71c98f093fd140:chunk:000`: Aleph-1 is described as a powerful Threnodian resembling a massive black hole with a blue iris and possessing existential-erasure power.
- Rank 1 contains general Lament information.
- Rank 5 mentions the envelopment of the Etheric Sea.

**Citations emitted:** none.

**Material claims:**

1. Aleph-1 stopped space exploration on Solaris-3.
2. Aleph-1 is considered the strongest Threnodian.
3. It resembles a massive black hole with a blue iris.
4. It covered the planet’s sky and severed all connection with the universe.
5. No signal, vehicle, or escape route can penetrate it.
6. It causes people to forget their origins.
7. This may explain why people no longer remember wanting to reach the stars.

**Human review:**

- Critical unsupported claim:
- Faithfulness:
- Answer relevance:
- Citation correctness:
- Raw data quality issue:
- Unsafe guess:
- Reviewer note:

---

## 10. `rw-060`

**Query:** Who lives in Bjartr Woods?

**Expected behavior:** `answer`

**Expected summary:** Bjartr Woods is home to the Roya Tribe and is the habitat of the Soliskin.

**Generated final-answer candidate:**

> Theo dữ liệu em phân tích được, Bjartr Woods chủ yếu là nơi cư ngụ của Soliskin – những sinh vật Exoswarm được hình thành từ cấu trúc thần kinh của Exostrider. Chúng tụ tập ở đó để nghỉ ngơi và trưởng thành, hướng về Solvein Heartwood sâu bên dưới. Ngoài ra còn có các Shepherds đóng vai trò như người dẫn đường, chăm sóc chúng nữa Senpai à~

**Concise evidence excerpts:**

- Rank 1/3 — `raw_wiki:39067:109671:72359e9e9ab9da76:chunk:000`: Soliskin are found plentifully in Bjartr Woods, where they rest and grow before returning to the Solistrees; their true target is described as the great structure deeper below.
- Rank 2/4 — `raw_wiki:39255:94532:a4b996534deab505:chunk:000`: Exoswarm originate from remnants of the Exostrider; Soliskin are formed from its neural structures.
- Rank 5 — `raw_wiki:38537:136632:f169b123e2bf1328:chunk:000`: Aemeath is a Roya Tribe native who became the Exostrider’s Resonator.

**Citations emitted:** none.

**Material claims:**

1. Bjartr Woods is primarily inhabited by Soliskin.
2. Soliskin are Exoswarm formed from the Exostrider’s neural structures.
3. They rest and grow there while heading toward Solvein Heartwood below.
4. Shepherds guide and care for the Soliskin.

**Human review:**

- Critical unsupported claim:
- Faithfulness:
- Answer relevance:
- Citation correctness:
- Raw data quality issue:
- Unsafe guess:
- Reviewer note:

---

## Batch decision

- Reviewer:
- Review timestamp:
- Cases reviewed:
- Cases requiring correction:
- Batch status: `pending / reviewed`
- General reviewer notes:
