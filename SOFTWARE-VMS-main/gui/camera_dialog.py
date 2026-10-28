"""
Diálogo de Cadastro e Edição de Câmeras (CameraDialog).
Permite configurar credenciais, portas, canais e marcas (Hikvision, HiLook, Intelbras, Dahua).
Exibe em tempo real o preview da URL RTSP calculada e inclui teste de diagnóstico aprofundado.
"""

from typing import List, Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from core.database import DatabaseManager
from core.models import Area, Brand, Camera, StreamType
from core.rtsp_profiles import RTSPProfileFactory


class ProbeRTSPThread(QThread):
    """Thread auxiliar para diagnosticar a conexão com múltiplos fallbacks de rota."""
    probe_finished = pyqtSignal(bool, str, str, str)  # success, working_main, working_sub, message

    def __init__(self, camera: Camera):
        super().__init__()
        self.camera = camera

    def run(self):
        success, main_url, sub_url, message = RTSPProfileFactory.probe_and_diagnose(self.camera)
        self.probe_finished.emit(success, main_url or "", sub_url or "", message)


class CameraDialog(QDialog):
    """Formulário modal para criação ou edição de câmeras com diagnóstico de rede."""

    def __init__(self, db: DatabaseManager, camera: Optional[Camera] = None, parent=None):
        super().__init__(parent)
        self.db = db
        self.camera = camera
        self.probe_thread: Optional[ProbeRTSPThread] = None
        self._working_main_url: Optional[str] = None
        self._working_sub_url: Optional[str] = None

        self.setWindowTitle("Configuração de Câmera IP / Canal" if camera else "Adicionar Nova Câmera IP")
        self.setMinimumWidth(540)
        self.setModal(True)

        self._init_ui()
        self._load_areas()

        if self.camera:
            self._fill_data(self.camera)
        else:
            self._update_preview()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)

        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form_layout.setSpacing(8)

        # Nome da Câmera
        self.txt_name = QLineEdit(self)
        self.txt_name.setPlaceholderText("Ex: CAM 01 - Portaria")
        self.txt_name.textChanged.connect(self._update_preview)
        form_layout.addRow("Nome da Câmera:", self.txt_name)

        # Marca / Fabricante
        self.combo_brand = QComboBox(self)
        for brand in Brand:
            self.combo_brand.addItem(brand.value, brand)
        self.combo_brand.currentIndexChanged.connect(self._on_brand_changed)
        form_layout.addRow("Marca / Protocolo:", self.combo_brand)

        # Dica da Marca
        self.lbl_brand_tip = QLabel(self)
        self.lbl_brand_tip.setWordWrap(True)
        self.lbl_brand_tip.setStyleSheet("color: #a0a6b5; font-size: 11px; margin-bottom: 4px;")
        form_layout.addRow("", self.lbl_brand_tip)

        # Área / Local Físico (Grupo)
        area_layout = QHBoxLayout()
        self.combo_area = QComboBox(self)
        self.btn_new_area = QPushButton("➕ Novo Grupo", self)
        self.btn_new_area.setToolTip("Criar um novo grupo de câmeras")
        self.btn_new_area.clicked.connect(self._create_new_area)
        area_layout.addWidget(self.combo_area, 1)
        area_layout.addWidget(self.btn_new_area)
        form_layout.addRow("Grupo / Área:", area_layout)

        # Endereço IP
        self.txt_ip = QLineEdit("192.168.1.100", self)
        self.txt_ip.setPlaceholderText("Ex: 192.168.1.64")
        self.txt_ip.textChanged.connect(self._update_preview)
        form_layout.addRow("Endereço IP:", self.txt_ip)

        # Porta RTSP
        self.spin_port = QSpinBox(self)
        self.spin_port.setRange(1, 65535)
        self.spin_port.setValue(554)
        self.spin_port.valueChanged.connect(self._update_preview)
        form_layout.addRow("Porta RTSP:", self.spin_port)

        # Canal do Dispositivo
        self.spin_channel = QSpinBox(self)
        self.spin_channel.setRange(1, 64)
        self.spin_channel.setValue(1)
        self.spin_channel.valueChanged.connect(self._update_preview)
        form_layout.addRow("Canal (NVR/DVR):", self.spin_channel)

        # Usuário
        self.txt_user = QLineEdit("admin", self)
        self.txt_user.textChanged.connect(self._update_preview)
        form_layout.addRow("Usuário:", self.txt_user)

        # Senha
        self.txt_pass = QLineEdit(self)
        self.txt_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_pass.setPlaceholderText("Senha do dispositivo")
        self.txt_pass.textChanged.connect(self._update_preview)
        form_layout.addRow("Senha:", self.txt_pass)

        main_layout.addLayout(form_layout)

        # Opção de URLs Customizadas
        self.chk_custom_urls = QCheckBox("Personalizar URLs RTSP manualmente (Avançado)", self)
        self.chk_custom_urls.toggled.connect(self._on_custom_urls_toggled)
        main_layout.addWidget(self.chk_custom_urls)

        self.widget_custom = QVBoxLayout()
        self.txt_custom_main = QLineEdit(self)
        self.txt_custom_main.setPlaceholderText("URL RTSP Stream Principal (Customizada)")
        self.txt_custom_sub = QLineEdit(self)
        self.txt_custom_sub.setPlaceholderText("URL RTSP Substream (Customizada)")
        self.widget_custom.addWidget(self.txt_custom_main)
        self.widget_custom.addWidget(self.txt_custom_sub)
        self.txt_custom_main.setVisible(False)
        self.txt_custom_sub.setVisible(False)
        main_layout.addLayout(self.widget_custom)

        # Pré-visualização das URLs calculadas
        preview_group = QVBoxLayout()
        self.lbl_preview_title = QLabel("🔗 URLs RTSP Calculadas (Engenharia Reversa):")
        self.lbl_preview_title.setStyleSheet("font-weight: bold; color: #0084ff; margin-top: 6px;")
        preview_group.addWidget(self.lbl_preview_title)

        self.lbl_preview_main = QLabel()
        self.lbl_preview_main.setWordWrap(True)
        self.lbl_preview_main.setStyleSheet("font-family: monospace; font-size: 11px; color: #ffd600;")
        preview_group.addWidget(self.lbl_preview_main)

        self.lbl_preview_sub = QLabel()
        self.lbl_preview_sub.setWordWrap(True)
        self.lbl_preview_sub.setStyleSheet("font-family: monospace; font-size: 11px; color: #00e5ff;")
        preview_group.addWidget(self.lbl_preview_sub)

        main_layout.addLayout(preview_group)

        # Botão de Teste de Conexão com Diagnóstico
        self.btn_test_conn = QPushButton("⚡ Testar e Diagnosticar Conexão", self)
        self.btn_test_conn.clicked.connect(self._test_connection)
        main_layout.addWidget(self.btn_test_conn)

        self.lbl_test_result = QLabel("")
        self.lbl_test_result.setWordWrap(True)
        self.lbl_test_result.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.lbl_test_result)

        # Botões de Ação
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Cancelar", self)
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_save = QPushButton("Salvar Câmera", self)
        self.btn_save.setStyleSheet("background-color: #0078d4; color: white; font-weight: bold;")
        self.btn_save.clicked.connect(self._save_camera)
        btn_layout.addWidget(self.btn_save)

        main_layout.addLayout(btn_layout)

    def _on_brand_changed(self):
        brand = self.combo_brand.currentData()
        if brand == Brand.HOLOWITS:
            self.lbl_brand_tip.setText("💡 Holowits: certifique-se de ativar o protocolo ONVIF/RTSP na interface web da câmera (Rede -> Plataforma de Acesso).")
        elif brand == Brand.POSITIVO:
            self.lbl_brand_tip.setText("💡 Positivo: no app Positivo Casa Inteligente, ative 'PC View / ONVIF' e defina a senha local para permitir o streaming.")
        elif brand == Brand.UNIVIEW:
            self.lbl_brand_tip.setText("💡 Uniview (UNV): certifique-se de que a porta RTSP padrão é a 554 e a autenticação está como Digest/Basic.")
        else:
            self.lbl_brand_tip.setText("")
        self._update_preview()

    def _create_new_area(self):
        name, ok = QInputDialog.getText(self, "Novo Grupo", "Nome do novo grupo de câmeras:")
        if ok and name.strip():
            new_id = self.db.add_area(name.strip())
            self._load_areas()
            idx = self.combo_area.findData(new_id)
            if idx >= 0:
                self.combo_area.setCurrentIndex(idx)

    def _load_areas(self):
        self.combo_area.clear()
        self.combo_area.addItem("Nenhum (Sem Grupo)", None)
        areas = self.db.get_all_areas()
        for area in areas:
            self.combo_area.addItem(area.name, area.id)

    def _on_custom_urls_toggled(self, checked: bool):
        self.txt_custom_main.setVisible(checked)
        self.txt_custom_sub.setVisible(checked)

    def _get_temp_camera(self) -> Camera:
        brand = self.combo_brand.currentData() or Brand.HIKVISION
        area_id = self.combo_area.currentData()
        name = self.txt_name.text().strip() or f"CAM {self.spin_channel.value()}"

        custom_main = (
            self.txt_custom_main.text().strip()
            if self.chk_custom_urls.isChecked()
            else self._working_main_url
        )
        custom_sub = (
            self.txt_custom_sub.text().strip()
            if self.chk_custom_urls.isChecked()
            else self._working_sub_url
        )

        return Camera(
            id=self.camera.id if self.camera else None,
            name=name,
            ip=self.txt_ip.text().strip(),
            port=self.spin_port.value(),
            username=self.txt_user.text().strip(),
            password=self.txt_pass.text().strip(),
            channel=self.spin_channel.value(),
            brand=brand,
            area_id=area_id,
            is_active=True,
            custom_main_url=custom_main,
            custom_sub_url=custom_sub
        )

    def _update_preview(self):
        temp_cam = self._get_temp_camera()
        main_url = temp_cam.get_main_stream_url()
        sub_url = temp_cam.get_sub_stream_url()

        masked_main = RTSPProfileFactory.mask_credentials(main_url)
        masked_sub = RTSPProfileFactory.mask_credentials(sub_url)

        self.lbl_preview_main.setText(f"Main (1080p): {masked_main}")
        self.lbl_preview_sub.setText(f"Sub (D1/360p): {masked_sub}")

    def _test_connection(self):
        temp_cam = self._get_temp_camera()
        self.btn_test_conn.setEnabled(False)
        self.lbl_test_result.setText("⏳ Testando rotas candidatas e checando porta RTSP...")
        self.lbl_test_result.setStyleSheet("color: #ffab00;")

        self.probe_thread = ProbeRTSPThread(temp_cam)
        self.probe_thread.probe_finished.connect(self._on_probe_finished)
        self.probe_thread.start()

    def _on_probe_finished(self, success: bool, working_main: str, working_sub: str, message: str):
        self.btn_test_conn.setEnabled(True)
        if success:
            self._working_main_url = working_main
            self._working_sub_url = working_sub
            self.lbl_test_result.setText(f"✅ {message}")
            self.lbl_test_result.setStyleSheet("color: #00e676; font-weight: bold;")
        else:
            self.lbl_test_result.setText(f"❌ {message}")
            self.lbl_test_result.setStyleSheet("color: #ff5252;")

    def _fill_data(self, camera: Camera):
        self.txt_name.setText(camera.name)
        idx = self.combo_brand.findData(camera.brand)
        if idx >= 0:
            self.combo_brand.setCurrentIndex(idx)
        if camera.area_id:
            a_idx = self.combo_area.findData(camera.area_id)
            if a_idx >= 0:
                self.combo_area.setCurrentIndex(a_idx)
        self.txt_ip.setText(camera.ip)
        self.spin_port.setValue(camera.port)
        self.spin_channel.setValue(camera.channel)
        self.txt_user.setText(camera.username)
        self.txt_pass.setText(camera.password)

        if camera.custom_main_url or camera.custom_sub_url:
            self.chk_custom_urls.setChecked(True)
            self.txt_custom_main.setText(camera.custom_main_url or "")
            self.txt_custom_sub.setText(camera.custom_sub_url or "")

        self._update_preview()

    def _save_camera(self):
        if not self.txt_ip.text().strip():
            QMessageBox.warning(self, "Aviso", "O endereço IP é obrigatório!")
            return

        cam = self._get_temp_camera()
        if self.camera and self.camera.id:
            self.db.update_camera(cam)
        else:
            self.db.add_camera(cam)

        self.accept()
