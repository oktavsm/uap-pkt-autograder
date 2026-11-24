"""Decode Packet Tracer .pkt/.pka containers and extract normalized lab state."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from pkt_core.codec.container import decode_bytes

from pkt_grader.ios_parser import ParsedIOSConfig, normalize_interface_name, parse_ios_config


@dataclass
class ParsedDevice:
    name: str
    save_ref_id: str
    device_type: str
    model: str
    running_config_text: str = ""
    startup_config_text: str = ""
    ios: ParsedIOSConfig = field(default_factory=ParsedIOSConfig)
    vlans: set[int] = field(default_factory=set)
    ip: str = ""
    subnet: str = ""
    gateway: str = ""
    dhcp_enabled: bool = False
    dhcp_server_ip: str = ""
    up_method: str = ""
    dns_client_ip: str = ""
    dns_server_enabled: bool = False
    dns_records: list[str] = field(default_factory=list)


@dataclass
class ParsedLink:
    device_a: str
    port_a: str
    device_b: str
    port_b: str
    cable_type: str = ""


@dataclass
class ParsedLab:
    pt_version: str
    file_kind: str
    devices: dict[str, ParsedDevice] = field(default_factory=dict)
    links: list[ParsedLink] = field(default_factory=list)


_CTRL_RE = re.compile(rb"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _sanitize_xml(xml_bytes: bytes) -> bytes:
    """Strip non-XML-1.0 control characters (e.g. MOTD banner ^C) before parsing."""
    return _CTRL_RE.sub(b"", xml_bytes)


def _extract_network_element(root: ET.Element) -> ET.Element:
    """Locate the student <NETWORK> block across .pkt and .pka roots."""
    direct = root.find("NETWORK")
    if direct is not None:
        return direct
    for candidate in root.iter("NETWORK"):
        return candidate
    raise ValueError("Struktur XML Packet Tracer tidak memiliki elemen <NETWORK>.")


def _read_config_lines(el: ET.Element | None) -> str:
    if el is None:
        return ""
    lines = [(line.text or "") for line in el.findall("LINE")]
    return "\n".join(lines).strip()


def _extract_dns_server(eng: ET.Element) -> tuple[bool, list[str]]:
    dns_srv = eng.find("DNS_SERVER")
    if dns_srv is None:
        return False, []
    enabled = (dns_srv.findtext("ENABLED") or "").strip().lower() in ("1", "true")
    records: list[str] = []
    db = dns_srv.find("NAMESERVER-DATABASE")
    if db is not None:
        for rec in db:
            domain = (rec.findtext("NAME") or rec.findtext("DOMAIN") or rec.attrib.get("name", "")).strip()
            addr = (rec.findtext("IP") or rec.findtext("ADDRESS") or rec.findtext("VALUE") or "").strip()
            if domain and addr:
                records.append(f"{domain} -> {addr}")
            elif domain:
                records.append(domain)
    return enabled, records


def parse_pkt_bytes(data: bytes) -> ParsedLab:
    """Decode raw .pkt or .pka bytes and extract devices, IOS configs, and links."""
    container = decode_bytes(data)
    clean_xml = _sanitize_xml(container.xml)
    root = ET.fromstring(clean_xml)

    pt_version = root.findtext("VERSION") or ""
    file_kind = "pka" if container.is_activity else "pkt"

    network = _extract_network_element(root)
    devices_by_name: dict[str, ParsedDevice] = {}
    ref_to_name: dict[str, str] = {}

    for dev_el in network.findall("./DEVICES/DEVICE"):
        eng = dev_el.find("ENGINE")
        if eng is None:
            continue

        name = (eng.findtext("NAME") or "").strip()
        type_el = eng.find("TYPE")
        device_type = (type_el.text or "").strip() if type_el is not None else ""
        model = (type_el.attrib.get("model", "") if type_el is not None else "").strip()
        save_ref = (eng.findtext("SAVE_REF_ID") or "").strip()

        if not name:
            continue

        if save_ref:
            ref_to_name[save_ref] = name

        # Ignore Packet Tracer's implicit physical rack power distribution unit
        if device_type.lower() == "power distribution device":
            continue

        running_text = _read_config_lines(eng.find("RUNNINGCONFIG"))
        startup_text = _read_config_lines(eng.find("STARTUPCONFIG"))
        ios_parsed = parse_ios_config(running_text) if running_text else ParsedIOSConfig()

        vlans: set[int] = set(ios_parsed.vlans_in_config)
        vlans_el = eng.find("VLANS")
        if vlans_el is not None:
            for v_el in vlans_el.findall("VLAN"):
                num = v_el.attrib.get("number", "")
                if num.isdigit():
                    vlans.add(int(num))

        ip = ""
        subnet = ""
        gateway = (eng.findtext("GATEWAY") or "").strip()
        dhcp_enabled = False
        dhcp_server_ip = ""
        up_method = ""
        dns_client_ip = (eng.findtext("./DNS_CLIENT/SERVER_IP") or "").strip()

        for port_el in eng.findall(".//PORT"):
            port_type = (port_el.findtext("TYPE") or "").strip().lower()
            if port_type == "ebluetooth":
                continue

            p_ip = (port_el.findtext("IP") or "").strip()
            p_sub = (port_el.findtext("SUBNET") or "").strip()
            p_gw = (port_el.findtext("PORT_GATEWAY") or "").strip()
            p_dns = (port_el.findtext("PORT_DNS") or "").strip()
            p_dhcp = (port_el.findtext("PORT_DHCP_ENABLE") or "").strip().lower() == "true"
            p_dhcp_srv = (port_el.findtext("DHCP_SERVER_IP") or "").strip()
            p_up = (port_el.findtext("UP_METHOD") or "").strip()

            if p_ip or p_dhcp or p_gw or (p_dhcp_srv and p_dhcp_srv != "0.0.0.0"):
                ip = p_ip
                subnet = p_sub
                if p_gw:
                    gateway = p_gw
                if p_dns and not dns_client_ip:
                    dns_client_ip = p_dns
                dhcp_enabled = p_dhcp
                if p_dhcp_srv and p_dhcp_srv != "0.0.0.0":
                    dhcp_server_ip = p_dhcp_srv
                up_method = p_up
                break

        dns_server_enabled, dns_records = _extract_dns_server(eng)

        devices_by_name[name] = ParsedDevice(
            name=name,
            save_ref_id=save_ref,
            device_type=device_type,
            model=model,
            running_config_text=running_text,
            startup_config_text=startup_text,
            ios=ios_parsed,
            vlans=vlans,
            ip=ip,
            subnet=subnet,
            gateway=gateway,
            dhcp_enabled=dhcp_enabled,
            dhcp_server_ip=dhcp_server_ip,
            up_method=up_method,
            dns_client_ip=dns_client_ip,
            dns_server_enabled=dns_server_enabled,
            dns_records=dns_records,
        )

    links: list[ParsedLink] = []
    for link_el in network.findall("./LINKS/LINK"):
        cable = link_el.find("CABLE")
        if cable is None:
            continue
        from_ref = (cable.findtext("FROM") or "").strip()
        to_ref = (cable.findtext("TO") or "").strip()
        ports = [(p.text or "").strip() for p in cable.findall("PORT")]
        if len(ports) < 2:
            continue
        dev_a = ref_to_name.get(from_ref, from_ref)
        dev_b = ref_to_name.get(to_ref, to_ref)
        links.append(
            ParsedLink(
                device_a=dev_a,
                port_a=normalize_interface_name(ports[0]),
                device_b=dev_b,
                port_b=normalize_interface_name(ports[1]),
                cable_type=(cable.findtext("TYPE") or "").strip(),
            )
        )

    return ParsedLab(
        pt_version=pt_version,
        file_kind=file_kind,
        devices=devices_by_name,
        links=links,
    )
