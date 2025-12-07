# PII Anonymizer - Dockerfile
# Hybrid Context-Aware Anonymizer for Polish

FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Model cache directories
    HF_HOME=/cache/huggingface \
    TRANSFORMERS_CACHE=/cache/huggingface \
    SPACY_DATA=/cache/spacy \
    # PyTorch device (CPU in container, MPS only on native macOS)
    TORCH_DEVICE=cpu

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Create cache directories
RUN mkdir -p /cache/huggingface /cache/spacy

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Download spaCy Polish model
RUN python -m spacy download pl_core_news_lg

# Copy application code
COPY app/ ./app/
COPY data/ ./data/
COPY tests/ ./tests/

# Create models directory
RUN mkdir -p app/models

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

