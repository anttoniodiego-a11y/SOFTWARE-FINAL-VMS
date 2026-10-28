"""
Ponto de Entrada Principal do VMS Desktop (Video Management System).
Inicializa o loop de eventos do PyQt6, aplica aceleração gráfica e instancia a janela corporativa.
"""

import os
import sys

# Garante que o diretório raiz do projeto esteja no sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
from gui.main_window import MainWindow


def main():
    # Otimização de renderização de alta densidade de pixels (High DPI)
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

    app = QApplication(sys.argv)
    app.setApplicationName("INTERFACE SOFTWARE VMS")
    app.setApplicationVersion("2.5.0")
    app.setOrganizationName("Interface")

    from PyQt6.QtGui import QIcon
    from core.config import LOGO_PATH
    if LOGO_PATH.exists():
        app.setWindowIcon(QIcon(str(LOGO_PATH)))

    # Instancia a janela principal corporativa
    window = MainWindow()
    if LOGO_PATH.exists():
        window.setWindowIcon(QIcon(str(LOGO_PATH)))
    window.show()

    # Executa o loop de eventos Qt
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
