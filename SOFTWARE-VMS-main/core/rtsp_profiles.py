"""
Fábrica de URLs RTSP e Motor de Diagnóstico / Fallback de Rotas.
Gera rotas canônicas e alternativas para contornar variações de firmware
em Hikvision, HiLook, Intelbras, Dahua e ONVIF.
"""

import re
import socket
import urllib.parse
from typing import List, Optional, Tuple

import cv2
from core.models import Brand, Camera, StreamType


class RTSPProfileFactory:
    """Gera e testa URLs RTSP com múltiplos caminhos de fallback por fabricante."""

    @staticmethod
    def _encode_auth(user: str, password: str) -> str:
        """Codifica credenciais de forma segura preservando caracteres aceitos."""
        safe_user = urllib.parse.quote(user, safe="")
        safe_pass = urllib.parse.quote(password, safe="")
        return f"{safe_user}:{safe_pass}"

    @classmethod
    def get_candidate_urls(cls, camera: Camera, stream_type: StreamType) -> List[str]:
        """
        Retorna uma lista ordenada de URLs candidatas baseadas na marca e canal.
        Se o substream não estiver habilitado na câmera, inclui o main stream como fallback.
        """
        auth = cls._encode_auth(camera.username, camera.password)
        raw_auth = f"{camera.username}:{camera.password}"
        host = f"{camera.ip}:{camera.port}"
        ch = camera.channel

        candidates = []

        if camera.brand in (Brand.HIKVISION, Brand.HILOOK):
            suffix = "01" if stream_type == StreamType.MAIN else "02"
            stream_id = f"{ch}{suffix}"

            # 1. Padrão canônico moderno Hikvision (/Streaming/Channels/101 ou 102)
            candidates.append(f"rtsp://{auth}@{host}/Streaming/Channels/{stream_id}")
            # 2. Rota curta (/Streaming/Channels/1 ou /Streaming/Channels/2)
            alt_id = f"{ch}" if stream_type == StreamType.MAIN else f"{ch * 2}"
            candidates.append(f"rtsp://{auth}@{host}/Streaming/Channels/{alt_id}")
            # 3. Se substream falhar, tentar canal 1 direto (muitas câmeras só têm stream 1)
            if stream_type == StreamType.SUB:
                candidates.append(f"rtsp://{auth}@{host}/Streaming/Channels/{ch}01")
                candidates.append(f"rtsp://{auth}@{host}/Streaming/Channels/{ch}")
            # 4. Padrão legacy H.264
            st_str = "main" if stream_type == StreamType.MAIN else "sub"
            candidates.append(f"rtsp://{auth}@{host}/h264/ch{ch}/{st_str}/av_stream")
            # 5. Padrão ISAPI
            candidates.append(f"rtsp://{auth}@{host}/ISAPI/Streaming/channels/{stream_id}")
            # 6. Rota /live/ch
            candidates.append(f"rtsp://{auth}@{host}/live/ch{ch}")

        elif camera.brand in (Brand.INTELBRAS, Brand.DAHUA):
            subtype = 0 if stream_type == StreamType.MAIN else 1
            # 1. Padrão Oficial Intelbras / Dahua (/cam/realmonitor)
            candidates.append(f"rtsp://{auth}@{host}/cam/realmonitor?channel={ch}&subtype={subtype}")
            if stream_type == StreamType.SUB:
                # Fallback para main stream caso substream esteja desativado
                candidates.append(f"rtsp://{auth}@{host}/cam/realmonitor?channel={ch}&subtype=0")
            # 2. Padrão Intelbras Mibo / Wi-Fi
            candidates.append(f"rtsp://{auth}@{host}/live/ch{ch}")
            # 3. Rota ONVIF padrão
            candidates.append(f"rtsp://{auth}@{host}/onvif{ch}")
            candidates.append(f"rtsp://{auth}@{host}/Streaming/Channels/{ch}01")

        elif camera.brand == Brand.HOLOWITS:
            # Holowits / Huawei Intelligent Vision (Rotas Canônicas SDC, Huawei e ONVIF)
            media_id = "Media1" if stream_type == StreamType.MAIN else "Media2"
            candidates.append(f"rtsp://{auth}@{host}/LiveMedia/ch{ch}/{media_id}")
            # Em muitas câmeras Holowits SDC o canal padrão é ch0
            candidates.append(f"rtsp://{auth}@{host}/LiveMedia/ch0/{media_id}")
            candidates.append(f"rtsp://{auth}@{host}/LiveMedia/ch1/{media_id}")
            if stream_type == StreamType.SUB:
                candidates.append(f"rtsp://{auth}@{host}/LiveMedia/ch{ch}/Media1")
                candidates.append(f"rtsp://{auth}@{host}/LiveMedia/ch0/Media1")
                candidates.append(f"rtsp://{auth}@{host}/LiveMedia/ch1/Media1")
            candidates.append(f"rtsp://{auth}@{host}/LiveMedia/ch{ch}/Media0")
            # Rotas SDP padrão Huawei / Holowits
            candidates.append(f"rtsp://{auth}@{host}/live{'1' if stream_type == StreamType.MAIN else '2'}.sdp")
            candidates.append(f"rtsp://{auth}@{host}/live1.sdp")
            candidates.append(f"rtsp://{auth}@{host}/live0.sdp")
            # Rotas H.264 AV Stream
            candidates.append(f"rtsp://{auth}@{host}/h264/ch{ch}/{'main' if stream_type == StreamType.MAIN else 'sub'}/av_stream")
            candidates.append(f"rtsp://{auth}@{host}/h264/ch1/{'main' if stream_type == StreamType.MAIN else 'sub'}/av_stream")
            # Rotas /live/ch
            candidates.append(f"rtsp://{auth}@{host}/live/ch{ch}")
            candidates.append(f"rtsp://{auth}@{host}/live/ch0")
            candidates.append(f"rtsp://{auth}@{host}/live/ch1")
            # Rotas de Mídia Genéricas
            candidates.append(f"rtsp://{auth}@{host}/media/video{1 if stream_type == StreamType.MAIN else 2}")
            candidates.append(f"rtsp://{auth}@{host}/video{1 if stream_type == StreamType.MAIN else 2}")
            candidates.append(f"rtsp://{auth}@{host}/Streaming/Channels/{ch}0{1 if stream_type == StreamType.MAIN else 2}")
            candidates.append(f"rtsp://{auth}@{host}/Streaming/Channels/10{1 if stream_type == StreamType.MAIN else 2}")
            candidates.append(f"rtsp://{auth}@{host}/profile{1 if stream_type == StreamType.MAIN else 2}")
            candidates.append(f"rtsp://{auth}@{host}/onvif{1 if stream_type == StreamType.MAIN else 2}")
            candidates.append(f"rtsp://{auth}@{host}/axis-media/media.amp")

            # Fallback de porta 8554 se configurada na 554
            if camera.port == 554:
                alt_host = f"{camera.ip}:8554"
                candidates.append(f"rtsp://{auth}@{alt_host}/LiveMedia/ch{ch}/{media_id}")
                candidates.append(f"rtsp://{auth}@{alt_host}/LiveMedia/ch0/{media_id}")
                candidates.append(f"rtsp://{auth}@{alt_host}/live{'1' if stream_type == StreamType.MAIN else '2'}.sdp")

        elif camera.brand == Brand.POSITIVO:
            # Positivo Casa Inteligente / Segurança (Tuya, Xiongmai, Anyka)
            st_idx = "0" if stream_type == StreamType.MAIN else "1"
            candidates.append(f"rtsp://{auth}@{host}/live/ch{st_idx}")
            candidates.append(f"rtsp://{auth}@{host}/live/ch{ch}")
            candidates.append(f"rtsp://{auth}@{host}/live/ch0")
            candidates.append(f"rtsp://{auth}@{host}/live/ch1")
            candidates.append(f"rtsp://{auth}@{host}/onvif{1 if stream_type == StreamType.MAIN else 2}")
            candidates.append(f"rtsp://{auth}@{host}/onvif1")
            candidates.append(f"rtsp://{auth}@{host}/onvif2")
            candidates.append(f"rtsp://{auth}@{host}/stream{1 if stream_type == StreamType.MAIN else 2}")
            candidates.append(f"rtsp://{auth}@{host}/stream1")
            candidates.append(f"rtsp://{auth}@{host}/media/stream1")
            candidates.append(f"rtsp://{auth}@{host}/media/video{1 if stream_type == StreamType.MAIN else 2}")
            # Padrão Xiongmai / Tuya URI format
            candidates.append(f"rtsp://{auth}@{host}/user={camera.username}_password={camera.password}_channel={ch}_stream={0 if stream_type == StreamType.MAIN else 1}.sdp")
            candidates.append(f"rtsp://{auth}@{host}/user={camera.username}&password={camera.password}&channel={ch}&stream={0 if stream_type == StreamType.MAIN else 1}.sdp")
            candidates.append(f"rtsp://{auth}@{host}/h264Preview_{ch:02d}_{'main' if stream_type == StreamType.MAIN else 'sub'}")
            candidates.append(f"rtsp://{auth}@{host}/ch0_{0 if stream_type == StreamType.MAIN else 1}.264")
            candidates.append(f"rtsp://{auth}@{host}/Streaming/Channels/10{1 if stream_type == StreamType.MAIN else 2}")

            if camera.port == 554:
                alt_host = f"{camera.ip}:8554"
                candidates.append(f"rtsp://{auth}@{alt_host}/live")
                candidates.append(f"rtsp://{auth}@{alt_host}/live/ch0")

        elif camera.brand == Brand.UNIVIEW:
            # Uniview (UNV) Padrão Oficial
            s_idx = "0" if stream_type == StreamType.MAIN else "1"
            candidates.append(f"rtsp://{auth}@{host}/unicast/c{ch}/s{s_idx}/live")
            candidates.append(f"rtsp://{auth}@{host}/unicast/c1/s{s_idx}/live")
            if stream_type == StreamType.SUB:
                candidates.append(f"rtsp://{auth}@{host}/unicast/c{ch}/s0/live")
                candidates.append(f"rtsp://{auth}@{host}/unicast/c1/s0/live")
            candidates.append(f"rtsp://{auth}@{host}/media/video{1 if stream_type == StreamType.MAIN else 2}")
            candidates.append(f"rtsp://{auth}@{host}/video{1 if stream_type == StreamType.MAIN else 2}")
            candidates.append(f"rtsp://{auth}@{host}/Streaming/Channels/{ch}0{1 if stream_type == StreamType.MAIN else 2}")
            candidates.append(f"rtsp://{auth}@{host}/Streaming/Channels/10{1 if stream_type == StreamType.MAIN else 2}")
            candidates.append(f"rtsp://{auth}@{host}/ch{ch}/{'main' if stream_type == StreamType.MAIN else 'sub'}/av_stream")
            candidates.append(f"rtsp://{auth}@{host}/ch1/{'main' if stream_type == StreamType.MAIN else 'sub'}/av_stream")
            candidates.append(f"rtsp://{auth}@{host}/live/ch{ch}")
            candidates.append(f"rtsp://{auth}@{host}/live/ch1")
            candidates.append(f"rtsp://{auth}@{host}/ch{ch:02d}/{0 if stream_type == StreamType.MAIN else 1}")
            candidates.append(f"rtsp://{auth}@{host}/onvif{1 if stream_type == StreamType.MAIN else 2}")

        else:
            # Genérico / ONVIF RTSP
            candidates.append(f"rtsp://{auth}@{host}/live/ch{ch}")
            candidates.append(f"rtsp://{auth}@{host}/onvif{ch}")
            candidates.append(f"rtsp://{auth}@{host}/Streaming/Channels/{ch}01")
            candidates.append(f"rtsp://{auth}@{host}/cam/realmonitor?channel={ch}&subtype=0")

        # Se houver senha com caracteres especiais que possam ter sido alterados pelo percent-encode,
        # adiciona também versão com credenciais diretas
        if raw_auth != auth:
            for url in list(candidates):
                raw_url = url.replace(auth, raw_auth)
                if raw_url not in candidates:
                    candidates.append(raw_url)

        return candidates

    @classmethod
    def build_url(cls, camera: Camera, stream_type: StreamType) -> str:
        """Retorna a URL prioritária canônica."""
        candidates = cls.get_candidate_urls(camera, stream_type)
        return candidates[0] if candidates else f"rtsp://{camera.ip}:{camera.port}"

    @classmethod
    def probe_and_diagnose(cls, camera: Camera) -> Tuple[bool, Optional[str], Optional[str], str]:
        """
        Diagnostica a conexão física e descobre a rota RTSP exata suportada pelo dispositivo.
        Retorna: (sucesso, working_main_url, working_sub_url, mensagem_diagnostica)
        """
        # 1. Teste de conectividade física na porta RTSP
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1.5)
        try:
            res = sock.connect_ex((camera.ip, camera.port))
            if res != 0:
                return (
                    False,
                    None,
                    None,
                    f"Porta {camera.port} inacessível em {camera.ip}. Câmera desligada ou subrede diferente."
                )
        except Exception as e:
            return False, None, None, f"Erro de conexão com host {camera.ip}: {e}"
        finally:
            sock.close()

        # 2. Testa as URLs candidatas
        sub_candidates = cls.get_candidate_urls(camera, StreamType.SUB)
        main_candidates = cls.get_candidate_urls(camera, StreamType.MAIN)

        working_sub_url = None
        working_main_url = None
        detected_res = ""

        for i, url in enumerate(sub_candidates):
            cap = None
            try:
                cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                if cap.isOpened():
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        h, w = frame.shape[:2]
                        detected_res = f"{w}x{h} px"
                        working_sub_url = url
                        working_main_url = main_candidates[min(i, len(main_candidates) - 1)]
                        break
            except Exception:
                pass
            finally:
                if cap is not None:
                    cap.release()

        if working_sub_url:
            masked = cls.mask_credentials(working_sub_url)
            return (
                True,
                working_main_url,
                working_sub_url,
                f"Conectado com sucesso! Resolução: {detected_res} | Rota: {masked}"
            )

        # 3. Diagnóstico de credencial
        if not camera.password:
            return (
                False,
                None,
                None,
                "A porta 554 respondeu, mas a câmera exige senha. Clique em 'Editar Câmera' e preencha a senha correta."
            )

        tips = [
            "1. Senha ou usuário incorretos (verifique maiúsculas e caracteres especiais);",
            "2. O protocolo RTSP/ONVIF precisa estar ativado na página web ou aplicativo da câmera;"
        ]

        if camera.brand == Brand.HOLOWITS:
            tips.append("3. Holowits/Huawei: Acesse a interface web da câmera (Configuração -> Rede -> Plataforma de Acesso -> ONVIF), ative o protocolo e crie um usuário de mídia com permissão RTSP.")
        elif camera.brand == Brand.POSITIVO:
            tips.append("3. Positivo: No aplicativo 'Positivo Casa Inteligente', abra as configurações da câmera -> ative a opção 'PC View / ONVIF' e defina a senha local para liberar o RTSP.")
        elif camera.brand == Brand.UNIVIEW:
            tips.append("3. Uniview (UNV): Na interface web da câmera (Rede -> Portas), verifique se o RTSP está na porta 554 e a autenticação configurada em 'Digest/Basic'.")
        else:
            tips.append("3. O canal selecionado pode estar inativo ou o dispositivo exige autenticação Digest.")

        return (
            False,
            None,
            None,
            f"Porta {camera.port} respondeu em {camera.ip}, mas o fluxo RTSP foi recusado. Verificações:\n" + "\n".join(tips)
        )

    @staticmethod
    def mask_credentials(rtsp_url: str) -> str:
        """Oculta a senha da URL RTSP para exibição segura."""
        return re.sub(r":([^@]+)@", r":****@", rtsp_url)
