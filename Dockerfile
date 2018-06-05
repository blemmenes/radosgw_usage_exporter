FROM python:2-slim

RUN mkdir -p /usr/src/app
WORKDIR /usr/src/app

COPY requirements.txt /usr/src/app
RUN pip install --no-cache-dir -r requirements.txt

COPY radosgw_usage_exporter.py /usr/src/app

EXPOSE 9242
ENV RADOSGW_SERVER=http://radosgw:80 VIRTUAL_PORT=9242 DEBUG=0

ENTRYPOINT [ "python", "-u", "./radosgw_usage_exporter.py" ]
CMD []
