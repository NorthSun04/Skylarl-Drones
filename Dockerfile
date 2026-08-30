FROM python:3.10-slim

WORKDIR /app/skylark-bi-agent

COPY skylark-bi-agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY skylark-bi-agent/ .

CMD ["python", "main.py"]
