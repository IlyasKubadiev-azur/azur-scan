"""Scan ingestion service.

`ingest_scan` is the single entry point: validate -> persist ScanSession ->
update Asset hot fields and rebuild NIC/Disk state. Idempotent on
(agent, client_scan_id) so agent retries don't create duplicates.
"""
from __future__ import annotations

import time
from typing import Optional

from django.db import transaction
from django.utils import timezone

from apps.agents.models import Agent
from apps.assets.models import Asset, Disk, NetworkInterface
from apps.core import audit
from apps.scanning.models import ScanSession
from apps.scanning.schemas import ScanPayload


@transaction.atomic
def ingest_scan(
    *, agent: Agent, raw_payload: dict, source: Optional[str] = None,
) -> ScanSession:
    started = time.monotonic()
    payload = ScanPayload.model_validate(raw_payload)
    source = source or payload.source

    existing = ScanSession.objects.filter(
        agent=agent, client_scan_id=payload.scan_id,
    ).first()
    if existing is not None:
        return existing

    payload_dict = payload.model_dump(mode="json")
    payload_hash = ScanSession.compute_payload_hash(payload_dict)

    session = ScanSession(
        agent=agent,
        asset=agent.asset,
        client_scan_id=payload.scan_id,
        started_at=payload.started_at,
        finished_at=payload.finished_at,
        agent_version=payload.agent_version,
        source=source,
        payload=payload_dict,
        payload_hash=payload_hash,
    )

    _apply_to_asset(agent.asset, payload)

    session.ingest_duration_ms = int((time.monotonic() - started) * 1000)
    session.save()

    audit.log_event(
        action=audit.SCAN_RECEIVED,
        object_type="asset",
        object_id=agent.asset_id,
        after={
            "scan_id": payload.scan_id,
            "hostname": agent.asset.hostname,
            "source": source,
            "agent_version": payload.agent_version,
            "ingest_ms": session.ingest_duration_ms,
        },
    )
    return session


def _apply_to_asset(asset: Asset, payload: ScanPayload) -> None:
    asset.hostname = payload.system.hostname or asset.hostname
    asset.fqdn = payload.system.fqdn or asset.fqdn
    asset.current_user_login = payload.system.current_user
    if payload.system.last_logged_user:
        asset.last_logged_user = payload.system.last_logged_user

    asset.os_name = payload.os.name
    asset.os_version = payload.os.version
    asset.os_build = payload.os.build
    asset.os_arch = payload.os.arch
    asset.os_display_version = payload.os.display_version
    asset.os_edition = payload.os.edition

    if payload.hardware.manufacturer:
        asset.manufacturer = payload.hardware.manufacturer
    if payload.hardware.model:
        asset.model = payload.hardware.model
    if payload.hardware.serial_number:
        asset.serial_number = payload.hardware.serial_number

    # CPU
    asset.cpu_model = payload.hardware.cpu.model
    asset.cpu_vendor = payload.hardware.cpu.vendor
    asset.cpu_cores = payload.hardware.cpu.cores
    asset.cpu_threads = payload.hardware.cpu.threads
    asset.cpu_base_ghz = payload.hardware.cpu.base_ghz
    asset.cpu_arch = payload.hardware.cpu.arch

    asset.ram_total_mb = payload.hardware.ram_total_mb

    # Motherboard — split fields + composite (back-compat)
    mb = payload.hardware.motherboard
    asset.motherboard_manufacturer = mb.manufacturer
    asset.motherboard_product = mb.product
    asset.motherboard_serial = mb.serial
    asset.motherboard = " ".join(p for p in (mb.manufacturer, mb.product) if p).strip()

    # BIOS
    asset.bios_vendor = payload.hardware.bios.vendor
    asset.bios_version = payload.hardware.bios.version
    asset.bios_release_date = payload.hardware.bios.release_date

    asset.gpu = payload.hardware.gpu

    asset.agent_version = payload.agent_version
    now = timezone.now()
    asset.last_seen_at = now
    if asset.first_seen_at is None:
        asset.first_seen_at = now
    asset.status = Asset.Status.ONLINE
    asset.save()

    # Network interfaces — replace state.
    # Dedupe by mac_address: macOS routinely reports the same MAC on multiple
    # logical interfaces (en0 + bridge0 + awdl0 + llw0 all share the Wi-Fi
    # hardware MAC) and Linux does the same for bonded/VLAN devices. The
    # (asset, mac_address) UNIQUE constraint enforces one row per physical
    # NIC, so we keep the first occurrence and drop later dupes.
    asset.network_interfaces.all().delete()
    if payload.network.interfaces:
        seen_macs: set[str] = set()
        nics_to_create: list[NetworkInterface] = []
        for nic in payload.network.interfaces:
            mac = (nic.mac_address or "").upper()
            if not mac or mac in seen_macs:
                continue
            seen_macs.add(mac)
            nics_to_create.append(NetworkInterface(
                asset=asset,
                name=nic.name,
                mac_address=mac,
                ip_addresses=nic.ip_addresses,
                is_primary=nic.is_primary,
            ))
        if nics_to_create:
            NetworkInterface.objects.bulk_create(nics_to_create)

    # Disks — replace state
    asset.disks.all().delete()
    if payload.storage.disks:
        Disk.objects.bulk_create([
            Disk(
                asset=asset,
                device=d.device,
                model=d.model,
                size_bytes=d.size_bytes,
                free_bytes=d.free_bytes,
                fs_type=d.fs_type,
                mount_point=d.mount_point,
            )
            for d in payload.storage.disks
        ])
