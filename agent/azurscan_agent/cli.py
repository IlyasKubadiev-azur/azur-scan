"""Click-based CLI for the agent."""
from __future__ import annotations

import sys

import click

from . import __version__
from .config import AgentConfig, CONFIG_PATH, DATA_DIR, LOG_FILE, ensure_dirs
from .logging_setup import configure as configure_logging
from .machine import fqdn, hostname, machine_id, os_kind
from .secrets_store import clear_credentials, load_credentials, store_credentials
from .transport import Transport, TransportError


def _build_fingerprint() -> dict:
    return {
        "machine_id": machine_id(),
        "hostname": hostname(),
        "primary_mac": "",
        "os_kind": os_kind(),
        "agent_version": __version__,
        "public_key_fingerprint": "",
    }


@click.group()
@click.version_option(__version__, prog_name="azurscan-agent")
def cli() -> None:
    """Azur-Scan endpoint agent."""


@cli.command("set-config")
@click.option("--server", required=True, help="Backend URL (e.g. http://10.0.20.143:8000).")
@click.option("--no-verify-tls", is_flag=True, help="Skip TLS verification (testing only).")
def set_config(server: str, no_verify_tls: bool) -> None:
    """Write the server URL into the agent config without contacting the server.

    Used by the MSI installer's CustomAction. The first run of the service then
    auto-enrolls against this URL. Idempotent.
    """
    ensure_dirs()
    cfg = AgentConfig.load()
    cfg.server_url = server.rstrip("/")
    cfg.verify_tls = not no_verify_tls
    cfg.save()
    click.echo(f"OK. server_url = {cfg.server_url}")
    click.echo(f"Config: {CONFIG_PATH}")


@cli.command()
@click.option("--server", required=True, help="Backend URL, e.g. http://10.0.20.143:8000")
@click.option("--no-verify-tls", is_flag=True, help="Skip TLS verification (testing only)")
def enroll(server: str, no_verify_tls: bool) -> None:
    """Register this machine with the backend and store credentials.

    Tokenless — the backend identifies devices by stable machine_id.
    Re-running on the same machine refreshes credentials in place.
    """
    ensure_dirs()
    configure_logging("INFO")

    cfg = AgentConfig.load()
    cfg.server_url = server.rstrip("/")
    cfg.verify_tls = not no_verify_tls

    transport = Transport(cfg)
    try:
        click.echo(f"Enrolling {hostname()} ({machine_id()}) at {server}...")
        result = transport.enroll(fingerprint=_build_fingerprint())
    except TransportError as exc:
        click.echo(f"FAILED: {exc}", err=True)
        sys.exit(2)
    finally:
        transport.close()

    cfg.device_id = result["device_id"]
    server_cfg = result.get("config", {}) or {}
    cfg.heartbeat_interval_s = int(server_cfg.get("heartbeat_s", cfg.heartbeat_interval_s))
    cfg.full_scan_interval_h = int(server_cfg.get("full_scan_h", cfg.full_scan_interval_h))
    cfg.save()

    store_credentials(
        access_token=result["access_token"],
        refresh_token=result["refresh_token"],
    )

    click.echo(f"OK. device_id = {cfg.device_id}")
    click.echo(f"Config:      {CONFIG_PATH}")
    click.echo(f"Logs:        {LOG_FILE}")
    click.echo(f"Heartbeat:   every {cfg.heartbeat_interval_s}s")
    click.echo(f"Full scan:   every {cfg.full_scan_interval_h}h")


@cli.command()
def run() -> None:
    """Run the main agent loop. Usually invoked by the OS service manager.

    If the agent isn't yet enrolled but a server URL is configured (via MSI
    `set-config`), the runtime auto-enrolls on first iteration.
    """
    cfg = AgentConfig.load()
    if not cfg.server_url:
        click.echo(
            "ERROR: server_url not configured. Run `azurscan-agent set-config "
            "--server <URL>` or `azurscan-agent enroll --server <URL>`.",
            err=True,
        )
        sys.exit(2)

    configure_logging(cfg.log_level)

    from .runtime import Runtime  # imported lazily so other commands stay light
    rt = Runtime(cfg)
    try:
        rt.run()
    except KeyboardInterrupt:
        rt.stop()


@cli.command("scan-now")
def scan_now() -> None:
    """Run a single scan and upload it (debugging)."""
    cfg = AgentConfig.load()
    if not cfg.server_url:
        click.echo("ERROR: server_url not configured.", err=True)
        sys.exit(2)
    configure_logging("DEBUG")

    from .runtime import Runtime
    rt = Runtime(cfg)
    if not rt.ensure_enrolled():
        click.echo("ERROR: enrollment failed.", err=True)
        sys.exit(2)
    rt.do_full_scan(source="manual")
    rt.transport.close()


@cli.command()
def status() -> None:
    """Print current agent state."""
    cfg = AgentConfig.load()
    creds = load_credentials()
    enrolled = bool(cfg.device_id and creds.get("access"))
    click.echo(f"Version:       {__version__}")
    click.echo(f"Hostname:      {hostname()}  ({fqdn()})")
    click.echo(f"Machine id:    {machine_id()}")
    click.echo(f"OS kind:       {os_kind()}")
    click.echo(f"Server URL:    {cfg.server_url or '<not set>'}")
    click.echo(f"Device id:     {cfg.device_id or '<not enrolled>'}")
    click.echo(f"Enrolled:      {'yes' if enrolled else 'no'}")
    click.echo(f"Data dir:      {DATA_DIR}")
    click.echo(f"Log file:      {LOG_FILE}")

    if enrolled:
        try:
            from .transport import Outbox
            stats = Outbox().stats()
            click.echo(f"Outbox:        pending={stats['pending']}  poisoned={stats['poisoned']}")
        except Exception as exc:
            click.echo(f"Outbox:        error reading: {exc}")


@cli.command()
@click.confirmation_option(prompt="Clear local credentials and config?")
def uninstall() -> None:
    """Remove credentials + config (does NOT remove the OS service)."""
    clear_credentials()
    try:
        CONFIG_PATH.unlink()
    except FileNotFoundError:
        pass
    click.echo("Local agent state removed. The service itself is removed by the uninstaller.")
