"""Unit and integration tests for pkt_grader engine, CLI, and FastAPI server."""

from __future__ import annotations

import io
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pkt_core.codec.container import decode_bytes, encode_bytes

from pkt_grader.cli import main as cli_main
from pkt_grader.engine import extract_student_identity, grade_archive_bytes, grade_bytes
from pkt_grader.exporter import batch_to_csv_string
from pkt_grader.server import create_app


TEMPLATE_PKT = Path(__file__).resolve().parent.parent.parent / "UAP Topology.pkt"


def _set_running_config(eng: ET.Element, lines: list[str], also_startup: bool = True) -> None:
    rc = eng.find("RUNNINGCONFIG")
    if rc is None:
        rc = ET.SubElement(eng, "RUNNINGCONFIG")
    rc.clear()
    for line in lines:
        el = ET.SubElement(rc, "LINE")
        el.text = line
    if also_startup:
        sc = eng.find("STARTUPCONFIG")
        if sc is None:
            sc = ET.SubElement(eng, "STARTUPCONFIG")
        sc.clear()
        for line in lines:
            el = ET.SubElement(sc, "LINE")
            el.text = line


def _build_synthetic_pkt(
    *,
    s1_vlans: list[int] = [10, 20],
    s1_extra_lines: list[str] | None = None,
    r1_extra_lines: list[str] | None = None,
    r2_extra_lines: list[str] | None = None,
    pc1_cfg: tuple[bool, str, str, str] = (True, "192.168.10.11", "255.255.255.0", "192.168.10.1"),
    pc2_cfg: tuple[bool, str, str, str] = (True, "192.168.20.11", "255.255.255.0", "192.168.20.1"),
    save_startup: bool = True,
) -> bytes:
    container = decode_bytes(TEMPLATE_PKT.read_bytes())
    root = ET.fromstring(container.xml)

    for dev in root.findall("./NETWORK/DEVICES/DEVICE"):
        eng = dev.find("ENGINE")
        if eng is None:
            continue
        name = (eng.findtext("NAME") or "").strip()

        if name == "S1":
            vlans_el = eng.find("VLANS")
            if vlans_el is not None:
                for vid in s1_vlans:
                    ET.SubElement(vlans_el, "VLAN", {"name": f"VLAN{vid}", "number": str(vid), "rspan": "0"})
            lines = s1_extra_lines if s1_extra_lines is not None else [
                "!",
                "hostname S1",
                "interface FastEthernet0/1",
                " switchport access vlan 10",
                " switchport mode access",
                "!",
                "interface FastEthernet0/2",
                " switchport access vlan 20",
                " switchport mode access",
                "!",
                "interface GigabitEthernet0/1",
                " switchport trunk allowed vlan 10,20",
                " switchport mode trunk",
                "!",
                "end",
            ]
            _set_running_config(eng, lines, also_startup=save_startup)

        elif name == "R1":
            lines = r1_extra_lines if r1_extra_lines is not None else [
                "!",
                "hostname R1",
                "ip dhcp excluded-address 192.168.10.1 192.168.10.10",
                "ip dhcp excluded-address 192.168.20.1 192.168.20.10",
                "!",
                "ip dhcp pool POOL_A",
                " network 192.168.10.0 255.255.255.0",
                " default-router 192.168.10.1",
                "ip dhcp pool POOL_B",
                " network 192.168.20.0 255.255.255.0",
                " default-router 192.168.20.1",
                "!",
                "interface GigabitEthernet0/0",
                " ip address 10.0.0.1 255.255.255.252",
                "!",
                "interface GigabitEthernet0/1",
                " no ip address",
                "!",
                "interface GigabitEthernet0/1.10",
                " encapsulation dot1Q 10",
                " ip address 192.168.10.1 255.255.255.0",
                "!",
                "interface GigabitEthernet0/1.20",
                " encapsulation dot1Q 20",
                " ip address 192.168.20.1 255.255.255.0",
                "!",
                "ip route 192.168.30.0 255.255.255.0 10.0.0.2",
                "end",
            ]
            _set_running_config(eng, lines, also_startup=save_startup)

        elif name == "R2":
            lines = r2_extra_lines if r2_extra_lines is not None else [
                "!",
                "hostname R2",
                "interface GigabitEthernet0/0",
                " ip address 10.0.0.2 255.255.255.252",
                "!",
                "interface GigabitEthernet0/1",
                " ip address 192.168.30.1 255.255.255.0",
                "!",
                "ip route 192.168.10.0 255.255.255.0 10.0.0.1",
                "ip route 192.168.20.0 255.255.255.0 10.0.0.1",
                "end",
            ]
            _set_running_config(eng, lines, also_startup=save_startup)

        elif name in ("PC1", "PC2"):
            dhcp_en, ip, mask, gw = pc1_cfg if name == "PC1" else pc2_cfg
            gw_el = eng.find("GATEWAY")
            if gw_el is not None:
                gw_el.text = gw
            port = eng.find(".//PORT")
            if port is not None:
                port.find("PORT_DHCP_ENABLE").text = "true" if dhcp_en else "false"
                port.find("IP").text = ip
                port.find("SUBNET").text = mask
                port.find("PORT_GATEWAY").text = gw

    new_xml = ET.tostring(root, encoding="utf-8")
    return encode_bytes(new_xml, container.format_name)


def test_extract_student_identity() -> None:
    assert extract_student_identity("UAP_245150600111001_Budi_Santoso.pkt") == (
        "245150600111001",
        "Budi Santoso",
    )
    assert extract_student_identity("245150600111099-Ani.pka") == ("245150600111099", "Ani")
    assert extract_student_identity("UAP Topology.pkt") == ("", "UAP Topology")


@pytest.mark.skipif(not TEMPLATE_PKT.exists(), reason="Template UAP Topology.pkt not present")
def test_grade_unconfigured_template() -> None:
    report = grade_bytes(TEMPLATE_PKT.read_bytes(), "UAP Topology.pkt")
    assert report.status == "fail"
    assert report.score == 11.0
    assert report.max_score == 100.0
    assert report.passed is False
    assert len(report.errors) == 15


@pytest.mark.skipif(not TEMPLATE_PKT.exists(), reason="Template UAP Topology.pkt not present")
def test_grade_perfect_submission() -> None:
    perfect_bytes = _build_synthetic_pkt()
    report = grade_bytes(perfect_bytes, "UAP_245150600111001_Budi_Santoso.pkt")
    assert report.nim == "245150600111001"
    assert report.student_name == "Budi Santoso"
    assert report.score == 100.0
    assert report.percentage == 100.0
    assert report.passed is True
    assert report.errors == []


@pytest.mark.skipif(not TEMPLATE_PKT.exists(), reason="Template UAP Topology.pkt not present")
def test_grade_partial_with_common_mistakes() -> None:
    broken = _build_synthetic_pkt(
        r1_extra_lines=[
            "!",
            "ip dhcp pool V10",
            " network 192.168.10.0 255.255.255.0",
            " default-router 192.168.10.1",
            "ip dhcp pool V20",
            " network 192.168.20.0 255.255.255.0",
            " default-router 192.168.20.1",
            "interface GigabitEthernet0/0",
            " ip address 10.0.0.1 255.255.255.252",
            "interface GigabitEthernet0/1",
            " no ip address",
            "interface GigabitEthernet0/1.10",
            " encapsulation dot1Q 10",
            " ip address 192.168.10.1 255.255.255.0",
            "interface GigabitEthernet0/1.20",
            " encapsulation dot1Q 20",
            " ip address 192.168.20.1 255.255.255.0",
            "ip route 192.168.30.0 255.255.255.0 10.0.0.2",
            "end",
        ],
        pc2_cfg=(True, "169.254.12.34", "255.255.0.0", ""),
        save_startup=False,
    )
    report = grade_bytes(broken, "UAP_245150600111002_Siti.pkt")
    assert report.score < 100.0
    failed_ids = {c.id for c in report.checks if c.status != "pass"}
    assert "r1_dhcp_excl_10" in failed_ids
    assert "r1_dhcp_excl_20" in failed_ids
    assert "pc2_dhcp" in failed_ids
    assert "save_config" in failed_ids


@pytest.mark.skipif(not TEMPLATE_PKT.exists(), reason="Template UAP Topology.pkt not present")
def test_zip_archive_cli_and_api(tmp_path: Path) -> None:
    perfect_bytes = _build_synthetic_pkt()
    template_bytes = TEMPLATE_PKT.read_bytes()

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as zf:
        zf.writestr("batch/UAP_245150600111001_Budi.pkt", perfect_bytes)
        zf.writestr("batch/UAP_245150600111002_Template.pkt", template_bytes)
        zf.writestr("__MACOSX/._junk.pkt", b"not a pkt")
        zf.writestr("batch/readme.txt", b"ignored")

    zip_bytes = zip_buf.getvalue()
    reports = grade_archive_bytes(zip_bytes, "kelas_a.zip")
    assert len(reports) == 2
    assert reports[0].score == 100.0
    assert reports[1].score == 11.0

    # CLI test with CSV output
    zip_file = tmp_path / "kelas_a.zip"
    zip_file.write_bytes(zip_bytes)
    csv_out = tmp_path / "out.csv"
    exit_code = cli_main([str(zip_file), "--csv", str(csv_out)])
    assert exit_code == 0
    csv_content = csv_out.read_text(encoding="utf-8")
    assert "245150600111001" in csv_content
    assert "100.00" in csv_content

    # FastAPI test
    client = TestClient(create_app())
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/rubric").status_code == 200

    res = client.post(
        "/api/grade",
        files=[("files", ("kelas_a.zip", zip_bytes, "application/zip"))],
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["summary"]["total"] == 2
    assert payload["summary"]["passed"] == 1
    assert payload["summary"]["average_score"] == 55.5

    csv_res = client.post("/api/export/csv", json=payload)
    assert csv_res.status_code == 200
    assert "text/csv" in csv_res.headers["content-type"]
    assert "245150600111001" in csv_res.text
