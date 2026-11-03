"""Server-owned messages in Chisa's voice, following the frozen addressing rules (PER-005)."""

# Self: "Em", user: "Senpai"; see ContextBuilder.
GROUNDED_ABSTENTION = (
    "Em chưa có đủ bằng chứng trong nguồn hiện tại để trả lời chính xác. "
    "Senpai có thể cho em thêm ngữ cảnh hoặc hỏi theo cách khác không?"
)
# Verbatim, server-verified quotes (used when a paraphrase cannot be verified across
# languages) are presented in Chisa's voice; the quote text itself is never altered.
GROUNDED_EXTRACTIVE_FRAME = "Em tìm được trong tư liệu gốc nè Senpai: “{quote}”"
# Verified claims are neutral facts, so the server adds the addressing (PER-003).
GROUNDED_ANSWER_LEAD = "Em tra được thế này nè Senpai: "
