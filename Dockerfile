# AWS Lambda container image with Playwright and Chromium
# Based on AWS Lambda Python base image

FROM public.ecr.aws/lambda/python:3.12

# Install system dependencies for Chromium
RUN dnf install -y \
    atk \
    cups-libs \
    gtk3 \
    libXcomposite \
    libXcursor \
    libXdamage \
    libXext \
    libXi \
    libXrandr \
    libXScrnSaver \
    libXtst \
    pango \
    alsa-lib \
    libdrm \
    libgbm \
    libxkbcommon \
    libxshmfence \
    nss \
    mesa-libgbm \
    at-spi2-atk \
    && dnf clean all

# Copy requirements and install Python dependencies
COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

# Install Playwright browsers (Chromium only to minimize size)
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright
RUN playwright install chromium --with-deps

# Copy application code
COPY src/ ${LAMBDA_TASK_ROOT}/src/

# Set the handler
CMD [ "src.handlers.crawler.handler" ]
