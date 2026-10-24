FROM python:3.11-alpine
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir --index-url https://mirrors.aliyun.com/pypi/simple -r requirements.txt
COPY app ./app
ENV DEMO_DB_PATH=/srv/data/demo.sqlite3
RUN mkdir -p /srv/data
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
