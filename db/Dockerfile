FROM python:3.12.14-slim-trixie

WORKDIR /db

COPY db/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY db/migrations ./migrations
COPY db/set_app_password.py .

CMD ["sh", "-c", "pyway validate && pyway migrate && python set_app_password.py"]