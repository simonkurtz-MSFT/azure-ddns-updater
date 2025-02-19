# Azure Dynamic DNS Updater

This repo exists to support scenarios where an IP address needs to be updated in DNS records. It used to be that dynamic DNS was a free offering, but that has changed. Most services I see nowadays charge, or, if it's free, it's limited in such ways as to not support custom domains. ISPs typically upcharge for static IPs such as through business plans, etc. As I use my own domain with Azure DNS, I wanted a process that could update the A record any time my home network's public IP changed. But Azure DNS does not natively support dynamic DNS. Records must be updated with an external process. So I went out in search to find whether a solution existed already and came across [Renan's blog post](https://renanm.com/posts/keep-your-dns-uptodate-with-azure/), which then formed the basis of my project.

## Docker Container Images

- The **linux/arm64** images are hosted on Docker Hub [here](https://hub.docker.com/r/simonkurtzmsft/azure-ddns-updater-arm64).
- The **linux/amd64** images are hosted on Docker Hub [here](https://hub.docker.com/r/simonkurtzmsft/azure-ddns-updater-amd64).

## Technology & Prerequisites

This repo contains a Python script and a docker container setup to update A records in Azure DNS. Specifically, the container is set up for an ARM64 build to be run on a Raspberry Pi. Specifically, Python 3.13 is used with an Alpine container image as Alpine is traditionally a small Linux distro. An Azure DNS zone must exist, and authentication to Azure is done with the help of a Service Principal.

## Setup

### Create a Service Principal

We first need to create an Azure Service Principal to obtain a client / app ID and password. It's best to keep the scope narrow to only what you need to access.

1. Log into Azure and select your subscription. Collect the following information:
    1. Azure Tenant ID
    1. Subscription ID
    1. Resource group associated with the Azure DNS zone
    1. DNS Zone name
    1. Service Principal name (e.g. *azure-ddns-updater*)

1. Replace the `<service-principal-name>`, `<subscription-id>`, `<resource-group>`, and `<dns-zone>` parameters with your own in this command:
    `az ad sp create-for-rbac --name <service-principal-name> --role Contributor --scopes /subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.Network/dnsZones/<dns-zone>`
1. If you run in a shell, ensure that paths are not converted:
    `export MSYS_NO_PATHCONV=1`
1. Run the `az ad sp create-for-rbac` command with your replaced parameters. Take note of all parameters in the results:

    ```json
   {
      "appId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
      "displayName": "azure-ddns-updater",
      "password": "yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy",
      "tenant": "zzzzzzzz-zzzz-zzzz-zzzz-zzzzzzzzzzzz"
    }
    ```

### Configure Environment Variables

Variables get passed into the python script (or, later, the container).

1. Copy the `azure-ddns-updater.env.template` file to one named `azure-ddns-updater.env`.
1. Replace these placeholders with your own values. **Do not use quotes or apostrophes with strings.**:

    - **RECORD_NAMES** is a comma-separated array with one or more entries (e.g. `[home]`, `[router,home]`)
    - **INTERVAL_MINUTES**: if negative (e.g. `-1`), the script only executes once; if equal to or greater than zero (ideally, `1` or higher), it executes on that interval.

    ```shell
    AZURE_CLIENT_ID=<your Client / App ID>
    AZURE_CLIENT_SECRET=<your Client App Secret>
    AZURE_TENANT_ID=<your Azure Tenant ID>
    SUBSCRIPTION_ID=<your Azure Subscription ID>
    RESOURCE_GROUP=<your Azure DNS Zone resource group>
    DNS_ZONE=<your Azure DNS Zone>
    RECORD_NAMES=<your Azure DNS A Record>
    INTERVAL_MINUTES=<number of minutes for the interval or negative for a single run>
    ```

    For example:

    ```shell
    AZURE_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
    AZURE_CLIENT_SECRET=yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy
    AZURE_TENANT_ID=zzzzzzzz-zzzz-zzzz-zzzz-zzzzzzzzzzzz
    SUBSCRIPTION_ID=aaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa
    RESOURCE_GROUP=rg-dns
    DNS_ZONE=contoso.com
    RECORD_NAMES=[router]
    INTERVAL_MINUTES=<number of minutes for the interval or negative for a single run>
    ```

## Test

The python script can be executed in a shell via `./run.sh`. Note the environment variable filename in the script and change, if desired.

## Build & Push the Container to the Container Registry

I build for `linux/arm64` as the container will run on a Raspberry Pi, but you can alter that build behavior as you need. Replace `<container-registry-name>` with your own. You can also replace the `latest` tag as you see fit.

1. `docker build --platform linux/arm64 -t azure-ddns-updater-arm64:latest .`
1. `docker tag azure-ddns-updater-arm64:latest <container-registry-name>/azure-ddns-updater-arm64:latest`
1. `docker push <container-registry-name>/azure-ddns-updater-arm64:latest`

The image should be in your registry's repository now.

## Pull & Run

Pull the image down on a host running Docker. An environment configuration file, *azure-ddns-updater.env* needs to be present, or you need to take another approach to passing variables into the container.

1) `docker pull <container-registry-name>/azure-ddns-updater-arm64:latest`
1) `docker run --detach --env-file azure-ddns-updater-env <container-registry-name>/azure-ddns-updater-arm64:latest` to run it detached (preferred), or
1) `docker run --it --env-file azure-ddns-updater-env <container-registry-name>/azure-ddns-updater-arm64:latest` to run it interactively and view the logs (good for initial verification)

## View the logs

When running `detached`, you can view the logs.

1) `docker ps`
1) `docker logs -f <container id or name>`
