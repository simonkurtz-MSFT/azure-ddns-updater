#!/bin/bash

# Check if the Python script is running
if ! pgrep -f "python3 azure-ddns-updater.py" > /dev/null; then
  exit 1
fi

# Check the contents of health.log
if grep -qv '0' ./health.log; then
  exit 1
fi

exit 0
