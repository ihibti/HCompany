from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(Path(__file__).parent.parent.parent / ".env"), extra="ignore")

    hai_api_key: str = ""
    linkup_api_key: str = ""
    gladia_api_key: str = ""
    holo_fast_model: str = "holo4-35b-a3b"
    holo_smart_model: str = "holo4-27b"
    fake_ai: bool = False
    h_local: bool = True
    data_dir: Path = Path(__file__).parent.parent / "data"


@lru_cache
def get_settings() -> Settings:
    return Settings()
