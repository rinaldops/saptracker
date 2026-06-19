"""Exportação da árvore de objetos e tabelas para JSON e CSV.

Funções puras (sem dependência de Qt/COM) para facilitar testes unitários.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


def to_json(data: Any, *, indent: int = 2) -> str:
    """Serializa ``data`` para uma string JSON legível (UTF-8, não-ASCII ok)."""
    return json.dumps(data, indent=indent, ensure_ascii=False, default=str)


def save_json(data: Any, path: str | Path, *, indent: int = 2) -> Path:
    """Grava ``data`` como JSON em ``path`` e retorna o caminho gravado."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(to_json(data, indent=indent), encoding="utf-8")
    return p


def rows_to_csv(
    rows: Sequence[Mapping[str, Any]],
    *,
    columns: Sequence[str] | None = None,
) -> str:
    """Converte uma sequência de dicionários em texto CSV.

    Args:
        rows: Linhas como dicionários ``coluna -> valor``.
        columns: Ordem explícita das colunas. Se omitido, é inferida a partir
            das chaves preservando a ordem de primeira aparição.

    Returns:
        Texto CSV com cabeçalho. Retorna apenas o cabeçalho se ``rows`` vazio
        e ``columns`` informado; string vazia se ambos vazios.
    """
    if columns is None:
        seen: dict[str, None] = {}
        for row in rows:
            for key in row:
                seen.setdefault(key, None)
        columns = list(seen)

    if not columns:
        return ""

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(columns), extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({c: row.get(c, "") for c in columns})
    return buffer.getvalue()


def save_csv(
    rows: Sequence[Mapping[str, Any]],
    path: str | Path,
    *,
    columns: Sequence[str] | None = None,
) -> Path:
    """Grava ``rows`` como CSV em ``path`` e retorna o caminho gravado."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(rows_to_csv(rows, columns=columns), encoding="utf-8", newline="")
    return p
