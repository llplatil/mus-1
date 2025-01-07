# Contributing to MUS1

## Development Setup
1. Clone the repository
2. Create a virtual environment (Python 3.10+)
3. Install in development mode: `pip install -e .`

## Code Style
- Follow PEP 8 (Python style guide: use consistent indentation, meaningful names, and keep lines under 79 characters)
- Use type hints for all function arguments and returns
- Document all functions and classes with docstrings
- Avoid using 'mice' to describe Mouse ID batch processing instead use 'subjects' 

## Testing
- Write unit tests for new features using pytest
- Run tests before submitting PR: `pytest tests/`

## Pull Request Process
1. Check [Issues](https://github.com/llplatil/mus1/issues) for available tasks
2. Create a feature branch from `develop`
3. Write tests for new features
4. Update documentation
5. Submit PR against `develop` branch 