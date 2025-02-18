#!/bin/bash

# Load the azure-ddns-updater-env file
if [ -f azure-ddns-updater.env ]; then
    export $(cat azure-ddns-updater.env | xargs)
fi

python azure-ddns-updater.py