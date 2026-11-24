"""Semantic Cisco IOS running-config parser for Switch & Router verification."""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field


@dataclass
class InterfaceConfig:
    name: str
    ip_address: str | None = None
    subnet_mask: str | None = None
    no_ip_address: bool = False
    shutdown: bool = False
    switchport_mode: str | None = None
    access_vlan: int | None = None
    trunk_allowed_vlans: set[int] | None = None
    trunk_allowed_explicit: bool = False
    dot1q_vlan: int | None = None
    raw_lines: list[str] = field(default_factory=list)


@dataclass
class DhcpPoolConfig:
    name: str
    network: str | None = None
    subnet_mask: str | None = None
    default_router: str | None = None
    dns_server: str | None = None
    raw_lines: list[str] = field(default_factory=list)


@dataclass
class StaticRoute:
    network: str
    subnet_mask: str
    next_hop: str
    raw_line: str


@dataclass
class ParsedIOSConfig:
    hostname: str = ""
    interfaces: dict[str, InterfaceConfig] = field(default_factory=dict)
    vlans_in_config: set[int] = field(default_factory=set)
    dhcp_excluded: list[tuple[str, str]] = field(default_factory=list)
    dhcp_pools: list[DhcpPoolConfig] = field(default_factory=list)
    static_routes: list[StaticRoute] = field(default_factory=list)


def normalize_interface_name(name: str) -> str:
    """Normalize Cisco interface names (e.g., Gi0/1.10 -> GigabitEthernet0/1.10)."""
    cleaned = name.strip()
    lower = cleaned.lower()
    prefixes = [
        ("gigabitethernet", "GigabitEthernet"),
        ("gig", "GigabitEthernet"),
        ("gi", "GigabitEthernet"),
        ("fastethernet", "FastEthernet"),
        ("fas", "FastEthernet"),
        ("fa", "FastEthernet"),
        ("ethernet", "Ethernet"),
        ("eth", "Ethernet"),
        ("serial", "Serial"),
        ("se", "Serial"),
        ("vlan", "Vlan"),
        ("loopback", "Loopback"),
        ("lo", "Loopback"),
    ]
    for short, full in prefixes:
        if lower.startswith(short):
            suffix = cleaned[len(short):].strip()
            return f"{full}{suffix}"
    return cleaned


def parse_vlan_list(spec: str) -> set[int]:
    """Parse Cisco VLAN list syntax such as '10,20' or '10-12,20'."""
    spec = spec.strip().lower()
    if spec in ("all", ""):
        return set(range(1, 4095))
    if spec == "none":
        return set()
    result: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            bounds = part.split("-", 1)
            if bounds[0].isdigit() and bounds[1].isdigit():
                start, end = int(bounds[0]), int(bounds[1])
                if start <= end:
                    result.update(range(start, end + 1))
        elif part.isdigit():
            result.add(int(part))
    return result


def is_ip_address(value: str) -> bool:
    try:
        ipaddress.IPv4Address(value)
        return True
    except ValueError:
        return False


def excluded_covers_range(
    excluded_ranges: list[tuple[str, str]], start_ip: str, end_ip: str
) -> tuple[bool, list[str]]:
    """Verify every IP from start_ip through end_ip is excluded by one or more rules."""
    start = int(ipaddress.IPv4Address(start_ip))
    end = int(ipaddress.IPv4Address(end_ip))
    parsed_ranges: list[tuple[int, int]] = []
    for low, high in excluded_ranges:
        try:
            lo_int = int(ipaddress.IPv4Address(low))
            hi_int = int(ipaddress.IPv4Address(high))
            if lo_int > hi_int:
                lo_int, hi_int = hi_int, lo_int
            parsed_ranges.append((lo_int, hi_int))
        except ValueError:
            continue

    missing: list[str] = []
    for ip_int in range(start, end + 1):
        if not any(lo <= ip_int <= hi for lo, hi in parsed_ranges):
            missing.append(str(ipaddress.IPv4Address(ip_int)))
    return len(missing) == 0, missing


def parse_ios_config(text: str) -> ParsedIOSConfig:
    """Parse Cisco IOS running-config text into structured networking sections."""
    parsed = ParsedIOSConfig()
    current_iface: InterfaceConfig | None = None
    current_pool: DhcpPoolConfig | None = None

    for raw in text.splitlines():
        if not raw.strip() or raw.strip() == "!":
            current_iface = None
            current_pool = None
            continue

        is_indented = raw[0].isspace()
        line = raw.strip()

        if not is_indented:
            current_iface = None
            current_pool = None

            if line.startswith("hostname "):
                parsed.hostname = line.split(None, 1)[1].strip()
                continue

            if line.startswith("interface "):
                iface_name = normalize_interface_name(line.split(None, 1)[1])
                current_iface = parsed.interfaces.get(iface_name)
                if current_iface is None:
                    current_iface = InterfaceConfig(name=iface_name)
                    parsed.interfaces[iface_name] = current_iface
                continue

            if line.startswith("ip dhcp pool "):
                pool_name = line[len("ip dhcp pool "):].strip()
                current_pool = DhcpPoolConfig(name=pool_name)
                parsed.dhcp_pools.append(current_pool)
                continue

            if line.startswith("ip dhcp excluded-address "):
                parts = line.split()
                if len(parts) == 4:
                    parsed.dhcp_excluded.append((parts[3], parts[3]))
                elif len(parts) >= 5:
                    parsed.dhcp_excluded.append((parts[3], parts[4]))
                continue

            if line.startswith("ip route "):
                parts = line.split()
                if len(parts) >= 5:
                    parsed.static_routes.append(
                        StaticRoute(
                            network=parts[2],
                            subnet_mask=parts[3],
                            next_hop=parts[4],
                            raw_line=line,
                        )
                    )
                continue

            m_vlan = re.match(r"^vlan\s+([\d,-]+)$", line, re.IGNORECASE)
            if m_vlan:
                parsed.vlans_in_config.update(parse_vlan_list(m_vlan.group(1)))
                continue
            continue

        # Indented sub-command inside interface or DHCP pool
        if current_iface is not None:
            current_iface.raw_lines.append(line)
            if line == "shutdown":
                current_iface.shutdown = True
            elif line == "no shutdown":
                current_iface.shutdown = False
            elif line == "no ip address":
                current_iface.no_ip_address = True
                current_iface.ip_address = None
                current_iface.subnet_mask = None
            elif line.startswith("ip address "):
                parts = line.split()
                if len(parts) >= 4:
                    current_iface.ip_address = parts[2]
                    current_iface.subnet_mask = parts[3]
                    current_iface.no_ip_address = False
            elif line.startswith("encapsulation dot1Q ") or line.startswith("encapsulation dot1q "):
                parts = line.split()
                if len(parts) >= 3 and parts[2].isdigit():
                    current_iface.dot1q_vlan = int(parts[2])
            elif line == "switchport mode access":
                current_iface.switchport_mode = "access"
            elif line == "switchport mode trunk":
                current_iface.switchport_mode = "trunk"
            elif line.startswith("switchport access vlan "):
                parts = line.split()
                if len(parts) >= 4 and parts[3].isdigit():
                    current_iface.access_vlan = int(parts[3])
            elif line.startswith("switchport trunk allowed vlan "):
                spec = line[len("switchport trunk allowed vlan "):].strip()
                current_iface.trunk_allowed_explicit = True
                if spec.startswith("add "):
                    added = parse_vlan_list(spec[4:])
                    if current_iface.trunk_allowed_vlans is None:
                        current_iface.trunk_allowed_vlans = set(added)
                    else:
                        current_iface.trunk_allowed_vlans.update(added)
                elif spec.startswith("remove "):
                    removed = parse_vlan_list(spec[7:])
                    if current_iface.trunk_allowed_vlans is None:
                        current_iface.trunk_allowed_vlans = set(range(1, 4095)) - removed
                    else:
                        current_iface.trunk_allowed_vlans.difference_update(removed)
                elif spec.startswith("except "):
                    excluded = parse_vlan_list(spec[7:])
                    current_iface.trunk_allowed_vlans = set(range(1, 4095)) - excluded
                else:
                    current_iface.trunk_allowed_vlans = parse_vlan_list(spec)

        elif current_pool is not None:
            current_pool.raw_lines.append(line)
            if line.startswith("network "):
                parts = line.split()
                if len(parts) >= 3:
                    current_pool.network = parts[1]
                    current_pool.subnet_mask = parts[2]
                elif len(parts) == 2 and "/" in parts[1]:
                    try:
                        net = ipaddress.IPv4Network(parts[1], strict=False)
                        current_pool.network = str(net.network_address)
                        current_pool.subnet_mask = str(net.netmask)
                    except ValueError:
                        pass
            elif line.startswith("default-router "):
                parts = line.split()
                if len(parts) >= 2:
                    current_pool.default_router = parts[1]
            elif line.startswith("dns-server "):
                parts = line.split()
                if len(parts) >= 2:
                    current_pool.dns_server = parts[1]

    return parsed
