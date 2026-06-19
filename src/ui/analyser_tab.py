"""Aba do Analyser — árvore de objetos, detalhes, highlight e exportação."""

from __future__ import annotations

import json
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QPlainTextEdit,
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


class AnalyserTab(QWidget):
    """Percorre e inspeciona a árvore de objetos da sessão selecionada."""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._analyser: Analyser | None = None
        self._root: ObjectNode | None = None
        self._build_ui()
        ctx.sessionChanged.connect(self._on_session_changed)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        barra = QHBoxLayout()
        self.btn_analyse = QPushButton("Analisar sessão")
        self.btn_analyse.clicked.connect(self.analyse)
        self.btn_highlight = QPushButton("Destacar (highlight)")
        self.btn_highlight.clicked.connect(self.highlight_selected)
        self.btn_copy_id = QPushButton("Copiar ID")
        self.btn_copy_id.clicked.connect(self.copy_selected_id)
        self.btn_json = QPushButton("Exportar JSON")
        self.btn_json.clicked.connect(self.export_json)
        self.btn_csv = QPushButton("Exportar CSV")
        self.btn_csv.clicked.connect(self.export_csv)
        for b in (
            self.btn_analyse,
            self.btn_highlight,
            self.btn_copy_id,
            self.btn_json,
            self.btn_csv,
        ):
            barra.addWidget(b)
        barra.addStretch(1)
        layout.addLayout(barra)

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
        self._analyser = Analyser(session) if session is not None else None
        self.tree.clear()
        self.details.clear()
        self._update_enabled()

    def _update_enabled(self) -> None:
        ok = self._ctx.has_session
        self.btn_analyse.setEnabled(ok)
        for b in (self.btn_highlight, self.btn_copy_id, self.btn_json, self.btn_csv):
            b.setEnabled(ok and self._root is not None)

    # ------------------------------------------------------------------ #
    def analyse(self) -> None:
        """Constrói a árvore de objetos da sessão e a exibe."""
        if self._analyser is None:
            return
        self._root = self._analyser.build_tree()
        self.tree.clear()
        root_item = self._make_item(self._root)
        self.tree.addTopLevelItem(root_item)
        root_item.setExpanded(True)
        self._update_enabled()
        self._ctx.statusMessage.emit("Árvore de objetos construída.")

    def _make_item(self, node: ObjectNode) -> QTreeWidgetItem:
        label = node.text or node.name or node.type
        item = QTreeWidgetItem([f"{label}", node.type])
        item.setData(0, _ID_ROLE, node.id)
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
    def highlight_selected(self) -> None:
        if self._analyser is None:
            return
        obj_id = self._selected_id()
        if obj_id and self._analyser.highlight(obj_id):
            self._ctx.statusMessage.emit(f"Highlight em {obj_id}.")

    def copy_selected_id(self) -> None:
        obj_id = self._selected_id()
        if obj_id and copy_text(obj_id):
            self._ctx.statusMessage.emit("ID copiado para o clipboard.")

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
