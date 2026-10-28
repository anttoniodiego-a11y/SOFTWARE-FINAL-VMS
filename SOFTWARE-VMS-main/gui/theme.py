"""
Estilos e tema visual do VMS (QSS - Qt Style Sheets).
Identidade Visual Corporativa: Preto e Amarelo Ouro (Padrão Interface Software VMS).
"""

DARK_THEME_QSS = """
/* Configurações Globais - Preto e Amarelo */
QWidget {
    background-color: #0f1013;
    color: #e5e8ef;
    font-family: 'Segoe UI', 'Roboto', 'Arial', sans-serif;
    font-size: 13px;
    selection-background-color: #f5b800;
    selection-color: #0b0c0e;
}

/* Janela Principal e Diálogos */
QMainWindow, QDialog {
    background-color: #090a0d;
}

QSplitter::handle {
    background-color: #1a1c22;
    width: 3px;
    height: 3px;
}
QSplitter::handle:hover {
    background-color: #f5b800;
}

/* Barra de Ferramentas Superior */
QToolBar {
    background-color: #14151a;
    border-bottom: 2px solid #20222b;
    spacing: 5px;
    padding: 5px 8px;
}

QToolButton {
    background-color: #1c1e26;
    border: 1px solid #2e313d;
    border-radius: 3px;
    padding: 5px 10px;
    font-weight: 500;
    color: #e5e8ef;
}
QToolButton:hover {
    background-color: #262933;
    border-color: #f5b800;
    color: #f5b800;
}
QToolButton:checked, QToolButton:pressed {
    background-color: #f5b800;
    border-color: #f5b800;
    color: #0b0c0e;
    font-weight: bold;
}

/* Botões Padrão */
QPushButton {
    background-color: #1c1e26;
    border: 1px solid #2e313d;
    border-radius: 3px;
    padding: 5px 12px;
    font-weight: 600;
    color: #e5e8ef;
    min-height: 22px;
}
QPushButton:hover {
    background-color: #262933;
    border-color: #f5b800;
    color: #f5b800;
}
QPushButton:pressed {
    background-color: #f5b800;
    color: #0b0c0e;
    border-color: #f5b800;
}
QPushButton:disabled {
    background-color: #121317;
    color: #4a4e5a;
    border-color: #1c1e24;
}

/* Árvore Lateral (Dispositivos e Áreas) */
QTreeView, QTreeWidget {
    background-color: #121317;
    border: 1px solid #20222a;
    border-radius: 3px;
    padding: 4px;
    outline: none;
}
QTreeView::item {
    padding: 5px 4px;
    border-radius: 2px;
}
QTreeView::item:hover {
    background-color: #1e2027;
    color: #f5b800;
}
QTreeView::item:selected {
    background-color: #f5b800;
    color: #0b0c0e;
    font-weight: bold;
}
QHeaderView::section {
    background-color: #181a20;
    color: #f5b800;
    padding: 6px;
    border: none;
    border-right: 1px solid #20222b;
    border-bottom: 2px solid #20222b;
    font-weight: bold;
}

/* Área Central */
QScrollArea {
    border: none;
    background-color: #090a0d;
}

/* Inputs e Formulários */
QLineEdit, QSpinBox, QComboBox {
    background-color: #16181f;
    border: 1px solid #2e313d;
    border-radius: 3px;
    padding: 5px 8px;
    color: #ffffff;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
    border-color: #f5b800;
    background-color: #1c1e26;
}
QComboBox QAbstractItemView {
    background-color: #16181f;
    border: 1px solid #f5b800;
    selection-background-color: #f5b800;
    selection-color: #0b0c0e;
}

/* Barra de Status */
QStatusBar {
    background-color: #0c0d10;
    border-top: 1px solid #1a1c22;
    color: #8a8f9d;
    font-size: 12px;
}

/* Barras de Rolagem */
QScrollBar:vertical {
    border: none;
    background: #0f1013;
    width: 7px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #252833;
    min-height: 20px;
    border-radius: 3px;
}
QScrollBar::handle:vertical:hover {
    background: #f5b800;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar:horizontal {
    border: none;
    background: #0f1013;
    height: 7px;
    margin: 0px;
}
QScrollBar::handle:horizontal {
    background: #252833;
    min-width: 20px;
    border-radius: 3px;
}
QScrollBar::handle:horizontal:hover {
    background: #f5b800;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

/* Tooltips */
QToolTip {
    background-color: #181920;
    color: #f5b800;
    border: 1px solid #f5b800;
    padding: 4px 8px;
    border-radius: 2px;
    font-weight: 500;
}

/* Badges da Logo (Identidade Preto e Amarelo) */
#mainLogoBadge {
    background-color: transparent;
}
#logoCard {
    background-color: #121317;
    border: 1px solid #20222a;
    border-radius: 4px;
}
"""
