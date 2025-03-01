"""
Module providing a dynamic DNS updater for Azure DNS. The module retrieves your current public IP address and updates the specified
Azure DNS A record if it has changed.
"""

# Python Standard Library Imports
from os import getenv
from schedule import every, run_pending
from sys import exit
from time import sleep
from requests import get
from datetime import datetime

# Azure SDK Imports
from azure.identity import ClientSecretCredential
from azure.mgmt.dns import DnsManagementClient
from azure.mgmt.dns.models import RecordSet, ARecord
from azure.core.exceptions import ResourceNotFoundError

# Third-Party Imports
from logging import getLogger

# Local Imports
from config import AzureDDNSUpdaterConfiguration

class AzureDDNSUpdater:
    def __init__(self, config: AzureDDNSUpdaterConfiguration):
        # "Private" instance variables
        self._log = getLogger("azure-ddns-updater")     # https://www.loggly.com/ultimate-guide/python-logging-basics/

        # TODO: We need a more thorough check for the config object properties if config exists.
        if not config:
            config = AzureDDNSUpdaterConfiguration()
            config.azure_client_id = get_env_var('AZURE_CLIENT_ID')
            config.azure_client_secret = get_env_var('AZURE_CLIENT_SECRET')
            config.azure_tenant_id = get_env_var('AZURE_TENANT_ID')
            config.subscription_id = get_env_var('SUBSCRIPTION_ID')
            config.resource_group = get_env_var('RESOURCE_GROUP')
            config.dns_zone = get_env_var('DNS_ZONE')
            config.record_names = get_env_var('RECORD_NAMES')
            config.ttl = get_env_var('TTL')

        self._config = config

        self._names = [name.strip() for name in self._config.record_names.strip("[]").split(',')]

    def _get_env_var(self, name, hide_value = False) -> str:
        """Retrieve an environment variable; exit if not set as they are all required."""

        value = getenv(name)

        if value is None:
            self._log.error("The environment variable %s is not set.", name)
            exit(1)

        value = value.strip()

        self._log.info("%s : %s", {name:20}, value if not hide_value else "*** (hidden)")

        return value

    def get_public_ip(self) -> str:
        """Retrieve the current public IP address using ipify."""

        try:
            response = get("https://api.ipify.org?format=json")
            response.raise_for_status()
            ip = response.json().get("ip", "")

            if not ip:
                raise ValueError("Empty IP address received.")

            return ip
        except Exception as e:
            self._log.error("Error retrieving public IP: %s", e)

            return None

    def run_dynamic_dns_check(self):
        # Get the current public IP.
        current_ip = self.get_public_ip()

        if not current_ip:
            self._log.info("Could not get public IP. Skipping update.")
            return

        self._log.info("Current public IP: %1", current_ip)

        config = self._config

        # Create Azure credentials and client.
        try:
            credential = ClientSecretCredential(config.azure_tenant_id, config.azure_client_id, config.azure_client_secret)
        except Exception as e:
            self._log.error("Error creating service principal credentials: %s", e)
            exit(1)

        dns_client = DnsManagementClient(credential, config.subscription_id)

        # Try to retrieve the existing A records.
        ip_match = True

        try:
            for name in self._names:
                record_set = dns_client.record_sets.get(config.resource_group, config.dns_zone, name, "A")
                existing_ips = [record.ipv4_address for record in record_set.a_records] if record_set.a_records else []
                ttl = record_set.ttl or config.ttl

                if current_ip in existing_ips:
                    self._log.info("DNS A record %s: IP matches current DNS. No update needed.", name)
                else:
                    ip_match = False
                    self._log.info("DNS A record %s: Existing DNS A record IPs: %s", name, existing_ips)
                    self._log.info("DNS A record %s: IPs differ. Updating DNS record.", name)
        except ResourceNotFoundError:
            ip_match = False
            self._log.error("DNS A record %s: No existing A record found. A new record set will be created.", name)

        # Create or update DNS record if needed.
        if not ip_match:
            for name in self._names:
                record_set_params = RecordSet(
                    ttl = ttl,
                    a_records = [ARecord(ipv4_address = current_ip)]
                )
                try:
                    dns_client.record_sets.create_or_update(config.resource_group, config.dns_zone, name, "A", record_set_params)
                    self._log.info("DNS A record %s: IP successfully updated to %s with TTL %s seconds.", name, current_ip, ttl)
                except Exception as e:
                    self._log.error("DNS A record %s: Error updating DNS record: %s", name, e)
