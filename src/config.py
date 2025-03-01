"""
Module providing Configuration for Azure Dynamic DNS Updater
"""

class AzureDDNSUpdaterConfiguration:
    azure_client_id = None
    azure_client_secret = None
    azure_tenant_id = None
    subscription_id = None
    resource_group = None
    dns_zone = None
    record_names = None
    ttl = None
