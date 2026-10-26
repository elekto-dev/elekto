FROM python:3.13-bookworm AS base

WORKDIR /app

ADD requirements.txt /app
RUN pip install -r requirements.txt

ADD . /app

RUN pip install --no-deps -e .

USER 10017

ENTRYPOINT ["./entrypoint.sh"]

FROM base AS test

RUN mkdir /tmp/app
RUN touch /tmp/app/test.db
ENV DB_PATH=/tmp/app/test.db

CMD ["./test-entrypoint.sh"]
