FROM python:3.9-slim

# Add at the top of Dockerfile
ENV PYTHONUNBUFFERED=1

# Install python-dotenv
RUN pip install python-dotenv

# Ensure .env is copied
COPY .env /app/.env

RUN apt-get update && apt-get install -y \
    build-essential \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . /app

# Install Python dependencies, including faiss-cpu explicitly
RUN pip install --no-cache-dir faiss-cpu==1.7.4 \
    && pip install --no-cache-dir -r requirements.txt

EXPOSE 5000

CMD ["gunicorn", "-b", "0.0.0.0:5000", "app:app"]
