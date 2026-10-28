"""
Motor de Streaming de Baixa Latência (Worker Thread).
Implementa captura de RTSP assíncrona, reconexão automática resiliente com fallbacks,
Zero-Lag (descarte de buffer acumulado), Hot-Swap Dual Stream (Main/Sub),
gravação manual e captura de snapshot com pré-validação por sonda RTSP rápida.
"""

import datetime
import os
import time
from typing import Optional

import cv2
import numpy as np
from PyQt6.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtGui import QImage

from core.config import (
    DEFAULT_MAIN_FPS_LIMIT,
    DEFAULT_RECONNECT_DELAY,
    DEFAULT_SUB_FPS_LIMIT,
    MAX_RECONNECT_DELAY,
    RECORDINGS_DIR,
    SNAPSHOTS_DIR,
)
from core.models import Camera, CameraStatus, StreamType
from core.rtsp_probe import RTSPProbe
from core.rtsp_profiles import RTSPProfileFactory


class StreamWorker(QThread):
    """
    Thread dedicada para a captura de vídeo de uma câmera específica.
    Garante que operações pesadas de decodificação I/O de rede não travem a GUI.
    """

    frame_ready = pyqtSignal(int, QImage, int, int)      # camera_id, qimage, width, height
    status_changed = pyqtSignal(int, str, str)           # camera_id, status_enum, message
    fps_updated = pyqtSignal(int, float)                 # camera_id, fps_medido
    recording_status = pyqtSignal(int, bool, str)        # camera_id, is_recording, file_path

    def __init__(self, camera: Camera, initial_stream_type: StreamType = StreamType.SUB):
        super().__init__()
        self.camera = camera
        self.stream_type = initial_stream_type

        # Controle de ciclo de vida
        self._is_running = True
        self._target_stream_type = initial_stream_type
        self._switch_stream_requested = False

        # Controle de Gravação Manual
        self._is_recording = False
        self._video_writer: Optional[cv2.VideoWriter] = None
        self._current_recording_path: Optional[str] = None

        # Controle de Snapshot
        self._snapshot_requested = False
        self._last_raw_frame: Optional[np.ndarray] = None

        # Estatísticas
        self._measured_fps = 0.0
        self._frame_count = 0
        self._last_fps_calc_time = time.time()

    def request_stream_type(self, stream_type: StreamType):
        """Solicita hot-swap de stream (Main <-> Sub) em tempo de execução."""
        if self._target_stream_type != stream_type:
            self._target_stream_type = stream_type
            self._switch_stream_requested = True

    def request_snapshot(self):
        """Solicita salvamento do quadro atual em disco."""
        self._snapshot_requested = True

    def toggle_recording(self) -> bool:
        """Inicia ou finaliza a gravação manual."""
        self._is_recording = not self._is_recording
        return self._is_recording

    def stop(self):
        """Sinaliza encerramento da thread com segurança sem travar a interface."""
        self._is_running = False
        self._is_recording = False
        self._close_writer()
        self.quit()

    def _close_writer(self):
        """Finaliza e salva o arquivo de vídeo MP4."""
        if self._video_writer is not None:
            try:
                self._video_writer.release()
            except Exception:
                pass
            self._video_writer = None
            if self._current_recording_path:
                self.recording_status.emit(self.camera.id or 0, False, self._current_recording_path)
                self._current_recording_path = None

    def _get_active_url(self) -> str:
        """Retorna a URL correspondente ao tipo de stream atual."""
        if self.stream_type == StreamType.MAIN:
            return self.camera.get_main_stream_url()
        return self.camera.get_sub_stream_url()

    def run(self):
        """Loop principal com pré-diagnóstico rápido de socket antes de invocar OpenCV."""
        reconnect_delay = DEFAULT_RECONNECT_DELAY

        while self._is_running:
            self.stream_type = self._target_stream_type
            self._switch_stream_requested = False

            # 1. Pré-checagem de porta em 0.5s para evitar que o OpenCV fique congelado por 30s
            self.status_changed.emit(
                self.camera.id or 0,
                CameraStatus.CONNECTING.value,
                f"Verificando {self.camera.ip}:{self.camera.port}..."
            )

            if not RTSPProbe.test_port(self.camera.ip, self.camera.port, timeout=0.8):
                self.status_changed.emit(
                    self.camera.id or 0,
                    CameraStatus.ERROR.value,
                    f"Porta {self.camera.port} inacessível em {self.camera.ip}"
                )
                self._wait_reconnect(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 1.5, MAX_RECONNECT_DELAY)
                continue

            # 2. Gera candidatos de rota
            primary_url = self._get_active_url()
            candidates = [primary_url]
            for cand in RTSPProfileFactory.get_candidate_urls(self.camera, self.stream_type):
                if cand not in candidates:
                    candidates.append(cand)

            cap = None
            last_error_msg = "Nenhuma rota RTSP respondeu"

            for url in candidates:
                if not self._is_running or self._switch_stream_requested:
                    break

                masked_url = RTSPProfileFactory.mask_credentials(url)
                self.status_changed.emit(
                    self.camera.id or 0,
                    CameraStatus.CONNECTING.value,
                    f"Conectando a {masked_url}..."
                )

                try:
                    test_cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
                    test_cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

                    if test_cap.isOpened():
                        ret, test_frame = test_cap.read()
                        if ret and test_frame is not None:
                            cap = test_cap
                            break
                    test_cap.release()
                except Exception as e:
                    last_error_msg = str(e)[:30]

            if cap is None or not cap.isOpened():
                diag_msg = "Sinal rejeitado (Verifique usuário/senha no botão Editar)"
                if not self.camera.password:
                    diag_msg = "Senha não informada (Clique com botão direito -> Editar Câmera)"

                self.status_changed.emit(
                    self.camera.id or 0,
                    CameraStatus.ERROR.value,
                    diag_msg
                )

                self._wait_reconnect(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 1.5, MAX_RECONNECT_DELAY)
                continue

            # Conexão estabelecida com sucesso
            reconnect_delay = DEFAULT_RECONNECT_DELAY
            self.status_changed.emit(
                self.camera.id or 0,
                CameraStatus.ONLINE.value,
                f"Online ({self.stream_type.value})"
            )

            fps_limit = (
                DEFAULT_MAIN_FPS_LIMIT
                if self.stream_type == StreamType.MAIN
                else DEFAULT_SUB_FPS_LIMIT
            )
            frame_interval = 1.0 / max(fps_limit, 1)

            consecutive_read_failures = 0
            consecutive_gray_frames = 0

            try:
                while self._is_running:
                    if self._switch_stream_requested:
                        break

                    loop_start = time.time()
                    ret, frame = cap.read()

                    if not ret or frame is None:
                        consecutive_read_failures += 1
                        if consecutive_read_failures > 25:
                            raise ConnectionError("Sinal RTSP interrompido")
                        time.sleep(0.04)
                        continue

                    consecutive_read_failures = 0

                    # Filtro inteligente contra quadros cinzas corrompidos (perda de P-frame / I-frame atrasado)
                    # Quando o decodificador perde pacotes de referência, o FFmpeg preenche com cinza neutro (~128).
                    # Uma amostragem rápida de 32x18 pixels (<0.05ms) detecta e descarta esses quadros, mantendo a imagem estável.
                    if frame.size > 0:
                        thumb = cv2.resize(frame, (32, 18), interpolation=cv2.INTER_NEAREST)
                        b = thumb[:, :, 0].astype(np.int16)
                        g = thumb[:, :, 1].astype(np.int16)
                        r = thumb[:, :, 2].astype(np.int16)

                        # Verifica neutralidade de cor (baixa cromaticidade)
                        diff_bg = np.abs(b - g)
                        diff_gr = np.abs(g - r)
                        diff_br = np.abs(b - r)
                        is_neutral = (diff_bg < 12) & (diff_gr < 12) & (diff_br < 12)

                        # Verifica luminância na faixa característica de decodificação não-inicializada (100 a 150)
                        is_mid_gray = (g >= 100) & (g <= 150)
                        gray_ratio = np.count_nonzero(is_neutral & is_mid_gray) / (thumb.shape[0] * thumb.shape[1])

                        if gray_ratio > 0.60:
                            consecutive_gray_frames += 1
                            # Se a tela cinza persistir por mais de 45 quadros (~2s), reinicia para forçar novo I-frame
                            if consecutive_gray_frames > 45:
                                raise ConnectionError("Perda prolongada de quadros-chave (tela cinza). Forçando reconexão...")
                            time.sleep(0.02)
                            continue  # Descarta o quadro cinza e preserva o último quadro válido na tela

                    consecutive_gray_frames = 0

                    self._last_raw_frame = frame

                    # Processamento de Snapshot
                    if self._snapshot_requested:
                        self._snapshot_requested = False
                        self._save_snapshot(frame)

                    # Processamento de Gravação
                    if self._is_recording:
                        self._write_recording_frame(frame)
                    else:
                        if self._video_writer is not None:
                            self._close_writer()

                    # Conversão BGR -> RGB
                    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    h, w, ch = rgb_frame.shape
                    bytes_per_line = ch * w

                    q_img = QImage(
                        rgb_frame.data,
                        w,
                        h,
                        bytes_per_line,
                        QImage.Format.Format_RGB888
                    ).copy()

                    self.frame_ready.emit(self.camera.id or 0, q_img, w, h)

                    # Cálculo de FPS real
                    self._frame_count += 1
                    now = time.time()
                    elapsed = now - self._last_fps_calc_time
                    if elapsed >= 1.0:
                        self._measured_fps = self._frame_count / elapsed
                        self._frame_count = 0
                        self._last_fps_calc_time = now
                        self.fps_updated.emit(self.camera.id or 0, round(self._measured_fps, 1))

                    processing_time = time.time() - loop_start
                    sleep_time = frame_interval - processing_time
                    if sleep_time > 0.002:
                        time.sleep(sleep_time)

            except Exception as e:
                self.status_changed.emit(
                    self.camera.id or 0,
                    CameraStatus.ERROR.value,
                    f"Conexão perdida: {str(e)[:35]}"
                )
            finally:
                if cap is not None:
                    try:
                        cap.release()
                    except Exception:
                        pass
                self._close_writer()

    def _wait_reconnect(self, delay: float):
        """Espera cooperativa com verificação de interrupção."""
        waited = 0.0
        while waited < delay and self._is_running:
            time.sleep(0.2)
            waited += 0.2
            if self._switch_stream_requested:
                break

    def _save_snapshot(self, frame: np.ndarray):
        try:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:19]
            cam_name_slug = "".join([c if c.isalnum() else "_" for c in self.camera.name])
            filename = f"SNAP_{cam_name_slug}_{timestamp}.jpg"
            filepath = SNAPSHOTS_DIR / filename
            cv2.imwrite(str(filepath), frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
        except Exception as e:
            print(f"Erro no snapshot: {e}")

    def _write_recording_frame(self, frame: np.ndarray):
        h, w = frame.shape[:2]
        if self._video_writer is None:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            cam_name_slug = "".join([c if c.isalnum() else "_" for c in self.camera.name])
            filename = f"REC_{cam_name_slug}_{timestamp}.mp4"
            filepath = str(RECORDINGS_DIR / filename)
            self._current_recording_path = filepath

            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            fps = self._measured_fps if self._measured_fps > 5 else 20.0
            self._video_writer = cv2.VideoWriter(filepath, fourcc, fps, (w, h))
            self.recording_status.emit(self.camera.id or 0, True, filepath)

        timestamp_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(
            frame,
            f"{self.camera.name} | {timestamp_str}",
            (16, h - 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 255),
            2,
            cv2.LINE_AA
        )
        self._video_writer.write(frame)
