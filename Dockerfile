FROM python:3.13-alpine

# Set the working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application code
COPY azure-ddns-updater.py .

# Set up health check
COPY healthcheck.sh .
RUN sed -i 's/\r$//' healthcheck.sh && chmod +x healthcheck.sh
HEALTHCHECK --interval=60s --timeout=5s --retries=3 CMD /bin/sh ./healthcheck.sh

# Run the application
CMD ["python3", "azure-ddns-updater.py"]
