FROM python:3.11-slim

WORKDIR /app

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the reclaim package (backend API)
COPY reclaim/ ./reclaim/

# Copy config for runtime policy
COPY config/ ./config/

# Ensure all source files are readable (local file perms can be restrictive)
RUN chmod -R a+rX reclaim/ config/

# Set Python path
ENV PYTHONPATH=/app

# Environment variables (overridden at deploy time)
ENV RECLAIM_USE_LLM=true
ENV RECLAIM_ENV=production

# Create non-root user for security
RUN adduser --disabled-password --no-create-home appuser
USER appuser

# Expose port
EXPOSE 8080

# Run the API
CMD ["uvicorn", "reclaim.api.app:app", "--host", "0.0.0.0", "--port", "8080"]
