# AI Software Factory - Camunda 8 & Claude Orchestration PoC

Ten projekt to Proof of Concept (PoC) demonstrujący zaawansowaną orkiestrację agentów AI przy użyciu silnika BPMN (Camunda 8) oraz API Anthropic (Claude 4.5). 

Celem projektu jest rozwiązanie kluczowych problemów przy wdrażaniu narzędzi AI w organizacjach: braku kontroli nad procesem, omijania wytycznych bezpieczeństwa oraz trudności w budowaniu pętli zwrotnych (feedback loops) dla LLM.

## 🚀 Główne funkcjonalności

Proces symuluje w pełni zautomatyzowaną linię produkcyjną oprogramowania z wykorzystaniem wyspecjalizowanych workerów (agentów):

1. **Code Writer Bot (`write-code`)**: Generuje kod na podstawie wymagań użytkownika. W przypadku wcześniejszego odrzucenia kodu, potrafi zaadaptować swój kontekst o historyczne błędy i wskazówki.
2. **Security & Review Bot (`review-code`)**: Narzuca firmowe wytyczne i procesy. Surowy weryfikator bezpieczeństwa, który sprawdza kod pod kątem podatności i wymusza zwrot ustrukturyzowanych danych (JSON).
3. **Motivation & Mentoring Bot (`motivate-dev`)**: Tłumaczy błędy wyłapane przez recenzenta na instrukcje techniczne i przekazuje je z powrotem do dewelopera, domykając pętlę samonaprawy (self-healing) systemu.
4. **Archiver Bot (`save-to-disk`)**: Zapisuje ostatecznie zatwierdzony i bezpieczny kod do lokalnego systemu plików.

## 🛠️️ Architektura i Technologie

* **Orkiestracja:** Camunda 8 (Zeebe), uruchamiana lokalnie via Docker Compose. Zapewnia observability całego procesu, wizualizację ścieżek decyzyjnych oraz niezawodność (ponawianie zadań po timeoutach).
* **Integracja:** Python 3 z wykorzystaniem biblioteki asynchronicznej `pyzeebe` (komunikacja gRPC z silnikiem).
* **Sztuczna Inteligencja:** Model `claude-haiku-4-5-20251001` (Anthropic API), wybrany ze względu na optymalizację kosztów (tokenów) przy zachowaniu wysokich zdolności analitycznych.

## ⚙️ Wymagania i Uruchomienie

### Wymagania wstępne
* Docker & Docker Compose
* Python 3.11+
* Klucz API Anthropic (Claude)
