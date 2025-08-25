FROM continuumio/miniconda3:latest

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy conda environment file
COPY conda-environment.yml .

# Create conda environment
RUN conda env create -f conda-environment.yml

# Activate conda environment and make it default
SHELL ["conda", "run", "-n", "balloon-hud", "/bin/bash", "-c"]

# Copy application code
COPY . .

# Create data directory for SQLite database
RUN mkdir -p /app/data

# Expose port (Render will provide PORT env var)
EXPOSE $PORT

# Set environment variables
ENV CONDA_DEFAULT_ENV=balloon-hud
ENV PATH="/opt/conda/envs/balloon-hud/bin:$PATH"

# Run the application
CMD ["conda", "run", "--no-capture-output", "-n", "balloon-hud", "python", "src/app.py"]