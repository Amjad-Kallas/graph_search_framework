FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY . .

EXPOSE 8501
 
RUN mkdir -p /root/.streamlit && \
    cp deploy/.streamlit/config.toml /root/.streamlit/config.toml

CMD ["sh", "-c", "streamlit run src/kg_to_story/app/demo_app.py --server.address=0.0.0.0 --server.port=8501"]