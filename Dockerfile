FROM python:3.13-alpine

# Set the working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application code
COPY azure-ddns-updater.py .

# Run the application
CMD ["python3", "azure-ddns-updater.py"]