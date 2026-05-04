from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="WEBSTALKER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Path("data")

    request_timeout_seconds: float = 30.0
    asset_timeout_seconds: float = 15.0
    max_asset_size_bytes: int = 5 * 1024 * 1024
    max_assets_per_page: int = 50
    user_agent: str = "WebStalker/0.1"

    bind_host: str = "127.0.0.1"
    bind_port: int = 8000

    enable_scheduler: bool = True

    @property
    def db_path(self) -> Path:
        return self.data_dir / "webstalker.db"

    @property
    def blob_dir(self) -> Path:
        return self.data_dir / "blobs"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.blob_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
