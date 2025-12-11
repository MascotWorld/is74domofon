# Installation Guide

## Quick Start

1. **Create a virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Install the package in development mode:**
   ```bash
   pip install -e .
   ```

4. **Verify installation:**
   ```bash
   python -m pytest tests/test_setup.py -v
   ```

## Configuration

1. Copy the example configuration:
   ```bash
   cp config/config.example.yaml config/config.yaml
   ```

2. Edit `config/config.yaml` with your IS74 credentials and Home Assistant details.

## Running Tests

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=src --cov-report=html

# Run specific test markers
pytest -m unit          # Unit tests only
pytest -m property      # Property-based tests only
pytest -m integration   # Integration tests only
```

## Development Setup

Install development dependencies:
```bash
pip install -e ".[dev]"
```

Run code quality tools:
```bash
black src/ tests/        # Format code
flake8 src/ tests/       # Lint
mypy src/                # Type check
```

## Hypothesis Configuration

The project uses Hypothesis for property-based testing with the following profiles:

- **default**: 100 examples per test (used in normal development)
- **ci**: 1000 examples per test (used in CI/CD)
- **dev**: 10 examples per test (quick feedback during development)

To use a different profile:
```bash
HYPOTHESIS_PROFILE=dev pytest
```
