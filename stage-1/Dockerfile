FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

# IANA timezone data baked into the image: the service resolves restaurant-local
# times with no outbound network at run time.
RUN pip install --no-cache-dir tzdata==2025.2

WORKDIR /app
COPY app.py ./

EXPOSE 8080
CMD ["python", "-u", "app.py"]
