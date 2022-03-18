FROM continuumio/miniconda3

WORKDIR /src

# Create the environment:
ADD requirements.txt /tmp/requirements.txt
RUN conda create -n human python=3.9
# && conda activate human && pip install -r /tmp/req

# Make RUN commands use the new environment:
SHELL ["conda", "run", "-n", "human", "/bin/bash", "-c"]

RUN pip install -r /tmp/requirements.txt

# Make sure the environment is activated:
# RUN echo "Make sure flask is installed:"
# RUN python -c "import flask"

# Copy files
COPY app app
COPY data data
COPY instance instance
COPY uploaded_files uploaded_files
# COPY logo.png .
COPY start.py .
COPY config.py .
COPY protocol.yml .

# The code to run when container is started:
# -

# Open port 8000
EXPOSE 8000

# Start with Gunicorn
ENTRYPOINT ["conda", "run", "--no-capture-output", "-n", "human", "gunicorn", "-b=0.0.0.0:8000", "-w=3", "--worker-tmp-dir=/dev/shm", "--log-level=debug", "start"]
