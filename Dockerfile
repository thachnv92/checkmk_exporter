FROM python:alpine

LABEL maintainer="ThachNV92"

COPY files/exporter.py /exporter.py

RUN pip install --no-cache-dir --upgrade requests pip

EXPOSE 9293

CMD [ "python", "/exporter.py" ]
