import re

def clean_query_for_rag(text: str) -> str:
    """
    Cleans user query by removing conversational greetings, chatbot request prefixes, 
    and common suffixes/particles. This prevents semantic dilution in dense embedding search,
    ensuring relevant lore chunks are retrieved.
    """
    if not text:
        return text
        
    original = text
    text = text.lower().strip()
    
    # Remove punctuation at ends
    text = re.sub(r'^[,\.\?\!\-\s]+|[,\.\?\!\-\s]+$', '', text)
    
    # 1. Greetings
    greetings = [
        "chào ngày mới", "chào buổi sáng", "chào buổi tối", "chào buổi chiều",
        "chào em chisa", "chào chisa", "chào em", "chào senpai", "chào",
        "hello chisa", "hello chías chías", "hello chía chía", "hello",
        "hi chisa", "hi", "hey chisa", "hey"
    ]
    for g in greetings:
        if text.startswith(g):
            text = text[len(g):].strip()
            text = re.sub(r'^[,\.\?\!\-\s\:]+', '', text).strip()
            
    # 2. Conversational prompt prefixes
    prefixes = [
        "kể cho anh nghe về", "kể cho em nghe về", "kể cho senpai nghe về",
        "kể anh nghe về", "kể em nghe về", "kể senpai nghe về",
        "nói cho anh nghe về", "nói cho em nghe về", "nói cho senpai nghe về",
        "cho anh biết về", "cho em biết về", "cho senpai biết về",
        "nói cho anh biết về", "nói cho em biết về",
        "kể cho anh về", "kể cho em về", "kể cho senpai về",
        "hãy kể về", "em hãy kể về", "kể về", "nói về", "chia sẻ về",
        "hỏi về", "kể cho anh", "kể cho em", "biết về"
    ]
    prefixes.sort(key=len, reverse=True)
    for p in prefixes:
        if text.startswith(p):
            text = text[len(p):].strip()
            text = re.sub(r'^[,\.\?\!\-\s\:]+', '', text).strip()
            break
            
    # 3. Suffixes and particles
    suffixes = [
        "đi chía chía", "đi chías chías", "đi chisa", "đi em", "đi anh",
        "nhé chía chía", "nhé chisa", "nhé em", "nhé",
        "nha chía chía", "nha chisa", "nha em", "nha",
        "đi chứ", "đi", "với", "ạ", "thế nào", "nhỉ", "sao", "được không"
    ]
    suffixes.sort(key=len, reverse=True)
    
    for s in suffixes:
        if text.endswith(s):
            text = text[:-len(s)].strip()
            text = re.sub(r'[,\.\?\!\-\s]+$', '', text).strip()
            
    # Remove name calls
    names = ["chía chía", "chías chías", "chisa", "senpai"]
    for name in names:
        if text.endswith(name):
            text = text[:-len(name)].strip()
            text = re.sub(r'[,\.\?\!\-\s]+$', '', text).strip()
        if text.startswith(name):
            text = text[len(name):].strip()
            text = re.sub(r'^[,\.\?\!\-\s\:]+', '', text).strip()
            
    text = re.sub(r'^[,\.\?\!\-\s]+|[,\.\?\!\-\s]+$', '', text).strip()
    
    if not text:
        return original
    return text
