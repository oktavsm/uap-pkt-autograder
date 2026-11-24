"""Semantic rule-based grading engine for UAP Jaringan Komputer PTI labs."""

from __future__ import annotations

import io
import ipaddress
import re
import statistics
import zipfile
from collections import Counter
from pathlib import Path
from typing import Iterable

from pkt_grader.diff_builder import build_config_diffs
from pkt_grader.ios_parser import (
    InterfaceConfig,
    excluded_covers_range,
    is_ip_address,
    normalize_interface_name,
)
from pkt_grader.models import (
    BatchReport,
    BatchSummary,
    CheckResult,
    DeviceSnapshot,
    OPTIONAL_CHECK_IDS,
    RubricConfig,
    StudentReport,
)
from pkt_grader.parser import ParsedDevice, ParsedLab, parse_pkt_bytes


EXPECTED_DEVICES = ("PC1", "PC2", "S1", "R1", "R2", "Server1")

EXPECTED_LINKS: list[tuple[tuple[str, str], tuple[str, str]]] = [
    (("PC1", "FastEthernet0"), ("S1", "FastEthernet0/1")),
    (("PC2", "FastEthernet0"), ("S1", "FastEthernet0/2")),
    (("S1", "GigabitEthernet0/1"), ("R1", "GigabitEthernet0/1")),
    (("R1", "GigabitEthernet0/0"), ("R2", "GigabitEthernet0/0")),
    (("R2", "GigabitEthernet0/1"), ("Server1", "FastEthernet0")),
]

MAX_ARCHIVE_ENTRY_BYTES = 50 * 1024 * 1024  # 50 MB safety cap per .pkt/.pka entry


def extract_student_identity(filename: str) -> tuple[str, str]:
    """Parse NIM and student name from conventions like UAP_245150600111001_Budi_Santoso.pkt."""
    stem = Path(filename).stem.strip()
    cleaned = re.sub(r"^(uap|uas|uts|praktikum)[_\-\s]+", "", stem, flags=re.IGNORECASE)

    m = re.match(r"^(\d{8,20})(?:[_\-\s]+(.*))?$", cleaned)
    if m:
        nim = m.group(1)
        name_part = (m.group(2) or "").strip(" _-")
        name = re.sub(r"[_\-]+", " ", name_part).strip()
        return nim, name

    m_any = re.search(r"(\d{8,20})", stem)
    if m_any:
        nim = m_any.group(1)
        remainder = (stem[: m_any.start()] + " " + stem[m_any.end() :]).strip()
        remainder = re.sub(r"\b(uap|uas|uts|praktikum)\b", "", remainder, flags=re.IGNORECASE)
        name = re.sub(r"[_\-\s]+", " ", remainder).strip()
        return nim, name

    return "", re.sub(r"[_\-]+", " ", stem).strip()


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


def _make_check(
    check_id: str,
    category: str,
    device: str,
    title: str,
    rubric: RubricConfig,
    earned_ratio: float,
    expected: str,
    actual: str,
    message: str,
    optional: bool = False,
) -> CheckResult:
    possible = rubric.weight(check_id)
    ratio = max(0.0, min(1.0, earned_ratio))
    earned = round(possible * ratio, 2)
    if optional and ratio <= 0.0:
        status = "optional"
    elif ratio >= 0.999:
        status = "pass"
    elif ratio > 0.0:
        status = "partial"
    else:
        status = "fail"
    return CheckResult(
        id=check_id,
        category=category,
        device=device,
        title=title,
        status=status,
        optional=optional,
        points_earned=earned,
        points_possible=possible,
        expected=expected,
        actual=actual,
        message=message,
    )


def _check_topology(lab: ParsedLab, rubric: RubricConfig) -> list[CheckResult]:
    checks: list[CheckResult] = []

    present_lower = {k.lower(): k for k in lab.devices}
    missing = [d for d in EXPECTED_DEVICES if d.lower() not in present_lower]
    extra = [
        k for k in lab.devices if k.lower() not in {d.lower() for d in EXPECTED_DEVICES}
    ]

    if not missing and not extra:
        checks.append(
            _make_check(
                "topo_devices",
                "Topologi",
                "Topologi",
                "Kelengkapan perangkat topologi",
                rubric,
                1.0,
                ", ".join(EXPECTED_DEVICES),
                ", ".join(sorted(lab.devices.keys())),
                "Seluruh 6 perangkat utama tersedia sesuai template.",
            )
        )
    else:
        parts = []
        if missing:
            parts.append(f"perangkat hilang: {', '.join(missing)}")
        if extra:
            parts.append(f"perangkat tambahan tidak sesuai aturan: {', '.join(extra)}")
        ratio = max(0.0, (len(EXPECTED_DEVICES) - len(missing)) / len(EXPECTED_DEVICES))
        if extra:
            ratio = min(ratio, 0.5)
        checks.append(
            _make_check(
                "topo_devices",
                "Topologi",
                "Topologi",
                "Kelengkapan perangkat topologi",
                rubric,
                ratio,
                ", ".join(EXPECTED_DEVICES),
                ", ".join(sorted(lab.devices.keys())),
                "Ketidaksesuaian perangkat: " + "; ".join(parts) + ".",
            )
        )

    actual_edges: set[frozenset[tuple[str, str]]] = set()
    for lnk in lab.links:
        a = (lnk.device_a.lower(), normalize_interface_name(lnk.port_a).lower())
        b = (lnk.device_b.lower(), normalize_interface_name(lnk.port_b).lower())
        actual_edges.add(frozenset((a, b)))

    missing_links: list[str] = []
    for (da, pa), (db, pb) in EXPECTED_LINKS:
        edge = frozenset(
            (
                (da.lower(), normalize_interface_name(pa).lower()),
                (db.lower(), normalize_interface_name(pb).lower()),
            )
        )
        if edge not in actual_edges:
            missing_links.append(f"{da}:{pa} <-> {db}:{pb}")

    if not missing_links:
        checks.append(
            _make_check(
                "topo_links",
                "Topologi",
                "Topologi",
                "Pemetaan koneksi kabel (5 link)",
                rubric,
                1.0,
                "5 link sesuai tabel koneksi",
                f"{len(lab.links)} link terdeteksi, seluruh koneksi sesuai",
                "Seluruh koneksi kabel sesuai pemetaan pada brief.",
            )
        )
    else:
        matched = len(EXPECTED_LINKS) - len(missing_links)
        checks.append(
            _make_check(
                "topo_links",
                "Topologi",
                "Topologi",
                "Pemetaan koneksi kabel (5 link)",
                rubric,
                matched / len(EXPECTED_LINKS),
                "5 link sesuai tabel koneksi",
                f"{matched}/5 link cocok",
                "Link tidak sesuai atau terputus: " + "; ".join(missing_links) + ".",
            )
        )
    return checks


def _check_switch_s1(lab: ParsedLab, rubric: RubricConfig) -> list[CheckResult]:
    checks: list[CheckResult] = []
    s1 = _get_device(lab, "S1")
    if s1 is None:
        for cid, title in [
            ("s1_vlans", "Pembuatan VLAN 10 dan VLAN 20"),
            ("s1_access_fa01", "Port access FastEthernet0/1 untuk VLAN 10"),
            ("s1_access_fa02", "Port access FastEthernet0/2 untuk VLAN 20"),
            ("s1_trunk_mode", "Mode trunk pada GigabitEthernet0/1"),
            ("s1_trunk_allowed", "Allowed VLAN 10,20 pada trunk GigabitEthernet0/1"),
        ]:
            checks.append(
                _make_check(
                    cid, "VLAN & Switch", "S1", title, rubric, 0.0,
                    "Perangkat S1 terkonfigurasi", "S1 tidak ditemukan",
                    "Perangkat S1 tidak ditemukan pada topologi.",
                )
            )
        return checks

    has_v10 = 10 in s1.vlans
    has_v20 = 20 in s1.vlans
    found_vlans = sorted(v for v in s1.vlans if v not in (1, 1002, 1003, 1004, 1005))
    if has_v10 and has_v20:
        checks.append(
            _make_check(
                "s1_vlans", "VLAN & Switch", "S1", "Pembuatan VLAN 10 dan VLAN 20",
                rubric, 1.0, "VLAN 10 dan VLAN 20 aktif",
                f"VLAN terdaftar: {found_vlans}",
                "VLAN 10 dan VLAN 20 terdaftar pada switch S1.",
            )
        )
    else:
        missing = [str(v) for v, ok in ((10, has_v10), (20, has_v20)) if not ok]
        ratio = 0.5 if (has_v10 or has_v20) else 0.0
        checks.append(
            _make_check(
                "s1_vlans", "VLAN & Switch", "S1", "Pembuatan VLAN 10 dan VLAN 20",
                rubric, ratio, "VLAN 10 dan VLAN 20 aktif",
                f"VLAN terdaftar: {found_vlans or ['hanya default']}",
                f"VLAN belum dibuat pada S1: VLAN {', '.join(missing)}.",
            )
        )

    for cid, iface_name, target_vlan, pc_label in [
        ("s1_access_fa01", "FastEthernet0/1", 10, "PC1"),
        ("s1_access_fa02", "FastEthernet0/2", 20, "PC2"),
    ]:
        iface = _get_iface(s1, iface_name)
        if iface is None:
            checks.append(
                _make_check(
                    cid, "VLAN & Switch", "S1", f"Port access {iface_name} untuk VLAN {target_vlan}",
                    rubric, 0.0,
                    f"mode access, access vlan {target_vlan}, aktif",
                    "interface tidak ditemukan di running-config",
                    f"Interface {iface_name} ({pc_label}) belum dikonfigurasi.",
                )
            )
            continue

        mode_ok = iface.switchport_mode == "access"
        vlan_ok = iface.access_vlan == target_vlan
        up_ok = not iface.shutdown
        actual_desc = (
            f"mode={iface.switchport_mode or 'default'}, "
            f"access_vlan={iface.access_vlan or '1(default)'}, "
            f"status={'shutdown' if iface.shutdown else 'up'}"
        )

        if mode_ok and vlan_ok and up_ok:
            checks.append(
                _make_check(
                    cid, "VLAN & Switch", "S1", f"Port access {iface_name} untuk VLAN {target_vlan}",
                    rubric, 1.0,
                    f"mode access, access vlan {target_vlan}, up",
                    actual_desc,
                    f"{iface_name} sudah diatur sebagai port access VLAN {target_vlan}.",
                )
            )
        else:
            issues = []
            score_parts = 0.0
            if mode_ok:
                score_parts += 0.4
            else:
                issues.append("belum diatur 'switchport mode access'")
            if vlan_ok:
                score_parts += 0.5
            else:
                issues.append(
                    f"access vlan bernilai {iface.access_vlan or 'default(1)'}, seharusnya {target_vlan}"
                )
            if up_ok:
                score_parts += 0.1
            else:
                issues.append("interface dalam keadaan shutdown")
            if not mode_ok and not vlan_ok:
                score_parts = 0.0
            checks.append(
                _make_check(
                    cid, "VLAN & Switch", "S1", f"Port access {iface_name} untuk VLAN {target_vlan}",
                    rubric, score_parts,
                    f"mode access, access vlan {target_vlan}, up",
                    actual_desc,
                    f"Kesalahan pada {iface_name}: " + "; ".join(issues) + ".",
                )
            )

    gi01 = _get_iface(s1, "GigabitEthernet0/1")
    if gi01 is None:
        checks.append(
            _make_check(
                "s1_trunk_mode", "VLAN & Switch", "S1", "Mode trunk pada GigabitEthernet0/1",
                rubric, 0.0, "switchport mode trunk, up", "tidak dikonfigurasi",
                "Interface GigabitEthernet0/1 ke R1 belum diatur sebagai trunk.",
            )
        )
        checks.append(
            _make_check(
                "s1_trunk_allowed", "VLAN & Switch", "S1", "Allowed VLAN 10,20 pada trunk GigabitEthernet0/1",
                rubric, 0.0, "switchport trunk allowed vlan 10,20", "tidak dikonfigurasi",
                "Interface GigabitEthernet0/1 belum memiliki konfigurasi trunk.",
            )
        )
        return checks

    trunk_ok = gi01.switchport_mode == "trunk" and not gi01.shutdown
    if trunk_ok:
        checks.append(
            _make_check(
                "s1_trunk_mode", "VLAN & Switch", "S1", "Mode trunk pada GigabitEthernet0/1",
                rubric, 1.0, "switchport mode trunk, up",
                f"mode={gi01.switchport_mode}, status=up",
                "GigabitEthernet0/1 berstatus trunk aktif menuju R1.",
            )
        )
    else:
        issues = []
        if gi01.switchport_mode != "trunk":
            issues.append(f"mode saat ini '{gi01.switchport_mode or 'default'}', seharusnya trunk")
        if gi01.shutdown:
            issues.append("port dalam keadaan shutdown")
        checks.append(
            _make_check(
                "s1_trunk_mode", "VLAN & Switch", "S1", "Mode trunk pada GigabitEthernet0/1",
                rubric, 0.0, "switchport mode trunk, up",
                f"mode={gi01.switchport_mode or 'default'}, status={'shutdown' if gi01.shutdown else 'up'}",
                "Trunk Gi0/1 belum valid: " + "; ".join(issues) + ".",
            )
        )

    if gi01.trunk_allowed_explicit:
        allowed = gi01.trunk_allowed_vlans or set()
        has_10 = 10 in allowed
        has_20 = 20 in allowed
        allowed_label = ",".join(str(v) for v in sorted(allowed)) if allowed else "none"
        if has_10 and has_20:
            checks.append(
                _make_check(
                    "s1_trunk_allowed", "VLAN & Switch", "S1", "Allowed VLAN 10,20 pada trunk GigabitEthernet0/1",
                    rubric, 1.0, "VLAN 10 dan 20 diizinkan",
                    f"allowed vlan {allowed_label}",
                    "Trunk Gi0/1 secara eksplisit mengizinkan VLAN 10 dan 20.",
                )
            )
        else:
            missing_v = [str(v) for v, ok in ((10, has_10), (20, has_20)) if not ok]
            ratio = 0.5 if (has_10 or has_20) else 0.0
            checks.append(
                _make_check(
                    "s1_trunk_allowed", "VLAN & Switch", "S1", "Allowed VLAN 10,20 pada trunk GigabitEthernet0/1",
                    rubric, ratio, "VLAN 10 dan 20 diizinkan",
                    f"allowed vlan {allowed_label}",
                    f"Daftar allowed VLAN trunk tidak mencakup VLAN {', '.join(missing_v)}.",
                )
            )
    else:
        if trunk_ok and not rubric.require_explicit_trunk_allowed:
            checks.append(
                _make_check(
                    "s1_trunk_allowed", "VLAN & Switch", "S1", "Allowed VLAN 10,20 pada trunk GigabitEthernet0/1",
                    rubric, 1.0, "VLAN 10 dan 20 diizinkan",
                    "default (semua VLAN diizinkan)",
                    "Trunk aktif dengan izin default (mencakup VLAN 10 dan 20).",
                )
            )
        elif trunk_ok:
            checks.append(
                _make_check(
                    "s1_trunk_allowed", "VLAN & Switch", "S1", "Allowed VLAN 10,20 pada trunk GigabitEthernet0/1",
                    rubric, 0.5, "switchport trunk allowed vlan 10,20",
                    "default (tidak eksplisit)",
                    "Trunk aktif tetapi perintah 'switchport trunk allowed vlan 10,20' tidak dikonfigurasi secara eksplisit.",
                )
            )
        else:
            checks.append(
                _make_check(
                    "s1_trunk_allowed", "VLAN & Switch", "S1", "Allowed VLAN 10,20 pada trunk GigabitEthernet0/1",
                    rubric, 0.0, "switchport trunk allowed vlan 10,20",
                    "tidak dikonfigurasi",
                    "Trunk dan allowed VLAN belum dikonfigurasi pada Gi0/1.",
                )
            )

    return checks


def _check_router_r1(lab: ParsedLab, rubric: RubricConfig) -> list[CheckResult]:
    checks: list[CheckResult] = []
    r1 = _get_device(lab, "R1")
    if r1 is None:
        for cid, cat, title in [
            ("r1_base_ip", "DHCP & R1", "Integritas IP interface awal R1"),
            ("r1_dhcp_excl_10", "DHCP & R1", "DHCP excluded-address VLAN 10 (.1-.10)"),
            ("r1_dhcp_excl_20", "DHCP & R1", "DHCP excluded-address VLAN 20 (.1-.10)"),
            ("r1_dhcp_pool_10", "DHCP & R1", "DHCP pool subnet VLAN 10"),
            ("r1_dhcp_pool_20", "DHCP & R1", "DHCP pool subnet VLAN 20"),
            ("r1_route_lanb", "Static Routing", "Static route R1 menuju LAN B (192.168.30.0/24)"),
        ]:
            checks.append(
                _make_check(
                    cid, cat, "R1", title, rubric, 0.0,
                    "Perangkat R1 terkonfigurasi", "R1 tidak ditemukan",
                    "Perangkat R1 tidak ditemukan pada topologi.",
                )
            )
        return checks

    base_issues: list[str] = []
    gi00 = _get_iface(r1, "GigabitEthernet0/0")
    if not gi00 or gi00.ip_address != "10.0.0.1" or gi00.subnet_mask != "255.255.255.252" or gi00.shutdown:
        base_issues.append("Gi0/0 seharusnya 10.0.0.1/30 dan aktif")

    gi01 = _get_iface(r1, "GigabitEthernet0/1")
    if not gi01 or gi01.shutdown or gi01.ip_address is not None:
        base_issues.append("Gi0/1 induk seharusnya tanpa IP dan aktif")

    gi01_10 = _get_iface(r1, "GigabitEthernet0/1.10")
    if (
        not gi01_10
        or gi01_10.dot1q_vlan != 10
        or gi01_10.ip_address != "192.168.10.1"
        or gi01_10.subnet_mask != "255.255.255.0"
        or gi01_10.shutdown
    ):
        base_issues.append("Gi0/1.10 seharusnya dot1Q 10 dengan IP 192.168.10.1/24")

    gi01_20 = _get_iface(r1, "GigabitEthernet0/1.20")
    if (
        not gi01_20
        or gi01_20.dot1q_vlan != 20
        or gi01_20.ip_address != "192.168.20.1"
        or gi01_20.subnet_mask != "255.255.255.0"
        or gi01_20.shutdown
    ):
        base_issues.append("Gi0/1.20 seharusnya dot1Q 20 dengan IP 192.168.20.1/24")

    if not base_issues:
        checks.append(
            _make_check(
                "r1_base_ip", "DHCP & R1", "R1", "Integritas IP interface awal R1",
                rubric, 1.0,
                "Gi0/0 10.0.0.1/30, Gi0/1.10 192.168.10.1/24, Gi0/1.20 192.168.20.1/24",
                "Semua interface awal R1 sesuai dan aktif",
                "Konfigurasi IP interface dan subinterface awal R1 tetap utuh.",
            )
        )
    else:
        ratio = max(0.0, (4 - len(base_issues)) / 4)
        checks.append(
            _make_check(
                "r1_base_ip", "DHCP & R1", "R1", "Integritas IP interface awal R1",
                rubric, ratio,
                "Gi0/0 10.0.0.1/30, Gi0/1.10 192.168.10.1/24, Gi0/1.20 192.168.20.1/24",
                f"{4 - len(base_issues)}/4 interface sesuai",
                "Perubahan tidak sesuai ketentuan pada IP awal R1: " + "; ".join(base_issues) + ".",
            )
        )

    excl_summary = (
        ", ".join(f"{lo}-{hi}" if lo != hi else lo for lo, hi in r1.ios.dhcp_excluded)
        or "tidak ada"
    )
    for cid, label, lo_ip, hi_ip in [
        ("r1_dhcp_excl_10", "VLAN 10 (.1-.10)", "192.168.10.1", "192.168.10.10"),
        ("r1_dhcp_excl_20", "VLAN 20 (.1-.10)", "192.168.20.1", "192.168.20.10"),
    ]:
        ok, missing_ips = excluded_covers_range(r1.ios.dhcp_excluded, lo_ip, hi_ip)
        if ok:
            checks.append(
                _make_check(
                    cid, "DHCP & R1", "R1", f"DHCP excluded-address {label}",
                    rubric, 1.0, f"{lo_ip} s/d {hi_ip}", excl_summary,
                    f"Rentang {lo_ip} sampai {hi_ip} sudah dikecualikan dari DHCP.",
                )
            )
        else:
            covered = 10 - len(missing_ips)
            ratio = round(covered / 10, 2) if covered > 0 else 0.0
            checks.append(
                _make_check(
                    cid, "DHCP & R1", "R1", f"DHCP excluded-address {label}",
                    rubric, ratio, f"{lo_ip} s/d {hi_ip}", excl_summary,
                    f"Alamat belum dikecualikan pada {label} ({len(missing_ips)} alamat kurang, mis. {missing_ips[0]}).",
                )
            )

    for cid, vlan_label, exp_net, exp_mask, exp_gw in [
        ("r1_dhcp_pool_10", "VLAN 10", "192.168.10.0", "255.255.255.0", "192.168.10.1"),
        ("r1_dhcp_pool_20", "VLAN 20", "192.168.20.0", "255.255.255.0", "192.168.20.1"),
    ]:
        matching_pools = [
            p for p in r1.ios.dhcp_pools if p.network == exp_net and p.subnet_mask == exp_mask
        ]
        exact = [p for p in matching_pools if p.default_router == exp_gw]
        if exact:
            pool = exact[0]
            checks.append(
                _make_check(
                    cid, "DHCP & R1", "R1", f"DHCP pool subnet {vlan_label}",
                    rubric, 1.0,
                    f"network {exp_net} {exp_mask}, default-router {exp_gw}",
                    f"pool '{pool.name}': network {pool.network} {pool.subnet_mask}, default-router {pool.default_router}",
                    f"Pool DHCP '{pool.name}' untuk {vlan_label} terkonfigurasi dengan benar.",
                )
            )
        elif matching_pools:
            pool = matching_pools[0]
            checks.append(
                _make_check(
                    cid, "DHCP & R1", "R1", f"DHCP pool subnet {vlan_label}",
                    rubric, 0.5,
                    f"network {exp_net} {exp_mask}, default-router {exp_gw}",
                    f"pool '{pool.name}': network {pool.network} {pool.subnet_mask}, default-router {pool.default_router or 'kosong'}",
                    f"Network pool '{pool.name}' benar, tetapi default-router bernilai '{pool.default_router or 'kosong'}' (seharusnya {exp_gw}).",
                )
            )
        else:
            near = [p for p in r1.ios.dhcp_pools if p.default_router == exp_gw or p.network == exp_net]
            if near:
                p = near[0]
                checks.append(
                    _make_check(
                        cid, "DHCP & R1", "R1", f"DHCP pool subnet {vlan_label}",
                        rubric, 0.25,
                        f"network {exp_net} {exp_mask}, default-router {exp_gw}",
                        f"pool '{p.name}': network {p.network or 'kosong'} {p.subnet_mask or ''}, default-router {p.default_router or 'kosong'}",
                        f"Pool '{p.name}' tidak sesuai spesifikasi network/mask {exp_net} {exp_mask}.",
                    )
                )
            else:
                pool_names = [p.name for p in r1.ios.dhcp_pools]
                checks.append(
                    _make_check(
                        cid, "DHCP & R1", "R1", f"DHCP pool subnet {vlan_label}",
                        rubric, 0.0,
                        f"network {exp_net} {exp_mask}, default-router {exp_gw}",
                        f"pool ditemukan: {pool_names or 'tidak ada'}",
                        f"Tidak ditemukan DHCP pool untuk subnet {exp_net}/24.",
                    )
                )

    checks.append(
        _check_static_route(
            dev=r1,
            check_id="r1_route_lanb",
            device_label="R1",
            title="Static route R1 menuju LAN B (192.168.30.0/24)",
            target_net="192.168.30.0",
            target_mask="255.255.255.0",
            expected_nh="10.0.0.2",
            expected_exit="GigabitEthernet0/0",
            rubric=rubric,
        )
    )

    return checks


def _check_static_route(
    dev: ParsedDevice,
    check_id: str,
    device_label: str,
    title: str,
    target_net: str,
    target_mask: str,
    expected_nh: str,
    expected_exit: str,
    rubric: RubricConfig,
) -> CheckResult:
    routes = dev.ios.static_routes
    routes_summary = "; ".join(r.raw_line for r in routes) or "tidak ada static route"

    for r in routes:
        if r.network == target_net and r.subnet_mask == target_mask and r.next_hop == expected_nh:
            return _make_check(
                check_id, "Static Routing", device_label, title, rubric, 1.0,
                f"ip route {target_net} {target_mask} {expected_nh}",
                r.raw_line,
                f"Static route menuju {target_net}/24 melalui next-hop {expected_nh} valid.",
            )

    for r in routes:
        if (
            r.network == target_net
            and r.subnet_mask == target_mask
            and normalize_interface_name(r.next_hop).lower() == expected_exit.lower()
        ):
            ratio = 1.0 if rubric.allow_exit_interface_route else 0.7
            msg = (
                f"Static route memakai exit-interface {r.next_hop} (diterima oleh rubrik)."
                if rubric.allow_exit_interface_route
                else f"Static route memakai exit-interface ({r.next_hop}), padahal brief meminta alamat next-hop IP ({expected_nh})."
            )
            return _make_check(
                check_id, "Static Routing", device_label, title, rubric, ratio,
                f"ip route {target_net} {target_mask} {expected_nh}",
                r.raw_line,
                msg,
            )

    for r in routes:
        if r.network == "0.0.0.0" and r.subnet_mask == "0.0.0.0" and r.next_hop == expected_nh:
            return _make_check(
                check_id, "Static Routing", device_label, title, rubric, 0.5,
                f"ip route {target_net} {target_mask} {expected_nh}",
                r.raw_line,
                f"Menggunakan default route (0.0.0.0/0), bukan rute spesifik ke {target_net}/24.",
            )

    for r in routes:
        if r.network == target_net:
            return _make_check(
                check_id, "Static Routing", device_label, title, rubric, 0.25,
                f"ip route {target_net} {target_mask} {expected_nh}",
                r.raw_line,
                f"Mask atau next-hop keliru: tertulis '{r.subnet_mask} {r.next_hop}', seharusnya '{target_mask} {expected_nh}'.",
            )

    target_subnet = ipaddress.IPv4Network(f"{target_net}/{target_mask}", strict=False)
    for r in routes:
        if is_ip_address(r.network) and ipaddress.IPv4Address(r.network) in target_subnet:
            return _make_check(
                check_id, "Static Routing", device_label, title, rubric, 0.25,
                f"ip route {target_net} {target_mask} {expected_nh}",
                r.raw_line,
                f"Menggunakan IP host ({r.network}) alih-alih network address ({target_net}).",
            )

    return _make_check(
        check_id, "Static Routing", device_label, title, rubric, 0.0,
        f"ip route {target_net} {target_mask} {expected_nh}",
        routes_summary,
        f"Static route menuju {target_net}/24 belum dikonfigurasi pada {device_label}.",
    )


def _check_router_r2(lab: ParsedLab, rubric: RubricConfig) -> list[CheckResult]:
    checks: list[CheckResult] = []
    r2 = _get_device(lab, "R2")
    srv = _get_device(lab, "Server1")

    base_issues: list[str] = []
    if r2 is None:
        base_issues.append("R2 tidak ditemukan")
    else:
        gi00 = _get_iface(r2, "GigabitEthernet0/0")
        if not gi00 or gi00.ip_address != "10.0.0.2" or gi00.subnet_mask != "255.255.255.252" or gi00.shutdown:
            base_issues.append("R2 Gi0/0 seharusnya 10.0.0.2/30 dan aktif")
        gi01 = _get_iface(r2, "GigabitEthernet0/1")
        if not gi01 or gi01.ip_address != "192.168.30.1" or gi01.subnet_mask != "255.255.255.0" or gi01.shutdown:
            base_issues.append("R2 Gi0/1 seharusnya 192.168.30.1/24 dan aktif")

    if srv is None:
        base_issues.append("Server1 tidak ditemukan")
    else:
        if srv.ip != "192.168.30.2" or srv.subnet != "255.255.255.0" or srv.gateway != "192.168.30.1":
            base_issues.append(
                f"Server1 seharusnya 192.168.30.2/24 GW 192.168.30.1 (aktual: {srv.ip or 'kosong'}/{srv.subnet or '-'} GW {srv.gateway or '-'})"
            )

    if not base_issues:
        checks.append(
            _make_check(
                "r2_base_ip", "Static Routing", "R2", "Integritas IP awal R2 dan Server1",
                rubric, 1.0,
                "R2 Gi0/0 10.0.0.2/30, Gi0/1 192.168.30.1/24; Server1 192.168.30.2/24",
                "Semua IP awal R2 dan Server1 utuh",
                "Konfigurasi IP awal pada R2 dan Server1 tetap sesuai template.",
            )
        )
    else:
        ratio = max(0.0, (3 - len(base_issues)) / 3)
        checks.append(
            _make_check(
                "r2_base_ip", "Static Routing", "R2", "Integritas IP awal R2 dan Server1",
                rubric, ratio,
                "R2 Gi0/0 10.0.0.2/30, Gi0/1 192.168.30.1/24; Server1 192.168.30.2/24",
                "; ".join(base_issues),
                "Perubahan tidak sesuai ketentuan pada IP awal R2/Server1: " + "; ".join(base_issues) + ".",
            )
        )

    if r2 is None:
        for cid, title in [
            ("r2_route_vlan10", "Static route R2 menuju VLAN 10 (192.168.10.0/24)"),
            ("r2_route_vlan20", "Static route R2 menuju VLAN 20 (192.168.20.0/24)"),
        ]:
            checks.append(
                _make_check(
                    cid, "Static Routing", "R2", title, rubric, 0.0,
                    "Perangkat R2 terkonfigurasi", "R2 tidak ditemukan",
                    "Perangkat R2 tidak ditemukan pada topologi.",
                )
            )
        return checks

    checks.append(
        _check_static_route(
            dev=r2,
            check_id="r2_route_vlan10",
            device_label="R2",
            title="Static route R2 menuju VLAN 10 (192.168.10.0/24)",
            target_net="192.168.10.0",
            target_mask="255.255.255.0",
            expected_nh="10.0.0.1",
            expected_exit="GigabitEthernet0/0",
            rubric=rubric,
        )
    )
    checks.append(
        _check_static_route(
            dev=r2,
            check_id="r2_route_vlan20",
            device_label="R2",
            title="Static route R2 menuju VLAN 20 (192.168.20.0/24)",
            target_net="192.168.20.0",
            target_mask="255.255.255.0",
            expected_nh="10.0.0.1",
            expected_exit="GigabitEthernet0/0",
            rubric=rubric,
        )
    )
    return checks


def _check_pc_dhcp(
    lab: ParsedLab,
    rubric: RubricConfig,
    check_id: str,
    pc_name: str,
    range_start: str,
    range_end: str,
    exp_mask: str,
    exp_gw: str,
) -> CheckResult:
    """Verify PC DHCP client mode and successful DHCP lease from R1.

    Packet Tracer 8.x/9.x clears dynamic <IP>/<SUBNET> when saving a DHCP-enabled
    host to .pkt XML, while persisting <PORT_DHCP_ENABLE>true</PORT_DHCP_ENABLE>,
    <DHCP_SERVER_IP> (from the replying DHCP server), and <GATEWAY>.
    """
    pc = _get_device(lab, pc_name)
    expected_str = f"DHCP aktif, DHCP Server {exp_gw}, Gateway {exp_gw} (rentang {range_start}-{range_end})"
    if pc is None:
        return _make_check(
            check_id, "End Device DHCP", pc_name, f"DHCP client & lease pada {pc_name}",
            rubric, 0.0, expected_str, f"{pc_name} tidak ditemukan",
            f"Perangkat {pc_name} tidak ditemukan pada topologi.",
        )

    ip_display = pc.ip if pc.ip else "dinamis (DHCP)"
    mask_display = pc.subnet if pc.subnet else (exp_mask if pc.dhcp_enabled and pc.dhcp_server_ip == exp_gw else "-")
    actual_str = (
        f"DHCP={'aktif' if pc.dhcp_enabled else 'statis'}, "
        f"DHCP_Server={pc.dhcp_server_ip or '-'}, "
        f"GW={pc.gateway or '-'}, IP={ip_display}, mask={mask_display}"
    )

    # Validate explicit IP/mask if serialized in the XML
    has_explicit_ip = bool(pc.ip)
    ip_in_range = False
    ip_in_excluded = False
    is_apipa = False
    if has_explicit_ip and is_ip_address(pc.ip):
        ip_int = int(ipaddress.IPv4Address(pc.ip))
        lo_int = int(ipaddress.IPv4Address(range_start))
        hi_int = int(ipaddress.IPv4Address(range_end))
        ip_in_range = lo_int <= ip_int <= hi_int
        is_apipa = pc.ip.startswith("169.254.")
        subnet_prefix = ".".join(range_start.split(".")[:3]) + "."
        if pc.ip.startswith(subnet_prefix) and not ip_in_range:
            last_octet = int(pc.ip.split(".")[-1])
            if 1 <= last_octet <= 10:
                ip_in_excluded = True

    mask_ok = (not pc.subnet) or (pc.subnet == exp_mask)
    gw_ok = pc.gateway == exp_gw
    dhcp_srv_ok = pc.dhcp_server_ip == exp_gw

    # Case 1: Native Packet Tracer DHCP save (PORT_DHCP_ENABLE=true, DHCP_SERVER_IP=exp_gw, GATEWAY=exp_gw)
    if pc.dhcp_enabled and dhcp_srv_ok and gw_ok and not is_apipa and not ip_in_excluded and mask_ok:
        if not has_explicit_ip or ip_in_range:
            detail_ip = f" ({pc.ip})" if has_explicit_ip else " (terverifikasi via DHCP server & gateway)"
            return _make_check(
                check_id, "End Device DHCP", pc_name, f"DHCP client & lease pada {pc_name}",
                rubric, 1.0, expected_str, actual_str,
                f"{pc_name} aktif dalam mode DHCP dan menerima lease valid dari {exp_gw}{detail_ip}.",
            )

    # Case 2: Synthetic / older PT save with explicit IP in range + mask + gateway + DHCP enabled
    if pc.dhcp_enabled and has_explicit_ip and ip_in_range and pc.subnet == exp_mask and gw_ok:
        return _make_check(
            check_id, "End Device DHCP", pc_name, f"DHCP client & lease pada {pc_name}",
            rubric, 1.0, expected_str, actual_str,
            f"{pc_name} aktif dalam mode DHCP dengan IP valid ({pc.ip}) dan gateway {pc.gateway}.",
        )

    issues: list[str] = []
    if not pc.dhcp_enabled:
        issues.append("mode DHCP belum diaktifkan (masih Static)")
    if is_apipa:
        issues.append(f"memperoleh alamat APIPA ({pc.ip}), menandakan permintaan DHCP gagal mencapai R1")
    elif ip_in_excluded:
        issues.append(f"IP {pc.ip} berada pada rentang excluded (.1-.10)")
    elif pc.dhcp_enabled and not dhcp_srv_ok and not (has_explicit_ip and ip_in_range):
        issues.append(
            f"DHCP server terdeteksi '{pc.dhcp_server_ip or 'tidak ada'}', seharusnya {exp_gw}"
        )
    if has_explicit_ip and not ip_in_range and not is_apipa and not ip_in_excluded:
        issues.append(f"IP aktual '{pc.ip}' di luar rentang {range_start}-{range_end}")
    if pc.subnet and pc.subnet != exp_mask:
        issues.append(f"subnet mask '{pc.subnet}' tidak sesuai {exp_mask}")
    if not gw_ok:
        issues.append(f"default gateway '{pc.gateway or 'kosong'}' tidak sesuai {exp_gw}")

    ratio = 0.0
    if pc.dhcp_enabled and ip_in_excluded and mask_ok and gw_ok:
        ratio = 0.6
    elif not pc.dhcp_enabled and ip_in_range and pc.subnet == exp_mask and gw_ok:
        ratio = 0.3
    elif pc.dhcp_enabled and (gw_ok or dhcp_srv_ok):
        ratio = 0.5
    elif pc.dhcp_enabled:
        ratio = 0.2

    return _make_check(
        check_id, "End Device DHCP", pc_name, f"DHCP client & lease pada {pc_name}",
        rubric, ratio, expected_str, actual_str,
        f"Konfigurasi DHCP {pc_name} belum valid: " + "; ".join(issues) + ".",
    )


def _check_save_config(lab: ParsedLab, rubric: RubricConfig) -> CheckResult:
    targets = ("S1", "R1", "R2")
    saved: list[str] = []
    unsaved: list[str] = []
    for name in targets:
        dev = _get_device(lab, name)
        if dev is not None and bool(dev.startup_config_text.strip()):
            saved.append(name)
        else:
            unsaved.append(name)

    ratio = len(saved) / len(targets)
    if not unsaved:
        return _make_check(
            "save_config", "Penyimpanan", "S1, R1, R2", "Simpan konfigurasi (write memory)",
            rubric, 1.0,
            "startup-config tersimpan di S1, R1, R2",
            f"tersimpan di: {', '.join(saved)}",
            "Seluruh perangkat jaringan sudah menjalankan write memory.",
        )
    return _make_check(
        "save_config", "Penyimpanan", "S1, R1, R2", "Simpan konfigurasi (write memory)",
        rubric, ratio,
        "startup-config tersimpan di S1, R1, R2",
        f"tersimpan: {', '.join(saved) or 'tidak ada'}; belum: {', '.join(unsaved)}",
        f"Konfigurasi belum disimpan (write memory) pada: {', '.join(unsaved)}.",
    )


def _check_optional_dns(lab: ParsedLab, rubric: RubricConfig) -> tuple[CheckResult, str]:
    """Optional DNS check (does not penalize if omitted; score remains capped at 100)."""
    r1 = _get_device(lab, "R1")
    srv = _get_device(lab, "Server1")
    pc1 = _get_device(lab, "PC1")
    pc2 = _get_device(lab, "PC2")

    pool_v10_dns = ""
    pool_v20_dns = ""
    if r1 is not None:
        for p in r1.ios.dhcp_pools:
            if p.network == "192.168.10.0" and p.dns_server:
                pool_v10_dns = p.dns_server
            if p.network == "192.168.20.0" and p.dns_server:
                pool_v20_dns = p.dns_server

    srv_dns_on = bool(srv and srv.dns_server_enabled)
    srv_records = srv.dns_records if srv else []
    pc1_dns = pc1.dns_client_ip if pc1 else ""
    pc2_dns = pc2.dns_client_ip if pc2 else ""

    has_any_dns = bool(pool_v10_dns or pool_v20_dns or srv_dns_on or srv_records or pc1_dns or pc2_dns)

    valid_records = [
        rec for rec in srv_records
        if "->" in rec and is_ip_address(rec.split("->", 1)[1].strip())
    ]

    expected = (
        "Opsional (+bonus maks. 100): dns-server 192.168.30.2 di pool VLAN10 & VLAN20, "
        "layanan DNS aktif + minimal 1 A-record (domain bebas) di Server1"
    )
    actual_parts = [
        f"R1 pool VLAN10 dns={pool_v10_dns or '-'}",
        f"VLAN20 dns={pool_v20_dns or '-'}",
        f"Server1 DNS={'aktif' if srv_dns_on else 'nonaktif'} ({', '.join(valid_records) if valid_records else '0 record'})",
    ]
    if pc1_dns or pc2_dns:
        actual_parts.append(f"PC1 dns={pc1_dns or '-'}, PC2 dns={pc2_dns or '-'}")
    actual = "; ".join(actual_parts)

    if not has_any_dns:
        check = _make_check(
            "opt_dns", "Opsional", "R1, Server1", "Konfigurasi DNS (opsional)",
            rubric, 0.0, expected, "Tidak dikonfigurasi",
            "Tidak dikonfigurasi (bersifat opsional sesuai brief, tidak mengurangi nilai).",
            optional=True,
        )
        return check, "none"

    v10_ok = pool_v10_dns == "192.168.30.2"
    v20_ok = pool_v20_dns == "192.168.30.2"
    srv_ok = srv_dns_on and len(valid_records) > 0

    if v10_ok and v20_ok and srv_ok:
        check = _make_check(
            "opt_dns", "Opsional", "R1, Server1", "Konfigurasi DNS (opsional)",
            rubric, 1.0, expected, actual,
            f"Konfigurasi DNS opsional lengkap (bonus +{rubric.weight('opt_dns'):g} poin, skor total tetap maks. 100).",
            optional=True,
        )
        return check, "complete"

    notes: list[str] = []
    if not v10_ok:
        notes.append("pool VLAN 10 belum menyertakan 'dns-server 192.168.30.2'")
    if not v20_ok:
        notes.append("pool VLAN 20 belum menyertakan 'dns-server 192.168.30.2'")
    if not srv_dns_on:
        notes.append("layanan DNS pada Server1 belum diaktifkan")
    elif not valid_records:
        notes.append("belum ada A-record dengan IP valid pada Server1 DNS")

    ratio = sum([v10_ok, v20_ok, srv_ok]) / 3.0
    check = _make_check(
        "opt_dns", "Opsional", "R1, Server1", "Konfigurasi DNS (opsional)",
        rubric, ratio, expected, actual,
        "Konfigurasi DNS opsional terdeteksi parsial: " + "; ".join(notes) + ".",
        optional=True,
    )
    return check, "partial"


def _build_snapshots(lab: ParsedLab) -> dict[str, DeviceSnapshot]:
    out: dict[str, DeviceSnapshot] = {}
    for name, dev in lab.devices.items():
        out[name] = DeviceSnapshot(
            name=dev.name,
            device_type=dev.device_type,
            model=dev.model,
            ip=dev.ip,
            subnet=dev.subnet,
            gateway=dev.gateway,
            dhcp_enabled=dev.dhcp_enabled,
            dhcp_server_ip=dev.dhcp_server_ip,
            dns_client_ip=dev.dns_client_ip,
            dns_server_enabled=dev.dns_server_enabled,
            dns_records=dev.dns_records,
            has_startup_config=bool(dev.startup_config_text.strip()),
            running_config=dev.running_config_text,
            vlans=sorted(v for v in dev.vlans if v not in (1002, 1003, 1004, 1005)),
        )
    return out


def grade_bytes(
    data: bytes,
    filename: str,
    source_path: str | None = None,
    rubric: RubricConfig | None = None,
) -> StudentReport:
    """Grade a single .pkt or .pka byte payload."""
    active_rubric = rubric or RubricConfig()
    nim, student_name = extract_student_identity(filename)
    src = source_path or filename

    mandatory_max = round(
        sum(
            active_rubric.weight(k)
            for k in active_rubric.weights
            if k not in OPTIONAL_CHECK_IDS
        ),
        2,
    )

    try:
        lab = parse_pkt_bytes(data)
    except Exception as exc:
        return StudentReport(
            filename=filename,
            source_path=src,
            nim=nim,
            student_name=student_name,
            status="error",
            score=0.0,
            max_score=mandatory_max,
            percentage=0.0,
            passed=False,
            errors=[f"Gagal membaca file Packet Tracer: {exc}"],
            parse_error=str(exc),
        )

    checks: list[CheckResult] = []
    checks.extend(_check_topology(lab, active_rubric))
    checks.extend(_check_switch_s1(lab, active_rubric))
    checks.extend(_check_router_r1(lab, active_rubric))
    checks.extend(_check_router_r2(lab, active_rubric))
    checks.append(
        _check_pc_dhcp(
            lab, active_rubric, "pc1_dhcp", "PC1",
            "192.168.10.11", "192.168.10.254", "255.255.255.0", "192.168.10.1",
        )
    )
    checks.append(
        _check_pc_dhcp(
            lab, active_rubric, "pc2_dhcp", "PC2",
            "192.168.20.11", "192.168.20.254", "255.255.255.0", "192.168.20.1",
        )
    )
    checks.append(_check_save_config(lab, active_rubric))

    dns_check, dns_status = _check_optional_dns(lab, active_rubric)
    checks.append(dns_check)

    # Mandatory max score caps total so optional bonus never exceeds max_score (100)
    max_score = round(sum(c.points_possible for c in checks if not c.optional), 2)
    raw_score = round(sum(c.points_earned for c in checks), 2)
    score = min(raw_score, max_score) if max_score > 0 else raw_score
    percentage = min(100.0, round((score / max_score * 100.0) if max_score > 0 else 0.0, 2))
    passed = percentage >= active_rubric.pass_threshold

    if percentage >= active_rubric.pass_threshold:
        status = "pass"
    elif percentage >= 40.0:
        status = "partial"
    else:
        status = "fail"

    category_scores: dict[str, dict[str, float]] = {}
    for c in checks:
        if c.optional:
            continue
        bucket = category_scores.setdefault(c.category, {"earned": 0.0, "possible": 0.0})
        bucket["earned"] = round(bucket["earned"] + c.points_earned, 2)
        bucket["possible"] = round(bucket["possible"] + c.points_possible, 2)

    errors = [
        f"[{c.device}] {c.title}: {c.message}"
        for c in checks
        if not c.optional and c.status != "pass"
    ]

    return StudentReport(
        filename=filename,
        source_path=src,
        nim=nim,
        student_name=student_name,
        pt_version=lab.pt_version,
        file_kind=lab.file_kind,
        status=status,
        score=score,
        max_score=max_score,
        percentage=percentage,
        passed=passed,
        dns_optional_status=dns_status,  # type: ignore[arg-type]
        checks=checks,
        errors=errors,
        category_scores=category_scores,
        devices=_build_snapshots(lab),
        config_diffs=build_config_diffs(lab),
    )


def grade_file(path: str | Path, rubric: RubricConfig | None = None) -> StudentReport:
    """Grade a single .pkt or .pka file from disk."""
    p = Path(path)
    return grade_bytes(p.read_bytes(), filename=p.name, source_path=str(p), rubric=rubric)


def grade_archive_bytes(
    zip_bytes: bytes,
    archive_name: str = "upload.zip",
    rubric: RubricConfig | None = None,
) -> list[StudentReport]:
    """Extract and grade all .pkt/.pka files inside a ZIP archive (recursively)."""
    results: list[StudentReport] = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for info in sorted(zf.infolist(), key=lambda x: x.filename):
            if info.is_dir():
                continue
            member_path = Path(info.filename)
            if "__MACOSX" in member_path.parts or member_path.name.startswith("."):
                continue
            suffix = member_path.suffix.lower()
            if suffix not in (".pkt", ".pka"):
                continue
            if info.file_size > MAX_ARCHIVE_ENTRY_BYTES:
                results.append(
                    StudentReport(
                        filename=member_path.name,
                        source_path=f"{archive_name}::{info.filename}",
                        status="error",
                        score=0.0,
                        max_score=100.0,
                        percentage=0.0,
                        passed=False,
                        errors=["Ukuran file melebihi batas maksimum 50 MB."],
                        parse_error="File size exceeds 50 MB limit.",
                    )
                )
                continue
            payload = zf.read(info)
            results.append(
                grade_bytes(
                    payload,
                    filename=member_path.name,
                    source_path=f"{archive_name}::{info.filename}",
                    rubric=rubric,
                )
            )
    return results


def summarize_batch(results: list[StudentReport], rubric: RubricConfig) -> BatchReport:
    """Compute aggregate statistics and top common failures for a batch of reports."""
    total = len(results)
    parse_errors = sum(1 for r in results if r.status == "error")
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    scores = [r.percentage for r in results if r.status != "error"]

    if scores:
        avg = round(statistics.mean(scores), 2)
        high = round(max(scores), 2)
        low = round(min(scores), 2)
        med = round(statistics.median(scores), 2)
    else:
        avg = high = low = med = 0.0

    pass_rate = round((passed / total * 100.0) if total > 0 else 0.0, 2)

    failure_counter: Counter[tuple[str, str, str]] = Counter()
    for r in results:
        for c in r.checks:
            if not c.optional and c.status != "pass":
                failure_counter[(c.id, c.device, c.title)] += 1

    common_failures = [
        {
            "check_id": cid,
            "device": dev,
            "title": title,
            "count": count,
            "rate": round((count / total * 100.0) if total > 0 else 0.0, 1),
        }
        for (cid, dev, title), count in failure_counter.most_common(8)
    ]

    summary = BatchSummary(
        total=total,
        passed=passed,
        failed=failed,
        parse_errors=parse_errors,
        average_score=avg,
        highest_score=high,
        lowest_score=low,
        median_score=med,
        pass_rate=pass_rate,
        common_failures=common_failures,
    )
    return BatchReport(rubric=rubric, summary=summary, results=results)


def grade_inputs(
    paths: Iterable[str | Path],
    rubric: RubricConfig | None = None,
) -> BatchReport:
    """Grade any mix of .pkt, .pka, .zip archives, and directories."""
    active_rubric = rubric or RubricConfig()
    results: list[StudentReport] = []

    for raw_path in paths:
        p = Path(raw_path)
        if not p.exists():
            results.append(
                StudentReport(
                    filename=p.name,
                    source_path=str(p),
                    status="error",
                    score=0.0,
                    max_score=100.0,
                    percentage=0.0,
                    passed=False,
                    errors=[f"File atau direktori tidak ditemukan: {p}"],
                    parse_error=f"Path not found: {p}",
                )
            )
            continue

        if p.is_dir():
            for child in sorted(p.rglob("*")):
                if not child.is_file() or child.name.startswith("."):
                    continue
                ext = child.suffix.lower()
                if ext in (".pkt", ".pka"):
                    results.append(grade_file(child, rubric=active_rubric))
                elif ext == ".zip":
                    results.extend(grade_archive_bytes(child.read_bytes(), child.name, rubric=active_rubric))
        else:
            ext = p.suffix.lower()
            if ext == ".zip":
                results.extend(grade_archive_bytes(p.read_bytes(), p.name, rubric=active_rubric))
            elif ext in (".pkt", ".pka"):
                results.append(grade_file(p, rubric=active_rubric))

    return summarize_batch(results, active_rubric)
