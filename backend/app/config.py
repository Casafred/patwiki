import sys
import os
from pathlib import Path
from pydantic_settings import BaseSettings


def _get_app_data_dir() -> Path:
    """获取应用数据目录。
    - 开发模式：项目根目录 / data
    - 打包模式（PyInstaller frozen）：用户数据目录 / PatWiki
      * Windows: %LOCALAPPDATA%/PatWiki
      * macOS:   ~/Library/Application Support/PatWiki
      * Linux:   ~/.local/share/PatWiki
    """
    if getattr(sys, "frozen", False):
        # PyInstaller 打包后
        if sys.platform == "win32":
            base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        elif sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support"
        else:
            base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        return base / "PatWiki"
    # 开发模式：项目根目录
    return Path(__file__).parent.parent.parent.resolve() / "data"


PROJECT_ROOT = _get_app_data_dir()


class Settings(BaseSettings):
    APP_NAME: str = "PatWiki"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True

    DATA_DIR: Path = PROJECT_ROOT
    DATABASE_PATH: Path = DATA_DIR / "patwiki.db"
    VECTORS_DIR: Path = DATA_DIR / "vectors"
    FILES_DIR: Path = DATA_DIR / "files"
    BACKUPS_DIR: Path = DATA_DIR / "backups"
    CACHE_DIR: Path = DATA_DIR / "cache"
    LOGS_DIR: Path = DATA_DIR / "logs"

    DATABASE_URL: str = ""

    API_PREFIX: str = "/api"
    HOST: str = "127.0.0.1"
    PORT: int = 8765

    LLM_PROVIDER: str = ""
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_BASE_URL: str = ""

    EMBEDDING_MODEL: str = "text-embedding-3-small"

    UPLOAD_MAX_SIZE: int = 100 * 1024 * 1024

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # SQLite URL 在 Windows 需要用正斜杠或四斜杠
        self.DATABASE_URL = f"sqlite:///{self.DATABASE_PATH.as_posix()}"
        self._ensure_dirs()

    def _ensure_dirs(self):
        for dir_path in [
            self.DATA_DIR,
            self.VECTORS_DIR,
            self.FILES_DIR,
            self.BACKUPS_DIR,
            self.CACHE_DIR,
            self.LOGS_DIR,
        ]:
            dir_path.mkdir(parents=True, exist_ok=True)


settings = Settings()
