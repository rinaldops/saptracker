"""Folha de estilo (QSS) da aplicação e helper de aplicação.

Tema escuro sóbrio, alinhado ao visual de ferramentas de desenvolvimento. Uma
única constante :data:`APP_QSS` é aplicada ao ``QApplication`` inteiro.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QApplication

APP_QSS = """
QWidget {
    background-color: #1e2228;
    color: #d7dae0;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
}
QTabWidget::pane {
    border: 1px solid #313640;
    top: -1px;
}
QTabBar::tab {
    background: #262b33;
    padding: 8px 18px;
    border: 1px solid #313640;
    border-bottom: none;
}
QTabBar::tab:selected {
    background: #2f7be0;
    color: #ffffff;
}
QPushButton {
    background-color: #2f7be0;
    color: #ffffff;
    border: none;
    padding: 7px 16px;
    border-radius: 4px;
}
QPushButton:hover { background-color: #3a8af0; }
QPushButton:disabled { background-color: #3a3f48; color: #7a808a; }
QPushButton#danger { background-color: #d0433b; }
QPushButton#danger:hover { background-color: #e0534b; }
QTreeWidget, QListWidget, QTableWidget, QTextEdit, QPlainTextEdit {
    background-color: #171a1f;
    border: 1px solid #313640;
    selection-background-color: #2f7be0;
}
QTreeWidget::item { padding: 3px; }
QTreeWidget::item:selected,
QTreeWidget::item:selected:!active {
    background-color: #5aa2ff;
    color: #ffffff;
}
QHeaderView::section {
    background-color: #262b33;
    padding: 4px;
    border: none;
}
QComboBox {
    background-color: #262b33;
    padding: 5px 8px;
    border: 1px solid #313640;
    border-radius: 4px;
}
QComboBox QAbstractItemView {
    background-color: #262b33;
    selection-background-color: #2f7be0;
}
QLabel#title { font-size: 16px; font-weight: bold; }
QLabel#hint { color: #9aa0aa; font-style: italic; }
QLabel#processing { color: #7fb2ff; font-weight: bold; }
QProgressBar {
    background-color: #171a1f;
    border: 1px solid #313640;
    border-radius: 3px;
    max-height: 8px;
}
QProgressBar::chunk { background-color: #2f7be0; }
QStatusBar { background-color: #262b33; }
"""


def apply_theme(app: QApplication) -> None:
    """Aplica o tema escuro ao ``QApplication``."""
    app.setStyleSheet(APP_QSS)
