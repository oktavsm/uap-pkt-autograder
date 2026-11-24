"""Data models for grading configuration, diagnostics, and batch reports."""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


DEFAULT_WEIGHTS: dict[str, float] = {
    "topo_devices": 2.0,
    "topo_links": 3.0,
    "s1_vlans": 5.0,
    "s1_access_fa01": 5.0,
    "s1_access_fa02": 5.0,
    "s1_trunk_mode": 5.0,
    "s1_trunk_allowed": 5.0,
    "r1_base_ip": 4.0,
    "r1_dhcp_excl_10": 5.0,
    "r1_dhcp_excl_20": 5.0,
    "r1_dhcp_pool_10": 8.0,
    "r1_dhcp_pool_20": 8.0,
    "r2_base_ip": 2.0,
    "r1_route_lanb": 6.0,
    "r2_route_vlan10": 6.0,
    "r2_route_vlan20": 6.0,
    "pc1_dhcp": 7.0,
    "pc2_dhcp": 7.0,
    "save_config": 6.0,
    "opt_dns": 0.0,
}

OPTIONAL_CHECK_IDS: frozenset[str] = frozenset({"opt_dns"})


class RubricConfig(BaseModel):
    name: str = "UAP Jaringan Komputer PTI"
    pass_threshold: float = 70.0
    allow_exit_interface_route: bool = False
    require_explicit_trunk_allowed: bool = True
    weights: dict[str, float] = Field(default_factory=lambda: dict(DEFAULT_WEIGHTS))

    def weight(self, check_id: str) -> float:
        return float(self.weights.get(check_id, DEFAULT_WEIGHTS.get(check_id, 0.0)))


class CheckResult(BaseModel):
    id: str
    category: str
    device: str
    title: str
    status: Literal["pass", "partial", "fail", "optional"]
    optional: bool = False
    points_earned: float
    points_possible: float
    expected: str
    actual: str
    message: str


class DeviceSnapshot(BaseModel):
    name: str
    device_type: str
    model: str
    ip: str = ""
    subnet: str = ""
    gateway: str = ""
    dhcp_enabled: bool = False
    dhcp_server_ip: str = ""
    dns_client_ip: str = ""
    dns_server_enabled: bool = False
    dns_records: list[str] = Field(default_factory=list)
    has_startup_config: bool = False
    running_config: str = ""
    vlans: list[int] = Field(default_factory=list)


class StudentReport(BaseModel):
    filename: str
    source_path: str
    nim: str = ""
    student_name: str = ""
    pt_version: str = ""
    file_kind: str = ""
    status: Literal["pass", "partial", "fail", "error"]
    score: float
    max_score: float
    percentage: float
    passed: bool
    dns_optional_status: Literal["complete", "partial", "none"] = "none"
    checks: list[CheckResult] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    category_scores: dict[str, dict[str, float]] = Field(default_factory=dict)
    devices: dict[str, DeviceSnapshot] = Field(default_factory=dict)
    parse_error: str | None = None


class BatchSummary(BaseModel):
    total: int
    passed: int
    failed: int
    parse_errors: int
    average_score: float
    highest_score: float
    lowest_score: float
    median_score: float
    pass_rate: float
    common_failures: list[dict[str, object]] = Field(default_factory=list)


class BatchReport(BaseModel):
    rubric: RubricConfig
    summary: BatchSummary
    results: list[StudentReport] = Field(default_factory=list)
