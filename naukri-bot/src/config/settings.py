"""Central settings loaded from .env. No secrets hardcoded."""
import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() == "true"


@dataclass(frozen=True)
class Settings:
    naukri_email: str = os.getenv("NAUKRI_EMAIL", "")
    naukri_password: str = os.getenv("NAUKRI_PASSWORD", "")
    openrouter_key: str = os.getenv("OPENROUTER_API_KEY", "")
    openrouter_model: str = os.getenv("OPENROUTER_MODEL", "openrouter/free")
    full_name: str = os.getenv("FULL_NAME", "Imran Sutar")
    phone: str = os.getenv("PHONE", "9370093936")
    city: str = os.getenv("CITY", "Pune")
    years_exp: str = os.getenv("YEARS_EXPERIENCE", "3.1")
    headless: bool = _bool("RUN_HEADLESS", False)
    resume_path: str = os.getenv(
        "RESUME_PATH",
        r"C:\Users\Hp\Desktop\naukari\Imran Sutar - Full Stack Developer.pdf",
    )
    github_url: str = os.getenv("GITHUB_URL", "https://github.com/Imran2909")
    linkedin_url: str = os.getenv(
        "LINKEDIN_URL", "https://www.linkedin.com/in/imran-sutar-0a858425b"
    )
    profile_dir: Path = BASE_DIR / os.getenv("CHROME_PROFILE_DIR", "data/bot-profile")
    data_dir: Path = BASE_DIR / "data"

    def validate(self) -> None:
        if not self.naukri_email or not self.naukri_password:
            raise RuntimeError("Set NAUKRI_EMAIL and NAUKRI_PASSWORD in .env")
        if not Path(self.resume_path).exists():
            raise RuntimeError(f"Resume not found: {self.resume_path}")
        self.data_dir.mkdir(parents=True, exist_ok=True)


SETTINGS = Settings()
