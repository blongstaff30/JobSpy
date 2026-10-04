FROM mcr.microsoft.com/azure-functions/python:4-python3.11

ENV AzureWebJobsScriptRoot=/home/site/wwwroot \
    AzureFunctionsJobHost__Logging__Console__IsEnabled=true \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

COPY . /home/site/wwwroot
WORKDIR /home/site/wwwroot
RUN pip install --no-cache-dir -r /home/site/wwwroot/requirements.txt
RUN apt-get update && apt-get install --no-install-recommends -y \
        libasound2 \
        libatk1.0-0 \
        libatk-bridge2.0-0 \
        libcairo-gobject2 \
        libcairo2 \
        libdbus-1-3 \
        libdrm2 \
        libgbm1 \
        libgdk-pixbuf-2.0-0 \
        libglib2.0-0 \
        libgtk-3-0 \
        libnspr4 \
        libnss3 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libx11-6 \
        libx11-xcb1 \
        libxcb1 \
        libxcomposite1 \
        libxcursor1 \
        libxdamage1 \
        libxext6 \
        libxfixes3 \
        libxi6 \
        libxrandr2 \
        libxtst6 \
    && rm -rf /var/lib/apt/lists/*
RUN playwright install firefox
