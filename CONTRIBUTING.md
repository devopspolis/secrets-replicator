# Contributing to Secrets Replicator

Thank you for your interest in contributing to Secrets Replicator! We welcome contributions from the community.

---

## Table of Contents

1. [Code of Conduct](#code-of-conduct)
2. [How Can I Contribute?](#how-can-i-contribute)
3. [Development Setup](#development-setup)
4. [Development Workflow](#development-workflow)
5. [Pull Request Process](#pull-request-process)
6. [Coding Standards](#coding-standards)
7. [Testing Guidelines](#testing-guidelines)
8. [Documentation](#documentation)
9. [Release Process](#release-process)

---

## Code of Conduct

This project adheres to a [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report unacceptable behavior to devopspolis@example.com.

---

## How Can I Contribute?

### Reporting Bugs

Before creating a bug report, please check existing [GitHub Issues](https://github.com/devopspolis/secrets-replicator/issues) to avoid duplicates.

**Good Bug Reports Include**:

- Clear, descriptive title
- Steps to reproduce the behavior
- Expected behavior
- Actual behavior
- Screenshots (if applicable)
- Environment details:
  - Python version
  - AWS region
  - SAM CLI version
  - Operating system
- CloudWatch logs (with secrets redacted)

**Bug Report Template**:

```markdown
## Bug Description
A clear description of the bug.

## Steps to Reproduce
1. Deploy stack with configuration...
2. Update source secret...
3. Check destination secret...

## Expected Behavior
Destination secret should have value...

## Actual Behavior
Destination secret has value...

## Environment
- Python: 3.12
- AWS Region: us-east-1
- SAM CLI: 1.100.0
- OS: macOS 14.0

## Logs
```
[CloudWatch logs here - redact secrets]
```

## Additional Context
Any other relevant information.
```

### Suggesting Enhancements

Enhancement suggestions are tracked as [GitHub Issues](https://github.com/devopspolis/secrets-replicator/issues).

**Good Enhancement Suggestions Include**:

- Clear, descriptive title
- Detailed description of the proposed feature
- Use cases and benefits
- Potential implementation approach (optional)
- Alternatives considered

**Enhancement Template**:

```markdown
## Feature Description
A clear description of the feature.

## Use Case
Why is this feature needed? What problem does it solve?

## Proposed Solution
How should this work?

## Alternatives Considered
What other approaches did you consider?

## Additional Context
Any other relevant information.
```

### Contributing Code

We welcome code contributions! Please follow the [Development Workflow](#development-workflow).

**Good First Issues**: Look for issues labeled [`good first issue`](https://github.com/devopspolis/secrets-replicator/labels/good%20first%20issue).

### Contributing Documentation

Documentation improvements are always welcome:

- Fix typos or unclear wording
- Add examples
- Improve existing guides
- Write tutorials or blog posts

---

## Development Setup

### Prerequisites

- **Python 3.12+**: [Download](https://www.python.org/downloads/)
- **AWS CLI**: [Installation guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
- **SAM CLI**: [Installation guide](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)
- **Git**: [Download](https://git-scm.com/downloads)
- **AWS Account**: For testing

### Setup Steps

```bash
# 1. Fork the repository on GitHub

# 2. Clone your fork
git clone https://github.com/YOUR_USERNAME/secrets-replicator.git
cd secrets-replicator

# 3. Add upstream remote
git remote add upstream https://github.com/devopspolis/secrets-replicator.git

# 4. Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 5. Install dependencies
pip install --upgrade pip
pip install -e ".[dev]"

# 6. Install pre-commit hooks
pre-commit install

# 7. Verify setup
pytest tests/unit/ -v
```

### IDE Setup

#### VS Code

Recommended extensions:

- Python (Microsoft)
- Pylance
- AWS Toolkit
- YAML

Workspace settings (`.vscode/settings.json`):

```json
{
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": true,
  "python.linting.mypyEnabled": true,
  "python.formatting.provider": "black",
  "python.testing.pytestEnabled": true,
  "python.testing.unittestEnabled": false,
  "editor.formatOnSave": true,
  "editor.codeActionsOnSave": {
    "source.organizeImports": true
  }
}
```

#### PyCharm

1. Open project in PyCharm
2. Configure Python interpreter: `venv/bin/python`
3. Enable pytest: Preferences → Tools → Python Integrated Tools → Testing → pytest
4. Enable Black: Preferences → Tools → Black → Enable on save

---

## Development Workflow

We use **trunk-based development** with short-lived feature branches.

### Workflow Overview

```
main (protected)
  └─ feature/your-feature (short-lived, 1-2 days max)
```

### Step-by-Step Workflow

#### 1. Create Feature Branch

```bash
# Ensure main is up to date
git checkout main
git pull upstream main

# Create feature branch
git checkout -b feature/your-feature-name
```

**Branch Naming Conventions**:

- `feature/` - New features (e.g., `feature/add-terraform-support`)
- `fix/` - Bug fixes (e.g., `fix/handle-binary-secrets`)
- `docs/` - Documentation changes (e.g., `docs/update-readme`)
- `refactor/` - Code refactoring (e.g., `refactor/cleanup-handler`)
- `test/` - Test improvements (e.g., `test/add-integration-tests`)

#### 2. Make Changes

```bash
# Make your changes
# ... edit files ...

# Run pre-commit hooks (automatically runs on commit)
pre-commit run --all-files

# Run tests
pytest tests/unit/ -v --cov=src --cov-report=html

# Check code quality
black --check src/ tests/
pylint src/ --fail-under=8.0
mypy src/ --ignore-missing-imports
```

#### 3. Commit Changes

```bash
# Stage changes
git add .

# Commit with meaningful message
git commit -m "feat: add support for Terraform deployment"

# Pre-commit hooks will run automatically
```

**Commit Message Format**:

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types**:

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, no logic change)
- `refactor`: Code refactoring
- `perf`: Performance improvements
- `test`: Adding or updating tests
- `chore`: Maintenance tasks
- `ci`: CI/CD changes

**Examples**:

```
feat(handler): add support for binary secrets

Implement base64 encoding for binary secret values.

Closes #123
```

```
fix(transformation): escape special characters in sed patterns

Fixes issue where dots in domain names were matching any character.

Fixes #456
```

#### 4. Push Changes

```bash
# Push to your fork
git push origin feature/your-feature-name
```

#### 5. Create Pull Request

1. Go to https://github.com/devopspolis/secrets-replicator
2. Click "New Pull Request"
3. Select your branch
4. Fill out PR template
5. Submit PR

---

## Pull Request Process

### PR Checklist

Before submitting a PR, ensure:

- [ ] Code follows [coding standards](#coding-standards)
- [ ] All tests pass (`pytest tests/unit/ -v`)
- [ ] Code coverage ≥ 90% (`pytest --cov=src --cov-fail-under=90`)
- [ ] Pre-commit hooks pass (`pre-commit run --all-files`)
- [ ] Documentation updated (if needed)
- [ ] CHANGELOG.md updated (if applicable)
- [ ] Commit messages follow conventions
- [ ] PR description is clear and complete

### PR Template

```markdown
## Description
Brief description of changes.

## Related Issue
Closes #123

## Type of Change
- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update

## Testing
How did you test this change?

- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] Manual testing performed

## Checklist
- [ ] Code follows project style guidelines
- [ ] Self-review completed
- [ ] Comments added for complex logic
- [ ] Documentation updated
- [ ] Tests pass locally
- [ ] No new warnings introduced
```

### Review Process

1. **Automated Checks**: CI runs automatically (linting, tests, security scan)
2. **Code Review**: Maintainer reviews your code
3. **Feedback**: Address review comments
4. **Approval**: Maintainer approves PR
5. **Merge**: Maintainer merges to main

**Review Timeline**: We aim to review PRs within 2-3 business days.

### After PR is Merged

```bash
# Update your local main branch
git checkout main
git pull upstream main

# Delete feature branch
git branch -d feature/your-feature-name
git push origin --delete feature/your-feature-name
```

---

## Coding Standards

### Python Style Guide

We follow [PEP 8](https://peps.python.org/pep-0008/) with these tools:

- **Black**: Code formatting (line length: 100)
- **Pylint**: Code quality (min score: 8.0)
- **Mypy**: Type checking
- **isort**: Import sorting

### Code Formatting

```bash
# Format code
black src/ tests/

# Sort imports
isort src/ tests/

# Check formatting
black --check src/ tests/
```

### Linting

```bash
# Run pylint
pylint src/ --fail-under=8.0

# Run mypy
mypy src/ --ignore-missing-imports
```

### Code Quality Rules

1. **Line Length**: Max 100 characters
2. **Function Length**: Max 60 lines (prefer smaller)
3. **Function Arguments**: Max 8 arguments
4. **Cyclomatic Complexity**: Max 15
5. **Nesting Depth**: Max 4 levels

### Naming Conventions

- **Variables**: `snake_case` (e.g., `secret_arn`)
- **Functions**: `snake_case` (e.g., `get_secret_value`)
- **Classes**: `PascalCase` (e.g., `SecretsManagerClient`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `MAX_SECRET_SIZE`)
- **Private**: Prefix with `_` (e.g., `_internal_function`)

### Documentation Strings

Use Google-style docstrings:

```python
def replicate_secret(source_arn: str, dest_name: str, transform_mode: str) -> dict:
    """
    Replicate a secret from source to destination with transformation.

    Args:
        source_arn: ARN of the source secret
        dest_name: Name of the destination secret
        transform_mode: Transformation mode ('sed' or 'json')

    Returns:
        dict: Result containing status and metadata

    Raises:
        SecretNotFoundError: If source secret doesn't exist
        TransformationError: If transformation fails
        AccessDeniedError: If IAM permissions are insufficient

    Example:
        >>> result = replicate_secret(
        ...     'arn:aws:secretsmanager:us-east-1:123:secret:my-secret',
        ...     'destination-secret',
        ...     'sed'
        ... )
    """
    # Implementation
```

### Type Hints

Use type hints for all function signatures:

```python
from typing import Dict, Optional, List

def get_secret_value(
    secret_arn: str,
    version_id: Optional[str] = None
) -> Dict[str, str]:
    """Get secret value from Secrets Manager."""
    # Implementation
```

### Error Handling

Use custom exceptions from `src/exceptions.py`:

```python
from src.exceptions import SecretNotFoundError, TransformationError

def transform_secret(value: str, sed_script: str) -> str:
    """Transform secret value with sed script."""
    try:
        result = apply_sed_transformation(value, sed_script)
    except subprocess.CalledProcessError as e:
        raise TransformationError(f"Sed transformation failed: {e}") from e

    return result
```

### Logging

Use structured logging, never log secrets:

```python
import logging

logger = logging.getLogger(__name__)

def replicate_secret(secret_arn: str, dest_name: str) -> None:
    """Replicate secret."""
    logger.info(
        "Starting replication",
        extra={
            "source_arn": secret_arn,
            "dest_name": dest_name,
            "dest_region": os.environ.get("DEST_REGION")
        }
    )

    # NEVER log secret values
    # BAD: logger.info(f"Secret value: {secret_value}")
    # GOOD: logger.info(f"Secret size: {len(secret_value)} bytes")
```

---

## Testing Guidelines

### Test Structure

```
tests/
├── unit/              # Unit tests (fast, no AWS calls)
│   ├── test_handler.py
│   ├── test_config.py
│   ├── test_transformer.py
│   └── ...
├── integration/       # Integration tests (require AWS)
│   ├── test_aws_integration.py
│   └── ...
└── fixtures/          # Test data
    ├── eventbridge_events.py
    └── sample_secrets.py
```

### Writing Unit Tests

```python
import pytest
from src.handler import lambda_handler
from tests.fixtures.eventbridge_events import PUT_SECRET_VALUE_EVENT

def test_lambda_handler_success(mocker):
    """Test successful secret replication."""
    # Mock AWS clients
    mock_secrets_client = mocker.patch('src.handler.SecretsManagerClient')
    mock_secrets_client.return_value.get_secret.return_value = {
        'SecretString': '{"key": "value"}'
    }

    # Call handler
    result = lambda_handler(PUT_SECRET_VALUE_EVENT, None)

    # Assert
    assert result['statusCode'] == 200
    mock_secrets_client.return_value.put_secret.assert_called_once()

def test_lambda_handler_secret_not_found(mocker):
    """Test handler when source secret doesn't exist."""
    # Mock client to raise exception
    mock_secrets_client = mocker.patch('src.handler.SecretsManagerClient')
    mock_secrets_client.return_value.get_secret.side_effect = SecretNotFoundError("Not found")

    # Call handler
    result = lambda_handler(PUT_SECRET_VALUE_EVENT, None)

    # Assert error response
    assert result['statusCode'] == 404
```

### Running Tests

```bash
# Run all unit tests
pytest tests/unit/ -v

# Run specific test file
pytest tests/unit/test_handler.py -v

# Run specific test
pytest tests/unit/test_handler.py::test_lambda_handler_success -v

# Run with coverage
pytest tests/unit/ -v --cov=src --cov-report=html

# Open coverage report
open htmlcov/index.html
```

### Test Coverage Requirements

- **Minimum Coverage**: 90%
- **New Code**: 100% coverage for new functions
- **Critical Paths**: 100% coverage for error handling

### Mocking AWS Services

Use `moto` for mocking AWS services:

```python
import boto3
from moto import mock_secretsmanager

@mock_secretsmanager
def test_get_secret():
    """Test getting secret from Secrets Manager."""
    # Create mock secret
    client = boto3.client('secretsmanager', region_name='us-east-1')
    client.create_secret(
        Name='test-secret',
        SecretString='{"key": "value"}'
    )

    # Test your code
    from src.aws_clients import SecretsManagerClient
    secrets_client = SecretsManagerClient(region='us-east-1')
    result = secrets_client.get_secret('test-secret')

    assert result['SecretString'] == '{"key": "value"}'
```

---

## Documentation

### Updating Documentation

When making changes, update relevant documentation:

- **README.md**: User-facing documentation
- **ARCHITECTURE.md**: Technical architecture
- **docs/**: Detailed guides
- **Code comments**: Complex logic
- **Docstrings**: Function documentation

### Documentation Standards

- Use clear, concise language
- Include examples
- Keep it up to date
- Use proper Markdown formatting

### Building Documentation Locally

```bash
# Preview README in GitHub format
grip README.md

# Check for broken links
markdown-link-check README.md
```

---

## Release Process

Releases are managed by maintainers.

### Versioning

We use [Semantic Versioning](https://semver.org/):

- **MAJOR**: Breaking changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes (backward compatible)

### Release Workflow

1. **Update CHANGELOG.md**: Document changes
2. **Create Release PR**: Update version in `pyproject.toml`
3. **Tag Release**: Create git tag (e.g., `v1.1.0`)
4. **GitHub Release**: Automated via GitHub Actions
5. **Deploy**: Automated deployment to production

---

## Questions?

- **General Questions**: [GitHub Discussions](https://github.com/devopspolis/secrets-replicator/discussions)
- **Bug Reports**: [GitHub Issues](https://github.com/devopspolis/secrets-replicator/issues)
- **Email**: devopspolis@example.com

---

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

**Thank you for contributing to Secrets Replicator!** 🎉
