FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    addgroup --system cvaas && \
    adduser --system --ingroup cvaas --home /home/cvaas cvaas

COPY . .

RUN mkdir -p /app/static/uploads/certificates && \
    chown -R cvaas:cvaas /app

EXPOSE 8000

USER cvaas

CMD ["python", "run.py"]
