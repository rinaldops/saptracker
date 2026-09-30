"""Testes da CLI headless (``src/cli.py``).

Usa *fakes* COM (sem pywin32/SAP): ``SapConnection`` é substituído por um
duble cujo ``get_session`` retorna diretamente a sessão falsa desejada.
"""

from __future__ import annotations

import io
import json
from typing import Any

import pytest

from src import cli
from src.core.sap_connection import SapConnectionError
from tests.conftest import FakeSession

Capsys = pytest.CaptureFixture[str]


class _FakeConnection:
    """Substitui ``SapConnection``: ``get_session`` devolve uma sessão fixa."""

    def __init__(self, session: Any) -> None:
        self._session = session

    def get_session(self, connection_index: int = 0, session_index: int = 0) -> Any:
        return self._session


class _FakeSessionComFind(FakeSession):
    """``FakeSession`` que resolve ``FindById`` para um único objeto-alvo."""

    def __init__(self, alvo: Any) -> None:
        super().__init__()
        self._alvo = alvo

    def FindById(self, obj_id: str, *_args: Any) -> Any:
        return self._alvo if obj_id == self._alvo.Id else None


class _FakeTarget:
    """Objeto COM alvo mínimo para ``inspect``/``highlight``."""

    Type = "GuiTextField"
    Id = "wnd[0]/usr/txtFIELD"
    Name = "FIELD"
    Text = "valor"

    def Visualize(self, on: bool) -> bool:  # noqa: ANN001 - assinatura COM
        return True


class _FakeSelectedNodes:
    """``GetSelectedNodes()`` falso: coleção COM com uma única chave."""

    def __init__(self, keys: list[str]) -> None:
        self._keys = keys
        self.Count = len(keys)

    def ElementAt(self, i: int) -> str:
        return self._keys[i]


class _FakeTreeTarget:
    """``GuiTree`` falso para ``select-node``."""

    Type = "GuiTree"
    Id = "wnd[0]/usr/cntlTREE1/shellcont/shell"

    def __init__(self) -> None:
        self._selected: list[str] = []

    def SelectNode(self, key: str) -> None:
        self._selected = [key]

    def GetSelectedNodes(self) -> _FakeSelectedNodes:
        return _FakeSelectedNodes(self._selected)


class _FakeGridTarget:
    """``GuiGridView`` falso para ``select-row``."""

    Type = "GuiGridView"
    Id = "wnd[0]/usr/cntlGRID1/shellcont/shell"

    def __init__(self) -> None:
        self.CurrentCellRow = -1
        self.SelectedRows = ""

    def SetCurrentCell(self, row: int, _column: str) -> None:
        self.CurrentCellRow = row


def _patch_connection(monkeypatch: pytest.MonkeyPatch, session: Any) -> None:
    monkeypatch.setattr(cli, "SapConnection", lambda: _FakeConnection(session))


def test_snapshot_imprime_arvore_em_json(monkeypatch: pytest.MonkeyPatch, capsys: Capsys) -> None:
    _patch_connection(monkeypatch, FakeSession())
    assert cli.main(["snapshot"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["type"] == "GuiSession"
    assert data["children"] == []


def test_snapshot_grava_arquivo_com_out(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    _patch_connection(monkeypatch, FakeSession())
    saida = tmp_path / "snap.json"
    assert cli.main(["snapshot", "--out", str(saida)]) == 0
    assert json.loads(saida.read_text(encoding="utf-8"))["type"] == "GuiSession"


def test_inspect_imprime_detalhes(monkeypatch: pytest.MonkeyPatch, capsys: Capsys) -> None:
    alvo = _FakeTarget()
    _patch_connection(monkeypatch, _FakeSessionComFind(alvo))
    assert cli.main(["inspect", alvo.Id]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["id"] == alvo.Id
    assert data["text"] == "valor"


def test_highlight_reporta_sucesso(monkeypatch: pytest.MonkeyPatch, capsys: Capsys) -> None:
    alvo = _FakeTarget()
    _patch_connection(monkeypatch, _FakeSessionComFind(alvo))
    assert cli.main(["highlight", alvo.Id]) == 0
    assert json.loads(capsys.readouterr().out) == {"id": alvo.Id, "on": True, "ok": True}


def test_highlight_off_desliga_destaque(monkeypatch: pytest.MonkeyPatch, capsys: Capsys) -> None:
    alvo = _FakeTarget()
    _patch_connection(monkeypatch, _FakeSessionComFind(alvo))
    assert cli.main(["highlight", alvo.Id, "--off"]) == 0
    assert json.loads(capsys.readouterr().out)["on"] is False


def test_select_node_reporta_sucesso(monkeypatch: pytest.MonkeyPatch, capsys: Capsys) -> None:
    alvo = _FakeTreeTarget()
    _patch_connection(monkeypatch, _FakeSessionComFind(alvo))
    assert cli.main(["select-node", alvo.Id, "000013"]) == 0
    assert json.loads(capsys.readouterr().out) == {"id": alvo.Id, "key": "000013", "ok": True}


def test_select_node_objeto_inexistente_retorna_codigo_1(
    monkeypatch: pytest.MonkeyPatch, capsys: Capsys
) -> None:
    _patch_connection(monkeypatch, _FakeSessionComFind(_FakeTreeTarget()))
    assert cli.main(["select-node", "wnd[0]/nao-existe", "000013"]) == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_select_row_reporta_sucesso(monkeypatch: pytest.MonkeyPatch, capsys: Capsys) -> None:
    alvo = _FakeGridTarget()
    _patch_connection(monkeypatch, _FakeSessionComFind(alvo))
    assert cli.main(["select-row", alvo.Id, "2"]) == 0
    assert json.loads(capsys.readouterr().out) == {"id": alvo.Id, "row": 2, "ok": True}
    assert alvo.SelectedRows == "2"


def test_select_row_objeto_inexistente_retorna_codigo_1(
    monkeypatch: pytest.MonkeyPatch, capsys: Capsys
) -> None:
    _patch_connection(monkeypatch, _FakeSessionComFind(_FakeGridTarget()))
    assert cli.main(["select-row", "wnd[0]/nao-existe", "2"]) == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_ensure_utf8_stdio_forca_utf8_mesmo_com_console_cp1252(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Reproduz o bug real: console Windows em cp1252 corrompe texto acentuado
    # ("ó" -> byte inválido) quando o stdout não é forçado para UTF-8.
    buf = io.BytesIO()
    stdout_cp1252 = io.TextIOWrapper(buf, encoding="cp1252", newline="")
    monkeypatch.setattr(cli.sys, "stdout", stdout_cp1252)

    cli._ensure_utf8_stdio()
    cli.sys.stdout.write("ó")
    cli.sys.stdout.flush()

    assert buf.getvalue() == "ó".encode()


def test_erro_de_conexao_retorna_codigo_2(monkeypatch: pytest.MonkeyPatch, capsys: Capsys) -> None:
    class _ConexaoFalha:
        def get_session(self, *_a: Any, **_k: Any) -> Any:
            raise SapConnectionError("sem SAP")

    monkeypatch.setattr(cli, "SapConnection", _ConexaoFalha)
    assert cli.main(["snapshot"]) == 2
    assert "sem SAP" in capsys.readouterr().err
