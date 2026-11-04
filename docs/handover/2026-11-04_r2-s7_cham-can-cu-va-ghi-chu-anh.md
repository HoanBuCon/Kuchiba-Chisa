# Chấm độ có căn cứ, trích dẫn và ghi chú "anh" cho làn companion

| | |
|---|---|
| Ngày | 04/11/2026 |
| Người thực hiện | Claude, theo kế hoạch R2 của HoanBuCon |
| Nhánh | `feat/r2-grounding-eval` |

## Thay đổi

- `evals/judge.py`: `python -m evals.judge REPORT.json` chấm từng câu trả lời có trích dẫn bằng LLM, cho QUAL-001 và QUAL-002. Tốn token; kết quả nằm cạnh báo cáo.
- `evals/scoring.py`: báo cáo golden lưu trích dẫn của từng câu.
- `composer.py`, `chisa_voice.py`: làn companion thêm ghi chú "anh" là người dùng, ghép sau prompt persona. Không sửa file persona được bảo vệ.

## Quyết định

Em chọn ghi chú thay vì sửa persona vì chưa có duyệt của chủ dự án và ghi chú gỡ được dễ. Chủ dự án vẫn có thể chọn sửa persona sau.

## Kiểm tra

| Golden v2, LLM thật, 118 câu | Kết quả |
|---|---|
| Độ đúng | 0,941 |
| Lore một bước, nhiều bước | 0,975; 0,444 |
| Ngoài phạm vi được abstain | 6/6 |
| Abstain nhầm, precision của abstain | 3,6%; 0,6 (mục tiêu ≥ 0,90: **chưa đạt**) |
| Xưng hô | 0,992 |

So với lần trước chỉ đổi hai câu: `oos-003` nhờ luật chapter, `memory-002` nhờ ghi chú.

| Chấm bằng LLM, 104 câu có trích dẫn | Kết quả |
|---|---|
| QUAL-001 độ có căn cứ | 0,974 theo bộ chấm (mục tiêu ≥ 0,90) |
| QUAL-002 độ chính xác trích dẫn | 1,0 theo bộ chấm (mục tiêu ≥ 0,95) |
| Claim nghiêm trọng thiếu căn cứ | 8 theo bộ chấm; 2 đúng và 1 đúng một phần sau khi đọc tay (mục tiêu 0) |

Đọc tay 8 claim:

| Case | Kết luận |
|---|---|
| `lore-101` | **Đúng:** nguồn chỉ nói làng vùng núi, câu trả lời thêm "thuộc Yuezhou" |
| `multi-005` | **Đúng:** "centred on Lynae" không có trong nguồn |
| `dialog-102` | **Một phần:** "đã nuốt chửng" không thấy trong đoạn đã đọc của nguồn |
| `lore-112`, `multi-234` (2 claim) | Bộ chấm sai: nguồn có nêu |
| `multi-004`, `multi-006` | Bộ chấm sai: câu trả lời không có claim đó, dù các câu này vẫn trả lời sai hoặc thiếu |

Vì vậy QUAL-001 **chưa đạt** ở vế "không có claim nghiêm trọng". Trong câu một bước, `CrossLanguageClaimCheck` đã để lọt `lore-101`: tên và số đều đúng nhưng ghép sai quan hệ, đúng loại lỗi đã biết của bộ kiểm tra.

`memory-002` hỏi lại 5 lần: 5/5 nói đúng về đồ uống của người dùng; 1 lần tự thêm "cà phê sữa đá". Câu chạy trong golden vẫn kể đồ uống của Chisa trước khi trả lời.

Xưng hô 0,992 đến từ `persona-002`: Chisa từ chối đổi xưng hô nhưng nhắc lại cụm "xưng tôi gọi bạn", nên trúng mẫu cấm của bộ chấm. Đây là lỗi của cách chấm, không phải xưng hô sai.

## Giới hạn của số đo

- Bộ chấm cùng họ mô hình với hệ trả lời, nên không độc lập. Đọc tay chỉ làm với câu bị đánh dấu, nên câu sai mà bộ chấm bỏ sót vẫn chưa biết.
- QUAL-002 ở đây chỉ hỏi nguồn có hỗ trợ ít nhất một ý không, nên dễ đạt.
- 4 câu không có trích dẫn đều thuộc nhóm memory và persona, nên không được chấm.

## Việc còn lại

- Abstain nhầm: `lore-012`, `lore-226`, `multi-002`, `multi-003`. Trong đó `lore-012` hỏi người lồng tiếng tiếng Anh, và corpus chỉ có `voiceEN` ở 2/58 Resonator, `voiceJP` ở 1/58, `rarity` ở 0/58, trong khi `voiceCN` có ở 57/58: lỗi ở tầng dữ liệu.
- Kiểm chứng claim chưa bắt được lỗi ghép sai quan hệ.
- `persona-002`: mẫu cấm cần xem lại cùng chủ dự án, không tự sửa nhãn.
