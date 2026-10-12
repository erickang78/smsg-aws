FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home smsg && mkdir /data && chown smsg:smsg /data
COPY app.py seed.json ./
COPY static ./static
ENV SMSG_DB=/data/smsg.sqlite3
USER smsg
EXPOSE 8000
CMD ["gunicorn","--bind","0.0.0.0:8000","--workers","2","--access-logfile","-","--error-logfile","-","--forwarded-allow-ips","*","app:application"]
