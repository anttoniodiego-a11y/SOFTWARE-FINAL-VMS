"""
Sonda de Protocolo RTSP de Baixo Nível (RTSP Probe).
Executa teste direto de socket e handshake RTSP (OPTIONS / DESCRIBE) em ~50 milissegundos,
evitando os travamentos de 30 segundos do OpenCV em rotas ou senhas inválidas.
"""

import base64
import re
import socket
from typing import Optional, Tuple


class RTSPProbe:
    """Diagnóstico rápido de socket e protocolo RTSP em nível de bytes."""

    @classmethod
    def test_port(cls, ip: str, port: int = 554, timeout: float = 1.0) -> bool:
        """Verifica se a porta TCP está aberta e respondendo."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            res = sock.connect_ex((ip, port))
            return res == 0
        except Exception:
            return False
        finally:
            sock.close()

    @classmethod
    def describe(
        cls,
        ip: str,
        port: int,
        path: str,
        user: str = "admin",
        password: str = "",
        timeout: float = 1.5
    ) -> Tuple[int, str, Optional[str]]:
        """
        Envia requisição RTSP DESCRIBE diretamente ao dispositivo.
        Retorna:
          (status_code, status_message, realm_or_details)
        Exemplos de retorno:
          - (200, "OK", "Stream pronto")
          - (401, "Unauthorized", "Exige autenticação Digest/Basic ou senha incorreta")
          - (404, "Not Found", "Canal/Rota inexistente no dispositivo")
          - (0, "Timeout/Recusado", "Porta fechada ou sem resposta")
        """
        if not path.startswith("/"):
            path = "/" + path

        url = f"rtsp://{ip}:{port}{path}"
        auth_header = ""
        if user and password:
            token = base64.b64encode(f"{user}:{password}".encode()).decode()
            auth_header = f"Authorization: Basic {token}\r\n"

        request = (
            f"DESCRIBE {url} RTSP/1.0\r\n"
            f"CSeq: 1\r\n"
            f"User-Agent: VMS-Pro/2.0\r\n"
            f"Accept: application/sdp\r\n"
            f"{auth_header}\r\n"
        )

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)

        try:
            sock.connect((ip, port))
            sock.sendall(request.encode("utf-8"))
            response_bytes = sock.recv(4096)
            response = response_bytes.decode("utf-8", errors="ignore")

            # Analisa código de status (ex: RTSP/1.0 200 OK ou RTSP/1.0 401 Unauthorized)
            match = re.search(r"RTSP/1\.0\s+(\d+)\s+([^\r\n]+)", response)
            if match:
                code = int(match.group(1))
                msg = match.group(2).strip()

                realm = ""
                if "WWW-Authenticate" in response:
                    auth_match = re.search(r'WWW-Authenticate:\s*([^\r\n]+)', response)
                    if auth_match:
                        realm = auth_match.group(1)

                return code, msg, realm

            return 0, "Resposta RTSP inválida", None

        except socket.timeout:
            return 0, "Timeout ao contatar porta RTSP", None
        except ConnectionRefusedError:
            return 0, "Porta RTSP recusou conexão", None
        except Exception as e:
            return 0, f"Erro de socket: {str(e)[:40]}", None
        finally:
            sock.close()
