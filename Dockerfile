FROM python:3.10-slim

WORKDIR /app

# Install dependencies required for the model and application
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Ensure the model directory can be created locally
RUN mkdir -p /app/model_weights

# Copy the config files and tokenizer into the model folder
COPY checkpoint-31074 /app/checkpoint-31074

# Download the heavy model weights directly from Azure Blob Storage
ADD https://weightsapd.blob.core.windows.net/weights/model.safetensors /app/checkpoint-31074/model.safetensors
RUN chmod 644 /app/checkpoint-31074/model.safetensors

# Copy application source code
COPY app.py .

# Expose port for FastAPI
EXPOSE 8000

# Start Uvicorn
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
