import os
import json
import asyncio
import re
from datetime import datetime
from pyzeebe import ZeebeWorker, ZeebeTaskRouter, create_insecure_channel
from anthropic import Anthropic

# 1. Inicjalizacja klienta Claude 
claude_client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

# 2. Tworzymy Router zamiast Workera na poziomie globalnym
router = ZeebeTaskRouter()

# --- BOT 1: Dev ---
@router.task(task_type="write-code", timeout_ms=120000)
def write_code_handler(user_task_description: str, review_feedback: str = "", generated_code: str = "", motivation_message: str = "") -> dict:
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

    response = claude_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4000,
        system="Jesteś programistą. Pisz tylko kod, bez żadnego tekstu wyjaśniającego.",
        messages=[{"role": "user", "content": user_task_description + context}]
    )
    
    generated = response.content[0].text
    print(f"[Write Code Bot] Kod wygenerowany. Przekazuję do recenzji.")
    return {"generated_code": generated}


# --- BOT 2: Recenzent ---
@router.task(task_type="review-code", timeout_ms=120000)
def review_code_handler(generated_code: str) -> dict:
    print(f"[Review Code Bot] Analizuję wygenerowany kod...")
    
    system_prompt = (
        "Jesteś surowym inżynierem bezpieczeństwa. Oceń kod. "
        "Zwróć wynik WYŁĄCZNIE jako poprawny JSON z polami 'is_approved' (boolean) "
        "oraz 'review_feedback' (string z uwagami)."
    )
    
    response = claude_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4000,
        system=system_prompt,
        messages=[{"role": "user", "content": f"Oceń ten kod:\n{generated_code}"}]
    )

    raw_text = response.content[0].text
    print(f"[DEBUG] Surowa odpowiedź Claude: {raw_text}")
    
    try:
        match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        if match:
            clean_json = match.group(0)
            ai_result = json.loads(clean_json)
            print(f"[Review Code Bot] Werdykt: {'ZATWIERDZONY' if ai_result.get('is_approved') else 'ODRZUCONY'}")
        else:
            raise json.JSONDecodeError("Nie znaleziono klamer JSON", raw_text, 0)
            
    except json.JSONDecodeError:
        print("[Review Code Bot] Błąd parsowania JSON od AI!")
        ai_result = {"is_approved": False, "review_feedback": "AI nie zwróciło poprawnego formatu JSON."}
        
    return {
        "is_approved": ai_result.get("is_approved", False),
        "review_feedback": ai_result.get("review_feedback", "Brak uwag")
    }


# --- BOT 3: Motywator ---
@router.task(task_type="motivate-dev")
def motivate_handler(review_feedback: str) -> dict:
    print(f"[Motivation Bot] Kod został odrzucony. Powód: {review_feedback}")
    
    response = claude_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        system="Jesteś przyjaznym mentorem programowania. Zmotywuj krótko i daj wskazówkę do błędu.",
        messages=[{"role": "user", "content": f"Mój kod odrzucono: {review_feedback}"}]
    )

    ai_motivation = response.content[0].text
    print(f"[Motivation Bot] Wiadomość dla dev: {response.content[0].text}")
    print("--- Zaczynamy pętlę od nowa ---")
    return {"motivation_message": ai_motivation}

# --- BOT 4: Archiwista (Zapis na dysk) ---
@router.task(task_type="save-to-disk")
def save_to_disk_handler(generated_code: str) -> dict:
    print("\n[Save Bot] Otrzymałem zatwierdzony kod. Zapisuję na dysk...")
    
    # Tworzymy folder 'output', jeśli jeszcze nie istnieje
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    
    # Generujemy unikalną nazwę pliku z datą i godziną
    filename = datetime.now().strftime("%Y%m%d_%H%M%S") + "_wynik.txt"
    filepath = os.path.join(output_dir, filename)
    
    # Zapisujemy wygenerowany kod do pliku
    with open(filepath, "w", encoding="utf-8") as file:
        file.write(generated_code)
        
    print(f"[Save Bot] Gotowe! Kod bezpiecznie zapisany w: {filepath}")
    
    return {"saved_file_path": filepath}

async def main():
    channel = create_insecure_channel(grpc_address="localhost:26500")
    worker = ZeebeWorker(channel)
    worker.include_router(router)
    
    print("AI Factory gotowe. Nasłuchuję na Camunda 8 (Zeebe)...")
    await worker.work()

if __name__ == "__main__":
    asyncio.run(main())