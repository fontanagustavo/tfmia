FROM python:3.12-slim
WORKDIR /app
COPY requirements-common.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY traffic/generator.py /app/generator.py
CMD ["python", "generator.py"]
