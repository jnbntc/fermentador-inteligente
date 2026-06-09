FROM mcr.microsoft.com/devcontainers/python:3.11-bookworm

# Dependencias del sistema y compiladores de C++
RUN apt-get update && apt-get install -y --no-install-recommends \
    bc \
    build-essential \
    curl \
    git \
    python3-pip \
    python3-setuptools \
    python3-venv \
    udev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

USER vscode

# Inyectamos el directorio local binario al PATH del sistema
ENV PATH="/home/vscode/.local/bin:${PATH}"

# Instalación de PlatformIO Core (ahora el sistema sabrá dónde queda 'pio')
RUN pip3 install --no-cache-dir -U platformio

# Precarga del framework de ESP32 para acelerar el cold-start
RUN pio platform install espressif32
