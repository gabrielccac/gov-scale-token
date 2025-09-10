# Start with a stable Python base image
FROM python:3.12-slim

# Set the working directory
WORKDIR /app

# --- Install System Dependencies for Xvfb and Chrome ---
RUN apt-get update && apt-get install -y \
    xvfb \
    xauth \
    gnupg \
    wget \
    ca-certificates \
    --no-install-recommends && \
    wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/googlechrome-linux-keyring.gpg && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/googlechrome-linux-keyring.gpg] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update && \
    apt-get install -y \
    google-chrome-stable \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# --- Install Python Packages ---
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Install Drivers during build to prevent race conditions ---
RUN seleniumbase install chromedriver
RUN seleniumbase install uc_driver

# --- Copy Application and Entrypoint ---
COPY server.py .
COPY docker-entrypoint.sh .

# --- Configure and Run ---
ENV DISPLAY=:99
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
