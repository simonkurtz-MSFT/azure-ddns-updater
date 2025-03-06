FROM python:3.13-alpine

# Set the working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Create a non-root user (no password, no home directory creation and instead use /app as home)
RUN adduser -D -H -h /app appuser

# Copy application code
COPY azure-ddns-updater.py .

# Set up health check
COPY healthcheck.sh .
RUN sed -i 's/\r$//' healthcheck.sh && chmod +x healthcheck.sh
HEALTHCHECK --interval=60s --timeout=5s --retries=3 CMD /bin/sh ./healthcheck.sh

# Change ownership of the application files to the non-root user (appuser) and group (appuser)
RUN chown -R appuser:appuser /app

# Switch to the non-root user
USER appuser

# Run the application
CMD ["python3", "azure-ddns-updater.py"]
