"""
Configurações globais e parâmetros de otimização de baixo nível para o VMS.
"""

import os
from pathlib import Path

# Diretórios base
BASE_DIR = Path(__file__).resolve().parent.parent
RECORDINGS_DIR = BASE_DIR / "recordings"
SNAPSHOTS_DIR = BASE_DIR / "snapshots"
ASSETS_DIR = BASE_DIR / "assets"
DATABASE_PATH = BASE_DIR / "vms_data.db"
LOGO_PATH = ASSETS_DIR / "logo_interface.png"
SOURCE_LOGO = LOGO_PATH

RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

# -------------------------------------------------------------------------
# Otimizações FFmpeg para OpenCV (Estabilidade contra telas cinzas e baixa latência)
# -------------------------------------------------------------------------
# Configuração otimizada para CFTV:
# - rtsp_transport;tcp: força transporte TCP para evitar perda de pacotes RTP (causa primordial de tela cinza)
# - buffer_size;4194304: 4 Megabytes de buffer de socket para absorver rajadas de rede
# - reorder_queue_size;500: reordena pacotes que cheguem fora de ordem
# - max_delay;500000: tolerância de jitter de 500ms
# - stimeout;5000000: timeout de socket de 5 segundos
# - fflags;discardcorrupt: descarta pacotes corrompidos para libavcodec não decodificar frames cinzas
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
    "rtsp_transport;tcp|"
    "buffer_size;4194304|"
    "reorder_queue_size;500|"
    "max_delay;500000|"
    "stimeout;5000000|"
    "fflags;discardcorrupt"
)

ENABLE_HW_ACCELERATION = True

# Parâmetros de Streaming e Reconexão
DEFAULT_RECONNECT_DELAY = 3.0      # Segundos antes de tentar reconectar
MAX_RECONNECT_DELAY = 12.0         # Limite máximo de backoff
FRAME_DROP_THRESHOLD = 2           # Descarte de quadros acumulados
DEFAULT_SUB_FPS_LIMIT = 15         # Limite de FPS no modo Grade (poupa CPU/GPU)
DEFAULT_MAIN_FPS_LIMIT = 30        # FPS pleno no modo 1x1

# Presets de Grade Suportados
SUPPORTED_GRIDS = {
    "1x1": (1, 1),
    "2x2": (2, 2),
    "3x3": (3, 3),
    "4x4": (4, 4),
    "5x5": (5, 5),
    "6x6": (6, 6),
    "7x7": (7, 7),
    "8x8": (8, 8),
}

MAX_CAMERAS = 64
