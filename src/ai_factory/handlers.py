import json
import re
from datetime import datetime

from pyzeebe import ZeebeTaskRouter

from ai_factory.claude import ask_claude
from ai_factory.config import OUTPUT_DIR
from ai_factory.validation import require

# Router z handlerami - worker podpina go w ai_factory.worker
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
