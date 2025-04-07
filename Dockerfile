# Use Python 3.8 base image
FROM python:3.8-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    gcc \
    pkg-config \
    libsm6 libxext6 libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy files
COPY requirements.txt ./
COPY server_echo.py ./
COPY ball_worker.py ./
COPY public ./public
COPY certificate.key ./
COPY certificate.pem ./
COPY readme.md ./


# Install Python dependencies
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Expose the WebTransport server port
EXPOSE 4433

# Run your server
CMD ["python", "-u", "server_echo.py", "certificate.pem", "certificate.key"]