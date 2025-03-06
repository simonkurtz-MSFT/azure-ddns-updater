"""
azure_dns_updater.py: A dynamic DNS updater for Azure DNS

This script retrieves your current public IP address and updates the specified Azure DNS A record if it has changed.
"""

import sys
from os import getenv
from datetime import datetime
from time import sleep
from requests import get
from schedule import every, run_pending
from azure.identity import ClientSecretCredential
from azure.mgmt.dns import DnsManagementClient
from azure.mgmt.dns.models import RecordSet, ARecord
from azure.core.exceptions import ResourceNotFoundError

# ------------------------
#    HELPER FUNCTIONS
# ------------------------

def log(message):
    """Log a timestamped message to the console."""

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {message}", flush = True)

def get_env_var(name, hide_value = False):
    """Retrieve an environment variable; exit if not set as they are all required."""

    value = getenv(name)

    if value is None:
        log(f"Error: The environment variable {name} is not set.")
        sys.exit(1)

    value = value.strip()

    log(f"{name:20} : {'*** (hidden)' if hide_value else value}")

    return value

def get_public_ip():
    """Retrieve the current public IP address using ipify."""

    try:
        response = get("https://api.ipify.org?format=json", timeout = (5, 5))  # 5 second connect timeout, 5 second read timeout
        response.raise_for_status()
        ip = response.json().get("ip", "")

        if not ip:
            raise ValueError("Empty IP address received.")

        return ip
    except Exception as e:
        log(f"Error retrieving public IP: {e}")

        return None

# ------------------------
#    CONFIGURATION
# ------------------------
log("Azure Dynamic DNS Updater - V1.0.0")
log("----------------------------------")
log("")

AZURE_CLIENT_ID = get_env_var('AZURE_CLIENT_ID')
AZURE_CLIENT_SECRET = get_env_var('AZURE_CLIENT_SECRET', hide_value = True)
AZURE_TENANT_ID = get_env_var('AZURE_TENANT_ID')
SUBSCRIPTION_ID = get_env_var('SUBSCRIPTION_ID')
RESOURCE_GROUP = get_env_var('RESOURCE_GROUP')
DNS_ZONE = get_env_var('DNS_ZONE')
RECORD_NAMES = get_env_var('RECORD_NAMES')

names = [name.strip() for name in RECORD_NAMES.strip("[]").split(',')]

try:
    INTERVAL_MINUTES = int(getenv('INTERVAL_MINUTES').strip())
except (TypeError, ValueError):
    INTERVAL_MINUTES = 5

log(f"{'INTERVAL_MINUTES':20} : {INTERVAL_MINUTES}")

TTL = 300  # Time-to-live in seconds

# ------------------------
#    MAIN LOGIC
# ------------------------

def main():
    """Main logic for the script."""

    log("")

    # Get the public IP.
    current_ip = get_public_ip()

    if not current_ip:
        log("Could not get public IP. Skipping update.")
        return

    log(f"Current public IP: {current_ip}")

    # Create Azure credentials and client.
    try:
        credential = ClientSecretCredential(AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET)
    except Exception as e:
        log(f"Error creating service principal credentials: {e}")
        sys.exit(1)

    dns_client = DnsManagementClient(credential, SUBSCRIPTION_ID)

    # Try to retrieve the existing A records.
    ip_match = True

    try:
        for name in names:
            record_set = dns_client.record_sets.get(RESOURCE_GROUP, DNS_ZONE, name, "A")
            existing_ips = [record.ipv4_address for record in record_set.a_records] if record_set.a_records else []
            ttl = record_set.ttl or TTL

            if current_ip in existing_ips:
                log(f"DNS A record {name}: IP matches current DNS. No update needed.")
            else:
                ip_match = False
                log(f"DNS A record {name}: Existing DNS A record IPs: {existing_ips}")
                log(f"DNS A record {name}: IPs differ. Updating DNS record.")
    except ResourceNotFoundError:
        ip_match = False
        log(f"DNS A record {name}: No existing A record found. A new record set will be created.")
        ttl = TTL

    # Create or update DNS record if needed.
    if not ip_match:
        for name in names:
            record_set_params = RecordSet(
                ttl = ttl,
                a_records = [ARecord(ipv4_address = current_ip)]
            )
            try:
                dns_client.record_sets.create_or_update(RESOURCE_GROUP, DNS_ZONE, name, "A", record_set_params)
                log(f"DNS A record {name}: IP successfully updated to {current_ip} with TTL {ttl} seconds.")
            except Exception as e:
                log(f"DNS A record {name}: Error updating DNS record: {e}")

if __name__ == "__main__":
    main()

    # Run the scheduler if INTERVAL_MINUTES is set to a non-negative value; otherwise, exit after the first run.
    if INTERVAL_MINUTES >= 0:
        log("")
        log(f"Starting schedule with {INTERVAL_MINUTES} minute interval...")

        every(INTERVAL_MINUTES).minutes.do(main)

        try:
            while True:
                run_pending()
                sleep(1)
        except KeyboardInterrupt:
            log("Exiting gracefully...")

    log("")
    log("Done.")
