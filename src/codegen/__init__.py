"""Pacote de geração de código.

Expõe o modelo de ação (:class:`Acao`, :class:`SessionInfoLite`), a interface
base (:class:`CodeGenerator`) e um registro de geradores concretos por
linguagem. A UI consome :func:`available_generators` para popular o ComboBox e
:func:`get_generator` para instanciar o gerador escolhido.
"""

from __future__ import annotations

from src.codegen.autoit import AutoItGenerator
from src.codegen.base import Acao, CodeGenerator, SessionInfoLite
from src.codegen.java import JavaGenerator
from src.codegen.powershell import PowerShellGenerator
from src.codegen.python_gen import PythonGenerator
from src.codegen.vba import VBAGenerator
from src.codegen.vbscript import VBScriptGenerator

#: Geradores na ordem em que aparecem na UI. VBA primeiro: público prioritário.
_GENERATORS: tuple[type[CodeGenerator], ...] = (
    VBAGenerator,
    PythonGenerator,
    VBScriptGenerator,
    PowerShellGenerator,
    AutoItGenerator,
    JavaGenerator,
)

#: Mapa ``language -> classe`` para lookup rápido.
_REGISTRY: dict[str, type[CodeGenerator]] = {g.language: g for g in _GENERATORS}


def available_generators() -> list[tuple[str, str]]:
    """Retorna ``[(language, display_name), ...]`` na ordem de exibição."""
    return [(g.language, g.display_name) for g in _GENERATORS]


def get_generator(language: str) -> CodeGenerator:
    """Instancia o gerador da ``language`` indicada.

    Raises:
        KeyError: se a linguagem não estiver registrada.
    """
    try:
        return _REGISTRY[language]()
    except KeyError as exc:
        disponiveis = ", ".join(sorted(_REGISTRY))
        raise KeyError(
            f"Linguagem desconhecida: {language!r}. Disponíveis: {disponiveis}"
        ) from exc


def register_generator(generator_cls: type[CodeGenerator]) -> None:
    """Registra (ou substitui) um gerador pela sua ``language``."""
    _REGISTRY[generator_cls.language] = generator_cls


__all__ = [
    "Acao",
    "AutoItGenerator",
    "CodeGenerator",
    "JavaGenerator",
    "PowerShellGenerator",
    "PythonGenerator",
    "SessionInfoLite",
    "VBAGenerator",
    "VBScriptGenerator",
    "available_generators",
    "get_generator",
    "register_generator",
]
