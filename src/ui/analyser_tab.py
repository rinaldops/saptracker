"""Aba do Analisador — árvore de objetos, detalhes, busca, destaque e exportação."""

from __future__ import annotations

import json
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.core.analyser import Analyser, ObjectNode
from src.ui.context import AppContext
from src.utils import export
from src.utils.clipboard import copy_text
from src.utils.logger import get_logger

logger = get_logger(__name__)

#: Papel onde guardamos o ID do objeto em cada item da árvore.
_ID_ROLE = int(Qt.ItemDataRole.UserRole)
_SEARCH_ROLE = _ID_ROLE + 1


class AnalyserTab(QWidget):
    """Percorre e inspeciona a árvore de objetos da sessão selecionada."""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._analyser: Analyser | None = None
        self._root: ObjectNode | None = None
        #: ID do único objeto atualmente destacado no SAP (evita acúmulo).
        self._highlighted_id: str = ""
        #: Estado da busca incremental (estilo Scripting Tracker).
        self._search_matches: list[QTreeWidgetItem] = []
        self._search_idx: int = -1
        self._last_query: str = ""
        self._build_ui()
        ctx.sessionChanged.connect(self._on_session_changed)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        barra = QHBoxLayout()
        self.btn_analyse = QPushButton("Analisar sessão")
        self.btn_analyse.clicked.connect(self.analyse)
        self.btn_highlight = QPushButton("Segure para destacar no SAP")
        self.btn_highlight.pressed.connect(self.highlight_selected)
        self.btn_highlight.released.connect(self.clear_highlight)
        self.btn_clear_highlight = QPushButton("Limpar destaque")
        self.btn_clear_highlight.clicked.connect(self.clear_highlight)
        self.btn_copy_id = QPushButton("Copiar ID")
        self.btn_copy_id.clicked.connect(self.copy_selected_id)
        self.btn_json = QPushButton("Exportar JSON")
        self.btn_json.clicked.connect(self.export_json)
        self.btn_csv = QPushButton("Exportar CSV")
        self.btn_csv.clicked.connect(self.export_csv)
        for b in (
            self.btn_analyse,
            self.btn_highlight,
            self.btn_clear_highlight,
            self.btn_copy_id,
            self.btn_json,
            self.btn_csv,
        ):
            barra.addWidget(b)
        barra.addStretch(1)
        layout.addLayout(barra)

        processamento = QHBoxLayout()
        self.analysis_status = QLabel("Analisando a sessão…")
        self.analysis_status.setObjectName("processing")
        self.analysis_status.setVisible(False)
        processamento.addWidget(self.analysis_status)
        self.analysis_progress = QProgressBar()
        self.analysis_progress.setRange(0, 0)
        self.analysis_progress.setTextVisible(False)
        self.analysis_progress.setVisible(False)
        processamento.addWidget(self.analysis_progress, 1)
        layout.addLayout(processamento)

        # Barra de busca: encontra objetos por qualquer texto associado e cicla
        # pelos resultados, expandindo a hierarquia para revelar cada um.
        busca = QHBoxLayout()
        busca.addWidget(QLabel("Buscar:"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Nome, texto, tipo ou ID do objeto…")
        self.search.setClearButtonEnabled(True)
        self.search.returnPressed.connect(self.find_next)
        self.search.textChanged.connect(self._on_query_changed)
        busca.addWidget(self.search, 1)
        self.btn_find = QPushButton("Próximo")
        self.btn_find.clicked.connect(self.find_next)
        busca.addWidget(self.btn_find)
        layout.addLayout(busca)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Objeto", "Tipo"])
        self.tree.itemSelectionChanged.connect(self._show_details)
        splitter.addWidget(self.tree)

        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        splitter.addWidget(self.details)
        splitter.setSizes([520, 360])
        layout.addWidget(splitter, 1)

        self._update_enabled()

    # ------------------------------------------------------------------ #
    def _on_session_changed(self, session: Any) -> None:
        self.clear_highlight()
        self._analyser = Analyser(session) if session is not None else None
        self._root = None
        self._highlighted_id = ""
        self.tree.clear()
        self.details.clear()
        self._reset_search()
        self._update_enabled()

    def _update_enabled(self) -> None:
        ok = self._ctx.has_session
        self.btn_analyse.setEnabled(ok)
        tem_arvore = ok and self._root is not None
        for b in (
            self.btn_highlight,
            self.btn_clear_highlight,
            self.btn_copy_id,
            self.btn_json,
            self.btn_csv,
            self.btn_find,
        ):
            b.setEnabled(tem_arvore)
        self.search.setEnabled(tem_arvore)

    # ------------------------------------------------------------------ #
    def analyse(self) -> None:
        """Constrói a árvore de objetos da sessão e a exibe.

        Mostra cursor de espera e mensagem de status enquanto percorre a árvore
        (a travessia faz muitas chamadas COM e pode levar alguns segundos).
        """
        if self._analyser is None:
            return
        self.clear_highlight()
        self._ctx.statusMessage.emit("Analisando sessão… aguarde.")
        self.btn_analyse.setEnabled(False)
        self.btn_analyse.setText("Analisando…")
        self.analysis_status.setVisible(True)
        self.analysis_progress.setVisible(True)
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        QApplication.processEvents()  # pinta a mensagem/cursor antes de bloquear
        try:
            self._root = self._analyser.build_tree()
            self.tree.clear()
            root_item = self._make_item(self._root)
            self.tree.addTopLevelItem(root_item)
            root_item.setExpanded(True)
        except Exception as exc:  # noqa: BLE001 - fronteira COM/UI
            self._root = None
            self.tree.clear()
            self.details.clear()
            self._reset_search()
            self._update_enabled()
            logger.exception("Falha ao analisar a sessão SAP: %s", exc)
            self._ctx.statusMessage.emit(f"Falha ao analisar a sessão: {exc}")
            return
        finally:
            QApplication.restoreOverrideCursor()
            self.analysis_status.setVisible(False)
            self.analysis_progress.setVisible(False)
            self.btn_analyse.setText("Analisar sessão")
            self.btn_analyse.setEnabled(True)

        self._reset_search()
        self._highlighted_id = ""
        self._update_enabled()
        total = len(self._root.flatten())
        self._ctx.statusMessage.emit(f"Árvore construída: {total} objetos.")

    def _make_item(self, node: ObjectNode) -> QTreeWidgetItem:
        label = node.text or node.name or node.type
        item = QTreeWidgetItem([f"{label}", node.type])
        item.setData(0, _ID_ROLE, node.id)
        item.setData(
            0,
            _SEARCH_ROLE,
            " ".join((node.id, node.type, node.name, node.text)).casefold(),
        )
        for child in node.children:
            item.addChild(self._make_item(child))
        return item

    def _selected_id(self) -> str:
        items = self.tree.selectedItems()
        if not items:
            return ""
        return str(items[0].data(0, _ID_ROLE) or "")

    def _show_details(self) -> None:
        if self._analyser is None:
            return
        obj_id = self._selected_id()
        if not obj_id:
            return
        detalhes = self._analyser.inspect(obj_id)
        self.details.setPlainText(json.dumps(detalhes, indent=2, ensure_ascii=False, default=str))

    # ------------------------------------------------------------------ #
    # Busca incremental
    # ------------------------------------------------------------------ #
    def _on_query_changed(self, _texto: str) -> None:
        # Força recomputar os resultados na próxima busca.
        self._last_query = ""

    def _reset_search(self) -> None:
        self._search_matches = []
        self._search_idx = -1
        self._last_query = ""

    def find_next(self) -> None:
        """Vai ao próximo objeto cujo texto/tipo/ID contém o termo buscado.

        Recalcula os resultados quando o termo muda; do contrário, avança
        ciclicamente, revelando (expandindo) cada objeto na hierarquia.
        """
        query = self.search.text().strip().casefold()
        if not query:
            return
        if query != self._last_query:
            self._search_matches = self._collect_matches(query)
            self._search_idx = -1
            self._last_query = query
        if not self._search_matches:
            self._ctx.statusMessage.emit(f"Nenhum objeto contém “{query}”.")
            return
        self._search_idx = (self._search_idx + 1) % len(self._search_matches)
        self._reveal(self._search_matches[self._search_idx])
        self._ctx.statusMessage.emit(
            f"Busca “{query}”: {self._search_idx + 1} de {len(self._search_matches)}."
        )

    def _collect_matches(self, query: str) -> list[QTreeWidgetItem]:
        encontrados: list[QTreeWidgetItem] = []

        def rec(item: QTreeWidgetItem) -> None:
            alvo = str(item.data(0, _SEARCH_ROLE) or "")
            if query in alvo:
                encontrados.append(item)
            for i in range(item.childCount()):
                filho = item.child(i)
                if filho is not None:
                    rec(filho)

        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            if top is not None:
                rec(top)
        return encontrados

    def _reveal(self, item: QTreeWidgetItem) -> None:
        pai = item.parent()
        while pai is not None:
            pai.setExpanded(True)
            pai = pai.parent()
        self.tree.setCurrentItem(item)
        self.tree.scrollToItem(item)

    # ------------------------------------------------------------------ #
    # Destaque (highlight) — apenas um objeto ativo por vez
    # ------------------------------------------------------------------ #
    def highlight_selected(self) -> None:
        """Destaca o objeto selecionado enquanto o botão estiver pressionado."""
        if self._analyser is None:
            return
        obj_id = self._selected_id()
        if not obj_id:
            return
        if self._highlighted_id:
            self._analyser.highlight(self._highlighted_id, on=False)
            self._highlighted_id = ""
        if self._analyser.highlight(obj_id, on=True):
            self._highlighted_id = obj_id
            self._ctx.statusMessage.emit(f"Destaque em {obj_id}.")

    def clear_highlight(self) -> None:
        """Remove o destaque atualmente ativo no SAP, se houver."""
        if self._analyser is not None and self._highlighted_id:
            self._analyser.highlight(self._highlighted_id, on=False)
            self._highlighted_id = ""
            self._ctx.statusMessage.emit("Destaque removido.")

    def copy_selected_id(self) -> None:
        obj_id = self._selected_id()
        if obj_id and copy_text(obj_id):
            self._ctx.statusMessage.emit("ID copiado para a área de transferência.")

    def export_json(self) -> None:
        if self._root is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Exportar JSON", "arvore.json", "JSON (*.json)")
        if path:
            export.save_json(self._root.to_dict(), path)
            self._ctx.statusMessage.emit(f"Árvore exportada para {path}.")

    def export_csv(self) -> None:
        if self._root is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Exportar CSV", "arvore.csv", "CSV (*.csv)")
        if path:
            rows = [
                {
                    "id": n.id,
                    "type": n.type,
                    "name": n.name,
                    "text": n.text,
                    "is_shell": n.is_shell,
                }
                for n in self._root.flatten()
            ]
            export.save_csv(rows, path)
            self._ctx.statusMessage.emit(f"Árvore exportada para {path}.")
