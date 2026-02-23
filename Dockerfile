FROM python:3.12-slim

RUN apt-get update && apt-get install -y libopus0 ffmpeg
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create data directory and set permissions
RUN mkdir -p /app/data && chown 1000:1000 /app/data

CMD ["python", "bot.py"]