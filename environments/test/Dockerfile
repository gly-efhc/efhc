FROM python:3.12-slim
WORKDIR /efhc
# Render Docker context is the GitHub repository root (.).
COPY backend/ /efhc/backend/
COPY environments/test/demo_backend/ /efhc/demo_backend/
RUN pip install --no-cache-dir -r /efhc/backend/requirements.txt
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "demo_backend.asgi:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
