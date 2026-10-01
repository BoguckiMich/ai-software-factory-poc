import os

import anthropic
from anthropic import Anthropic

from ai_factory.config import MODEL

claude_client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))


class ClaudeResponseError(RuntimeError):
    """Claude zwrócił odpowiedź, której nie da się użyć (pusta, ucięta, odmowa)."""


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
