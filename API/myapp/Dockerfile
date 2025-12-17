# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /app

# Copy the pyproject.toml and poetry.lock files to the working directory
COPY pyproject.toml poetry.lock* /app/

# Install Poetry
RUN pip install poetry

# Install dependencies (this layer will be cached if pyproject.toml and poetry.lock don't change)
RUN poetry install --no-root --no-interaction --no-ansi

# Copy the rest of the application code
COPY myapp /app/myapp

# Expose the port FastAPI will run on
EXPOSE 8000

# Command to run the FastAPI app using uvicorn
CMD ["poetry", "run", "uvicorn", "myapp.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

