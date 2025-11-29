# InstaChatico Test Suite

Comprehensive test suite achieving 95%+ code coverage.

## Quick Start

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run only unit tests (fast)
pytest -m unit

# Run only integration tests
pytest -m integration
```

## Test Structure

- `unit/` - Fast, isolated unit tests
- `integration/` - Integration tests with dependencies  
- `conftest.py` - Shared fixtures

## Coverage Target: 95%+

All layers tested: API → Use Cases → Services → Repositories → Models
