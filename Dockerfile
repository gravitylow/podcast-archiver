FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Enable unbuffered output and disable tqdm
ENV PYTHONUNBUFFERED=1
ENV TQDM_DISABLE=1

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the script
COPY archive_podcasts.py .

# Make script executable
RUN chmod +x archive_podcasts.py

# Set the entrypoint
ENTRYPOINT ["python", "-u", "archive_podcasts.py"]
