FROM python:slim-bookworm

WORKDIR /app

COPY app.py requirements.txt ./
COPY templates/ ./templates/

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 5000

CMD ["flask", "run", "--host=0.0.0.0"]