"""Pydantic contract for the agent scan payload.

This is the canonical wire format. The DRF serializer accepts a loose dict
and we validate it strictly via these schemas inside the ingest service.
Adding a new field is a matter of extending the relevant model below; the
JSON snapshot in `ScanSession.payload` is kept verbatim, so historical scans
remain readable even after schema evolution.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class SystemFacts(_Strict):
    hostname: str
    fqdn: str = ""
    machine_id: str
    current_user: str = ""
    last_logged_user: str = ""


class OSFacts(_Strict):
    name: str = ""
    version: str = ""
    build: str = ""
    arch: str = ""


class CPUFacts(_Strict):
    model: str = ""
    cores: int | None = None
    threads: int | None = None


class HardwareFacts(_Strict):
    cpu: CPUFacts = Field(default_factory=CPUFacts)
    ram_total_mb: int | None = None
    motherboard: str = ""
    gpu: str = ""
    manufacturer: str = ""
    model: str = ""
    serial_number: str = ""


class DiskFacts(_Strict):
    device: str
    model: str = ""
    size_bytes: int | None = None
    free_bytes: int | None = None
    fs_type: str = ""
    mount_point: str = ""


class StorageFacts(_Strict):
    disks: list[DiskFacts] = Field(default_factory=list)


class NICFacts(_Strict):
    name: str
    mac_address: str
    ip_addresses: list[str] = Field(default_factory=list)
    is_primary: bool = False


class NetworkFacts(_Strict):
    interfaces: list[NICFacts] = Field(default_factory=list)


class ScanPayload(_Strict):
    scan_id: str
    started_at: datetime
    finished_at: datetime
    source: str = "scheduled"
    agent_version: str

    system: SystemFacts
    os: OSFacts = Field(default_factory=OSFacts)
    hardware: HardwareFacts = Field(default_factory=HardwareFacts)
    storage: StorageFacts = Field(default_factory=StorageFacts)
    network: NetworkFacts = Field(default_factory=NetworkFacts)

    errors: dict[str, str] = Field(default_factory=dict)
