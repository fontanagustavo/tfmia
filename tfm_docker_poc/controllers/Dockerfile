FROM python:3.12-slim
WORKDIR /app
COPY requirements-common.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY controllers /app
CMD ["python", "aiops.py"]
