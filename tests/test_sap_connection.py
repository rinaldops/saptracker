"""Testes da reconexão automática de :class:`SapConnection` (NFR seção 9).

Não dependem de pywin32/SAP: ``_acquire_application`` é substituído e o relógio
e o ``sleep`` são injetados para que a janela de 30s seja simulada sem esperas.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.core.sap_connection import SapConnection, SapConnectionError


class _FakeClock:
    """Relógio monotônico controlável; avança apenas quando ``sleep`` é chamado."""

    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def sleep(self, segundos: float) -> None:
        self.t += segundos


def _app_vivo() -> MagicMock:
    app = MagicMock()
    app.Children = MagicMock()  # is_connected checa safe_get(app, "Children")
    return app


def test_ensure_connected_retorna_cache_quando_ja_conectado() -> None:
    conn = SapConnection()
    app = _app_vivo()
    conn._application = app
    # Não deve nem tentar readquirir.
    conn._acquire_application = lambda: pytest.fail("não deveria readquirir")  # type: ignore[assignment]
    assert conn.ensure_connected() is app


def test_ensure_connected_reconecta_em_tentativa_posterior() -> None:
    conn = SapConnection()
    app = _app_vivo()
    tentativas: list[int] = []

    def fake_acquire() -> MagicMock | None:
        tentativas.append(1)
        return app if len(tentativas) >= 3 else None

    conn._acquire_application = fake_acquire  # type: ignore[assignment]
    relogio = _FakeClock()
    resultado = conn.ensure_connected(
        timeout=10, interval=1, _sleep=relogio.sleep, _clock=relogio
    )
    assert resultado is app
    assert len(tentativas) == 3  # falhou duas vezes, conectou na terceira


def test_ensure_connected_desiste_apos_timeout() -> None:
    conn = SapConnection()
    conn._acquire_application = lambda: None  # type: ignore[assignment]
    relogio = _FakeClock()
    with pytest.raises(SapConnectionError, match="30s|3s|reconectar"):
        conn.ensure_connected(
            timeout=3, interval=1, _sleep=relogio.sleep, _clock=relogio
        )
    assert relogio.t >= 3  # esgotou a janela antes de desistir
