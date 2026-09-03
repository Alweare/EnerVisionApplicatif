FROM python:3.12.14-slim-trixie
WORKDIR /frontend
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8501
CMD ["streamlit", "run", "Dashboard.py", "--server.address=0.0.0.0", "--server.port=8501"]