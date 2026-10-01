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

### Instalacja

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt   # przypięte, przetestowane wersje
pip install -e .                  # instaluje pakiet ai_factory i komendę ai-factory
```

### Konfiguracja

Skopiuj `.env.example` do `.env` i uzupełnij `ANTHROPIC_API_KEY`. Worker wczytuje `.env` automatycznie; zmienne ustawione w powłoce mają pierwszeństwo.

| Zmienna | Wymagana | Domyślnie | Opis |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | tak | - | Klucz Anthropic API (lub klucz gateway przy pracy przez proxy) |
| `ANTHROPIC_BASE_URL` | nie | `https://api.anthropic.com` | Adres API; ustaw na adres AI Gateway, aby łączyć się przez proxy |
| `CLAUDE_MODEL` | nie | `claude-haiku-4-5-20251001` | Model używany przez wszystkie boty |
| `ZEEBE_ADDRESS` | nie | `localhost:26500` | Adres gateway Zeebe (gRPC) |
| `OUTPUT_DIR` | nie | `output` | Katalog na zatwierdzony kod (względem katalogu uruchomienia) |

#### Połączenie przez AI Gateway (proxy)

Aby ruch do Anthropic szedł przez lokalne proxy (autoryzacja, skan promptów, limity tokenów, audit log), ustaw w `.env`:

```env
ANTHROPIC_BASE_URL=http://127.0.0.1:8088
ANTHROPIC_API_KEY=<klucz gateway z GATEWAY_KEYS proxy>
```

Zmiany w kodzie nie są potrzebne - SDK Anthropic samo odczytuje `ANTHROPIC_BASE_URL`. Prawdziwy klucz Anthropic zna wtedy tylko proxy. Uwaga: w trybie `enforce` proxy może zablokować zapytanie (np. gdy kod zawiera coś przypominającego klucz API) lub zwrócić 429 po przekroczeniu dziennego limitu tokenów - job w Camundzie zostanie wtedy oznaczony jako nieudany.

### Uruchomienie

1. Uruchom lokalnie Camundę 8 (gateway Zeebe dostępny pod `ZEEBE_ADDRESS`).
2. Wdróż `bpmn/ai_factory.bpmn` oraz formularz `bpmn/ai_start_form.form` (np. z Camunda Modeler).
3. Z katalogu głównego projektu uruchom worker:

```powershell
ai-factory
# lub równoważnie
python -m ai_factory
```

4. Uruchom instancję procesu, podając `user_task_description` w formularzu startowym.

## 🧯 Obsługa błędów

* **Brak zmiennej procesu** (np. `generated_code`): worker rzuca błąd BPMN o kodzie `MISSING_VARIABLE`. Można go złapać Error Boundary Event; jeśli nie jest złapany, Zeebe od razu tworzy incydent z nazwą brakującej zmiennej (bez ponawiania).
* **Błędy Claude API** (limit zapytań, błąd serwera, brak sieci, zły klucz lub model): job jest oznaczany jako nieudany z czytelnym komunikatem i ponawiany zgodnie z liczbą retry w modelu BPMN.
* **Brak `ANTHROPIC_API_KEY`**: worker nie startuje i wypisuje, co ustawić.

## 📁 Struktura projektu

```
├── bpmn/                   # model procesu i formularz startowy
├── src/ai_factory/
│   ├── worker.py           # punkt wejścia: połączenie z Zeebe i start workera
│   ├── handlers.py         # handlery zadań: write-code, review-code, motivate-dev, save-to-disk
│   ├── claude.py           # klient Claude i obsługa błędów API
│   ├── validation.py       # walidacja zmiennych procesu (MISSING_VARIABLE)
│   └── config.py           # konfiguracja ze zmiennych środowiskowych / .env
├── .env.example
├── pyproject.toml
└── requirements.txt
```
