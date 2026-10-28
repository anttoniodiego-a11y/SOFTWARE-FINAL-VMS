"""
Árvore Lateral de Dispositivos e Áreas (CameraTree).
Layout hierárquico corporativo com organização completa de grupos (adicionar, editar, remover, mover câmeras),
busca em tempo real, suporte a Drag-and-Drop, Auto-Discovery e badge da marca com fundo de alto contraste.
"""

from typing import Dict, List, Optional

from PyQt6.QtCore import QByteArray, QMimeData, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QDrag, QFont, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.config import LOGO_PATH
from core.database import DatabaseManager
from core.models import Area, Camera


class GroupManagerDialog(QDialog):
    """Diálogo corporativo para visualização, criação, edição e exclusão de grupos/áreas."""

    def __init__(self, db: DatabaseManager, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Gerenciador de Grupos de Câmeras")
        self.resize(460, 400)
        self.setModal(True)
        self._init_ui()
        self.reload_groups()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        header = QLabel("Grupos e Setores de Monitoramento")
        header.setStyleSheet("font-weight: bold; font-size: 14px; color: #f5b800;")
        layout.addWidget(header)

        self.list_groups = QListWidget(self)
        self.list_groups.setStyleSheet("background-color: #121317; border: 1px solid #20222a; padding: 4px;")
        layout.addWidget(self.list_groups, 1)

        btn_layout = QHBoxLayout()
        self.btn_add = QPushButton("➕ Criar Grupo", self)
        self.btn_add.setStyleSheet("background-color: #f5b800; color: #0b0c0e; font-weight: bold;")
        self.btn_add.clicked.connect(self._add_group)
        btn_layout.addWidget(self.btn_add)

        self.btn_edit = QPushButton("✏ Renomear", self)
        self.btn_edit.clicked.connect(self._edit_group)
        btn_layout.addWidget(self.btn_edit)

        self.btn_del = QPushButton("🗑 Excluir", self)
        self.btn_del.clicked.connect(self._delete_group)
        btn_layout.addWidget(self.btn_del)

        layout.addLayout(btn_layout)

        close_layout = QHBoxLayout()
        close_layout.addStretch()
        self.btn_close = QPushButton("Concluir", self)
        self.btn_close.clicked.connect(self.accept)
        close_layout.addWidget(self.btn_close)
        layout.addLayout(close_layout)

    def reload_groups(self):
        self.list_groups.clear()
        areas = self.db.get_all_areas()
        all_cams = self.db.get_all_cameras()

        for a in areas:
            cam_count = sum(1 for c in all_cams if c.area_id == a.id)
            desc_text = f" - {a.description}" if a.description else ""
            item = QListWidgetItem(f"📁 {a.name} ({cam_count} câmeras){desc_text}")
            item.setData(Qt.ItemDataRole.UserRole, a.id)
            self.list_groups.addItem(item)

    def _add_group(self):
        name, ok = QInputDialog.getText(self, "Novo Grupo", "Digite o nome do novo grupo/área:")
        if ok and name.strip():
            self.db.add_area(name.strip())
            self.reload_groups()

    def _edit_group(self):
        item = self.list_groups.currentItem()
        if not item:
            QMessageBox.information(self, "Aviso", "Selecione um grupo para editar.")
            return
        area_id = item.data(Qt.ItemDataRole.UserRole)
        area = self.db.get_area_by_id(area_id)
        if not area:
            return

        new_name, ok = QInputDialog.getText(self, "Editar Grupo", "Novo nome do grupo:", text=area.name)
        if ok and new_name.strip():
            self.db.update_area(area_id, new_name.strip(), area.description)
            self.reload_groups()

    def _delete_group(self):
        item = self.list_groups.currentItem()
        if not item:
            QMessageBox.information(self, "Aviso", "Selecione um grupo para excluir.")
            return
        area_id = item.data(Qt.ItemDataRole.UserRole)
        area = self.db.get_area_by_id(area_id)
        if not area:
            return

        reply = QMessageBox.question(
            self,
            "Confirmar Exclusão de Grupo",
            f"Deseja remover o grupo '{area.name}'?\n\n(As câmeras vinculadas não serão apagadas, apenas movidas para 'Sem Grupo').",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.db.delete_area(area_id)
            self.reload_groups()


class DraggableCameraTreeWidget(QTreeWidget):
    """QTreeWidget customizado com suporte a Drag-and-Drop entre grupos e para a grade."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

    def startDrag(self, supportedActions):
        item = self.currentItem()
        if not item:
            return

        cam_id = item.data(0, Qt.ItemDataRole.UserRole)
        if cam_id is None:
            return

        mime_data = QMimeData()
        mime_data.setData("application/x-vms-camera-id", QByteArray(str(cam_id).encode()))

        drag = QDrag(self)
        drag.setMimeData(mime_data)
        drag.exec(Qt.DropAction.CopyAction)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-vms-camera-id"):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat("application/x-vms-camera-id"):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasFormat("application/x-vms-camera-id"):
            target_item = self.itemAt(event.position().toPoint())
            if target_item:
                target_area_id = target_item.data(0, Qt.ItemDataRole.UserRole + 1)
                # Se soltou sobre uma câmera, pega a área do pai
                if target_area_id is None and target_item.parent():
                    target_area_id = target_item.parent().data(0, Qt.ItemDataRole.UserRole + 1)

                if target_area_id is not None:
                    cam_id = int(event.mimeData().data("application/x-vms-camera-id").data().decode())
                    parent_tree = self.parent()
                    if isinstance(parent_tree, CameraTree):
                        actual_area_id = None if target_area_id == -1 else target_area_id
                        parent_tree.move_camera_to_group(cam_id, actual_area_id)
                    event.acceptProposedAction()
                    return
        super().dropEvent(event)


class CameraTree(QWidget):
    """
    Barra lateral esquerda do VMS (Dispositivos Locais).
    Permite busca rápida, organização total por grupos e atribuição à grade.
    """

    camera_selected_for_cell = pyqtSignal(object)  # Camera
    edit_camera_requested = pyqtSignal(int)        # camera_id
    delete_camera_requested = pyqtSignal(int)      # camera_id
    add_camera_requested = pyqtSignal()
    auto_discovery_requested = pyqtSignal()
    group_changed = pyqtSignal()

    def __init__(self, db: DatabaseManager, parent=None):
        super().__init__(parent)
        self.db = db
        self.cameras: List[Camera] = []
        self.areas: List[Area] = []

        self._init_ui()
        self.reload_data()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # 1. Badge da Marca (Identidade Preto e Amarelo)
        self.logo_card = QWidget(self)
        self.logo_card.setObjectName("logoCard")
        self.logo_card.setStyleSheet("""
            QWidget#logoCard {
                background-color: #121317;
                border: 1px solid #20222a;
                border-radius: 4px;
                padding: 4px 6px;
            }
        """)
        logo_layout = QHBoxLayout(self.logo_card)
        logo_layout.setContentsMargins(6, 4, 6, 4)
        logo_layout.setSpacing(8)

        self.lbl_logo_img = QLabel()
        if LOGO_PATH.exists():
            pix = QPixmap(str(LOGO_PATH))
            if not pix.isNull():
                self.lbl_logo_img.setPixmap(pix.scaledToHeight(26, Qt.TransformationMode.SmoothTransformation))
                logo_layout.addWidget(self.lbl_logo_img)

        self.lbl_logo_text = QLabel("DISPOSITIVOS LOCAIS")
        self.lbl_logo_text.setStyleSheet("font-weight: 900; font-size: 12px; color: #f5b800;")
        logo_layout.addWidget(self.lbl_logo_text)
        logo_layout.addStretch()

        layout.addWidget(self.logo_card)

        # 2. Botão de Destaque: Auto-Discovery
        self.btn_discovery = QPushButton("🔍 Auto-Discovery (Buscar na Rede)", self)
        self.btn_discovery.setStyleSheet("""
            QPushButton {
                background-color: #f5b800;
                color: #0b0c0e;
                font-weight: bold;
                padding: 7px;
                border: 1px solid #f5b800;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #ffd000;
            }
        """)
        self.btn_discovery.clicked.connect(self.auto_discovery_requested.emit)
        layout.addWidget(self.btn_discovery)

        # 3. Barra de Busca Rápida
        self.txt_search = QLineEdit(self)
        self.txt_search.setPlaceholderText("Filtrar câmeras, grupos ou IPs...")
        self.txt_search.textChanged.connect(self._filter_tree)
        layout.addWidget(self.txt_search)

        # 4. Barra de Gerenciamento de Grupos
        group_bar = QHBoxLayout()
        group_bar.setSpacing(4)

        self.btn_add_group = QPushButton("📁 + Novo Grupo", self)
        self.btn_add_group.setToolTip("Criar um novo grupo para organizar suas câmeras")
        self.btn_add_group.clicked.connect(self._create_new_group)
        group_bar.addWidget(self.btn_add_group)

        self.btn_manage_groups = QPushButton("⚙️ Grupos", self)
        self.btn_manage_groups.setToolTip("Gerenciar, renomear ou remover grupos existentes")
        self.btn_manage_groups.clicked.connect(self._open_group_manager)
        group_bar.addWidget(self.btn_manage_groups)

        layout.addLayout(group_bar)

        # 5. Árvore de Dispositivos Hierárquica
        self.tree = DraggableCameraTreeWidget(self)
        self.tree.setHeaderLabels(["Dispositivos & Grupos", "IP / Marca"])
        self.tree.setColumnWidth(0, 180)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.tree, 1)

        # 6. Botão Inferior de Adição Manual
        btn_layout = QHBoxLayout()
        self.btn_add_cam = QPushButton("➕ Adicionar Câmera Manual", self)
        self.btn_add_cam.clicked.connect(self.add_camera_requested.emit)
        btn_layout.addWidget(self.btn_add_cam)

        layout.addLayout(btn_layout)

    def reload_data(self):
        """Recarrega todas as áreas e câmeras do SQLite e remonta a árvore."""
        self.tree.clear()
        self.areas = self.db.get_all_areas()
        self.cameras = self.db.get_all_cameras()

        area_nodes: Dict[int, QTreeWidgetItem] = {}

        # Mapeia câmeras por área
        cams_by_area: Dict[Optional[int], List[Camera]] = {}
        for cam in self.cameras:
            cams_by_area.setdefault(cam.area_id, []).append(cam)

        for area in self.areas:
            count = len(cams_by_area.get(area.id, []))
            node = QTreeWidgetItem(self.tree)
            node.setText(0, f"📁 {area.name} ({count})")
            node.setText(1, area.description)
            node.setFont(0, QFont("Segoe UI", 9, QFont.Weight.Bold))
            node.setData(0, Qt.ItemDataRole.UserRole, None)
            node.setData(0, Qt.ItemDataRole.UserRole + 1, area.id)  # ID do grupo
            if area.id is not None:
                area_nodes[area.id] = node

        # Câmeras sem grupo definido
        unassigned_cams = cams_by_area.get(None, [])
        unassigned_node = None
        if unassigned_cams or not self.areas:
            unassigned_node = QTreeWidgetItem(self.tree)
            unassigned_node.setText(0, f"📁 Câmeras Sem Grupo ({len(unassigned_cams)})")
            unassigned_node.setText(1, "Sem área vinculada")
            unassigned_node.setFont(0, QFont("Segoe UI", 9, QFont.Weight.Bold))
            unassigned_node.setData(0, Qt.ItemDataRole.UserRole, None)
            unassigned_node.setData(0, Qt.ItemDataRole.UserRole + 1, -1)  # Representa sem grupo

        for cam in self.cameras:
            if cam.area_id and cam.area_id in area_nodes:
                parent_node = area_nodes[cam.area_id]
            else:
                if unassigned_node is None:
                    unassigned_node = QTreeWidgetItem(self.tree)
                    unassigned_node.setText(0, "📁 Câmeras Sem Grupo")
                    unassigned_node.setData(0, Qt.ItemDataRole.UserRole, None)
                    unassigned_node.setData(0, Qt.ItemDataRole.UserRole + 1, -1)
                parent_node = unassigned_node

            cam_item = QTreeWidgetItem(parent_node)
            cam_item.setText(0, f"📹 {cam.name}")
            cam_item.setText(1, f"{cam.ip} ({cam.brand.value})")
            cam_item.setData(0, Qt.ItemDataRole.UserRole, cam.id)
            cam_item.setData(0, Qt.ItemDataRole.UserRole + 1, None)
            cam_item.setToolTip(0, f"Marca: {cam.brand.value}\nCanal: {cam.channel}\nRTSP Port: {cam.port}")

        self.tree.expandAll()

    def _create_new_group(self):
        name, ok = QInputDialog.getText(self, "Novo Grupo", "Nome do novo grupo/área:")
        if ok and name.strip():
            self.db.add_area(name.strip())
            self.reload_data()
            self.group_changed.emit()

    def _open_group_manager(self):
        dialog = GroupManagerDialog(self.db, parent=self)
        dialog.exec()
        self.reload_data()
        self.group_changed.emit()

    def move_camera_to_group(self, camera_id: int, area_id: Optional[int]):
        """Move uma câmera para o grupo informado e atualiza a interface."""
        self.db.move_camera_to_area(camera_id, area_id)
        self.reload_data()
        self.group_changed.emit()

    def _filter_tree(self, text: str):
        query = text.lower().strip()
        for i in range(self.tree.topLevelItemCount()):
            area_item = self.tree.topLevelItem(i)
            area_visible = False
            for j in range(area_item.childCount()):
                cam_item = area_item.child(j)
                name_match = query in cam_item.text(0).lower()
                ip_match = query in cam_item.text(1).lower()
                is_match = name_match or ip_match or not query
                cam_item.setHidden(not is_match)
                if is_match:
                    area_visible = True
            area_item.setHidden(not area_visible and bool(query))

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        cam_id = item.data(0, Qt.ItemDataRole.UserRole)
        if cam_id is not None:
            cam = next((c for c in self.cameras if c.id == cam_id), None)
            if cam:
                self.camera_selected_for_cell.emit(cam)

    def _show_context_menu(self, position):
        item = self.tree.itemAt(position)
        if not item:
            # Clique com botão direito no espaço vazio da árvore
            menu = QMenu(self)
            action_new_group = menu.addAction("📁 Criar Novo Grupo")
            action_add_cam = menu.addAction("➕ Adicionar Câmera Manual")
            chosen = menu.exec(self.tree.viewport().mapToGlobal(position))
            if chosen == action_new_group:
                self._create_new_group()
            elif chosen == action_add_cam:
                self.add_camera_requested.emit()
            return

        cam_id = item.data(0, Qt.ItemDataRole.UserRole)
        area_id = item.data(0, Qt.ItemDataRole.UserRole + 1)

        menu = QMenu(self)

        # Contexto de Câmera
        if cam_id is not None:
            action_play = menu.addAction("▶ Exibir na Célula Ativa")
            menu.addSeparator()

            # Submenu Mover para Grupo
            move_menu = menu.addMenu("📁 Mover para Grupo")
            areas = self.db.get_all_areas()
            for a in areas:
                action_area = move_menu.addAction(f"📁 {a.name}")
                action_area.triggered.connect(lambda ch, cid=cam_id, aid=a.id: self.move_camera_to_group(cid, aid))

            action_unassigned = move_menu.addAction("🚫 Sem Grupo (Gerais)")
            action_unassigned.triggered.connect(lambda ch, cid=cam_id: self.move_camera_to_group(cid, None))

            action_new_grp = move_menu.addAction("➕ Novo Grupo...")
            action_new_grp.triggered.connect(lambda ch, cid=cam_id: self._create_group_and_move(cid))

            menu.addSeparator()
            action_edit = menu.addAction("✏ Editar Configurações")
            action_delete = menu.addAction("🗑 Excluir Câmera")

            action = menu.exec(self.tree.viewport().mapToGlobal(position))
            cam = next((c for c in self.cameras if c.id == cam_id), None)

            if action == action_play and cam:
                self.camera_selected_for_cell.emit(cam)
            elif action == action_edit:
                QTimer.singleShot(0, lambda cid=cam_id: self.edit_camera_requested.emit(cid))
            elif action == action_delete:
                QTimer.singleShot(0, lambda cid=cam_id: self.delete_camera_requested.emit(cid))

        # Contexto de Grupo / Área
        elif area_id is not None and area_id != -1:
            area = self.db.get_area_by_id(area_id)
            area_name = area.name if area else "Grupo"

            action_add_here = menu.addAction(f"➕ Adicionar Câmera em '{area_name}'")
            action_rename = menu.addAction(f"✏ Renomear Grupo '{area_name}'")
            action_del_grp = menu.addAction(f"🗑 Excluir Grupo '{area_name}'")

            action = menu.exec(self.tree.viewport().mapToGlobal(position))
            if action == action_add_here:
                self.add_camera_requested.emit()
            elif action == action_rename:
                new_name, ok = QInputDialog.getText(self, "Renomear Grupo", "Novo nome:", text=area_name)
                if ok and new_name.strip():
                    self.db.update_area(area_id, new_name.strip(), area.description if area else "")
                    self.reload_data()
                    self.group_changed.emit()
            elif action == action_del_grp:
                reply = QMessageBox.question(
                    self,
                    "Confirmar Exclusão",
                    f"Deseja excluir o grupo '{area_name}'? As câmeras vinculadas permanecerão salvas sem grupo.",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self.db.delete_area(area_id)
                    self.reload_data()
                    self.group_changed.emit()

    def _create_group_and_move(self, camera_id: int):
        name, ok = QInputDialog.getText(self, "Novo Grupo", "Nome do novo grupo:")
        if ok and name.strip():
            new_id = self.db.add_area(name.strip())
            self.move_camera_to_group(camera_id, new_id)
