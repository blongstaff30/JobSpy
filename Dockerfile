FROM mcr.microsoft.com/azure-functions/python:4-python3.11

ENV AzureWebJobsScriptRoot=/home/site/wwwroot \
    AzureFunctionsJobHost__Logging__Console__IsEnabled=true \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

COPY . /home/site/wwwroot
WORKDIR /home/site/wwwroot
RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        libasound2 \
        libatk1.0-0 \
        libcairo-gobject2 \
        libcairo2 \
        libdbus-1-3 \
        libgdk-pixbuf-2.0-0 \
        libgtk-3-0 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libxcomposite1 \
        libxcursor1 \
        libxdamage1 \
        libxfixes3 \
        libxi6 \
        libxrandr2 \
        libnss3 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r /home/site/wwwroot/requirements.txt \
    && playwright install firefox
