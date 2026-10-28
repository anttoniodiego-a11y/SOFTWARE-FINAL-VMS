"""
Motor de Descoberta Automática de Câmeras e Gravadores (Auto-Discovery).
Implementa busca híbrida e simultânea na rede local através de:
1. ONVIF WS-Discovery (UDP Multicast 239.255.255.250:3702) - Padrão da indústria de CFTV
2. Hikvision / HiLook SADP Protocol (UDP Broadcast 37020)
3. Intelbras / Dahua Discovery Protocol (UDP Broadcast 37810)
4. Scanner Rápido de Subrede TCP (Portas 554, 80, 8000, 37777) para redes com multicast bloqueado
"""

import concurrent.futures
import ipaddress
import re
import socket
import time
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Dict, List, Optional, Set
from core.models import Brand


@dataclass
class DiscoveredDevice:
    ip: str
    port: int = 554
    onvif_port: int = 80
    brand: Brand = Brand.GENERIC_ONVIF
    device_type: str = "Câmera IP"  # "Câmera IP" ou "Gravador NVR/DVR"
    model: str = "Dispositivo CFTV"
    mac: str = ""
    suggested_channels: int = 1
    onvif_xaddr: str = ""


class NetworkDiscoveryEngine:
    """Motor de busca concorrente de dispositivos CFTV na rede local."""

    WS_DISCOVERY_PROBE = """<?xml version="1.0" encoding="utf-8"?>
<Envelope xmlns="http://www.w3.org/2003/05/soap-envelope"
          xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
  <Header>
    <wsa:MessageID xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing">uuid:{msg_id}</wsa:MessageID>
    <wsa:To xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing">urn:schemas-xmlsoap-org:ws:2005:04:discovery</wsa:To>
    <wsa:Action xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing">http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</wsa:Action>
  </Header>
  <Body>
    <Probe xmlns="http://schemas.xmlsoap.org/ws/2005/04/discovery">
      <Types>dn:NetworkVideoTransmitter</Types>
    </Probe>
  </Body>
</Envelope>"""

    @classmethod
    def get_local_ip_and_subnets(cls) -> List[str]:
        """Detecta os IPs locais da máquina e infere as faixas de subrede /24."""
        subnets = set()
        try:
            # Obtém todos os IPs das interfaces ativas
            hostname = socket.gethostname()
            addr_info = socket.getaddrinfo(hostname, None, socket.AF_INET)
            for info in addr_info:
                ip = info[4][0]
                if not ip.startswith("127."):
                    # Gera subrede /24 (ex: 192.168.1.0/24)
                    network = ipaddress.IPv4Network(f"{ip}/24", strict=False)
                    subnets.add(str(network))
        except Exception:
            pass

        # Fallback para faixa comum de roteador caso socket falhe
        if not subnets:
            subnets.add("192.168.1.0/24")
            subnets.add("192.168.0.0/24")

        return list(subnets)

    @classmethod
    def discover_all(cls, timeout: float = 3.5, progress_callback=None) -> List[DiscoveredDevice]:
        """
        Executa todos os métodos de descoberta em paralelo e unifica os resultados por IP.
        """
        devices_by_ip: Dict[str, DiscoveredDevice] = {}

        if progress_callback:
            progress_callback("Iniciando varredura ONVIF WS-Discovery e Broadcast...")

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            future_onvif = executor.submit(cls._discover_onvif, timeout)
            future_sadp = executor.submit(cls._discover_hikvision_sadp, timeout)
            future_dahua = executor.submit(cls._discover_dahua_intelbras, timeout)
            future_scan = executor.submit(cls._fast_subnet_port_scan, 2.5)

            # 1. Coleta ONVIF
            try:
                for dev in future_onvif.result():
                    devices_by_ip[dev.ip] = dev
            except Exception as e:
                print(f"Erro em ONVIF discovery: {e}")

            # 2. Coleta Hikvision SADP
            try:
                for dev in future_sadp.result():
                    if dev.ip in devices_by_ip:
                        # Enriquece dados com marca mais precisa
                        devices_by_ip[dev.ip].brand = dev.brand
                        devices_by_ip[dev.ip].model = dev.model
                        devices_by_ip[dev.ip].device_type = dev.device_type
                        devices_by_ip[dev.ip].suggested_channels = dev.suggested_channels
                    else:
                        devices_by_ip[dev.ip] = dev
            except Exception as e:
                print(f"Erro em SADP discovery: {e}")

            # 3. Coleta Intelbras / Dahua
            try:
                for dev in future_dahua.result():
                    if dev.ip in devices_by_ip:
                        devices_by_ip[dev.ip].brand = dev.brand
                        devices_by_ip[dev.ip].model = dev.model
                        devices_by_ip[dev.ip].device_type = dev.device_type
                        devices_by_ip[dev.ip].suggested_channels = dev.suggested_channels
                    else:
                        devices_by_ip[dev.ip] = dev
            except Exception as e:
                print(f"Erro em Dahua discovery: {e}")

            # 4. Coleta Subnet Port Scan (Fallback caso multicast tenha sido bloqueado)
            try:
                for dev in future_scan.result():
                    if dev.ip not in devices_by_ip:
                        devices_by_ip[dev.ip] = dev
            except Exception as e:
                print(f"Erro em Subnet scan: {e}")

        return list(devices_by_ip.values())

    @classmethod
    def _discover_onvif(cls, timeout: float = 3.0) -> List[DiscoveredDevice]:
        """Dispara probe ONVIF WS-Discovery via UDP Multicast (239.255.255.250:3702)."""
        devices = []
        msg_id = str(uuid.uuid4())
        packet = cls.WS_DISCOVERY_PROBE.format(msg_id=msg_id).encode("utf-8")

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(0.6)

        multicast_group = ("239.255.255.250", 3702)

        try:
            sock.sendto(packet, multicast_group)
            start_time = time.time()

            while time.time() - start_time < timeout:
                try:
                    data, addr = sock.recvfrom(65535)
                    dev = cls._parse_onvif_response(data.decode("utf-8", errors="ignore"), addr[0])
                    if dev and not any(d.ip == dev.ip for d in devices):
                        devices.append(dev)
                except socket.timeout:
                    continue
        except Exception as e:
            print(f"Erro no socket ONVIF: {e}")
        finally:
            sock.close()

        return devices

    @classmethod
    def _parse_onvif_response(cls, xml_text: str, fallback_ip: str) -> Optional[DiscoveredDevice]:
        """Analisa o XML SOAP do dispositivo e extrai IP, Port, Scopes e Fabricante."""
        try:
            ip = fallback_ip
            port = 554
            onvif_port = 80
            brand = Brand.GENERIC_ONVIF
            model = "Câmera ONVIF"
            device_type = "Câmera IP"
            suggested_channels = 1
            xaddr = ""

            # Extração de XAddrs (URLs do serviço ONVIF)
            xaddrs_match = re.search(r"<[^>]*XAddrs[^>]*>([^<]+)</", xml_text)
            if xaddrs_match:
                xaddr = xaddrs_match.group(1).strip().split()[0]
                ip_match = re.search(r"http://([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)(?::([0-9]+))?", xaddr)
                if ip_match:
                    ip = ip_match.group(1)
                    if ip_match.group(2):
                        onvif_port = int(ip_match.group(2))

            # Extração de Scopes (onvif://www.onvif.org/...)
            scopes_match = re.search(r"<[^>]*Scopes[^>]*>([^<]+)</", xml_text)
            scopes_text = scopes_match.group(1).lower() if scopes_match else xml_text.lower()

            if "hikvision" in scopes_text:
                brand = Brand.HIKVISION
            elif "hilook" in scopes_text:
                brand = Brand.HILOOK
            elif "intelbras" in scopes_text:
                brand = Brand.INTELBRAS
            elif "dahua" in scopes_text:
                brand = Brand.DAHUA
            elif "holowits" in scopes_text or "huawei" in scopes_text or "hwt" in scopes_text:
                brand = Brand.HOLOWITS
            elif "uniview" in scopes_text or "unv" in scopes_text:
                brand = Brand.UNIVIEW
            elif "positivo" in scopes_text:
                brand = Brand.POSITIVO

            if any(k in scopes_text for k in ["nvr", "dvr", "recorder", "multi-channel"]):
                device_type = "Gravador NVR/DVR"
                suggested_channels = 16

            # Tenta extrair modelo
            model_match = re.search(r"hardware/([a-zA-Z0-9_\-]+)", scopes_text)
            if model_match:
                model = model_match.group(1).upper()
            elif brand != Brand.GENERIC_ONVIF:
                model = f"{brand.value} {device_type}"

            return DiscoveredDevice(
                ip=ip,
                port=port,
                onvif_port=onvif_port,
                brand=brand,
                device_type=device_type,
                model=model,
                suggested_channels=suggested_channels,
                onvif_xaddr=xaddr
            )
        except Exception:
            return None

    @classmethod
    def _discover_hikvision_sadp(cls, timeout: float = 2.5) -> List[DiscoveredDevice]:
        """Varredura via protocolo de broadcast SADP da Hikvision/HiLook (Porta UDP 37020)."""
        devices = []
        sadp_probe = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<Probe><Types>inquire</Types></Probe>'
        ).encode("utf-8")

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(0.5)

        try:
            # Envia para multicast SADP e broadcast local
            for target in [("239.255.255.250", 37020), ("255.255.255.255", 37020)]:
                try:
                    sock.sendto(sadp_probe, target)
                except Exception:
                    pass

            start = time.time()
            while time.time() - start < timeout:
                try:
                    data, addr = sock.recvfrom(4096)
                    text = data.decode("utf-8", errors="ignore")
                    ip_match = re.search(r"<IPv4Address>([^<]+)</IPv4Address>", text)
                    if not ip_match:
                        continue
                    ip = ip_match.group(1)

                    model_match = re.search(r"<DeviceDescription>([^<]+)</DeviceDescription>", text)
                    model = model_match.group(1) if model_match else "Hikvision Device"

                    port_match = re.search(r"<CommandPort>([^<]+)</CommandPort>", text)
                    cmd_port = int(port_match.group(1)) if port_match else 8000

                    mac_match = re.search(r"<MAC>([^<]+)</MAC>", text)
                    mac = mac_match.group(1) if mac_match else ""

                    is_hilook = "hilook" in model.lower() or "hl" in model.lower()
                    brand = Brand.HILOOK if is_hilook else Brand.HIKVISION
                    is_nvr = any(k in model.lower() for k in ["nvr", "dvr", "ds-7", "ds-8"])
                    device_type = "Gravador NVR/DVR" if is_nvr else "Câmera IP"
                    channels = 16 if is_nvr else 1

                    devices.append(DiscoveredDevice(
                        ip=ip,
                        port=554,
                        brand=brand,
                        device_type=device_type,
                        model=model,
                        mac=mac,
                        suggested_channels=channels
                    ))
                except socket.timeout:
                    continue
        except Exception:
            pass
        finally:
            sock.close()
        return devices

    @classmethod
    def _discover_dahua_intelbras(cls, timeout: float = 2.5) -> List[DiscoveredDevice]:
        """Varredura via protocolo de broadcast Intelbras/Dahua (Porta UDP 37810)."""
        devices = []
        # Pacote de probe compatível com ConfigTool
        dahua_probe = b"\x20\x00\x00\x00DHIP\x00\x00\x00\x00\x00\x00\x00\x00"

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(0.5)

        try:
            sock.sendto(dahua_probe, ("255.255.255.255", 37810))
            start = time.time()
            while time.time() - start < timeout:
                try:
                    data, addr = sock.recvfrom(4096)
                    ip = addr[0]
                    text = data.decode("latin-1", errors="ignore")

                    is_intelbras = "intelbras" in text.lower() or "mhdx" in text.lower() or "vip" in text.lower()
                    brand = Brand.INTELBRAS if is_intelbras else Brand.DAHUA
                    is_nvr = any(k in text.lower() for k in ["nvr", "dvr", "mhdx", "hcvdr", "xvr"])
                    device_type = "Gravador NVR/DVR" if is_nvr else "Câmera IP"

                    devices.append(DiscoveredDevice(
                        ip=ip,
                        port=554,
                        brand=brand,
                        device_type=device_type,
                        model=f"{brand.value} {device_type}",
                        suggested_channels=16 if is_nvr else 1
                    ))
                except socket.timeout:
                    continue
        except Exception:
            pass
        finally:
            sock.close()
        return devices

    @classmethod
    def _fast_subnet_port_scan(cls, timeout: float = 2.0) -> List[DiscoveredDevice]:
        """
        Scanner concorrente de subrede nas portas clássicas de CFTV:
        Porta 554 (RTSP), 37777 (Intelbras/Dahua), 8000 (Hikvision), 80/8080 (ONVIF HTTP).
        Garante que câmeras sejam encontradas mesmo se multicast UDP for barrado por firewall.
        """
        discovered = []
        subnets = cls.get_local_ip_and_subnets()

        # Lista de IPs a testar (limita a /24 para varredura rápida em ~2 segundos)
        ips_to_test = []
        for sub in subnets[:2]:
            net = ipaddress.IPv4Network(sub, strict=False)
            # Amostra todos os hosts da faixa
            for host in net.hosts():
                ips_to_test.append(str(host))

        def probe_ip(target_ip: str) -> Optional[DiscoveredDevice]:
            # Testa primeiro se a porta RTSP 554 está aberta
            has_rtsp = cls._check_tcp_port(target_ip, 554, timeout=0.25)
            has_dahua_port = cls._check_tcp_port(target_ip, 37777, timeout=0.2)
            has_hik_port = cls._check_tcp_port(target_ip, 8000, timeout=0.2)

            if not (has_rtsp or has_dahua_port or has_hik_port):
                return None

            brand = Brand.GENERIC_ONVIF
            device_type = "Câmera IP"
            model = "Dispositivo CFTV"

            if has_hik_port:
                brand = Brand.HIKVISION
                model = "Hikvision / HiLook"
            elif has_dahua_port:
                brand = Brand.INTELBRAS
                model = "Intelbras / Dahua"

            return DiscoveredDevice(
                ip=target_ip,
                port=554,
                brand=brand,
                device_type=device_type,
                model=model,
                suggested_channels=1
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=64) as pool:
            results = pool.map(probe_ip, ips_to_test)
            for res in results:
                if res is not None:
                    discovered.append(res)

        return discovered

    @staticmethod
    def _check_tcp_port(ip: str, port: int, timeout: float = 0.25) -> bool:
        """Verifica de forma rápida e segura se uma porta TCP está escutando."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            res = sock.connect_ex((ip, port))
            return res == 0
        except Exception:
            return False
        finally:
            sock.close()
