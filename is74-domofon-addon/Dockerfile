ARG BUILD_FROM
FROM $BUILD_FROM

# Install system dependencies
RUN apk add --no-cache \
    python3 \
    py3-pip \
    gcc \
    musl-dev \
    python3-dev \
    libffi-dev \
    openssl-dev

# Set working directory
WORKDIR /app

# Copy requirements first for caching
COPY ../requirements.txt /app/

# Install Python dependencies
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# Copy source code
COPY ../src/ /app/src/
COPY ../run_api.py /app/
COPY ../static/ /app/static/

# Copy run script
COPY run.sh /
RUN chmod a+x /run.sh

# Create config directory
RUN mkdir -p /app/config

# Expose port
EXPOSE 10777

CMD [ "/run.sh" ]
