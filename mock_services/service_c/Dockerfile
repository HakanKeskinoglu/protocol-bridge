FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir "pymodbus==3.5.4"
COPY main.py .
CMD ["python", "main.py"]