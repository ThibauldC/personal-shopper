from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_path: Path = Path("personal_shopper.db")

    delhaize_base_url: str = "https://www.delhaize.be"
    delhaize_recipes_path: str = "/nl/nl/food-inspiration/recipes"
    delhaize_vegetarian_tag: str = "vegetarisch"
    delhaize_recipes_per_run: int = 8

    slack_bot_token: str = ""
    slack_signing_secret: str = ""
    slack_channel: str = "#recepten"

    @property
    def delhaize_recipes_url(self) -> str:
        return f"{self.delhaize_base_url}{self.delhaize_recipes_path}"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    """Reset cached settings — used in tests."""
    global _settings
    _settings = None
