from pyzeebe.errors import BusinessError

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


def require(task_type: str, **variables: str | None) -> None:
    """Sprawdza, czy wszystkie przekazane zmienne procesu są ustawione i niepuste."""
    for name, value in variables.items():
        if value is None or (isinstance(value, str) and not value.strip()):
            print(f"[{task_type}] BŁĄD: brak zmiennej '{name}'")
            raise MissingVariableError(task_type, name)
