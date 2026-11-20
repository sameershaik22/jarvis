# Official Microsoft Playwright base image with Python and all Linux browser dependencies pre-installed
FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

WORKDIR /app

# Ensure non-buffered stdout for real-time logging in cloud environments
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    BROWSER_HEADLESS=true \
    BROWSER_CHANNEL=chromium \
    ENVIRONMENT=production

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install Playwright browser binaries (OS dependencies are already pre-baked into the image)
RUN playwright install chromium

# Copy application source code
COPY . .

# Expose backend port
EXPOSE 8000

# Start FastAPI application using uvicorn binding to the dynamic Render $PORT
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
