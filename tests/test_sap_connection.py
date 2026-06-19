"""Testes da reconexão automática de :class:`SapConnection` (NFR seção 9).

Não dependem de pywin32/SAP: ``_acquire_application`` é substituído e o relógio
e o ``sleep`` são injetados para que a janela de 30s seja simulada sem esperas.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from src.core.sap_connection import SapConnection, SapConnectionError, SessionInfo
from tests.conftest import FakeComponent, FakeInfo, FakeSession


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


# --------------------------------------------------------------------------- #
# Navegação (connect / iter_sessions / get_session / list_sessions_info)
# --------------------------------------------------------------------------- #
class _FakeColl:
    """``GuiComponentCollection`` falsa."""

    def __init__(self, items: list[Any]) -> None:
        self._items = list(items)
        self.Count = len(self._items)

    def ElementAt(self, i: int) -> Any:
        return self._items[i]


def _app_com_sessoes(*sessoes: Any) -> Any:
    conn = FakeComponent(Children=_FakeColl(list(sessoes)))
    return FakeComponent(Children=_FakeColl([conn]))


def _conectado(app: Any) -> SapConnection:
    conn = SapConnection()
    conn._application = app
    return conn


def test_is_connected_e_disconnect() -> None:
    conn = SapConnection()
    assert conn.is_connected is False  # sem application
    conn._application = _app_com_sessoes(FakeSession())
    assert conn.is_connected is True
    conn.disconnect()
    assert conn.is_connected is False


def test_connect_levanta_quando_indisponivel() -> None:
    conn = SapConnection()
    conn._acquire_application = lambda: None  # type: ignore[assignment]
    with pytest.raises(SapConnectionError, match="Scripting"):
        conn.connect()


def test_connect_usa_acquire_e_cacheia() -> None:
    app = _app_com_sessoes(FakeSession())
    conn = SapConnection()
    conn._acquire_application = lambda: app  # type: ignore[assignment]
    assert conn.connect() is app
    assert conn.application is app  # já em cache, não readquire


def test_iter_sessions_e_active_session() -> None:
    s1, s2 = FakeSession(), FakeSession()
    conn = _conectado(_app_com_sessoes(s1, s2))
    assert conn.iter_sessions() == [s1, s2]
    assert conn.active_session() is s1


def test_active_session_none_quando_vazio() -> None:
    conn = _conectado(_app_com_sessoes())
    assert conn.active_session() is None


def test_get_session_por_indices() -> None:
    sess = FakeSession()
    conn = _conectado(_app_com_sessoes(sess))
    assert conn.get_session(0, 0) is sess


def test_get_session_conexao_inexistente() -> None:
    app = FakeComponent(Children=_FakeColl([None]))
    conn = _conectado(app)
    with pytest.raises(SapConnectionError, match="Conexão"):
        conn.get_session(0, 0)


def test_get_session_sessao_inexistente() -> None:
    conn_obj = FakeComponent(Children=_FakeColl([None]))
    app = FakeComponent(Children=_FakeColl([conn_obj]))
    conn = _conectado(app)
    with pytest.raises(SapConnectionError, match="Sessão"):
        conn.get_session(0, 0)


def test_list_sessions_info_extrai_metadados() -> None:
    sess = FakeSession(FakeInfo(system="NSP", client="800", user="USER01", transaction="SE16"))
    conn = _conectado(_app_com_sessoes(sess))
    infos = conn.list_sessions_info()
    assert len(infos) == 1
    info = infos[0]
    assert (info.system, info.client, info.user) == ("NSP", "800", "USER01")
    assert info.connection_index == 0 and info.session_index == 0


def test_session_info_label() -> None:
    info = SessionInfo(0, 0, "NSP", "800", "USER01", "SE16", "Título")
    assert info.label == "NSP/800 - USER01"
    incompleto = SessionInfo(0, 0, "", "", "", "", "")
    assert incompleto.label == "?/? - ?"
