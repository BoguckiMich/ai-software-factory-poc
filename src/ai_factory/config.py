import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Wczytuje zmienne z pliku .env (jeśli istnieje); zmienne ustawione w systemie mają pierwszeństwo
load_dotenv()

# --- Konfiguracja (nadpisywalna zmiennymi środowiskowymi) ---
MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
ZEEBE_ADDRESS = os.environ.get("ZEEBE_ADDRESS", "localhost:26500")
# Względem katalogu, z którego uruchomiono worker (zwykle katalog główny projektu)
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "output")).resolve()

REQUIRED_ENV_VARS = ("ANTHROPIC_API_KEY",)


def check_environment() -> None:
    """Zatrzymuje start workera, jeśli brakuje wymaganych zmiennych środowiskowych."""
    missing = [name for name in REQUIRED_ENV_VARS if not os.environ.get(name)]
    if missing:
        print(f"BŁĄD: brak zmiennych środowiskowych: {', '.join(missing)}")
        print("Skopiuj .env.example do .env i uzupełnij wartości, albo ustaw je w powłoce,")
        print("np. w PowerShell: $env:ANTHROPIC_API_KEY = \"sk-ant-...\"")
        sys.exit(1)
