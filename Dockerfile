FROM python:3.10-slim

WORKDIR /app

COPY skylark-bi-agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY skylark-bi-agent/ .

CMD ["chainlit", "run", "main.py", "--port", "8000", "--host", "0.0.0.0"]
