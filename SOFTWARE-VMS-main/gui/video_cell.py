"""
Célula Individual de Vídeo (VideoCell).
Componente de exibição de alta performance com QPainter, OSD informativo,
Zero-Jitter (sem popups no hover da grade), suporte completo a Arrastar e Soltar entre células,
renderização da Logo oficial da Interface nos espaços vazios e tema Preto e Amarelo.
"""

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QByteArray, QMimeData, QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QDrag,
    QFont,
    QImage,
    QPainter,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.config import LOGO_PATH
from core.models import Camera, CameraStatus, StreamType


class VideoCell(QWidget):
    """
    Representa uma única porta de vídeo na grade do VMS.
    Otimizada para renderizar frames com baixo uso de CPU via QPainter.
    """

    cell_selected = pyqtSignal(int)                         # cell_index
    cell_double_clicked = pyqtSignal(int)                  # cell_index
    snapshot_requested = pyqtSignal(int)                   # camera_id
    record_toggle_requested = pyqtSignal(int)             # camera_id
    reconnect_requested = pyqtSignal(int)                  # camera_id
    camera_dropped = pyqtSignal(int, int)                  # cell_index, camera_id
    cell_swapped = pyqtSignal(int, int)                    # source_cell_idx, target_cell_idx
    remove_from_cell_requested = pyqtSignal(int)           # cell_index
    delete_requested = pyqtSignal(int)                     # camera_id
    edit_requested = pyqtSignal(int)                       # camera_id
    stream_quality_toggle_requested = pyqtSignal(int, str) # camera_id, StreamType (MAIN/SUB)

    # Cache estático compartilhado da logo da empresa para economizar memória
    _logo_pixmap: Optional[QPixmap] = None

    def __init__(self, cell_index: int, parent=None):
        super().__init__(parent)
        self.cell_index = cell_index
        self.camera: Optional[Camera] = None
        self.stream_type = StreamType.SUB
        self.status = CameraStatus.DISCONNECTED
        self.status_message = "Vazio"

        # Frame de vídeo atual
        self._current_frame: Optional[QImage] = None
        self._frame_width = 0
        self._frame_height = 0
        self._fps = 0.0

        # Estados de controle
        self.is_selected = False
        self.is_recording = False
        self.is_maximized = False
        self.is_hovered = False
        self._drag_start_pos: Optional[QPoint] = None

        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setMinimumSize(140, 90)

        self._init_overlay_ui()
        self._load_logo_if_needed()

    @classmethod
    def _load_logo_if_needed(cls):
        """Carrega a imagem da logo oficial da empresa na memória uma única vez."""
        if cls._logo_pixmap is None:
            if LOGO_PATH.exists():
                pix = QPixmap(str(LOGO_PATH))
                if not pix.isNull():
                    cls._logo_pixmap = pix

    def _init_overlay_ui(self):
        """
        Inicializa a barra inferior de controles.
        Agora ela é exibida estritamente quando a câmera é aberta em foco (1x1),
        eliminando completamente a animação involuntária ao passar o mouse na grade.
        """
        self.layout_overlay = QVBoxLayout(self)
        self.layout_overlay.setContentsMargins(6, 6, 6, 6)
        self.layout_overlay.addStretch()

        self.toolbar_widget = QWidget(self)
        self.toolbar_widget.setStyleSheet("""
            QWidget {
                background-color: rgba(10, 11, 14, 0.92);
                border-radius: 3px;
                border: 1px solid rgba(245, 184, 0, 0.25);
            }
            QPushButton {
                background-color: #1a1c24;
                border: 1px solid #2e313d;
                color: #e5e8ef;
                font-size: 11px;
                padding: 3px 8px;
                border-radius: 2px;
            }
            QPushButton:hover {
                background-color: #f5b800;
                color: #0b0c0e;
                font-weight: bold;
            }
        """)
        tb_layout = QHBoxLayout(self.toolbar_widget)
        tb_layout.setContentsMargins(6, 2, 6, 2)
        tb_layout.setSpacing(6)

        self.lbl_bar_status = QLabel("Offline", self.toolbar_widget)
        self.lbl_bar_status.setStyleSheet("color: #f5b800; font-size: 11px; font-weight: bold; border: none; background: transparent;")
        tb_layout.addWidget(self.lbl_bar_status)
        tb_layout.addStretch()

        # Botão de Ajuste Individual de Qualidade: SUB (SD) <-> MAIN (HD)
        self.btn_stream_toggle = QPushButton("SD", self.toolbar_widget)
        self.btn_stream_toggle.setToolTip("Alternar entre Substream (SD) e Stream Principal (HD)")
        self._apply_stream_toggle_style()
        self.btn_stream_toggle.clicked.connect(self._on_stream_toggle_clicked)
        tb_layout.addWidget(self.btn_stream_toggle)

        # Botão Snapshot
        self.btn_snapshot = QPushButton("📷 Foto", self.toolbar_widget)
        self.btn_snapshot.setToolTip("Capturar Imagem Estática (Snapshot)")
        self.btn_snapshot.clicked.connect(self._on_snapshot_clicked)
        tb_layout.addWidget(self.btn_snapshot)

        # Botão Gravar
        self.btn_record = QPushButton("⏺ Gravar", self.toolbar_widget)
        self.btn_record.setToolTip("Iniciar/Parar Gravação Manual")
        self.btn_record.clicked.connect(self._on_record_clicked)
        tb_layout.addWidget(self.btn_record)

        # Botão Reconectar
        self.btn_reconnect = QPushButton("🔄", self.toolbar_widget)
        self.btn_reconnect.setToolTip("Forçar Reconexão RTSP")
        self.btn_reconnect.clicked.connect(self._on_reconnect_clicked)
        tb_layout.addWidget(self.btn_reconnect)

        # Botão Editar Câmera / Senha
        self.btn_edit = QPushButton("⚙️", self.toolbar_widget)
        self.btn_edit.setToolTip("Editar Câmera / Senha")
        self.btn_edit.clicked.connect(self._on_edit_clicked)
        tb_layout.addWidget(self.btn_edit)

        self.layout_overlay.addWidget(self.toolbar_widget)
        # Oculto por padrão: só aparece quando a câmera é aberta em foco (1x1)
        self.toolbar_widget.setVisible(False)

    def _apply_stream_toggle_style(self):
        """Atualiza a aparência do botão de qualidade SD/HD no padrão preto e amarelo."""
        if self.stream_type == StreamType.MAIN:
            self.btn_stream_toggle.setText("HD")
            self.btn_stream_toggle.setStyleSheet("""
                QPushButton {
                    background-color: #f5b800;
                    border: 1px solid #f5b800;
                    color: #0b0c0e;
                    font-weight: bold;
                    font-size: 10px;
                    padding: 2px 6px;
                    border-radius: 2px;
                }
                QPushButton:hover {
                    background-color: #ffd000;
                }
            """)
        else:
            self.btn_stream_toggle.setText("SD")
            self.btn_stream_toggle.setStyleSheet("""
                QPushButton {
                    background-color: #1a1c24;
                    border: 1px solid #4a5060;
                    color: #f5b800;
                    font-weight: bold;
                    font-size: 10px;
                    padding: 2px 6px;
                    border-radius: 2px;
                }
                QPushButton:hover {
                    border-color: #f5b800;
                    background-color: #242733;
                }
            """)

    def _on_stream_toggle_clicked(self):
        if not self.camera or not self.camera.id:
            return
        target = StreamType.MAIN if self.stream_type == StreamType.SUB else StreamType.SUB
        self.stream_type = target
        self._apply_stream_toggle_style()
        self.stream_quality_toggle_requested.emit(self.camera.id, target.value)
        self.update()

    def set_stream_type(self, stream_type: StreamType):
        self.stream_type = stream_type
        self._apply_stream_toggle_style()
        self.update()

    def set_maximized_mode(self, maximized: bool):
        """Controla a exibição da barra de ações apenas no modo maximizado (1x1)."""
        self.is_maximized = maximized
        if maximized and self.camera:
            self.toolbar_widget.setVisible(True)
        else:
            self.toolbar_widget.setVisible(False)
        self.update()

    def assign_camera(self, camera: Optional[Camera], stream_type: StreamType = StreamType.SUB):
        """Associa ou desassocia uma câmera desta célula."""
        self.camera = camera
        self.stream_type = stream_type
        self._current_frame = None
        self._fps = 0.0
        self.is_recording = False
        if camera:
            self.status = CameraStatus.CONNECTING
            self.status_message = "Iniciando comunicação..."
            self.lbl_bar_status.setText(f"Canal {camera.channel}")
            if self.is_maximized:
                self.toolbar_widget.setVisible(True)
        else:
            self.status = CameraStatus.DISCONNECTED
            self.status_message = "Vazio"
            self.lbl_bar_status.setText("Vazio")
            self.toolbar_widget.setVisible(False)
        self.update()

    def update_frame(self, qimage: QImage, width: int, height: int):
        self._current_frame = qimage
        self._frame_width = width
        self._frame_height = height
        self.update()

    def update_status(self, status: str, message: str):
        try:
            self.status = CameraStatus(status)
        except ValueError:
            pass
        self.status_message = message
        self.lbl_bar_status.setText(self.status.value)
        self.update()

    def update_fps(self, fps: float):
        self._fps = fps
        self.update()

    def set_recording(self, recording: bool):
        self.is_recording = recording
        if recording:
            self.btn_record.setText("⏹ Parar")
            self.btn_record.setStyleSheet("background-color: #d32f2f; color: white; font-weight: bold;")
        else:
            self.btn_record.setText("⏺ Gravar")
            self.btn_record.setStyleSheet("")
        self.update()

    def set_selected(self, selected: bool):
        self.is_selected = selected
        self.update()

    def _on_edit_clicked(self):
        if self.camera and self.camera.id:
            self.edit_requested.emit(self.camera.id)

    def _on_snapshot_clicked(self):
        if self.camera and self.camera.id:
            self.snapshot_requested.emit(self.camera.id)

    def _on_record_clicked(self):
        if self.camera and self.camera.id:
            self.record_toggle_requested.emit(self.camera.id)

    def _on_reconnect_clicked(self):
        if self.camera and self.camera.id:
            self.reconnect_requested.emit(self.camera.id)

    # --- Mouse e Drag-and-Drop entre Células ---
    def enterEvent(self, event):
        self.is_hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.is_hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.cell_selected.emit(self.cell_index)
            if self.camera:
                self._drag_start_pos = event.pos()
        elif event.button() == Qt.MouseButton.RightButton:
            self.cell_selected.emit(self.cell_index)
            self._show_cell_context_menu(event.globalPosition().toPoint())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Inicia operação de arrastar da célula para mover ou trocar com outro slot."""
        if (event.buttons() & Qt.MouseButton.LeftButton) and self._drag_start_pos and self.camera:
            dist = (event.pos() - self._drag_start_pos).manhattanLength()
            if dist >= 10:  # Limiar de início de drag
                mime = QMimeData()
                mime.setData("application/x-vms-cell-move", str(self.cell_index).encode())
                mime.setData("application/x-vms-camera-id", str(self.camera.id).encode())

                drag = QDrag(self)
                drag.setMimeData(mime)
                # Snapshot visual durante o drag
                drag.setPixmap(self.grab().scaled(160, 90, Qt.AspectRatioMode.KeepAspectRatio))
                self._drag_start_pos = None
                drag.exec(Qt.DropAction.MoveAction)
        super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Duplo clique estrito para expandir ou restaurar."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.cell_double_clicked.emit(self.cell_index)
        super().mouseDoubleClickEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-vms-cell-move") or event.mimeData().hasFormat("application/x-vms-camera-id"):
            event.acceptProposedAction()

    def dropEvent(self, event):
        """Recebe câmera da árvore lateral OU de outra célula (mover/trocar)."""
        mime = event.mimeData()
        if mime.hasFormat("application/x-vms-cell-move"):
            src_cell_idx = int(mime.data("application/x-vms-cell-move").data().decode())
            if src_cell_idx != self.cell_index:
                self.cell_swapped.emit(src_cell_idx, self.cell_index)
                event.acceptProposedAction()
        elif mime.hasFormat("application/x-vms-camera-id"):
            cam_id = int(mime.data("application/x-vms-camera-id").data().decode())
            self.camera_dropped.emit(self.cell_index, cam_id)
            event.acceptProposedAction()

    def _show_cell_context_menu(self, global_pos):
        """Menu de contexto acionado ao clicar com botão direito na célula."""
        menu = QMenu(self)
        if self.camera:
            action_focus = menu.addAction("⛶ Abrir em Foco Total (Duplo Clique)")
            action_toggle_q = menu.addAction(f"🔄 Alternar para {'HD (Alta Resolução)' if self.stream_type == StreamType.SUB else 'SD (Baixa Latência)'}")
            action_snap = menu.addAction("📷 Capturar Imagem (Snapshot)")
            action_rec = menu.addAction("⏺ Iniciar/Parar Gravação")
            action_edit = menu.addAction("⚙️ Configurar Câmera / Senha")
            menu.addSeparator()
            action_remove = menu.addAction("❌ Liberar este Slot (Remover da Grade)")
            action_delete = menu.addAction("🗑 Excluir Câmera do Sistema")

            chosen = menu.exec(global_pos)
            if chosen == action_focus:
                self.cell_double_clicked.emit(self.cell_index)
            elif chosen == action_toggle_q:
                self._on_stream_toggle_clicked()
            elif chosen == action_snap:
                self._on_snapshot_clicked()
            elif chosen == action_rec:
                self._on_record_clicked()
            elif chosen == action_edit:
                self._on_edit_clicked()
            elif chosen == action_remove:
                self.remove_from_cell_requested.emit(self.cell_index)
            elif chosen == action_delete:
                if self.camera and self.camera.id:
                    self.delete_requested.emit(self.camera.id)
        else:
            action_info = menu.addAction("➕ Arraste uma câmera da barra lateral para cá")
            action_info.setEnabled(False)
            menu.exec(global_pos)

    # --- Renderização com QPainter e Identidade Visual Preto e Amarelo ---
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        rect = self.rect()

        # Fundo Preto Puro
        painter.fillRect(rect, QColor("#08090b"))

        # 1. Renderiza o quadro de vídeo se disponível
        if self._current_frame is not None and not self._current_frame.isNull():
            scaled_img = self._current_frame.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation
            )
            x = (self.width() - scaled_img.width()) // 2
            y = (self.height() - scaled_img.height()) // 2
            painter.drawImage(x, y, scaled_img)
        else:
            # 2. Desenha placeholder com Logo da Empresa nos espaços vazios
            self._paint_placeholder(painter, rect)

        # 3. OSD Superior (exibido apenas no hover do mouse ou caso não haja sinal de vídeo)
        if self.camera and (self.is_hovered or self._current_frame is None):
            self._paint_osd_header(painter, rect)

        # 4. Moldura de Seleção: Amarelo Ouro (#f5b800) em foco, cinza discreto quando inativo
        if self.is_selected:
            painter.setPen(QPen(QColor("#f5b800"), 2))
            painter.drawRect(rect.adjusted(1, 1, -1, -1))
        else:
            painter.setPen(QPen(QColor("#1c1e24"), 1))
            painter.drawRect(rect.adjusted(0, 0, -1, -1))

    def _paint_placeholder(self, painter: QPainter, rect: QRect):
        """Desenha a Logo da Empresa centralizada nos slots pretos vazios ou status de conexão."""
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        if not self.camera:
            # Slot vazio: exibe a Logo oficial da Interface diretamente sobre o fundo preto
            if self._logo_pixmap and not self._logo_pixmap.isNull():
                max_w = min(int(rect.width() * 0.72), 290)
                max_h = min(int(rect.height() * 0.48), 100)
                if max_w > 40 and max_h > 25:
                    scaled_logo = self._logo_pixmap.scaled(
                        max_w - 24, max_h - 16,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    )
                    lx = (rect.width() - scaled_logo.width()) // 2
                    ly = (rect.height() - scaled_logo.height()) // 2 - 14
                    painter.drawPixmap(lx, ly, scaled_logo)

            # Legenda elegante em Preto e Amarelo
            painter.setPen(QColor("#f5b800"))
            painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            text_rect = QRect(rect.x() + 4, rect.bottom() - 36, rect.width() - 8, 16)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, "INTERFACE SOFTWARE VMS")

            painter.setPen(QColor("#616777"))
            painter.setFont(QFont("Segoe UI", 8))
            sub_rect = QRect(rect.x() + 4, rect.bottom() - 20, rect.width() - 8, 14)
            painter.drawText(sub_rect, Qt.AlignmentFlag.AlignCenter, f"Canal {self.cell_index + 1:02d} • Slot Disponível")

        else:
            # Câmera vinculada aguardando sinal
            content_rect = rect.adjusted(12, 30, -12, -30)
            if self.status == CameraStatus.CONNECTING:
                painter.setPen(QColor("#f5b800"))
                text = f"⏳ Conectando...\n{self.camera.name}\n{self.status_message}"
            else:
                painter.setPen(QColor("#ff4d4d"))
                text = f"⚠️ Sem Sinal\n{self.camera.name}\n{self.status_message}"

            painter.setFont(QFont("Segoe UI", 9))
            painter.drawText(content_rect, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, text)

    def _paint_osd_header(self, painter: QPainter, rect: QRect):
        header_height = 24
        header_rect = QRect(rect.x(), rect.y(), rect.width(), header_height)

        painter.fillRect(header_rect, QColor(10, 11, 14, 210))

        x_offset = 8
        if self.is_recording:
            painter.setBrush(QBrush(QColor("#ff1744")))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(x_offset, rect.y() + 6, 10, 10)
            x_offset += 16

        painter.setPen(QColor("#ffffff"))
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        cam_title = f"{self.camera.name}"
        painter.drawText(x_offset, rect.y() + 16, cam_title)

        stream_badge = "[SUB]" if self.stream_type == StreamType.SUB else "[MAIN HD]"
        if self._frame_width > 0 and self._frame_height > 0:
            right_info = f"{stream_badge} {self._frame_width}x{self._frame_height} | {self._fps:.1f} FPS"
        else:
            right_info = f"{stream_badge} | {self.status.value}"

        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        badge_color = QColor("#00e5ff") if self.stream_type == StreamType.SUB else QColor("#f5b800")
        painter.setPen(badge_color)

        info_rect = QRect(rect.width() - 230, rect.y(), 222, header_height)
        painter.drawText(info_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, right_info)
