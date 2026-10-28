"""
Gerenciador Central de Streams (StreamManager).
Orquestra o ciclo de vida das threads de streaming (StreamWorker),
garantindo limpeza segura de memória e prevenindo crashes de destruição de QThread.
"""

from typing import Callable, Dict, List, Optional
from core.models import Camera, StreamType
from core.stream_worker import StreamWorker


class StreamManager:
    """Controlador mestre para gerenciar até 64 fluxos concorrentes."""

    def __init__(self):
        self._workers: Dict[int, StreamWorker] = {}
        # Lista de retenção para threads em encerramento (impede 'QThread: Destroyed while running')
        self._dying_workers: List[StreamWorker] = []
        self._maximized_camera_id: Optional[int] = None

    def start_camera_stream(
        self,
        camera: Camera,
        initial_stream_type: StreamType = StreamType.SUB,
        on_frame: Optional[Callable] = None,
        on_status: Optional[Callable] = None,
        on_fps: Optional[Callable] = None,
        on_recording: Optional[Callable] = None,
    ) -> StreamWorker:
        """Inicia uma nova thread de streaming para a câmera especificada."""
        if not camera.id:
            raise ValueError("Câmera deve possuir um ID válido para iniciar stream.")

        if camera.id in self._workers:
            self.stop_camera_stream(camera.id)

        worker = StreamWorker(camera, initial_stream_type=initial_stream_type)

        if on_frame:
            worker.frame_ready.connect(on_frame)
        if on_status:
            worker.status_changed.connect(on_status)
        if on_fps:
            worker.fps_updated.connect(on_fps)
        if on_recording:
            worker.recording_status.connect(on_recording)

        self._workers[camera.id] = worker
        worker.start()
        return worker

    def stop_camera_stream(self, camera_id: int):
        """Interrompe e remove o worker de forma segura sem crash de thread."""
        if camera_id in self._workers:
            worker = self._workers.pop(camera_id)

            # Desconecta os sinais da GUI imediatamente
            try:
                worker.frame_ready.disconnect()
                worker.status_changed.disconnect()
                worker.fps_updated.disconnect()
                worker.recording_status.disconnect()
            except Exception:
                pass

            # Retém a referência em memória até que a thread do SO termine
            self._dying_workers.append(worker)

            def cleanup(w=worker):
                if w in self._dying_workers:
                    self._dying_workers.remove(w)

            worker.finished.connect(cleanup)
            worker.stop()

    def get_worker(self, camera_id: int) -> Optional[StreamWorker]:
        return self._workers.get(camera_id)

    def set_maximized_camera(self, camera_id: Optional[int]):
        """Política de Dual Stream: Main para canal em foco, Sub para os demais."""
        self._maximized_camera_id = camera_id

        for cid, worker in self._workers.items():
            if cid == camera_id:
                worker.request_stream_type(StreamType.MAIN)
            else:
                worker.request_stream_type(StreamType.SUB)

    def set_all_to_substream(self):
        self.set_maximized_camera(None)

    def stop_all(self):
        """Encerramento ordenado de todas as threads ao fechar o VMS."""
        for cid in list(self._workers.keys()):
            self.stop_camera_stream(cid)
