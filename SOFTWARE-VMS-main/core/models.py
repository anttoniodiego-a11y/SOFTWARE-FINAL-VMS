"""
Modelos de dados estruturados e enums do VMS.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Brand(str, Enum):
    HIKVISION = "Hikvision"
    HILOOK = "HiLook"
    INTELBRAS = "Intelbras"
    DAHUA = "Dahua"
    HOLOWITS = "Holowits"
    POSITIVO = "Positivo"
    UNIVIEW = "Uniview (UNV)"
    GENERIC_ONVIF = "Genérico / ONVIF"


class StreamType(str, Enum):
    MAIN = "MAIN"   # Alta Resolução (1080p, 4K) - Modo 1x1
    SUB = "SUB"     # Baixa Resolução (D1, 360p) - Modo Grade (Multi-View)


class CameraStatus(str, Enum):
    DISCONNECTED = "Desconectado"
    CONNECTING = "Conectando..."
    ONLINE = "Online"
    RECORDING = "Gravando"
    ERROR = "Sem Sinal / Erro"


@dataclass
class Area:
    id: Optional[int]
    name: str
    description: str = ""


@dataclass
class Camera:
    id: Optional[int]
    name: str
    ip: str
    port: int = 554
    username: str = "admin"
    password: str = ""
    channel: int = 1
    brand: Brand = Brand.HIKVISION
    area_id: Optional[int] = None
    is_active: bool = True
    custom_main_url: Optional[str] = None
    custom_sub_url: Optional[str] = None

    def get_main_stream_url(self) -> str:
        """Gera ou retorna a URL RTSP do Stream Principal (Alta Resolução)."""
        if self.custom_main_url:
            return self.custom_main_url
        from core.rtsp_profiles import RTSPProfileFactory
        return RTSPProfileFactory.build_url(self, StreamType.MAIN)

    def get_sub_stream_url(self) -> str:
        """Gera ou retorna a URL RTSP do Substream (Baixa Resolução)."""
        if self.custom_sub_url:
            return self.custom_sub_url
        from core.rtsp_profiles import RTSPProfileFactory
        return RTSPProfileFactory.build_url(self, StreamType.SUB)
