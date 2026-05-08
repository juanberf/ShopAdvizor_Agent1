import uuid
from dataclasses import dataclass, field


@dataclass
class SessionConfig:
    user_id: str
    tone: str = "ejecutivo"
    language: str = "es"
    focus_segments: list = field(default_factory=list)
    campaign_files: list = field(default_factory=list)
    session_id: str = field(
        default_factory=lambda: str(uuid.uuid4())[:8]
    )

    def __post_init__(self):
        valid_tones = ["ejecutivo", "técnico", "comercial"]
        valid_languages = ["es", "fr"]
        if self.tone not in valid_tones:
            raise ValueError(f"Tono debe ser uno de: {valid_tones}")
        if self.language not in valid_languages:
            raise ValueError(f"Idioma debe ser uno de: {valid_languages}")