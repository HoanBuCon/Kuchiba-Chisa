"""
Nguồn tri thức duy nhất chứa các Regex Pattern dùng cho System Actions
(Tóm tắt cuộc trò chuyện, báo cáo cảm xúc, tra cứu internet).
Được sử dụng chung bởi IntentClassifier (L2) và KeywordToolRouter.
"""

SYSTEM_PATTERNS = {
    "summarize_conversation_memory": [
        r"tóm tắt.{0,15}(cuộc trò chuyện|hội thoại|nãy giờ|buổi chat|session)",
        r"(tổng hợp|tổng kết).{0,15}(cuộc trò chuyện|những gì|điểm chính|nãy giờ)",
        r"em ghi lại.{0,15}(điểm chính|những gì|cuộc trò chuyện)",
        r"cho anh xem tóm tắt",
    ],
    "get_emotion_report": [
        r"(cho anh xem|xuất|hiển thị|xem).{0,15}(chỉ số cảm xúc|bảng đo cảm xúc|báo cáo cảm xúc)",
        r"(em đang cảm thấy thế nào|tâm trạng của em).{0,10}(theo số liệu|theo chỉ số)",
        r"(chỉ số|bảng đo|báo cáo).{0,10}cảm xúc.{0,10}(của em|hiện tại)",
    ],
    "web_search": [
        r"(tra mạng|lên mạng|tra cứu trên internet|lên web).{0,25}",
        r"search google.{0,20}",
        r"(em tìm kiếm|em tra|em tìm).{0,10}(trên internet|trên mạng|giúp anh)",
        r"(tìm giúp|tra giúp).{0,10}(anh|tớ|mình).{0,10}(trên|mạng|internet)",
    ],
}

ALL_SYSTEM_PATTERNS = [
    pattern for patterns in SYSTEM_PATTERNS.values() for pattern in patterns
]
