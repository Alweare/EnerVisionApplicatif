FROM python:3.12.14-slim-trixie
RUN pip install pyway psycopg2-binary
WORKDIR /app
COPY migrations ./migrations
COPY set_app_password.py .
CMD ["sh", "-c", "pyway validate && pyway migrate && python set_app_password.py"]