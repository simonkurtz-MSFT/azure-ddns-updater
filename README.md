# Azure Dynamic DNS Updater

[![contributions welcome](https://img.shields.io/badge/contributions-welcome-brightgreen.svg?style=flat)](https://github.com/simonkurtz-MSFT/azure-ddns-updater/tree/main)
[![MIT license](https://img.shields.io/badge/License-MIT-blue.svg)](https://mit-license.org/)

This repo exists to support scenarios where an IP address needs to be updated in DNS records. It used to be that dynamic DNS was a free offering, but that has changed. Most services I see nowadays charge, or, if it's free, it's limited in such ways as to not support custom domains. ISPs typically upcharge for static IPs such as through business plans, etc. As I use my own domain with Azure DNS, I wanted a process that could update the A record any time my home network's public IP changed. But Azure DNS does not natively support dynamic DNS. Records must be updated with an external process. So I went out in search to find whether a solution existed already and came across [Renan's blog post](https://renanm.com/posts/keep-your-dns-uptodate-with-azure/), which then formed the basis of my project.

## Docker Container Images

- The **linux/arm64** images are hosted on Docker Hub [here](https://hub.docker.com/r/simonkurtzmsft/azure-ddns-updater-arm64).
- The **linux/amd64** images are hosted on Docker Hub [here](https://hub.docker.com/r/simonkurtzmsft/azure-ddns-updater-amd64).

## Technology & Prerequisites

This repo contains a Python script and a docker container setup to update A records in Azure DNS. Specifically, the container is set up for an ARM64 build to be run on a Raspberry Pi. Python 3.13 is used with an Alpine container image as Alpine is traditionally a small Linux distro. An Azure DNS zone must exist, and authentication to Azure is done with the help of a Service Principal.

### Simply Running the Container

If all you want to do is run the container, you need the following:

- An active Azure subscription
- An Azure DNS zone (e.g. *contoso.com*) with at least one A record
- An Azure Service Principal (client/app ID and secret) to authenticate (see below)
- A container runtime such as Docker or Podman
- The Azure CLI, so that you can log in and create the service principal

### Developing the Container

If you want to code, you need the following in addition to the aforementioned items above:

- An IDE such as VS Code
- Python 3.13

## Setup

Once you have covered your appropriate prerequisites above, you can proceed.

### Create a Service Principal

We first need to create an Azure Service Principal to obtain a client/app ID and password. It's best to keep the scope narrow to only what you need to access.

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

### Python Requirements

To avoid clobbering global Python packages, it is advisable to create a virtual environment local to this project.

1. In VS Code, press F1, then type *Python: Select Interpreter*.
1. Select *Create Virtual Environment*.
1. Select *Venv*.
1. Select the Python version to use based on what you have installed.
1. Check *requirements.txt* to subsequently install all the packages this project needs. Press *OK* to start the setup. This may take a few minutes.

You should now see a new *.venv* folder in the root of this project. Note that the folder and its contents are deliberately excluded from Git, so they will not be checked in.

### Configure Environment Variables

These are two ways to set up the environment variables:

#### Environment File

If you are not running a container locally, you can set variables to get passed into the python script (or, later, the container).

1. Copy the `azure-ddns-updater.env.template` file to one named `azure-ddns-updater.env`.
1. Replace these placeholders with your own values. **Do not use quotes or apostrophes with strings.**:

    - **RECORD_NAMES** is a comma-separated array with one or more entries (e.g. `[home]`, `[router,home]`)
    - **INTERVAL_MINUTES**: if negative (e.g. `-1`), the script only executes once; if equal to or greater than zero (ideally, `1` or higher), it executes on that interval.

    ```shell
    AZURE_CLIENT_ID=<your Client / App ID>
    AZURE_CLIENT_SECRET=<your Client App Secret (best to reference rather than adding in clear text here)>
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

#### Docker Compose

Modify the Docker `compose.yml` file with your values, then save it.

## Test

There are two ways to test this:

### Environment File

The python script can be executed in a shell via `./run.sh`. Note the environment variable filename in the script and change, if desired.

### Docker Compose

Follow these steps if you want to run the container:

1. Build the container (see steps 1 & 2 in the next section).
1. Change the [container image source to a local directory](https://stackoverflow.com/questions/70473147/how-to-use-locally-built-image-in-docker-compose-file-correctly).
1. Switch to the directory containing the `compose.yml` file.
1. `docker compose up -d`

## Build & Push the Container to the Container Registry

Ensure that the desired version is set in the `VERSION` constant in *azure-ddns-updater.py*.

### ARM64

I primarily build for `linux/arm64` as the container will run on a Raspberry Pi, but you can alter that build behavior as you need (e.g. `linux/amd64`). Replace `<container-registry-name>` and `<version>`with your own.

1. In a shell, set the variables appropriately:

    ```shell
    BUILD_PLATFORM=linux/arm64
    IMAGE_NAME=azure-ddns-updater-arm64
    CONTAINER_REGISTRY_NAME=<container-registry-name>
    AZURE_DDNS_UPDATER_CONTAINER_VERSION=<version>
    ```

1. Execute the build, tag the image, then push it to the registry:

    ```shell
    docker build --platform $BUILD_PLATFORM -t $CONTAINER_REGISTRY_NAME/$IMAGE_NAME:$AZURE_DDNS_UPDATER_CONTAINER_VERSION .
    docker push $CONTAINER_REGISTRY_NAME/$IMAGE_NAME:$AZURE_DDNS_UPDATER_CONTAINER_VERSION
    ```

1. The image should be in your registry's repository now. If you need to set this version to be `latest` as well, run the following:

    ```shell
    docker tag $IMAGE_NAME:$AZURE_DDNS_UPDATER_CONTAINER_VERSION $CONTAINER_REGISTRY_NAME/$IMAGE_NAME:latest
    docker push $CONTAINER_REGISTRY_NAME/$IMAGE_NAME:latest
    ```

### AMD64

1. Repeat the steps above but set two variables differently:

    ```shell
    BUILD_PLATFORM=linux/amd64
    IMAGE_NAME=azure-ddns-updater-amd64
    ```

## Pull & Run the Container

Pull the image down on a host running Docker. You can either pull it from [my repos on DockerHub](https://hub.docker.com/u/simonkurtzmsft) or host your own. There are a variety of ways to do this.

### Docker Compose

1. On the host, copy this repo's Docker `compose.yml` file with your values.
1. `docker compose up -d` (`-d` runs in detached mode, which is what we want)

### Environment File

1. On the host, create an environment configuration file, *azure-ddns-updater.env*. Copy the settings from above. Alternatively, take another approach to passing variables into the container (e.g. arguments on `docker run`)

1. `docker pull <container-registry-name>/azure-ddns-updater-arm64:latest`
1. Run the container:
    1. `docker run --detach --env-file azure-ddns-updater-env <container-registry-name>/azure-ddns-updater-arm64:latest` to run it detached (preferred method), or
    1. `docker run --it --env-file azure-ddns-updater-env <container-registry-name>/azure-ddns-updater-arm64:latest` to run it interactively and view the logs (good for initial verification)

## View the logs

When running `detached`, you can view the logs.

1. `docker ps`
1. `docker logs -f <container id or name>`

## Check Container Health

The Dockerfile sets up a health check, which you can query: `docker inspect --format='{{json .State.Health.Status}}' azure-ddns-updater`

For more details, use jq to format the JSON of the larger object. You may need to get jq via `sudo apt-get install jq`.

```shell
docker inspect --format='{{json .State.Health}}' azure-ddns-updater | jq .
```

## Limitations

- Does not (yet) support IPv6 (AAAA records).
