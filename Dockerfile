FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd -m app
COPY core.py server.py ./
USER app
ENTRYPOINT ["python", "server.py"]
