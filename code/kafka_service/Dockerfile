# image used by the worker and the API
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py ./
EXPOSE 8619
CMD ["python", "worker.py"]
