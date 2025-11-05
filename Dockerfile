# Use a modern, supported base image: Debian 12 (Bookworm)
FROM python:3.11-slim-bookworm

# Install Chromium and its essential dependencies
# This list is optimized for headless browser operation in a container
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    libglib2.0-0 \
    libnss3 \
    libgconf-2-4 \
    libfontconfig1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your application code into the container
COPY . .

# Command to run your Python script
# Replace 'your_script_name.py' with your actual script filename
CMD ["python", "main.py"]
