# ADR-0001: Hướng phát triển hệ thống Chisa v2

- Trạng thái: **Accepted**
- Ngày: 2026-10-31
- Người quyết định: chủ dự án
- Liên quan: [SRS v2](../SRS_Chisa_v2_Advanced_Agentic_RAG.md) (mục 10, 15), [khảo sát wiki](../../reports/WuWa_Wiki_Source_Survey.md) (mục 12), [nghiên cứu kiến trúc](../../reports/Agentic_Chisa_Architecture_Research.md)

## Bối cảnh

- Hệ hiện tại là pipeline tuyến tính 12 stage; dữ liệu lore cũ coi là rác; trí nhớ dài hạn chỉ được gợi khi router chọn vector search.
- Khảo sát 2.395 trang wiki cho thấy chất lượng phụ thuộc chủ yếu vào dữ liệu:
  - 92% quest phụ và 45% main quest không có Summary;
  - khoảng 6,8% token trùng lặp xuyên trang;
  - 36% cảnh thoại vượt một chunk;
  - metadata quốc gia và phiên bản từ category không đáng tin cho nội dung mới.
- Chisa là dự án cá nhân, chạy trên một VPS 4 vCPU / 8 GB, do một người phát triển.

## Quyết định

1. Phê duyệt **SRS v2** (hai chế độ Advanced/Agentic, RBAC 4 vai trò, trí nhớ 4 lớp, Monitoring M0, quy ước bắt buộc) và các chỉnh sửa **E1–E13**.
2. Lộ trình theo nguyên tắc **dữ liệu trước, agent sau; đo trước khi xây; mỗi pha giao được giá trị**:
   - R0 Nền móng
   - R1 Dữ liệu Tier A
   - R2 Advanced RAG v2
   - R3 IAM v2
   - R4 Agentic beta (Admin trước, rồi nhóm Chía-con nhỏ)
   - R5 Mở rộng (trí nhớ đầy đủ, Tier B, alias Hán-Việt)
   - R6 Dọn dẹp
3. Agentic chỉ mở rộng khi đạt QUAL-007 (hơn Advanced ≥ 15 điểm % ở nhóm câu hỏi nhiều bước/liệt kê/chi tiết thoại).
4. Hệ hiện tại: đóng băng tính năng, chỉ sửa lỗi bảo mật và lỗi nghiêm trọng.
5. Tạm gác ngoài v2.0: multi-agent, tự động chuyển chế độ, "trả lời nhanh rồi đào sâu", lọc spoiler theo phiên bản, Monitoring M1, Telegram/Facebook, fine-tune, đổi model embedding khi chưa có bằng chứng.
6. SRS v2 quản lý trong `docs/`. Bản chụp dữ liệu khảo sát lưu cục bộ ở `data/survey/wuwa_wiki_20261030/` (gitignore) làm baseline cho R1.

## Hệ quả

- Giá trị lớn nhất cho người dùng đến sớm, ở R2: trả lời đúng hơn, nhớ người dùng ở mọi lượt, nhân cách ổn định.
- Phần đổi SRS về ngân sách LLM chỉ còn áp cho chế độ Agentic (R4).
- Rủi ro khối lượng lớn được kiểm soát vì có thể dừng sau bất kỳ pha nào mà vẫn có hệ thống tốt hơn hiện tại.

## Phương án đã cân nhắc

- Làm Agentic trước: bị loại vì phụ thuộc dữ liệu sạch, kho có cấu trúc và IAM.
- Nâng cấp dần hệ hiện tại thay vì xây runtime mới: bị loại vì pipeline tuyến tính và object ngữ cảnh dùng chung không mở rộng được cho agent.
