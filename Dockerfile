# Use Python as base for Podman Build from Dockerfiles

FROM python:3.12

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install any needed dependencies specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

#EXPOSE 4141

# Run app.py when the container launches
CMD ["python3", "app.py"]
