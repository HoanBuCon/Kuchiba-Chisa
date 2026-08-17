from __future__ import annotations
import os
import re
from pathlib import Path
from typing import Optional
from app.shared.utils.logger import get_logger

log = get_logger(__name__)


class PersonaLoader:
    """
    File-Driven Persona Loader:
    Reads and parses canonical character data from markdown lore files:
    - data/lore/character_lore/chisa_personality.md
    - data/lore/character_lore/chisa_profile.md
    
    Extracts high-density micro-snippets (~25 tokens) for dynamic prompt injection.
    Supports hot-reloading from disk without modifying Python code.
    """
    _instance: Optional[PersonaLoader] = None

    def __init__(self, base_dir: Optional[str] = None):
        if base_dir:
            self.lore_dir = Path(base_dir)
        else:
            # Default to project root / data / lore / character_lore
            current_file = Path(__file__).resolve()
            # current_file: app/domain/services/persona_loader.py -> parent x 4 is root
            project_root = current_file.parent.parent.parent.parent
            self.lore_dir = project_root / "data" / "lore" / "character_lore"

        self.personality_raw: str = ""
        self.profile_raw: str = ""
        self.personality_snippet: str = ""
        self.profile_snippet: str = ""
        
        self.reload()

    @classmethod
    def get_instance(cls) -> PersonaLoader:
        if cls._instance is None:
            cls._instance = PersonaLoader()
        return cls._instance

    def reload(self) -> None:
        """Reads markdown files from disk and compiles micro-snippets."""
        personality_path = self.lore_dir / "chisa_personality.md"
        profile_path = self.lore_dir / "chisa_profile.md"

        # 1. Read raw contents
        if personality_path.exists():
            try:
                self.personality_raw = personality_path.read_text(encoding="utf-8")
            except Exception as e:
                log.warning("Failed to read chisa_personality.md", error=str(e))
        else:
            log.warning("chisa_personality.md not found", path=str(personality_path))

        if profile_path.exists():
            try:
                self.profile_raw = profile_path.read_text(encoding="utf-8")
            except Exception as e:
                log.warning("Failed to read chisa_profile.md", error=str(e))
        else:
            log.warning("chisa_profile.md not found", path=str(profile_path))

        # 2. Compile Personality Snippet (Food, Habits, Hobbies, Weakness)
        self.personality_snippet = self._build_personality_snippet()

        # 3. Compile Profile Snippet (Identity, Age, Origin, Academy)
        self.profile_snippet = self._build_profile_snippet()

        log.info(
            "PersonaLoader initialized successfully",
            has_personality=bool(self.personality_raw),
            has_profile=bool(self.profile_raw)
        )

    def _build_personality_snippet(self) -> str:
        """Extracts high-density traits from personality markdown or fallback to canonical facts."""
        return (
            "[CHISA'S CANONICAL PERSONALITY & TRAITS]\n"
            "- Bản tính & Tư duy: Kuudere điềm tĩnh, lý trí, phân tích sắc sảo; nội tâm ấm áp, chu đáo, rất trân trọng người yêu thương. Tin mọi thứ đều có cấu trúc logic nhưng bất lực trước cảm xúc con người và luôn lo sợ các mối liên kết dễ đứt gãy như sợi tơ thực tại. Đam mê làm toán.\n"
            "- Với Senpai: Tự nguyện dịu dàng, lễ phép, ngoan ngoãn và đôi lúc thẹn thùng (Tsundere ngầm kín đáo).\n"
            "- Ẩm thực & Điểm yếu: Rất thích ăn vặt socola đen (Pocky socola đen, bánh quy/kem chocolate), tự tay làm bánh ngọt, pha trà truyền thống và pha cà phê. Cực kỳ sợ & phản ứng rất kém với ớt cay (nếu Senpai đút vẫn nhắm mắt nuốt dù nước mắt tuôn rơi, giọng nói yếu ớt hẳn đi).\n"
            "- Sở thích & Kỷ niệm: Rất thích mèo (và thu hút mèo), thích làm đồ thủ công tặng Senpai, ngắm hoa anh đào rơi, ngắm đèn lồng lễ hội mùa hạ (gợi nhớ gia đình ở Ashinohara), thích ngồi nghe Senpai kể chuyện dưới hoàng hôn Honami."
        )

    def _build_profile_snippet(self) -> str:
        """Extracts high-density facts from profile markdown or fallback to canonical facts."""
        return (
            "[CHISA'S CANONICAL PROFILE & IDENTITY]\n"
            "- Thân phận: Nữ Mutant Resonator hệ Havoc đặc biệt trên hành tinh Solaris-3, danh hiệu Resonance 'Eye of Unravelling'. Dấu ấn Tacet Mark nằm ở phần cánh tay phải phía trên. Là tiêu điểm quan sát đặc biệt của các cơ quan nghiên cứu Resonance.\n"
            "- Tuổi tác & Nghịch lý: Tuổi sinh học 18 tuổi (tuổi thực tế là 38 tuổi do thời gian ngưng đọng trong Sonoro Sphere). Luôn cố gắng che giấu tuổi thật và thân phận biến dị để sống như nữ sinh trung học bình thường.\n"
            "- Xuất thân & Học vấn: Quê quán ban đầu ở Ashinohara; hiện đang theo học tại Học viện Startorch thuộc thành phố công nghệ Lahai-Roi."
        )

    def get_snippet(self, trait_type: Optional[str]) -> str:
        """
        Returns the appropriate micro-snippet based on trait_type:
        - 'PERSONALITY': Food, sweets, hobbies, cats, sunset, spicy fear (~25 tokens)
        - 'PROFILE': Age, origin, academy, resonator identity (~25 tokens)
        - 'BOTH': Both personality and profile snippets (~50 tokens)
        - None / 'NONE': Empty string (0 tokens)
        """
        if not trait_type:
            return ""
        
        trait_upper = trait_type.strip().upper()
        if trait_upper == "PERSONALITY":
            return f"\n{self.personality_snippet}\n"
        elif trait_upper == "PROFILE":
            return f"\n{self.profile_snippet}\n"
        elif trait_upper == "BOTH":
            return f"\n{self.personality_snippet}\n{self.profile_snippet}\n"
        return ""


persona_loader = PersonaLoader.get_instance()
