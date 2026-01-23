FROM python:3.11-slim

WORKDIR /app

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the shopq package (backend API)
COPY shopq/ ./shopq/

# Copy config for runtime policy
COPY config/ ./config/

# Create data directory for SQLite
RUN mkdir -p /app/shopq/data

# Set Python path
ENV PYTHONPATH=/app

# Environment variables (overridden at deploy time)
ENV SHOPQ_USE_LLM=true

# Expose port
EXPOSE 8080

# Run the API
CMD ["uvicorn", "shopq.api.app:app", "--host", "0.0.0.0", "--port", "8080"]
