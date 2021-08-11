FROM python:3.9-alpine

RUN apk add sqlite

WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY ./src .
CMD ["./entrypoint.sh"]
