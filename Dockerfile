FROM mcr.microsoft.com/azure-functions/python:4-python3.11

ENV AzureWebJobsScriptRoot=/home/site/wwwroot \
    AzureFunctionsJobHost__Logging__Console__IsEnabled=true \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

COPY . /home/site/wwwroot
WORKDIR /home/site/wwwroot
RUN pip install --no-cache-dir -r /home/site/wwwroot/requirements.txt \
    && playwright install --with-deps firefox
