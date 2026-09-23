FROM python:3.11-slim

WORKDIR /app

# Install git and curl
RUN apt-get update && apt-get install -y --no-install-recommends git curl && rm -rf /var/lib/apt/lists/*

# Install python dependencies
ENV PIP_ROOT_USER_ACTION=ignore
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy codebase
COPY . .

# Set default git identity
RUN git config --global user.name "larsson-scanner[bot]" && \
    git config --global user.email "bot@larsson-scanner.cloud"

EXPOSE 8080 10000

ENV PYTHONUNBUFFERED=1
ENV PORT=8080

CMD ["python", "src/main.py", "--scheduler"]
