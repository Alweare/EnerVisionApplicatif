FROM python:3.12.14-slim-trixie
RUN pip install pyway
WORKDIR /app
COPY migrations ./migrations
CMD ["sh", "-c", "pyway validate && pyway migrate"]