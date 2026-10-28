"""
Janela Principal do VMS Desktop (MainWindow).
Integra a Barra Lateral Hierárquica, a Grade de Vídeo Multi-Canal (1x1 até 8x8),
a Toolbar de Ações Rápidas, o Auto-Discovery e o Gerenciador Central de Streams.
"""

import os
import subprocess
import sys
from datetime import datetime
from typing import List

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QAction, QIcon, QKeySequence, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from core.config import LOGO_PATH
from core.database import DatabaseManager
from core.models import Camera, StreamType
from core.stream_manager import StreamManager
from gui.camera_dialog import CameraDialog
from gui.camera_tree import CameraTree
from gui.discovery_dialog import DiscoveryDialog
from gui.theme import DARK_THEME_QSS
from gui.video_grid import VideoGrid


class MainWindow(QMainWindow):
    """Janela principal corporativa do sistema de monitoramento de CFTV."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("INTERFACE SOFTWARE VMS - Central de Monitoramento CFTV")
        self.resize(1400, 900)
        self.setMinimumSize(1024, 600)

        # Inicializa banco de dados e motor de stream
        self.db = DatabaseManager()
        self.stream_manager = StreamManager()

        # Aplica folha de estilo corporativa Preto e Amarelo
        self.setStyleSheet(DARK_THEME_QSS)

        self._init_ui()
        self._init_shortcuts()
        self._init_status_timer()
        self._auto_populate_first_grid()

    def _init_ui(self):
        # 1. Barra de Ferramentas Superior (Quick Actions & Grids)
        self.toolbar = QToolBar("Barra Principal", self)
        self.toolbar.setMovable(False)
        self.toolbar.setIconSize(QSize(20, 20))
        self.addToolBar(self.toolbar)

        # Badge da Marca no Topo (Identidade Preto e Amarelo)
        self.logo_badge = QWidget(self)
        self.logo_badge.setObjectName("mainLogoBadge")
        self.logo_badge.setStyleSheet("""
            QWidget#mainLogoBadge {
                background-color: transparent;
                padding: 2px 6px;
            }
        """)
        logo_layout = QHBoxLayout(self.logo_badge)
        logo_layout.setContentsMargins(4, 2, 8, 2)
        logo_layout.setSpacing(8)

        if LOGO_PATH.exists():
            pix = QPixmap(str(LOGO_PATH))
            if not pix.isNull():
                self.lbl_logo_img = QLabel()
                self.lbl_logo_img.setPixmap(pix.scaledToHeight(26, Qt.TransformationMode.SmoothTransformation))
                logo_layout.addWidget(self.lbl_logo_img)

        self.lbl_logo_title = QLabel("INTERFACE VMS")
        self.lbl_logo_title.setStyleSheet("font-weight: 900; font-size: 15px; color: #f5b800;")
        logo_layout.addWidget(self.lbl_logo_title)
        self.toolbar.addWidget(self.logo_badge)

        self.toolbar.addSeparator()

        # Botão para Minimizar / Ocultar a Barra Lateral ("Dispositivos Locais")
        self.btn_toggle_sidebar = QPushButton("◀ Ocultar Dispositivos", self)
        self.btn_toggle_sidebar.setToolTip("Ocultar ou exibir a aba de dispositivos e grupos para maximizar o vídeo (Atalho: Ctrl+B)")
        self.btn_toggle_sidebar.clicked.connect(self._toggle_sidebar)
        self.toolbar.addWidget(self.btn_toggle_sidebar)

        self.toolbar.addSeparator()

        # Botão de Destaque: Auto-Discovery (Preto e Amarelo)
        self.btn_discovery = QPushButton("🔍 Buscar Câmeras na Rede (Auto-Discovery)")
        self.btn_discovery.setStyleSheet("""
            QPushButton {
                background-color: #f5b800;
                color: #0b0c0e;
                font-weight: bold;
                padding: 6px 14px;
                border: 1px solid #f5b800;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #ffd000;
            }
        """)
        self.btn_discovery.clicked.connect(self._open_discovery_dialog)
        self.toolbar.addWidget(self.btn_discovery)

        self.toolbar.addSeparator()

        # Botões de Seleção de Grade
        self.lbl_grids = QLabel(" Layout: ")
        self.lbl_grids.setStyleSheet("font-weight: bold; color: #a0a6b5;")
        self.toolbar.addWidget(self.lbl_grids)

        grid_buttons = [
            ("1x1", "1x1"),
            ("2x2", "2x2"),
            ("3x3", "3x3"),
            ("4x4", "4x4"),
            ("5x5", "5x5"),
            ("6x6", "6x6"),
            ("7x7", "7x7"),
            ("8x8 (64 Ch)", "8x8"),
        ]

        for label, layout_key in grid_buttons:
            btn = QPushButton(label)
            btn.setCheckable(False)
            btn.clicked.connect(lambda checked, k=layout_key: self.video_grid.apply_layout(k))
            self.toolbar.addWidget(btn)

        self.toolbar.addSeparator()

        # Botão Adicionar Câmera Manual
        self.btn_add_cam = QPushButton("➕ Adicionar Manual")
        self.btn_add_cam.clicked.connect(self._open_add_camera_dialog)
        self.toolbar.addWidget(self.btn_add_cam)

        self.toolbar.addSeparator()

        # Tela Cheia
        self.btn_fullscreen = QPushButton("⛶ F11")
        self.btn_fullscreen.setToolTip("Alternar Modo Tela Cheia (F11)")
        self.btn_fullscreen.clicked.connect(self._toggle_fullscreen)
        self.toolbar.addWidget(self.btn_fullscreen)

        # 2. Painel Central Dividido (Splitter)
        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.setCollapsible(0, True)

        # Lado Esquerdo: Árvore de Câmeras e Grupos
        self.camera_tree = CameraTree(self.db, self.splitter)
        self.camera_tree.setMinimumWidth(260)
        self.camera_tree.setMaximumWidth(450)
        self.camera_tree.camera_selected_for_cell.connect(self._on_tree_camera_selected)
        self.camera_tree.add_camera_requested.connect(self._open_add_camera_dialog)
        self.camera_tree.edit_camera_requested.connect(self._open_edit_camera_dialog)
        self.camera_tree.delete_camera_requested.connect(self._delete_camera)
        self.camera_tree.auto_discovery_requested.connect(self._open_discovery_dialog)
        self.camera_tree.group_changed.connect(lambda: self._show_status_message("Grupos organizados com sucesso."))

        # Lado Direito: Grade de Vídeo
        self.video_grid = VideoGrid(self.stream_manager, self.splitter)
        self.video_grid.status_message_emitted.connect(self._show_status_message)
        self.video_grid.edit_camera_requested.connect(self._open_edit_camera_dialog)

        self.splitter.addWidget(self.camera_tree)
        self.splitter.addWidget(self.video_grid)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)

        self.setCentralWidget(self.splitter)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)

        self.setCentralWidget(self.splitter)

        # 3. Barra de Status Inferior
        self.status_bar = QStatusBar(self)
        self.setStatusBar(self.status_bar)

        self.lbl_status_msg = QLabel("INTERFACE SOFTWARE VMS Pronto. Use 'Buscar Câmeras na Rede' para localizar seus dispositivos.")
        self.lbl_status_stats = QLabel("Canais: 0 ativos | Modo: SUBSTREAM")
        self.lbl_status_time = QLabel("")

        self.status_bar.addWidget(self.lbl_status_msg, 1)
        self.status_bar.addPermanentWidget(self.lbl_status_stats)
        self.status_bar.addPermanentWidget(self.lbl_status_time)

    def _init_shortcuts(self):
        QShortcut(QKeySequence("F11"), self, self._toggle_fullscreen)
        QShortcut(QKeySequence("Ctrl+B"), self, self._toggle_sidebar)
        QShortcut(QKeySequence("Escape"), self, self._on_escape_pressed)

    def _init_status_timer(self):
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self._update_status_bar)
        self.status_timer.start(1000)

    def _update_status_bar(self):
        now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        self.lbl_status_time.setText(f"🕒 {now_str}  ")

        active_workers = len(self.stream_manager._workers)
        stream_mode = "[MAIN ALTA RES]" if self.video_grid.is_maximized_1x1 else "[SUBSTREAM RESUMO]"
        self.lbl_status_stats.setText(f"Canais Ativos: {active_workers} | {stream_mode}  ")

    def _show_status_message(self, message: str):
        self.lbl_status_msg.setText(message)

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _on_escape_pressed(self):
        if self.isFullScreen():
            self.showNormal()
        elif self.video_grid.is_maximized_1x1:
            self.video_grid.apply_layout(self.video_grid.previous_layout_name)

    def _toggle_sidebar(self):
        visible = not self.camera_tree.isVisible()
        self.camera_tree.setVisible(visible)
        if visible:
            self.btn_toggle_sidebar.setText("◀ Ocultar Dispositivos")
            self.btn_toggle_sidebar.setStyleSheet("")
            self._show_status_message("Painel de dispositivos reexibido.")
        else:
            self.btn_toggle_sidebar.setText("▶ Mostrar Dispositivos")
            self.btn_toggle_sidebar.setStyleSheet("background-color: #f5b800; color: #0b0c0e; font-weight: bold;")
            self._show_status_message("Painel de dispositivos ocultado (Visualização expandida).")

    def _open_discovery_dialog(self):
        """Abre a janela de Auto-Discovery e carrega os canais importados."""
        dialog = DiscoveryDialog(self.db, parent=self)
        dialog.cameras_added.connect(self._on_cameras_discovered_and_added)
        dialog.exec()

    def _on_cameras_discovered_and_added(self, added_cameras: List[Camera]):
        """Atualiza a árvore e preenche a grade com as câmeras recém-adicionadas."""
        self.camera_tree.reload_data()
        for i, cam in enumerate(added_cameras):
            if i < 64:
                self.video_grid.assign_camera_to_cell(i, cam)

        if len(added_cameras) > 4:
            self.video_grid.apply_layout("3x3" if len(added_cameras) <= 9 else "4x4")

        self._show_status_message(f"✅ {len(added_cameras)} câmeras importadas e conectadas na grade!")

    def _open_add_camera_dialog(self):
        dialog = CameraDialog(self.db, parent=self)
        if dialog.exec():
            self.camera_tree.reload_data()
            self._show_status_message("Nova câmera adicionada com sucesso!")

    def _open_edit_camera_dialog(self, camera_id: int):
        cam = self.db.get_camera_by_id(camera_id)
        if cam:
            dialog = CameraDialog(self.db, camera=cam, parent=self)
            if dialog.exec():
                self.camera_tree.reload_data()
                # Atualiza na grade se estiver ativa
                for idx, c in self.video_grid.cell_camera_map.items():
                    if c and c.id == camera_id:
                        updated_cam = self.db.get_camera_by_id(camera_id)
                        if updated_cam:
                            self.video_grid.assign_camera_to_cell(idx, updated_cam)
                        break
                self._show_status_message(f"Câmera {cam.name} atualizada.")

    def _delete_camera(self, camera_id: int):
        cam = self.db.get_camera_by_id(camera_id)
        if not cam:
            return
        reply = QMessageBox.question(
            self,
            "Confirmar Exclusão",
            f"Deseja realmente remover a câmera '{cam.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            # 1. Desvincula imediatamente da grade para evitar sinais de pintura em células mortas
            for idx, c in list(self.video_grid.cell_camera_map.items()):
                if c and c.id == camera_id:
                    self.video_grid.cells[idx].assign_camera(None)
                    self.video_grid.cell_camera_map[idx] = None

            # 2. Encerra a thread via stream_manager (com retenção de referência para evitar crash)
            self.stream_manager.stop_camera_stream(camera_id)

            # 3. Remove do banco SQLite
            self.db.delete_camera(camera_id)

            # 4. Atualiza a árvore de forma segura e assíncrona
            QTimer.singleShot(50, self.camera_tree.reload_data)
            self._show_status_message(f"Câmera '{cam.name}' excluída com sucesso.")

    def _auto_populate_first_grid(self):
        self._populate_grid_with_cameras()

    def _populate_grid_with_cameras(self):
        all_cams = self.db.get_all_cameras()
        for i, cam in enumerate(all_cams[:64]):
            self.video_grid.assign_camera_to_cell(i, cam)

    def _on_tree_camera_selected(self, camera: Camera):
        selected_idx = self.video_grid.selected_cell_index
        self.video_grid.assign_camera_to_cell(selected_idx, camera)
        self._show_status_message(f"Câmera '{camera.name}' carregada na Célula #{selected_idx + 1}")

    def closeEvent(self, event):
        self._show_status_message("Encerrando fluxos de vídeo com segurança...")
        self.stream_manager.stop_all()
        event.accept()
