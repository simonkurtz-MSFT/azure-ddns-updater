"""Update Azure DNS A records to match the current public IPv4 address."""

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from ipaddress import IPv4Address
from pathlib import Path
from time import sleep
from typing import Final, Mapping, Optional

import requests
from azure.core.exceptions import AzureError, ResourceNotFoundError
from azure.identity import ClientSecretCredential
from azure.mgmt.dns import DnsManagementClient
from azure.mgmt.dns.models import ARecord, RecordSet
from schedule import Scheduler

VERSION: Final[str] = "1.1.0"
TTL: Final[int] = 300
HEALTH_FILE: Final[Path] = Path(__file__).with_name("health.log")


@dataclass(frozen=True)
class Config:
    """Validated settings for an updater process."""

    client_id: str
    client_secret: str = field(repr=False)
    tenant_id: str
    subscription_id: str
    resource_group: str
    dns_zone: str
    record_names: tuple[str, ...]
    interval_minutes: int


def log(message: str) -> None:
    """Log a timestamped message to the console."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp} UTC] {message}", flush=True)


def load_config(environment: Mapping[str, str]) -> Config:
    """Read and validate the updater settings."""
    required = (
        "AZURE_CLIENT_ID",
        "AZURE_CLIENT_SECRET",
        "AZURE_TENANT_ID",
        "SUBSCRIPTION_ID",
        "RESOURCE_GROUP",
        "DNS_ZONE",
        "RECORD_NAMES",
    )
    values = {}
    for name in required:
        value = environment.get(name)
        if value is None or not value.strip():
            raise ValueError(f"The environment variable {name} is missing or empty.")
        values[name] = value.strip()

    names = tuple(
        name.strip() for name in values["RECORD_NAMES"].strip("[]").split(",")
    )
    if not all(names):
        raise ValueError(
            "RECORD_NAMES must contain one or more non-empty record names."
        )

    raw_interval = environment.get("INTERVAL_MINUTES")
    try:
        interval = int(raw_interval) if raw_interval is not None else 5
    except ValueError as error:
        raise ValueError("INTERVAL_MINUTES must be an integer.") from error
    if interval == 0:
        raise ValueError(
            "INTERVAL_MINUTES must not be zero; use a positive interval "
            "or a negative value for a single run."
        )

    return Config(
        client_id=values["AZURE_CLIENT_ID"],
        client_secret=values["AZURE_CLIENT_SECRET"],
        tenant_id=values["AZURE_TENANT_ID"],
        subscription_id=values["SUBSCRIPTION_ID"],
        resource_group=values["RESOURCE_GROUP"],
        dns_zone=values["DNS_ZONE"],
        record_names=names,
        interval_minutes=interval,
    )


def log_config(config: Config) -> None:
    """Log the effective settings without revealing the client secret."""
    settings = (
        ("AZURE_CLIENT_ID", config.client_id),
        ("AZURE_CLIENT_SECRET", "*** (hidden)"),
        ("AZURE_TENANT_ID", config.tenant_id),
        ("SUBSCRIPTION_ID", config.subscription_id),
        ("RESOURCE_GROUP", config.resource_group),
        ("DNS_ZONE", config.dns_zone),
        ("RECORD_NAMES", f"[{', '.join(config.record_names)}]"),
        ("INTERVAL_MINUTES", str(config.interval_minutes)),
    )
    for name, value in settings:
        log(f"{name:20} = {value}")


def get_public_ip() -> Optional[str]:
    """Retrieve and validate the current public IPv4 address."""
    try:
        with requests.get(
            "https://api.ipify.org?format=json", timeout=(5, 5)
        ) as response:
            response.raise_for_status()
            payload = response.json()
        address = payload.get("ip") if isinstance(payload, dict) else None
        if not isinstance(address, str):
            raise ValueError("The response did not contain an IPv4 address.")
        return str(IPv4Address(address))
    except (requests.RequestException, ValueError) as error:
        log(f"Error retrieving public IP: {error}")
        return None


def update_health_file(health_status: int) -> None:
    """Update the health file with the current status."""
    HEALTH_FILE.write_text(str(health_status), encoding="utf-8")


def update_dns_records(
    config: Config, dns_client: DnsManagementClient, current_ip: str
) -> bool:
    """Update the configured records and return whether every operation succeeded."""
    succeeded = True
    for name in config.record_names:
        try:
            record_set = dns_client.record_sets.get(
                config.resource_group, config.dns_zone, name, "A"
            )
        except ResourceNotFoundError:
            log(
                f"DNS A record {name}: No existing A record found. "
                "A new record set will be created."
            )
            ttl = TTL
        except AzureError as error:
            log(f"DNS A record {name}: Error retrieving DNS record: {error}")
            succeeded = False
            continue
        else:
            existing_ips = (
                [record.ipv4_address for record in record_set.a_records]
                if record_set.a_records
                else []
            )
            ttl = record_set.ttl or TTL
            if current_ip in existing_ips:
                log(f"DNS A record {name}: IP matches current DNS. No update needed.")
                continue
            log(f"DNS A record {name}: Existing DNS A record IPs: {existing_ips}")
            log(f"DNS A record {name}: IPs differ. Updating DNS record.")

        record_set_params = RecordSet(
            ttl=ttl, a_records=[ARecord(ipv4_address=current_ip)]
        )
        try:
            dns_client.record_sets.create_or_update(
                config.resource_group, config.dns_zone, name, "A", record_set_params
            )
        except AzureError as error:
            log(f"DNS A record {name}: Error updating DNS record: {error}")
            succeeded = False
        else:
            log(
                f"DNS A record {name}: IP successfully updated to {current_ip} "
                f"with TTL {ttl} seconds."
            )

    return succeeded


def run_update(config: Config) -> bool:
    """Run one update cycle and persist its health result."""
    succeeded = False
    try:
        log("")
        current_ip = get_public_ip()
        if current_ip is None:
            log("Could not get public IP. Skipping update.")
            return False

        log(f"Current public IP: {current_ip}")
        try:
            with ClientSecretCredential(
                config.tenant_id, config.client_id, config.client_secret
            ) as credential:
                with DnsManagementClient(
                    credential, config.subscription_id
                ) as dns_client:
                    cycle_succeeded = update_dns_records(config, dns_client, current_ip)
        except (AzureError, ValueError) as error:
            log(f"Error initializing or using the Azure DNS client: {error}")
            return False

        succeeded = cycle_succeeded
        return succeeded
    finally:
        update_health_file(0 if succeeded else 1)


def main() -> int:
    """Load configuration, run once, and optionally schedule subsequent runs."""
    log(f"Azure Dynamic DNS Updater - V{VERSION}")
    log("----------------------------------")
    log("")
    update_health_file(1)

    try:
        config = load_config(os.environ)
    except ValueError as error:
        log(f"Error: {error}")
        return 1

    log_config(config)
    succeeded = run_update(config)
    if config.interval_minutes > 0:
        log("")
        log(f"Starting schedule with {config.interval_minutes} minute interval...")
        scheduler = Scheduler()
        scheduler.every(config.interval_minutes).minutes.do(run_update, config)
        try:
            while True:
                scheduler.run_pending()
                sleep(1)
        except KeyboardInterrupt:
            log("Exiting gracefully...")
        exit_code = 0
    else:
        exit_code = 0 if succeeded else 1

    log("")
    log("Done.")
    return exit_code
