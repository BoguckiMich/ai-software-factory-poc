import os
import sys
import json
import asyncio
import re
from datetime import datetime
from pathlib import Path

import anthropic
from anthropic import Anthropic
from pyzeebe import ZeebeWorker, ZeebeTaskRouter, create_insecure_channel
from pyzeebe.errors import BusinessError

# --- Konfiguracja (nadpisywalna zmiennymi środowiskowymi) ---
MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
ZEEBE_ADDRESS = os.environ.get("ZEEBE_ADDRESS", "localhost:26500")
# Domyślnie <katalog projektu>/output, niezależnie od katalogu, z którego uruchomiono skrypt
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", Path(__file__).resolve().parent.parent / "output"))

# Kod błędu BPMN - można go złapać Error Boundary Event w modelu.
# Jeśli nie jest złapany, Zeebe od razu tworzy incydent (bez marnowania retry).
MISSING_VARIABLE_ERROR_CODE = "MISSING_VARIABLE"


class MissingVariableError(BusinessError):
    """Brak wymaganej zmiennej procesu - ponowienie zadania nic nie zmieni."""

    def __init__(self, task_type: str, variable_name: str) -> None:
        super().__init__(
            MISSING_VARIABLE_ERROR_CODE,
            f"[{task_type}] Brak wymaganej zmiennej procesu '{variable_name}' (pusta lub nieustawiona).",
        )


class ClaudeResponseError(RuntimeError):
    """Claude zwrócił odpowiedź, której nie da się użyć (pusta, ucięta, odmowa)."""


def require(task_type: str, **variables: str | None) -> None:
    """Sprawdza, czy wszystkie przekazane zmienne procesu są ustawione i niepuste."""
    for name, value in variables.items():
        if value is None or (isinstance(value, str) and not value.strip()):
            print(f"[{task_type}] BŁĄD: brak zmiennej '{name}'")
            raise MissingVariableError(task_type, name)


# 1. Inicjalizacja klienta Claude
claude_client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))


def ask_claude(task_type: str, system: str, user_content: str, max_tokens: int) -> str:
    """Wywołuje Claude i zwraca tekst odpowiedzi; błędy zamienia na czytelne wyjątki.

    Wyjątki przechodzą do pyzeebe, który oznacza job jako nieudany (retry wg ustawień BPMN).
    """
    try:
        response = claude_client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_content}],
        )
    except anthropic.AuthenticationError as e:
        print(f"[{task_type}] BŁĄD: nieprawidłowy lub brakujący ANTHROPIC_API_KEY")
        raise RuntimeError("Błąd uwierzytelnienia w Claude API - sprawdź ANTHROPIC_API_KEY") from e
    except anthropic.NotFoundError as e:
        print(f"[{task_type}] BŁĄD: model '{MODEL}' nie istnieje lub jest niedostępny")
        raise RuntimeError(f"Model '{MODEL}' niedostępny") from e
    except anthropic.RateLimitError as e:
        print(f"[{task_type}] Limit zapytań Claude API przekroczony - job zostanie ponowiony")
        raise RuntimeError("Przekroczony limit zapytań Claude API (429)") from e
    except anthropic.APIStatusError as e:
        print(f"[{task_type}] BŁĄD Claude API {e.status_code}: {e.message}")
        raise RuntimeError(f"Claude API zwróciło błąd {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        print(f"[{task_type}] BŁĄD: brak połączenia z Claude API")
        raise RuntimeError("Brak połączenia z Claude API") from e

    if response.stop_reason == "refusal":
        raise ClaudeResponseError(f"[{task_type}] Claude odmówił odpowiedzi")

    text = "".join(block.text for block in response.content if block.type == "text")
    if not text.strip():
        raise ClaudeResponseError(f"[{task_type}] Claude zwrócił pustą odpowiedź")

    if response.stop_reason == "max_tokens":
        print(f"[{task_type}] UWAGA: odpowiedź ucięta po {max_tokens} tokenach")

    return text


# 2. Tworzymy Router zamiast Workera na poziomie globalnym
router = ZeebeTaskRouter()

# --- BOT 1: Dev ---
# Domyślne wartości parametrów sprawiają, że brak zmiennej w procesie nie kończy się
# TypeError-em z pyzeebe, tylko czytelnym MissingVariableError z require().
@router.task(task_type="write-code", timeout_ms=120000)
def write_code_handler(user_task_description: str = "", review_feedback: str = "", generated_code: str = "", motivation_message: str = "") -> dict:
    require("write-code", user_task_description=user_task_description)
    print(f"\n[Write Code Bot] Otrzymałem zadanie: {user_task_description}")

    context = ""
    if review_feedback and generated_code:
        context = (
            f"\n\nPoprzednio wygenerowałeś taki kod:\n{generated_code}\n\n"
            f"Został on jednak ODRZUCONY przez recenzenta. Powód: {review_feedback}.\n"
        )
        if motivation_message:
            context += f"Motywacja od mentora: {motivation_message}\n"

        context += "Wygeneruj kod od nowa, aby spełniał wymagania recenzenta i zastosuj sie do wskazówek od mentora."
    elif review_feedback or generated_code:
        print("[Write Code Bot] UWAGA: jest tylko jedna z 'review_feedback'/'generated_code' - pomijam kontekst poprawki")

    generated = ask_claude(
        "write-code",
        system="Jesteś programistą. Pisz tylko kod, bez żadnego tekstu wyjaśniającego.",
        user_content=user_task_description + context,
        max_tokens=4000,
    )

    print(f"[Write Code Bot] Kod wygenerowany. Przekazuję do recenzji.")
    return {"generated_code": generated}


# --- BOT 2: Recenzent ---
@router.task(task_type="review-code", timeout_ms=120000)
def review_code_handler(generated_code: str = "") -> dict:
    require("review-code", generated_code=generated_code)
    print(f"[Review Code Bot] Analizuję wygenerowany kod...")

    system_prompt = (
        "Jesteś surowym inżynierem bezpieczeństwa. Oceń kod. "
        "Zwróć wynik WYŁĄCZNIE jako poprawny JSON z polami 'is_approved' (boolean) "
        "oraz 'review_feedback' (string z uwagami)."
    )

    raw_text = ask_claude(
        "review-code",
        system=system_prompt,
        user_content=f"Oceń ten kod:\n{generated_code}",
        max_tokens=4000,
    )
    print(f"[DEBUG] Surowa odpowiedź Claude: {raw_text}")

    try:
        match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        if not match:
            raise json.JSONDecodeError("Nie znaleziono klamer JSON", raw_text, 0)
        ai_result = json.loads(match.group(0))
        if not isinstance(ai_result, dict):
            raise ValueError("JSON nie jest obiektem")
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[Review Code Bot] Błąd parsowania JSON od AI: {e}")
        ai_result = {"is_approved": False, "review_feedback": "AI nie zwróciło poprawnego formatu JSON."}

    # Bramka BPMN porównuje `is_approved = true`, więc wymuszamy prawdziwy boolean
    # (np. string "false" byłby inaczej traktowany jako prawda w Pythonie).
    is_approved = ai_result.get("is_approved") is True
    review_feedback = str(ai_result.get("review_feedback") or "Brak uwag")
    print(f"[Review Code Bot] Werdykt: {'ZATWIERDZONY' if is_approved else 'ODRZUCONY'}")

    return {
        "is_approved": is_approved,
        "review_feedback": review_feedback,
    }


# --- BOT 3: Motywator ---
@router.task(task_type="motivate-dev", timeout_ms=120000)
def motivate_handler(review_feedback: str = "") -> dict:
    require("motivate-dev", review_feedback=review_feedback)
    print(f"[Motivation Bot] Kod został odrzucony. Powód: {review_feedback}")

    ai_motivation = ask_claude(
        "motivate-dev",
        system="Jesteś przyjaznym mentorem programowania. Zmotywuj krótko i daj wskazówkę do błędu.",
        user_content=f"Mój kod odrzucono: {review_feedback}",
        max_tokens=300,
    )

    print(f"[Motivation Bot] Wiadomość dla dev: {ai_motivation}")
    print("--- Zaczynamy pętlę od nowa ---")
    return {"motivation_message": ai_motivation}

# --- BOT 4: Archiwista (Zapis na dysk) ---
@router.task(task_type="save-to-disk")
def save_to_disk_handler(generated_code: str = "") -> dict:
    require("save-to-disk", generated_code=generated_code)
    print("\n[Save Bot] Otrzymałem zatwierdzony kod. Zapisuję na dysk...")

    # Generujemy unikalną nazwę pliku z datą i godziną
    filename = datetime.now().strftime("%Y%m%d_%H%M%S") + "_wynik.txt"
    filepath = OUTPUT_DIR / filename

    try:
        # Tworzymy folder 'output', jeśli jeszcze nie istnieje
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        filepath.write_text(generated_code, encoding="utf-8")
    except OSError as e:
        print(f"[Save Bot] BŁĄD zapisu do {filepath}: {e}")
        raise

    print(f"[Save Bot] Gotowe! Kod bezpiecznie zapisany w: {filepath}")

    return {"saved_file_path": str(filepath)}


def check_environment() -> None:
    """Zatrzymuje start workera, jeśli brakuje wymaganych zmiennych środowiskowych."""
    missing = [name for name in ("ANTHROPIC_API_KEY",) if not os.environ.get(name)]
    if missing:
        print(f"BŁĄD: brak zmiennych środowiskowych: {', '.join(missing)}")
        print("Ustaw je przed uruchomieniem, np. w PowerShell: $env:ANTHROPIC_API_KEY = \"sk-ant-...\"")
        sys.exit(1)


async def main():
    check_environment()
    channel = create_insecure_channel(grpc_address=ZEEBE_ADDRESS)
    worker = ZeebeWorker(channel)
    worker.include_router(router)

    print(f"AI Factory gotowe. Nasłuchuję na Camunda 8 (Zeebe) pod {ZEEBE_ADDRESS}...")
    await worker.work()

if __name__ == "__main__":
    asyncio.run(main())
