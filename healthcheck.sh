#!/bin/sh

# Check if the Python script is running
if ! pgrep -f "python3 azure-ddns-updater.py" > /dev/null; then
    echo "Python3 azure-ddns-updater.py is not running."
    exit 1
fi

# Check the contents of health.log - if we don't find exactly, we error
if [ "$(tr -d '\n' < ./health.log)" != "0" ]; then
    echo "Health.log does not contain 0."
    exit 1
fi

echo "All health checks passed."
exit 0
