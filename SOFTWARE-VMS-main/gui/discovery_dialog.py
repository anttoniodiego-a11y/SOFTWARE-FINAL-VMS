"""
Janela de Descoberta Automática de Dispositivos (DiscoveryDialog).
Varre a rede local via ONVIF WS-Discovery, Hikvision SADP, Intelbras e Scanner de Subrede.
Permite adicionar câmeras e gravadores (NVR/DVR multi-canal) com um único clique.
"""

from typing import List, Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.database import DatabaseManager
from core.discovery import DiscoveredDevice, NetworkDiscoveryEngine
from core.models import Area, Brand, Camera, StreamType
from core.rtsp_profiles import RTSPProfileFactory


class DiscoveryThread(QThread):
    """Thread de varredura de rede sem travar a interface gráfica."""
    status_updated = pyqtSignal(str)
    discovery_finished = pyqtSignal(list)

    def run(self):
        self.status_updated.emit("Transmitindo pacotes ONVIF WS-Discovery e Broadcast SADP/Intelbras...")
        devices = NetworkDiscoveryEngine.discover_all(
            timeout=3.5,
            progress_callback=lambda msg: self.status_updated.emit(msg)
        )
        self.discovery_finished.emit(devices)


class DiscoveryDialog(QDialog):
    """Diálogo corporativo para localizar e importar câmeras automaticamente."""

    cameras_added = pyqtSignal(list)  # Lista de Camera adicionadas

    def __init__(self, db: DatabaseManager, parent=None):
        super().__init__(parent)
        self.db = db
        self.discovered_devices: List[DiscoveredDevice] = []
        self.discovery_thread: Optional[DiscoveryThread] = None

        self.setWindowTitle("Localizador Automático de Câmeras e NVRs (Auto-Discovery)")
        self.resize(850, 580)
        self.setModal(True)

        self._init_ui()
        self._load_areas()
        # Inicia varredura automática ao abrir a janela
        self.start_scan()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # 1. Barra de Ação Superior
        top_bar = QHBoxLayout()
        self.btn_rescan = QPushButton("🔄 Nova Varredura na Rede", self)
        self.btn_rescan.setStyleSheet("background-color: #0078d4; font-weight: bold; color: white;")
        self.btn_rescan.clicked.connect(self.start_scan)
        top_bar.addWidget(self.btn_rescan)

        self.lbl_scan_status = QLabel("Preparando varredura...", self)
        self.lbl_scan_status.setStyleSheet("color: #00e5ff; font-weight: bold;")
        top_bar.addWidget(self.lbl_scan_status, 1)

        layout.addLayout(top_bar)

        # Barra de Progresso
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 0)  # Modo indeterminado durante scan
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)

        # 2. Tabela de Dispositivos Encontrados
        self.table = QTableWidget(self)
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Selecionar", "Endereço IP", "Fabricante", "Tipo de Dispositivo", "Modelo / Identificação", "Porta RTSP"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._on_table_selection_changed)
        layout.addWidget(self.table, 1)

        # 3. Painel de Credenciais e Configuração de Importação
        group_config = QGroupBox("Credenciais e Parâmetros de Importação", self)
        form = QFormLayout(group_config)
        form.setSpacing(8)

        cred_layout = QHBoxLayout()
        self.txt_user = QLineEdit("admin", self)
        self.txt_user.setPlaceholderText("Usuário do dispositivo")
        cred_layout.addWidget(QLabel("Usuário:"))
        cred_layout.addWidget(self.txt_user)

        self.txt_pass = QLineEdit(self)
        self.txt_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_pass.setPlaceholderText("Senha do dispositivo")
        cred_layout.addWidget(QLabel("Senha:"))
        cred_layout.addWidget(self.txt_pass)
        form.addRow("Credenciais de Acesso:", cred_layout)

        # Seletor de Área
        area_layout = QHBoxLayout()
        self.combo_area = QComboBox(self)
        area_layout.addWidget(self.combo_area)

        # Quantidade de Canais (em caso de NVR/DVR)
        self.spin_channels = QSpinBox(self)
        self.spin_channels.setRange(1, 64)
        self.spin_channels.setValue(1)
        area_layout.addWidget(QLabel("Canais a importar:"))
        area_layout.addWidget(self.spin_channels)
        form.addRow("Destino e Canais:", area_layout)

        layout.addWidget(group_config)

        # 4. Status de Diagnóstico
        self.lbl_diag_result = QLabel("", self)
        self.lbl_diag_result.setWordWrap(True)
        self.lbl_diag_result.setStyleSheet("color: #a0a6b5; font-size: 11px;")
        layout.addWidget(self.lbl_diag_result)

        # 5. Botões de Ação Inferiores
        btn_box = QHBoxLayout()
        btn_box.addStretch()

        self.btn_cancel = QPushButton("Fechar", self)
        self.btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(self.btn_cancel)

        self.btn_add = QPushButton("📥 Adicionar Dispositivos Selecionados", self)
        self.btn_add.setStyleSheet("background-color: #0078d4; color: white; font-weight: bold; padding: 8px 16px;")
        self.btn_add.clicked.connect(self._import_selected_devices)
        btn_box.addWidget(self.btn_add)

        layout.addLayout(btn_box)

    def _load_areas(self):
        self.combo_area.clear()
        areas = self.db.get_all_areas()
        for a in areas:
            self.combo_area.addItem(a.name, a.id)

    def start_scan(self):
        """Inicia o processo de descoberta em thread de fundo."""
        self.btn_rescan.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.lbl_scan_status.setText("🔍 Varrendo a rede local (ONVIF, Hikvision SADP, Intelbras)...")
        self.lbl_diag_result.setText("")

        self.discovery_thread = DiscoveryThread()
        self.discovery_thread.status_updated.connect(self.lbl_scan_status.setText)
        self.discovery_thread.discovery_finished.connect(self._on_discovery_finished)
        self.discovery_thread.start()

    def _on_discovery_finished(self, devices: List[DiscoveredDevice]):
        self.btn_rescan.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.discovered_devices = devices

        count = len(devices)
        if count == 0:
            self.lbl_scan_status.setText("⚠️ Nenhum dispositivo detectado automaticamente na subrede.")
            self.lbl_diag_result.setText(
                "Dica: Certifique-se de que o computador está conectado no mesmo roteador/switch das câmeras "
                "e que o Firewall do Windows não está bloqueando conexões de rede privada."
            )
        else:
            self.lbl_scan_status.setText(f"✅ {count} dispositivo(s) CFTV localizado(s) na rede!")

        self._populate_table()

    def _populate_table(self):
        self.table.setRowCount(0)
        for i, dev in enumerate(self.discovered_devices):
            self.table.insertRow(i)

            # Checkbox de seleção
            chk_item = QTableWidgetItem()
            chk_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk_item.setCheckState(Qt.CheckState.Checked)  # Marca por padrão
            self.table.setItem(i, 0, chk_item)

            # Endereço IP
            ip_item = QTableWidgetItem(dev.ip)
            ip_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.table.setItem(i, 1, ip_item)

            # Fabricante
            brand_item = QTableWidgetItem(dev.brand.value)
            brand_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.table.setItem(i, 2, brand_item)

            # Tipo
            type_item = QTableWidgetItem(dev.device_type)
            type_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.table.setItem(i, 3, type_item)

            # Modelo
            model_item = QTableWidgetItem(dev.model)
            model_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.table.setItem(i, 4, model_item)

            # Porta RTSP
            port_item = QTableWidgetItem(str(dev.port))
            port_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.table.setItem(i, 5, port_item)

    def _on_table_selection_changed(self):
        """Ao clicar em uma linha, ajusta o número de canais sugeridos se for NVR."""
        selected_rows = self.table.selectionModel().selectedRows()
        if selected_rows:
            row = selected_rows[0].row()
            if row < len(self.discovered_devices):
                dev = self.discovered_devices[row]
                self.spin_channels.setValue(dev.suggested_channels)

    def _import_selected_devices(self):
        """Importa os dispositivos selecionados para o banco de dados SQLite."""
        user = self.txt_user.text().strip()
        pwd = self.txt_pass.text().strip()
        area_id = self.combo_area.currentData()

        added_cameras = []
        total_created = 0

        for row in range(self.table.rowCount()):
            chk_item = self.table.item(row, 0)
            if chk_item and chk_item.checkState() == Qt.CheckState.Checked:
                dev = self.discovered_devices[row]
                channels_to_import = self.spin_channels.value() if dev.device_type == "Gravador NVR/DVR" else 1

                for ch in range(1, channels_to_import + 1):
                    cam_name = (
                        f"{dev.model} - Ch {ch:02d}"
                        if dev.device_type == "Gravador NVR/DVR"
                        else f"{dev.brand.value} ({dev.ip})"
                    )

                    camera = Camera(
                        id=None,
                        name=cam_name,
                        ip=dev.ip,
                        port=dev.port,
                        username=user,
                        password=pwd,
                        channel=ch,
                        brand=dev.brand,
                        area_id=area_id,
                        is_active=True
                    )

                    new_id = self.db.add_camera(camera)
                    camera.id = new_id
                    added_cameras.append(camera)
                    total_created += 1

        if total_created > 0:
            QMessageBox.information(
                self,
                "Importação Concluída",
                f"{total_created} canal(is) importado(s) com sucesso!\n"
                "As câmeras agora aparecem na árvore lateral e foram carregadas na grade de vídeo."
            )
            self.cameras_added.emit(added_cameras)
            self.accept()
        else:
            QMessageBox.warning(self, "Aviso", "Nenhum dispositivo selecionado para importação.")
