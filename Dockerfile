# Build:
#   docker build -t fair-runner:local .
#
# Run with defaults (bundled example data, 2000-2050, abrupt+ramp scenarios):
#   echo '{}' | docker run --rm -i fair-runner:local
#
# Run with a local input file:
#   docker run --rm -i fair-runner:local < my_input.json
#
# Run runner.py directly inside the container (interactive):
#   docker run --rm -it fair-runner:local bash
#   # then inside: echo '{}' | python runner.py

FROM python:3.12-slim

WORKDIR /app

# Prevent matplotlib from trying to open a display
ENV MPLBACKEND=Agg

# Copy packaging files first so dependency install is cached separately from source changes
COPY setup.py setup.cfg versioneer.py README.md MANIFEST.in ./

# Copy the package source and default example data used by runner.py
COPY src ./src
COPY examples/data ./examples/data
COPY runner.py ./

RUN pip install --no-cache-dir -U pip \
    && pip install --no-cache-dir -e .

ENTRYPOINT ["python", "runner.py"]

# Read from stdin by default; the Modelfile will pass a file path as the argument
CMD ["-"]
