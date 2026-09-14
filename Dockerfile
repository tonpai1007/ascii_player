FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
# ffmpeg: video decoding
# libgl1: opencv GUI backend
# libglib2.0-0: opencv runtime
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        libgl1-mesa-glx \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install the package
COPY . .
RUN pip install --no-cache-dir -e .

# Create non-root user
RUN useradd -m -u 1000 runner && chown -R runner:runner /app
USER runner

# Expose port for health endpoint (if running in server mode)
EXPOSE 8080

# Default to TUI mode; user can override with --webcam or video file
ENTRYPOINT ["ascii-player"]
CMD []