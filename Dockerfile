FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

ENV CVAAS_ADMIN_USER=admin
ENV CVAAS_ADMIN_PASSWORD=allthingsareperfect

EXPOSE 8000

CMD ["python", "run.py"]
