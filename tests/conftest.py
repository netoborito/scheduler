from pathlib import Path

from dotenv import load_dotenv


def pytest_configure() -> None:
    root = Path(__file__).resolve().parent.parent
    load_dotenv(root / ".env.test", override=True)
