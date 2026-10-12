FROM python:3.12-slim
WORKDIR /app
COPY requirements*.txt ./
RUN --mount=type=secret,id=build_ca \
    if [ -f /run/secrets/build_ca ]; then PIP_CERT=/run/secrets/build_ca pip install --no-cache-dir -r requirements.lock.txt; else pip install --no-cache-dir -r requirements.lock.txt; fi
RUN useradd --create-home dataneat && mkdir /app/storage && chown dataneat:dataneat /app/storage
COPY --chown=dataneat:dataneat app ./app
USER dataneat
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
