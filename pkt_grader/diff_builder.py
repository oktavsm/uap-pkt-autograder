"""Semantic git-diff generator comparing student configs against reference key."""

from __future__ import annotations

from pkt_grader.ios_parser import (
    DhcpPoolConfig,
    InterfaceConfig,
    excluded_covers_range,
    normalize_interface_name,
)
from pkt_grader.models import DiffLine
from pkt_grader.parser import ParsedDevice, ParsedLab


def _get_device(lab: ParsedLab, target: str) -> ParsedDevice | None:
    if target in lab.devices:
        return lab.devices[target]
    lower = target.lower()
    for name, dev in lab.devices.items():
        if name.lower() == lower:
            return dev
    return None


def _get_iface(dev: ParsedDevice | None, iface_name: str) -> InterfaceConfig | None:
    if dev is None:
        return None
    norm = normalize_interface_name(iface_name)
    if norm in dev.ios.interfaces:
        return dev.ios.interfaces[norm]
    lower = norm.lower()
    for key, val in dev.ios.interfaces.items():
        if key.lower() == lower:
            return val
    return None


def _hdr(title: str) -> DiffLine:
    return DiffLine(kind="header", prefix="@@", text=title)


def _match(text: str, note: str = "") -> DiffLine:
    return DiffLine(kind="match", prefix=" ", text=text, note=note)


def _missing(text: str, note: str = "") -> DiffLine:
    return DiffLine(kind="missing", prefix="-", text=text, note=note)


def _extra(text: str, note: str = "") -> DiffLine:
    return DiffLine(kind="extra", prefix="+", text=text, note=note)


def _opt_match(text: str, note: str = "opsional") -> DiffLine:
    return DiffLine(kind="optional_match", prefix="+", text=text, note=note)


def _opt_missing(text: str, note: str = "opsional") -> DiffLine:
    return DiffLine(kind="optional_missing", prefix="~", text=text, note=note)


def _diff_s1(lab: ParsedLab) -> list[DiffLine]:
    lines: list[DiffLine] = []
    s1 = _get_device(lab, "S1")

    lines.append(_hdr("VLAN Database"))
    for vid in (10, 20):
        if s1 is not None and vid in s1.vlans:
            lines.append(_match(f"vlan {vid}"))
        else:
            lines.append(_missing(f"vlan {vid}", "belum dibuat"))

    for iface_name, target_vlan, desc in [
        ("FastEthernet0/1", 10, "PC1"),
        ("FastEthernet0/2", 20, "PC2"),
    ]:
        lines.append(_hdr(f"interface {iface_name} ({desc})"))
        iface = _get_iface(s1, iface_name)
        if iface is not None and iface.switchport_mode == "access":
            lines.append(_match(" switchport mode access"))
        else:
            lines.append(_missing(" switchport mode access"))
            if iface is not None and iface.switchport_mode:
                lines.append(_extra(f" switchport mode {iface.switchport_mode}", "tidak sesuai"))

        if iface is not None and iface.access_vlan == target_vlan:
            lines.append(_match(f" switchport access vlan {target_vlan}"))
        else:
            lines.append(_missing(f" switchport access vlan {target_vlan}"))
            if iface is not None and iface.access_vlan is not None:
                lines.append(_extra(f" switchport access vlan {iface.access_vlan}", "VLAN keliru"))

        if iface is not None and iface.shutdown:
            lines.append(_extra(" shutdown", "port harus aktif"))

    lines.append(_hdr("interface GigabitEthernet0/1 (Trunk ke R1)"))
    gi01 = _get_iface(s1, "GigabitEthernet0/1")
    if gi01 is not None and gi01.switchport_mode == "trunk":
        lines.append(_match(" switchport mode trunk"))
    else:
        lines.append(_missing(" switchport mode trunk"))
        if gi01 is not None and gi01.switchport_mode:
            lines.append(_extra(f" switchport mode {gi01.switchport_mode}", "tidak sesuai"))

    if gi01 is not None and gi01.trunk_allowed_explicit:
        allowed = gi01.trunk_allowed_vlans or set()
        actual_spec = ",".join(str(v) for v in sorted(allowed)) if allowed else "none"
        if {10, 20}.issubset(allowed):
            lines.append(_match(f" switchport trunk allowed vlan {actual_spec}"))
        else:
            lines.append(_missing(" switchport trunk allowed vlan 10,20"))
            lines.append(_extra(f" switchport trunk allowed vlan {actual_spec}", "belum mencakup 10,20"))
    else:
        lines.append(_missing(" switchport trunk allowed vlan 10,20", "belum dikonfigurasi eksplisit"))

    if gi01 is not None and gi01.shutdown:
        lines.append(_extra(" shutdown", "port harus aktif"))

    return lines


def _match_pool(pools: list[DhcpPoolConfig], net: str, gw: str) -> DhcpPoolConfig | None:
    for p in pools:
        if p.network == net:
            return p
    for p in pools:
        if p.default_router == gw:
            return p
    return None


def _diff_r1(lab: ParsedLab) -> list[DiffLine]:
    lines: list[DiffLine] = []
    r1 = _get_device(lab, "R1")

    lines.append(_hdr("DHCP Excluded Addresses"))
    excluded = r1.ios.dhcp_excluded if r1 is not None else []
    for lo, hi in [
        ("192.168.10.1", "192.168.10.10"),
        ("192.168.20.1", "192.168.20.10"),
    ]:
        ok, _ = excluded_covers_range(excluded, lo, hi)
        if ok:
            lines.append(_match(f"ip dhcp excluded-address {lo} {hi}"))
        else:
            lines.append(_missing(f"ip dhcp excluded-address {lo} {hi}"))

    pools = r1.ios.dhcp_pools if r1 is not None else []
    for default_name, net, mask, gw, label in [
        ("VLAN10", "192.168.10.0", "255.255.255.0", "192.168.10.1", "DHCP Pool VLAN 10"),
        ("VLAN20", "192.168.20.0", "255.255.255.0", "192.168.20.1", "DHCP Pool VLAN 20"),
    ]:
        lines.append(_hdr(label))
        pool = _match_pool(pools, net, gw)
        if pool is not None:
            lines.append(_match(f"ip dhcp pool {pool.name}", "nama pool bebas"))
            if pool.network == net and pool.subnet_mask == mask:
                lines.append(_match(f" network {net} {mask}"))
            else:
                lines.append(_missing(f" network {net} {mask}"))
                if pool.network:
                    lines.append(_extra(f" network {pool.network} {pool.subnet_mask or ''}", "tidak sesuai"))

            if pool.default_router == gw:
                lines.append(_match(f" default-router {gw}"))
            else:
                lines.append(_missing(f" default-router {gw}"))
                if pool.default_router:
                    lines.append(_extra(f" default-router {pool.default_router}", "gateway keliru"))

            if pool.dns_server == "192.168.30.2":
                lines.append(_opt_match(" dns-server 192.168.30.2", "DNS opsional aktif"))
            elif pool.dns_server:
                lines.append(_opt_missing(" dns-server 192.168.30.2", "opsional"))
                lines.append(_extra(f" dns-server {pool.dns_server}", "IP DNS bukan Server1 (192.168.30.2)"))
            else:
                lines.append(_opt_missing(" dns-server 192.168.30.2", "opsional"))
        else:
            lines.append(_missing(f"ip dhcp pool {default_name}"))
            lines.append(_missing(f" network {net} {mask}"))
            lines.append(_missing(f" default-router {gw}"))
            lines.append(_opt_missing(" dns-server 192.168.30.2", "opsional"))

    lines.append(_hdr("Interfaces (Konfigurasi Awal R1)"))
    for iface_name, exp_ip, exp_mask, dot1q in [
        ("GigabitEthernet0/0", "10.0.0.1", "255.255.255.252", None),
        ("GigabitEthernet0/1", None, None, None),
        ("GigabitEthernet0/1.10", "192.168.10.1", "255.255.255.0", 10),
        ("GigabitEthernet0/1.20", "192.168.20.1", "255.255.255.0", 20),
    ]:
        iface = _get_iface(r1, iface_name)
        lines.append(_match(f"interface {iface_name}"))
        if dot1q is not None:
            if iface is not None and iface.dot1q_vlan == dot1q:
                lines.append(_match(f" encapsulation dot1Q {dot1q}"))
            else:
                lines.append(_missing(f" encapsulation dot1Q {dot1q}"))
        if exp_ip is None:
            if iface is not None and iface.ip_address is None:
                lines.append(_match(" no ip address"))
            else:
                lines.append(_missing(" no ip address"))
                if iface is not None and iface.ip_address:
                    lines.append(_extra(f" ip address {iface.ip_address} {iface.subnet_mask or ''}", "seharusnya tanpa IP"))
        else:
            if iface is not None and iface.ip_address == exp_ip and iface.subnet_mask == exp_mask:
                lines.append(_match(f" ip address {exp_ip} {exp_mask}"))
            else:
                lines.append(_missing(f" ip address {exp_ip} {exp_mask}"))
                if iface is not None and iface.ip_address:
                    lines.append(_extra(f" ip address {iface.ip_address} {iface.subnet_mask or ''}", "IP berubah"))
        if iface is not None and iface.shutdown:
            lines.append(_extra(" shutdown", "interface harus aktif"))

    lines.append(_hdr("Static Routing"))
    routes = r1.ios.static_routes if r1 is not None else []
    target_line = "ip route 192.168.30.0 255.255.255.0 10.0.0.2"
    found = False
    for r in routes:
        if r.network == "192.168.30.0" and r.subnet_mask == "255.255.255.0" and r.next_hop == "10.0.0.2":
            lines.append(_match(target_line))
            found = True
        else:
            lines.append(_extra(r.raw_line, "rute lain / tidak sesuai kunci"))
    if not found:
        lines.append(_missing(target_line))

    return lines


def _diff_r2(lab: ParsedLab) -> list[DiffLine]:
    lines: list[DiffLine] = []
    r2 = _get_device(lab, "R2")

    lines.append(_hdr("Interfaces (Konfigurasi Awal R2)"))
    for iface_name, exp_ip, exp_mask in [
        ("GigabitEthernet0/0", "10.0.0.2", "255.255.255.252"),
        ("GigabitEthernet0/1", "192.168.30.1", "255.255.255.0"),
    ]:
        iface = _get_iface(r2, iface_name)
        lines.append(_match(f"interface {iface_name}"))
        if iface is not None and iface.ip_address == exp_ip and iface.subnet_mask == exp_mask:
            lines.append(_match(f" ip address {exp_ip} {exp_mask}"))
        else:
            lines.append(_missing(f" ip address {exp_ip} {exp_mask}"))
            if iface is not None and iface.ip_address:
                lines.append(_extra(f" ip address {iface.ip_address} {iface.subnet_mask or ''}", "IP berubah"))
        if iface is not None and iface.shutdown:
            lines.append(_extra(" shutdown", "interface harus aktif"))

    lines.append(_hdr("Static Routing"))
    routes = r2.ios.static_routes if r2 is not None else []
    expected_routes = [
        ("192.168.10.0", "255.255.255.0", "10.0.0.1"),
        ("192.168.20.0", "255.255.255.0", "10.0.0.1"),
    ]
    matched_keys: set[tuple[str, str, str]] = set()
    extra_routes: list[str] = []

    for r in routes:
        key = (r.network, r.subnet_mask, r.next_hop)
        if key in expected_routes:
            matched_keys.add(key)
        else:
            extra_routes.append(r.raw_line)

    for key in expected_routes:
        cmd = f"ip route {key[0]} {key[1]} {key[2]}"
        if key in matched_keys:
            lines.append(_match(cmd))
        else:
            lines.append(_missing(cmd))

    for raw in extra_routes:
        lines.append(_extra(raw, "rute lain / tidak sesuai kunci"))

    return lines


def _diff_server1_dns(lab: ParsedLab) -> list[DiffLine]:
    lines: list[DiffLine] = []
    srv = _get_device(lab, "Server1")

    lines.append(_hdr("Server1 · IP Statis (Konfigurasi Awal)"))
    if srv is not None and srv.ip == "192.168.30.2" and srv.subnet == "255.255.255.0" and srv.gateway == "192.168.30.1":
        lines.append(_match("IP: 192.168.30.2  Subnet: 255.255.255.0  Gateway: 192.168.30.1"))
    else:
        lines.append(_missing("IP: 192.168.30.2  Subnet: 255.255.255.0  Gateway: 192.168.30.1"))
        if srv is not None:
            lines.append(
                _extra(
                    f"IP: {srv.ip or '-'}  Subnet: {srv.subnet or '-'}  Gateway: {srv.gateway or '-'}",
                    "tidak sesuai template",
                )
            )

    lines.append(_hdr("Server1 · Layanan DNS (Opsional, Domain Bebas)"))
    if srv is not None and srv.dns_server_enabled:
        lines.append(_opt_match("DNS Service: On", "DNS opsional aktif"))
    else:
        lines.append(_opt_missing("DNS Service: On", "opsional"))

    if srv is not None and srv.dns_records:
        for rec in srv.dns_records:
            lines.append(_opt_match(f"A-Record: {rec}", "domain bebas terdeteksi"))
    else:
        lines.append(_opt_missing("A-Record: <domain-bebas> -> 192.168.30.2", "opsional"))

    return lines


def build_config_diffs(lab: ParsedLab) -> dict[str, list[DiffLine]]:
    """Build semantic git-diff blocks for S1, R1, R2, and Server1."""
    return {
        "S1": _diff_s1(lab),
        "R1": _diff_r1(lab),
        "R2": _diff_r2(lab),
        "Server1": _diff_server1_dns(lab),
    }
