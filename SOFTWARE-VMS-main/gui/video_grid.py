"""
Gerenciador de Grade de Vídeo (VideoGrid).
Suporta layouts flexíveis: 1x1, 2x2, 3x3, 4x4, até 8x8 (64 canais simultâneos).
Controla a paginação de canais e o chaveamento dinâmico de Dual Stream (Main/Sub).
"""

from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.config import MAX_CAMERAS, SUPPORTED_GRIDS
from core.models import Camera, StreamType
from core.stream_manager import StreamManager
from gui.video_cell import VideoCell


class VideoGrid(QWidget):
    """
    Área central de exibição das câmeras.
    Controla o layout dinâmico em matriz e a paginação das 64 portas de vídeo.
    """

    status_message_emitted = pyqtSignal(str)
    edit_camera_requested = pyqtSignal(int)    # camera_id
    delete_camera_requested = pyqtSignal(int)  # camera_id

    def __init__(self, stream_manager: StreamManager, parent=None):
        super().__init__(parent)
        self.stream_manager = stream_manager

        # Estado da grade
        self.current_layout_name = "2x2"
        self.previous_layout_name = "2x2"
        self.rows, self.cols = SUPPORTED_GRIDS["2x2"]
        self.current_page = 0
        self.selected_cell_index = 0
        self.is_maximized_1x1 = False
        self.maximized_cell_index: Optional[int] = None

        # Alocação de 64 células pré-instanciadas
        self.cells: List[VideoCell] = []
        self.cell_camera_map: Dict[int, Optional[Camera]] = {i: None for i in range(MAX_CAMERAS)}

        self._init_ui()
        self.apply_layout("2x2")

    def _init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(2, 2, 2, 2)
        self.main_layout.setSpacing(2)

        # Container do grid de vídeo
        self.grid_container = QWidget(self)
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setSpacing(2)
        self.main_layout.addWidget(self.grid_container, 1)

        # Barra de Navegação de Páginas
        self.pagination_bar = QWidget(self)
        self.pagination_bar.setStyleSheet("background-color: #1a1b1e; padding: 2px;")
        pag_layout = QHBoxLayout(self.pagination_bar)
        pag_layout.setContentsMargins(6, 2, 6, 2)
        pag_layout.setSpacing(8)

        self.btn_prev_page = QPushButton("◀ Página Anterior")
        self.btn_prev_page.clicked.connect(self.prev_page)
        pag_layout.addWidget(self.btn_prev_page)

        self.lbl_page_info = QLabel("Página 1 de 4 (Canais 1-16 de 64)")
        self.lbl_page_info.setStyleSheet("font-weight: bold; color: #a0a6b5;")
        pag_layout.addWidget(self.lbl_page_info)

        self.btn_next_page = QPushButton("Próxima Página ▶")
        self.btn_next_page.clicked.connect(self.next_page)
        pag_layout.addWidget(self.btn_next_page)

        pag_layout.addStretch()

        self.lbl_active_info = QLabel("Modo Grade: 2x2 | Dual Stream: [SUB]")
        self.lbl_active_info.setStyleSheet("color: #00e5ff; font-size: 11px;")
        pag_layout.addWidget(self.lbl_active_info)

        self.main_layout.addWidget(self.pagination_bar)

        # Instancia as 64 células de vídeo
        for i in range(MAX_CAMERAS):
            cell = VideoCell(cell_index=i, parent=self.grid_container)
            cell.cell_selected.connect(self._on_cell_selected)
            cell.cell_double_clicked.connect(self._on_cell_double_clicked)
            cell.snapshot_requested.connect(self._on_snapshot_requested)
            cell.record_toggle_requested.connect(self._on_record_toggle_requested)
            cell.reconnect_requested.connect(self._on_reconnect_requested)
            cell.camera_dropped.connect(self.assign_camera_to_cell)
            cell.edit_requested.connect(self.edit_camera_requested.emit)
            cell.stream_quality_toggle_requested.connect(self._on_cell_quality_toggled)
            cell.cell_swapped.connect(self.swap_or_move_cells)
            cell.remove_from_cell_requested.connect(self.remove_camera_from_cell)
            cell.delete_requested.connect(self.delete_camera_requested.emit)
            self.cells.append(cell)

        self.cells[0].set_selected(True)

    def _get_active_indices(self) -> List[int]:
        """Retorna os índices das células que possuem câmera vinculada."""
        return [idx for idx, cam in self.cell_camera_map.items() if cam is not None]

    def _get_active_camera_count(self) -> int:
        """Retorna a contagem necessária de slots para abrigar todas as câmeras ativas."""
        indices = self._get_active_indices()
        if not indices:
            return 0
        return max(indices) + 1

    def _get_total_pages(self, cells_per_page: int) -> int:
        """Calcula o total de páginas restrito estritamente à quantidade de câmeras ativas."""
        needed_slots = self._get_active_camera_count()
        if needed_slots == 0:
            return 1
        return max(1, (needed_slots + cells_per_page - 1) // cells_per_page)

    def apply_layout(self, layout_name: str):
        """Altera a disposição da grade (1x1, 2x2, 3x3, 4x4, 8x8)."""
        if layout_name not in SUPPORTED_GRIDS:
            return

        was_1x1 = self.is_maximized_1x1
        if not was_1x1:
            self.previous_layout_name = self.current_layout_name

        self.current_layout_name = layout_name
        self.rows, self.cols = SUPPORTED_GRIDS[layout_name]
        self.is_maximized_1x1 = (layout_name == "1x1")

        cells_per_page = self.rows * self.cols
        total_pages = self._get_total_pages(cells_per_page)

        if self.is_maximized_1x1:
            self._update_dual_stream_policy(maximized_cell_index=self.selected_cell_index)
        else:
            # Ao sair do 1x1, calcula a página exata da câmera selecionada para não iniciar em página errada
            target_page = self.selected_cell_index // cells_per_page
            self.current_page = min(target_page, total_pages - 1)
            self._update_dual_stream_policy(maximized_cell_index=None)

        self._refresh_grid_display()

    def _refresh_grid_display(self):
        while self.grid_layout.count() > 0:
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)

        cells_per_page = self.rows * self.cols
        active_indices = self._get_active_indices()
        total_cams = len(active_indices)

        if self.is_maximized_1x1:
            active_cell = self.cells[self.selected_cell_index]
            self.grid_layout.addWidget(active_cell, 0, 0)
            active_cell.show()

            active_cam = self.cell_camera_map.get(self.selected_cell_index)
            cam_name = active_cam.name if active_cam else f"Canal {self.selected_cell_index + 1}"
            self.lbl_page_info.setText(f"📹 {cam_name} (Foco Total 1x1)")

            self.btn_prev_page.setEnabled(total_cams > 1 or self.selected_cell_index > 0)
            self.btn_next_page.setEnabled(total_cams > 1 or self.selected_cell_index < MAX_CAMERAS - 1)
            self.lbl_active_info.setText("Modo: 1x1 Foco | Dual Stream: [MAIN ALTA RESOLUÇÃO]")
            return

        total_pages = self._get_total_pages(cells_per_page)
        if self.current_page >= total_pages:
            self.current_page = max(0, total_pages - 1)

        start_idx = self.current_page * cells_per_page
        end_idx = min(start_idx + cells_per_page, MAX_CAMERAS)

        for cell in self.cells:
            cell.hide()

        for i, cell_idx in enumerate(range(start_idx, end_idx)):
            r = i // self.cols
            c = i % self.cols
            cell = self.cells[cell_idx]
            self.grid_layout.addWidget(cell, r, c)
            cell.show()

        # Barra de navegação visível apenas quando houver mais de uma página
        self.pagination_bar.setVisible(total_pages > 1 or total_cams > cells_per_page)
        self.btn_prev_page.setEnabled(self.current_page > 0)
        self.btn_next_page.setEnabled(self.current_page < total_pages - 1)
        self.lbl_page_info.setText(
            f"Página {self.current_page + 1} de {total_pages} ({total_cams} Câmera(s) Ativa(s))"
        )
        self.lbl_active_info.setText(f"Modo Grade: {self.current_layout_name} | Dual Stream: [SUB]")

    def prev_page(self):
        if self.is_maximized_1x1:
            active_indices = self._get_active_indices()
            if active_indices and self.selected_cell_index in active_indices:
                pos = active_indices.index(self.selected_cell_index)
                if pos > 0:
                    self._select_cell(active_indices[pos - 1])
                    self._update_dual_stream_policy(maximized_cell_index=self.selected_cell_index)
                    self._refresh_grid_display()
            elif self.selected_cell_index > 0:
                self._select_cell(self.selected_cell_index - 1)
                self._update_dual_stream_policy(maximized_cell_index=self.selected_cell_index)
                self._refresh_grid_display()
        else:
            if self.current_page > 0:
                self.current_page -= 1
                self._refresh_grid_display()

    def next_page(self):
        cells_per_page = self.rows * self.cols
        total_pages = self._get_total_pages(cells_per_page)
        if self.is_maximized_1x1:
            active_indices = self._get_active_indices()
            if active_indices and self.selected_cell_index in active_indices:
                pos = active_indices.index(self.selected_cell_index)
                if pos < len(active_indices) - 1:
                    self._select_cell(active_indices[pos + 1])
                    self._update_dual_stream_policy(maximized_cell_index=self.selected_cell_index)
                    self._refresh_grid_display()
            elif self.selected_cell_index < MAX_CAMERAS - 1:
                self._select_cell(self.selected_cell_index + 1)
                self._update_dual_stream_policy(maximized_cell_index=self.selected_cell_index)
                self._refresh_grid_display()
        else:
            if self.current_page < total_pages - 1:
                self.current_page += 1
                self._refresh_grid_display()

    def _select_cell(self, cell_index: int):
        for i, cell in enumerate(self.cells):
            cell.set_selected(i == cell_index)
        self.selected_cell_index = cell_index

    def _on_cell_selected(self, cell_index: int):
        self._select_cell(cell_index)

    def _on_cell_double_clicked(self, cell_index: int):
        self._select_cell(cell_index)
        if self.is_maximized_1x1:
            self.apply_layout(self.previous_layout_name)
        else:
            self.apply_layout("1x1")

    def _update_dual_stream_policy(self, maximized_cell_index: Optional[int]):
        if maximized_cell_index is not None:
            active_cam = self.cell_camera_map.get(maximized_cell_index)
            target_cam_id = active_cam.id if active_cam else None
            self.stream_manager.set_maximized_camera(target_cam_id)
            for i, cell in enumerate(self.cells):
                cell.set_stream_type(StreamType.MAIN if i == maximized_cell_index else StreamType.SUB)
                cell.set_maximized_mode(i == maximized_cell_index)
        else:
            self.stream_manager.set_all_to_substream()
            for cell in self.cells:
                cell.set_stream_type(StreamType.SUB)
                cell.set_maximized_mode(False)

    def _on_cell_quality_toggled(self, camera_id: int, target_stream_type_str: str):
        """Alterna a resolução de um canal individualmente sob demanda do operador."""
        worker = self.stream_manager.get_worker(camera_id)
        if worker:
            target = StreamType(target_stream_type_str)
            worker.request_stream_type(target)
            self.status_message_emitted.emit(f"Câmera #{camera_id}: qualidade ajustada para {target.value}")

    def swap_or_move_cells(self, src_idx: int, target_idx: int):
        """Move ou troca a posição de duas câmeras entre células da grade."""
        if src_idx == target_idx or src_idx < 0 or target_idx < 0:
            return
        cam_src = self.cell_camera_map.get(src_idx)
        cam_target = self.cell_camera_map.get(target_idx)

        if not cam_src:
            return

        if cam_target:
            self.assign_camera_to_cell(src_idx, cam_target)
            self.assign_camera_to_cell(target_idx, cam_src)
            self.status_message_emitted.emit(f"Posições trocadas: Canal {src_idx + 1} ↔ Canal {target_idx + 1}")
        else:
            self.assign_camera_to_cell(target_idx, cam_src)
            self.remove_camera_from_cell(src_idx)
            self.status_message_emitted.emit(f"Câmera movida para o Canal {target_idx + 1} (Slot {src_idx + 1} liberado)")

    def remove_camera_from_cell(self, cell_idx: int):
        """Desassocia a câmera da célula, encerra o stream e exibe a logo da empresa."""
        if cell_idx < 0 or cell_idx >= MAX_CAMERAS:
            return
        cam = self.cell_camera_map.get(cell_idx)
        if cam:
            if cam.id:
                self.stream_manager.stop_camera_stream(cam.id)
            self.cells[cell_idx].assign_camera(None)
            self.cell_camera_map[cell_idx] = None
            self._refresh_grid_display()
            self.status_message_emitted.emit(f"Canal {cell_idx + 1} liberado. Slot pronto para nova câmera.")

    def assign_camera_to_cell(self, cell_index: int, camera: Camera):
        if cell_index < 0 or cell_index >= MAX_CAMERAS:
            return

        cell = self.cells[cell_index]
        self.cell_camera_map[cell_index] = camera

        stream_type = StreamType.MAIN if self.is_maximized_1x1 and cell_index == self.selected_cell_index else StreamType.SUB
        cell.assign_camera(camera, stream_type=stream_type)
        cell.set_maximized_mode(self.is_maximized_1x1 and cell_index == self.selected_cell_index)

        def on_frame(cam_id, qimg, w, h):
            if cell.camera and cell.camera.id == cam_id:
                cell.update_frame(qimg, w, h)

        def on_status(cam_id, status, msg):
            if cell.camera and cell.camera.id == cam_id:
                cell.update_status(status, msg)

        def on_fps(cam_id, fps):
            if cell.camera and cell.camera.id == cam_id:
                cell.update_fps(fps)

        def on_recording(cam_id, is_rec, filepath):
            if cell.camera and cell.camera.id == cam_id:
                cell.set_recording(is_rec)
                action = "iniciada" if is_rec else "salva em"
                self.status_message_emitted.emit(f"Gravação {action}: {filepath}")

        self.stream_manager.start_camera_stream(
            camera=camera,
            initial_stream_type=stream_type,
            on_frame=on_frame,
            on_status=on_status,
            on_fps=on_fps,
            on_recording=on_recording,
        )
        self._refresh_grid_display()

    def _on_snapshot_requested(self, camera_id: int):
        worker = self.stream_manager.get_worker(camera_id)
        if worker:
            worker.request_snapshot()
            self.status_message_emitted.emit(f"📸 Snapshot capturado para a câmera #{camera_id}!")

    def _on_record_toggle_requested(self, camera_id: int):
        worker = self.stream_manager.get_worker(camera_id)
        if worker:
            is_now_rec = worker.toggle_recording()
            self.status_message_emitted.emit(
                f"⏺ Gravação {'iniciada' if is_now_rec else 'finalizada'} para a câmera #{camera_id}"
            )

    def _on_reconnect_requested(self, camera_id: int):
        cam = next((c for c in self.cell_camera_map.values() if c and c.id == camera_id), None)
        if cam:
            for idx, c in self.cell_camera_map.items():
                if c and c.id == camera_id:
                    self.assign_camera_to_cell(idx, cam)
                    self.status_message_emitted.emit(f"🔄 Reconexão forçada para {cam.name}")
                    break
