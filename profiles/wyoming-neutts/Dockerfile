FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        espeak-ng \
        libsndfile1 \
        build-essential \
        cmake \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
        setuptools \
        wheel \
        numpy \
        wyoming[zeroconf] \
        "neutts[llama]" \
    && rm -rf /root/.cache/pip

COPY server.py /server.py

EXPOSE 10400

ENTRYPOINT ["python", "/server.py"]
