# Preserve the supported Python runtime while using Alpine's small base image.
FROM python:3.13-alpine

# Avoid runtime bytecode writes and send logs immediately to the container runtime.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Keep relative application paths, including the health check, rooted in /app.
WORKDIR /app

# Install runtime dependencies separately so code changes reuse this cached layer.
# Development tools are declared in requirements-dev.txt and stay out of the image.
COPY requirements.txt .
# Skip pip caches and bytecode to reduce layer size. Require prebuilt wheels so
# missing native wheels fail the build rather than requiring a compiler toolchain.
RUN python -m pip install --no-cache-dir --no-compile --only-binary=:all: -r requirements.txt

# Copy only runtime files, after the dependency layer to preserve build caching.
COPY azure-ddns-updater.py azure_ddns_updater.py healthcheck.sh ./
# Create a password-disabled system account with stable IDs and no home directory.
# Normalize Windows line endings so Alpine's shell can run the health check.
# Keep /app and source files root-owned and readable, but not writable by appuser.
# Pre-create health.log beside the source, with read/write access for appuser only.
RUN addgroup -S -g 10001 appuser \
    && adduser -S -D -H -u 10001 -G appuser -h /app appuser \
    && sed -i 's/\r$//' healthcheck.sh \
    && chmod 644 requirements.txt azure-ddns-updater.py azure_ddns_updater.py healthcheck.sh \
    && chmod 755 /app \
    && touch health.log \
    && chown appuser:appuser health.log \
    && chmod 600 health.log

# Drop root privileges for both the updater and its health check. Numeric IDs also
# make ownership predictable when mounting the writable health file.
USER 10001:10001

# Check the local process and last update result without making network requests.
# Allow startup time for the first update before counting health-check failures.
# Invoke the script through /bin/sh so it does not need executable permissions.
HEALTHCHECK --interval=60s --timeout=5s --start-period=30s --retries=3 \
    CMD ["/bin/sh", "/app/healthcheck.sh"]

# Exec-form startup makes Python PID 1, receiving container stop signals directly
# rather than through a shell wrapper.
CMD ["python3", "azure-ddns-updater.py"]
