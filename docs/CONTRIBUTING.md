# Contributing to MUS1

## Testing Strategy
- build up hierarchcally and push whats stable before next layer (stable is currently empty lol)
### Philosophy
- Tests should mirror real user workflows
- Use actual DLC data files from experiments
- Create and clean up real project folders
- Log test execution to global app log

### Running Tests
```bash
# Run all tests
pytest tests/

# Run specific workflow test
pytest tests/test_app.py -k test_create_project

# Run with logging
pytest tests/ --log-cli-level=INFO
```

### Test Development Guidelines
1. Write tests that mirror user actions
2. Use real DLC data whenever possible
3. Use global logging
4. Clean up test artifacts
5. Document what does and does not work
6. push to stable once it is reasonably working (avoid being overwhelmed by too many features)

## Pull Request Process
1. Check [Issues](https://github.com/llplatil/mus1/issues) for available tasks
2. Create a feature branch from `develop`
3. Write tests for new features
4. Update documentation
5. Submit PR against `develop` branch 