"""Fixtures e *fakes* compartilhados pelos testes.

Os testes não dependem de um SAP GUI real nem de pywin32: objetos COM são
substituídos por *fakes* simples que expõem apenas as propriedades lidas pelo
código sob teste (``safe_get`` usa ``getattr``, então atributos comuns bastam).
"""

from __future__ import annotations

from typing import Any


class FakeComponent:
    """Componente COM falso: expõe atributos arbitrários via construtor."""

    def __init__(self, **attrs: Any) -> None:
        self.__dict__.update(attrs)


class FakeInfo:
    """``GuiSession.Info`` falso."""

    def __init__(
        self,
        system: str = "PRD",
        client: str = "100",
        user: str = "TESTER",
        transaction: str = "SE16",
    ) -> None:
        self.SystemName = system
        self.Client = client
        self.User = user
        self.Transaction = transaction


class FakeSession:
    """``GuiSession`` falso com ``Info`` (suficiente para session_info)."""

    def __init__(self, info: FakeInfo | None = None) -> None:
        self.Info = info or FakeInfo()
        self.Children = None
        self.Id = "/app/con[0]/ses[0]"
        self.Type = "GuiSession"
        self.Name = "session"
