"""Profile refresh timestamp log."""
from src.config.settings import SETTINGS
from src.tools.history import now_ist


def log_refresh(text: str | None = None) -> None:
    SETTINGS.data_dir.mkdir(parents=True, exist_ok=True)
    p = SETTINGS.data_dir / "profile_refresh.log"
    with p.open("a", encoding="utf-8") as f:
        f.write(f"{text or 'updated at ' + now_ist()}\n")
