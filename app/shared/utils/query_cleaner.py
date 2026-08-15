import re
from typing import Any, List, Optional, Set

# Comprehensive Vietnamese Chat Abbreviations Dictionary
ABBREVIATIONS = {
    r'\bko\b': 'không',
    r'\bk\b': 'không',
    r'\bhok\b': 'không',
    r'\bhông\b': 'không',
    r'\bkhum\b': 'không',
    r'\bkhg\b': 'không',
    r'\bđc\b': 'được',
    r'\bdc\b': 'được',
    r'\bvs\b': 'với',
    r'\bng\b': 'người',
    r'\bgđ\b': 'gia đình',
    r'\bthik\b': 'thích',
    r'\btik\b': 'thích',
    r'\bnx\b': 'nữa',
    r'\bcx\b': 'cũng',
    r'\bj\b': 'gì',
    r'\bjz\b': 'gì vậy',
    r'\bjztr\b': 'gì vậy trời',
    r'\bmn\b': 'mọi người',
    r'\bmng\b': 'mọi người',
    r'\bbth\b': 'bình thường',
    r'\btrc\b': 'trước',
    r'\bmik\b': 'mình',
    r'\bmềnh\b': 'mình',
    r'\bbít\b': 'biết',
    r'\bbit\b': 'biết',
    r'\bz\b': 'vậy',
    r'\bzậy\b': 'vậy',
    r'\blun\b': 'luôn',
    r'\blunh\b': 'luôn',
    r'\bs\b': 'sao',
    r'\bntn\b': 'như thế nào',
}

# Coreference / Follow-up pronoun patterns
COREFERENCE_PATTERNS = [
    r'\b(anh|cô|bà|ông|ngài|hắn|họ)\s*(ấy|đó|này|kia)\b',
    r'\b(người|nhân vật|tiểu thư|vị tướng|tướng quân|bác sĩ|giáo sư|họa sĩ|thủ lĩnh)\s*(đó|này|ấy|kia)\b',
    r'\b(cái|chiếc|món|đồ|vật|con|vị|bức|quyển|trang|vùng|mảnh|nơi|chỗ)\s*(đó|này|ấy|kia)\b',
    r'\b(vũ khí|cây kiếm|khẩu súng|con rồng|linh thú|sinh vật|thần thú|chuông|kính|nhẫn|dây chuyền|trang phục|áo|quần)\s*(đó|này|ấy|kia)\b',
    r'\b(ở|tại|nơi|chỗ)\s*(đó|đấy|này|kia|đâu)\b',
    r'\b(chiêu|kỹ năng|năng lực|forte|phép|nộ)\s*(đó|này|ấy|kia|nào)\b',
    r'\b(tổ chức|học viện|phe phái|đội quân|bang hội)\s*(đó|này|ấy|kia)\b',
    r'^(còn|thế còn|vậy còn|thế|vậy|sao)\b',
    r'\b(tại sao lại (thế|vậy|như vậy)|tại sao (như vậy|vậy|thế)|vì sao lại (thế|vậy|như vậy)|như thế nào vậy|là sao ta)\b',
    r'\b(anh ta|cô ta|họ|nó|chúng nó|hắn ta)\b',
    r'\b(đó|này|ấy|kia)\s+(là\s+gì|ở\s+đâu|ra\s+sao|như\s+thế\s+nào|xuất\s+hiện\s+khi\s+nào|có\s+tác\s+dụng\s+gì)\b',
]

GREETING_PREFIXES = [
    "chào ngày mới", "chào buổi sáng", "chào buổi tối", "chào buổi chiều",
    "chào em chisa", "chào chisa", "chào em", "chào senpai", "chào bạn", "chào",
    "hello chisa", "hello chía chía", "hello chía", "hello",
    "hi chisa", "hi chía chía", "hi em", "hi", "hey chisa", "hey",
    "alo chisa", "alo em", "alo", "lô chisa", "lô"
]

CONVERSATIONAL_PREFIXES = [
    "à mà cho anh hỏi về", "à mà cho em hỏi về", "à mà cho anh hỏi", "à mà cho em hỏi", "à mà",
    "nhưng mà cho anh hỏi", "nhưng mà cho em hỏi", "nhưng mà",
    "nhân tiện cho anh hỏi", "nhân tiện cho em hỏi", "nhân tiện",
    "tiện thể cho anh hỏi", "tiện thể cho em hỏi", "tiện thể",
    "với lại cho anh hỏi", "với lại cho em hỏi", "với lại",
    "cho anh hỏi về", "cho em hỏi về", "cho senpai hỏi về", "cho hỏi về", "cho tớ hỏi về",
    "cho anh hỏi là", "cho em hỏi là", "cho senpai hỏi là", "cho hỏi là",
    "cho anh hỏi", "cho em hỏi", "cho senpai hỏi", "cho tớ hỏi", "cho mình hỏi", "cho hỏi",
    "kể cho anh nghe về", "kể cho em nghe về", "kể cho senpai nghe về",
    "kể anh nghe về", "kể em nghe về", "kể senpai nghe về",
    "nói cho anh nghe về", "nói cho em nghe về", "nói cho senpai nghe về",
    "cho anh biết về", "cho em biết về", "cho senpai biết về", "cho biết về",
    "nói cho anh biết về", "nói cho em biết về", "nói cho senpai biết về",
    "kể cho anh về", "kể cho em về", "kể cho senpai về", "kể cho tớ về",
    "hãy kể về", "em hãy kể về", "hãy giải thích về", "giải thích giúp anh về",
    "giải thích giúp em về", "giải thích giúp về", "giải thích về",
    "kể về", "nói về", "chia sẻ về", "hỏi về", "kể cho anh", "kể cho em",
    "tìm hiểu về", "thông tin về", "chi tiết về", "biết về", "muốn biết về",
    "senpai muốn biết về", "anh muốn biết về", "tớ muốn biết về",
    "chisa có biết về", "em có biết về", "có biết về",
    "chisa có biết", "em có biết", "anh có biết", "senpai có biết", "bạn có biết", "có biết",
    "chisa biết về", "em biết về", "anh biết về", "senpai biết về", "bạn biết về",
    "chisa biết", "em biết", "anh biết", "senpai biết", "bạn biết"
]

CONVERSATIONAL_SUFFIXES = [
    "đi chía chía", "đi chisa", "đi em", "đi anh", "đi senpai",
    "nhé chía chía", "nhé chisa", "nhé em", "nhé anh", "nhé senpai", "nhé",
    "nha chía chía", "nha chisa", "nha em", "nha anh", "nha senpai", "nha",
    "nhỉ chisa", "nhỉ em", "nhỉ", "nhở", "nhá", "nhen", "hén",
    "phải không em", "phải không chisa", "phải không chía", "phải không anh", "phải không senpai", "phải không ạ", "phải không nè", "phải không",
    "đúng không em", "đúng không chisa", "đúng không anh", "đúng không senpai", "đúng không ạ", "đúng không nè", "đúng không",
    "có phải không em", "có phải không chisa", "có phải không", "có đúng không",
    "không em", "không chisa", "không chía", "không anh", "không senpai", "không ạ", "không nè", "không nha", "không nhé", "không nhỉ", "không",
    "hông em", "hông chisa", "hông anh", "hông",
    "ko em", "ko chisa", "ko anh", "ko", "k em", "k chisa", "k",
    "chưa em", "chưa chisa", "chưa anh", "chưa senpai", "chưa ạ", "chưa",
    "đi chứ", "đi nào", "đi", "với em", "với", "ạ", "thế nào", "sao",
    "được không em", "được không", "hả em", "hả chisa", "hả anh", "hả", "vậy em", "vậy anh", "vậy"
]

CALLING_NAMES = ["chía chía", "chía", "chisa", "senpai", "bé chisa", "em chisa"]

PRONOUNS_STOPWORDS = {
    "em", "anh", "chisa", "chía", "chía chía", "senpai", "tớ", "cậu", "bạn", 
    "ơi", "à", "nhé", "nha", "nè", "hả", "đấy", "đó", "thế", "vậy", "đi", "ạ",
    "của", "và", "là", "gì", "nào", "sao"
}


# Community Nicknames & Slang to Canonical Game Names
COMMUNITY_NICKNAMES = {
    r'\b(tướng rồng|rồng xanh|long vương)\b': 'Jiyan',
    r'\b(rùa chuông|con rùa chuông|chuông mai rùa)\b': 'Bell-Borne Geochelone',
    r'\b(cá voi|người giữ bờ|thủ hộ giả)\b': 'Shorekeeper',
    r'\b(chị dậu|bướm hoa)\b': 'Camellya',
    r'\b(cáo lửa|cô giáo changli)\b': 'Changli',
    r'\b(bác sĩ rồng|tiểu thư jinhsi)\b': 'Jinhsi',
    r'\b(thầy thuốc baizhi|bác sĩ baizhi)\b': 'Baizhi',
    r'\b(mỏ đá|khu mỏ)\b': "Tiger's Maw",
    r'\b(thừa tiêu sơn)\b': 'Mt. Firmament',
    r'\b(thành jinzhou|kim châu)\b': 'Jinzhou',
    r'\b(hắc ngạn|biển đen)\b': 'Black Shores',
    r'\b(thánh thú jue|rồng vàng)\b': 'Jué',
    r'\b(thảm họa lament|diệt vong lament)\b': 'The Lament',
    r'\b(dạ hành quân)\b': 'Midnight Rangers',
    r'\b(tàn tinh hội)\b': 'Fractsidus',
}

# Bot Persona indicators: Match when asking about AI (Chisa)'s attributes
# Ensures "em" does NOT match if immediately followed by another name (e.g. "em Chixia")
BOT_PERSONA_INDICATORS = [
    r'\b(em|chisa|chía|bé chisa)\b\s+(có\s+)?(năng lực|kỹ năng|forte|chiêu|resonance|vũ khí|thuộc tính|hệ|tiểu sử|xuất thân|lý lịch|lai lịch|quê|tuổi|sở thích|món ăn|sợ|điểm yếu|bí mật)',
    r'\b(năng lực|kỹ năng|forte|chiêu|resonance|vũ khí|thuộc tính|hệ|tiểu sử|xuất thân|lý lịch|lai lịch|quê|tuổi|sở thích|món ăn|sợ|điểm yếu|bí mật)\s+(của\s+)?(em|chisa|chía|bé chisa)\b',
    r'\b(em|chisa|chía|bé chisa)\b\s+(dùng\s+vũ\s+khí|chiến\s+đấu|sinh\s+ra|thích\s+ăn|thích\s+gì|ghét\s+gì|sợ\s+gì)',
    r'\b(em|chisa|chía)\s+(là\s+ai|là\s+gì|ở\s+đâu|thuộc\s+phe\s+nào|đến\s+từ\s+đâu)\b',
]

# User Persona indicators: Match when asking about User (Senpai)'s memory/profile
USER_PERSONA_INDICATORS = [
    r'\b(anh|tôi|mình|senpai|tớ|chị)\b\s+(tên\s+là|làm\s+nghề|làm\s+việc|ở\s+đâu|sinh\s+năm|mấy\s+tuổi|thích|dị\s+ứng|ghét|hứa|bảo|dặn|nhớ)',
    r'\b(tên|công\s+việc|nghề\s+nghiệp|sở\s+thích|món\s+ăn|kỷ\s+niệm|lời\s+hứa|quê\s+quán|tuổi)\s+(của\s+)?(anh|tôi|mình|senpai|tớ|chị)\b',
    r'\b(anh|tôi|mình|senpai|tớ|chị)\b\s+(có\s+nhớ|hôm\s+trước|hôm\s+qua|ngày\s+mai)',
]


def resolve_persona_pronouns(text: str, intent_hint: Optional[str] = None) -> str:
    """
    Deictic Pronoun & Community Slang Disambiguation:
    - Resolves 'em', 'chisa' inquiring about bot attributes -> 'Kuchiba Chisa (Resonator)'
    - Resolves 'anh', 'senpai' inquiring about user memory -> 'Senpai / người dùng'
    - Normalizes community nicknames ('tướng rồng' -> 'Jiyan', 'rùa chuông' -> 'Bell-Borne Geochelone')
    Zero-token Fast-Path (<0.1ms).
    """
    if not text:
        return text

    resolved = text.strip()
    resolved_lower = resolved.lower()

    # 1. Apply Community Nicknames Normalization
    for pattern, repl in COMMUNITY_NICKNAMES.items():
        if re.search(pattern, resolved_lower, re.IGNORECASE):
            resolved = re.sub(pattern, repl, resolved, flags=re.IGNORECASE)
            resolved_lower = resolved.lower()

    # 2. Resolve Bot Persona ("em", "chisa" -> Kuchiba Chisa)
    is_bot_persona_query = any(re.search(pat, resolved_lower) for pat in BOT_PERSONA_INDICATORS)
    if is_bot_persona_query or intent_hint == "LORE":
        # Check if "em" is used without a third-party character name directly behind it
        # e.g., "em chixia" -> do NOT replace; "em có năng lực gì" -> REPLACE
        if re.search(r'\b(em|bé chisa|chía)\b', resolved_lower) and not re.search(r'\b(em|bé)\s+(chixia|jiyan|sanhua|yinlin|camellya|jinhsi|changli|yangyang|baizhi|danjin|encore|aalto|calcharo|mortefi|verina|lingyang|taoqi|rover)\b', resolved_lower):
            # If query has persona words, enrich with canonical Kuchiba Chisa
            if "kuchiba chisa" not in resolved_lower and "chisa" not in resolved_lower:
                resolved = f"{resolved} (Kuchiba Chisa Resonator)"
            elif "kuchiba" not in resolved_lower:
                resolved = re.sub(r'\bchisa\b', 'Kuchiba Chisa', resolved, flags=re.IGNORECASE)

    # 3. Resolve User Persona ("anh", "senpai" -> Senpai/User memory)
    is_user_persona_query = any(re.search(pat, resolved_lower) for pat in USER_PERSONA_INDICATORS)
    if is_user_persona_query or intent_hint == "MEMORY":
        if re.search(r'\b(anh|senpai|tớ|mình|chị)\b', resolved_lower) and not re.search(r'\b(anh|ông|chú)\s+(jiyan|aalto|calcharo|mortefi|lingyang|geshu lin|scar)\b', resolved_lower):
            if "senpai" not in resolved_lower and "người dùng" not in resolved_lower:
                resolved = f"{resolved} (Senpai / người dùng)"

    return resolved


def clean_query_for_rag(text: str) -> str:
    """
    Cleans user query by iteratively removing conversational greetings, chatbot request prefixes, 
    and common suffixes/particles with strict word-boundary matching.
    Intelligently preserves calling names when no other entity exists in the query.
    """
    if not text:
        return text
        
    original = text
    text = text.lower().strip()
    
    # 1. Apply abbreviation normalization
    for pattern, repl in ABBREVIATIONS.items():
        text = re.sub(pattern, repl, text)
        
    # Iterative cleaning pass (up to 3 passes to handle nested patterns like "Chào em Chisa nhé, cho anh hỏi là...")
    for _ in range(3):
        prev_text = text
        text = re.sub(r'^[,\.\?\!\-\s\:]+|[,\.\?\!\-\s\:]+$', '', text).strip()
        
        # Strip greetings with word boundaries
        for g in sorted(GREETING_PREFIXES, key=len, reverse=True):
            text = re.sub(rf'^(?:{re.escape(g)})(?:\s+|$|[,\.\?\!\-\:])', '', text).strip()
                
        # Strip conversational prefixes with word boundaries
        for p in sorted(CONVERSATIONAL_PREFIXES, key=len, reverse=True):
            subbed = re.sub(rf'^(?:{re.escape(p)})(?:\s+|$|[,\.\?\!\-\:])', '', text).strip()
            if subbed != text:
                text = subbed
                break
                
        # Strip trailing suffixes with word boundaries
        for s in sorted(CONVERSATIONAL_SUFFIXES, key=len, reverse=True):
            text = re.sub(rf'(?:\s+|^|[,\.\?\!\-\:])(?:{re.escape(s)})$', '', text).strip()

        # Strip particles at start like "nhé,", "nha,"
        text = re.sub(r'^(nhé|nha|ạ|ơi|nè)[,\.\?\!\-\s\:]+', '', text).strip()

        # Strip calling names with word boundaries ONLY IF the question is not about bot's own attributes
        # (e.g. "Chisa ơi Jiyan dùng gì" -> "jiyan dùng gì", but "Chisa có năng lực gì" -> keeps "chisa có năng lực gì")
        for name in CALLING_NAMES:
            if re.search(rf'^(?:{re.escape(name)})(?:\s+|$|[,\.\?\!\-\:])', text):
                test_sub = re.sub(rf'^(?:{re.escape(name)})(?:\s+|$|[,\.\?\!\-\:])', '', text).strip()
                is_attr_inquiry = any(re.search(pat, text) for pat in BOT_PERSONA_INDICATORS)
                if not is_attr_inquiry:
                    text = test_sub
            
            # Suffix calling name
            text = re.sub(rf'(?:\s+|^|[,\.\?\!\-\:])(?:{re.escape(name)})$', '', text).strip()

        if text == prev_text:
            break
            
    text = re.sub(r'^[,\.\?\!\-\s\:]+|[,\.\?\!\-\s\:]+$', '', text).strip()
    
    if not text:
        return original.strip()
    return text


def has_coreference_markers(text: str) -> bool:
    """
    Checks if a query contains pronouns or follow-up markers referring to prior context.
    Example: "Vũ khí của anh ấy là gì?", "Con rồng đó xuất hiện khi nào?", "Thế còn kỹ năng nộ?", "Tại sao lại như vậy?"
    """
    if not text:
        return False
    text_lower = text.lower().strip()
    for pat in COREFERENCE_PATTERNS:
        if re.search(pat, text_lower):
            return True
    return False


REACTION_WORDS = {
    "haha", "hihi", "hehe", "kaka", "kkk", "lol", "lmao", "ahihi",
    "ok", "okay", "ừ", "ừm", "vâng", "dạ", "chào", "đúng", "chuẩn", "chính xác",
    "cảm", "ơn", "cảm ơn", "thanks", "thank", "tks", "bye", "tạm", "biệt", "tạm biệt",
    "g9", "ngủ", "ngon", "ngủ ngon", "uầy", "chà", "wow", "oh", "ô", "ôi", "haiz",
    "hic", "huhu", "vui", "quá", "đi", "nhỉ", "nhở", "thật", "luôn", "nha", "nhé",
    "nè", "nhen", "hén", "đấy", "đó", "lắm", "ghê", "đỉnh", "tuyệt", "hay"
}


def is_meaningful_query(query: str) -> bool:
    """
    Kiểm tra xem query sau khi làm sạch có chứa từ vựng mang ngữ nghĩa tìm kiếm RAG hay không.
    Nếu chỉ là các câu cảm thán/phản hồi ngắn (haha, ok, cảm ơn, uầy đỉnh vậy...) hoặc đại từ thì trả về False.
    """
    if not query:
        return False
    words = re.findall(r'\w+', query.lower())
    non_reaction_words = [w for w in words if w not in PRONOUNS_STOPWORDS and w not in REACTION_WORDS]
    total_chars = sum(len(w) for w in non_reaction_words)
    return len(non_reaction_words) > 0 and total_chars >= 3


def enrich_query_with_entities(cleaned_query: str, entity_resolver: Any, intent_hint: Optional[str] = None) -> str:
    """
    Fast-Path Entity & Persona Enrichment:
    1. Resolves Persona Pronouns ('em' -> 'Kuchiba Chisa', 'anh' -> 'Senpai') and Community Nicknames.
    2. Extracts matched entities from EntityResolver and appends canonical/English aliases.
    Zero LLM cost (< 0.2ms).
    """
    if not cleaned_query:
        return cleaned_query

    # Step 1: Deictic Persona & Slang Disambiguation
    query = resolve_persona_pronouns(cleaned_query, intent_hint=intent_hint)
    if not entity_resolver:
        return query

    try:
        extracted = entity_resolver.extract_entities(query)
        if not extracted:
            return query
            
        aliases_to_add: Set[str] = set()
        for ent in extracted:
            if ent.lower() not in query.lower():
                aliases_to_add.add(ent)
            # Check canonical / English mappings in entity registry
            if hasattr(entity_resolver, "get_entity_record"):
                rec = entity_resolver.get_entity_record(ent)
                if rec and rec.canonical_name and rec.canonical_name.lower() not in query.lower():
                    aliases_to_add.add(rec.canonical_name)
                    
        if aliases_to_add:
            return f"{query} ({', '.join(sorted(aliases_to_add))})"
    except Exception:
        pass
        
    return query
