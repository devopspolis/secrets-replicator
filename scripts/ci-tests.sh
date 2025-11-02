#!/bin/bash
#
# CI/CD test runner script for Secrets Replicator
#
# Optimized for continuous integration environments (GitHub Actions, etc.)
# Runs linters, unit tests with coverage, and optionally integration tests
#
# Usage:
#   ./scripts/ci-tests.sh [options]
#
# Options:
#   --skip-lint     Skip linting checks
#   --skip-tests    Skip unit tests
#   --integration   Run integration tests (requires AWS credentials)
#   --strict        Fail on any warning
#
# Environment Variables:
#   AWS_REGION              AWS region for tests (default: us-east-1)
#   AWS_DEST_REGION         Destination region for cross-region tests (default: us-west-2)
#   COVERAGE_THRESHOLD      Minimum coverage percentage (default: 90)
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Default options
SKIP_LINT=false
SKIP_TESTS=false
RUN_INTEGRATION=false
STRICT_MODE=false

# Configuration
AWS_REGION=${AWS_REGION:-us-east-1}
AWS_DEST_REGION=${AWS_DEST_REGION:-us-west-2}
COVERAGE_THRESHOLD=${COVERAGE_THRESHOLD:-90}

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --skip-lint)
      SKIP_LINT=true
      shift
      ;;
    --skip-tests)
      SKIP_TESTS=true
      shift
      ;;
    --integration)
      RUN_INTEGRATION=true
      shift
      ;;
    --strict)
      STRICT_MODE=true
      shift
      ;;
    --help|-h)
      echo "Usage: $0 [options]"
      echo ""
      echo "Options:"
      echo "  --skip-lint     Skip linting checks"
      echo "  --skip-tests    Skip unit tests"
      echo "  --integration   Run integration tests"
      echo "  --strict        Fail on any warning"
      exit 0
      ;;
    *)
      echo -e "${RED}Unknown option: $1${NC}"
      exit 1
      ;;
  esac
done

echo -e "${BLUE}╔════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  Secrets Replicator - CI Test Suite       ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════╝${NC}"
echo ""

# Track failures
FAILURES=0

# Install dependencies
echo -e "${BLUE}[1/5] Installing dependencies...${NC}"
pip install -q -e ".[dev]" || {
  echo -e "${RED}✗ Failed to install dependencies${NC}"
  exit 1
}
echo -e "${GREEN}✓ Dependencies installed${NC}"
echo ""

# Run linters
if [ "$SKIP_LINT" = false ]; then
  echo -e "${BLUE}[2/5] Running linters...${NC}"

  # Black (code formatting)
  echo -n "  • black... "
  if black --check src/ tests/ --quiet; then
    echo -e "${GREEN}✓${NC}"
  else
    echo -e "${RED}✗${NC}"
    FAILURES=$((FAILURES + 1))
    echo ""
    echo -e "${YELLOW}    To fix: black src/ tests/${NC}"
  fi

  # Pylint (code quality)
  echo -n "  • pylint... "
  PYLINT_THRESHOLD=8.0
  PYLINT_OUTPUT=$(pylint src/ --disable=fixme,duplicate-code 2>&1 || true)
  PYLINT_SCORE=$(echo "$PYLINT_OUTPUT" | grep -oP "rated at \K[0-9.]+" | head -1 || echo "0")

  if (( $(echo "$PYLINT_SCORE >= $PYLINT_THRESHOLD" | bc -l) )); then
    echo -e "${GREEN}✓ (score: $PYLINT_SCORE)${NC}"
  else
    echo -e "${RED}✗ (score: $PYLINT_SCORE < $PYLINT_THRESHOLD)${NC}"
    FAILURES=$((FAILURES + 1))
    if [ "$STRICT_MODE" = true ]; then
      echo "$PYLINT_OUTPUT"
    fi
  fi

  # Mypy (type checking)
  echo -n "  • mypy... "
  if mypy src/ --ignore-missing-imports --quiet; then
    echo -e "${GREEN}✓${NC}"
  else
    echo -e "${RED}✗${NC}"
    FAILURES=$((FAILURES + 1))
    if [ "$STRICT_MODE" = true ]; then
      mypy src/ --ignore-missing-imports
    fi
  fi

  echo ""
else
  echo -e "${YELLOW}[2/5] Skipping linters (--skip-lint)${NC}"
  echo ""
fi

# Run unit tests
if [ "$SKIP_TESTS" = false ]; then
  echo -e "${BLUE}[3/5] Running unit tests...${NC}"

  if python -m pytest tests/unit/ -v \
      --cov=src \
      --cov-report=term-missing \
      --cov-report=html \
      --cov-report=xml \
      --cov-fail-under=$COVERAGE_THRESHOLD \
      --tb=short; then
    echo -e "${GREEN}✓ Unit tests passed (coverage >= ${COVERAGE_THRESHOLD}%)${NC}"
  else
    echo -e "${RED}✗ Unit tests failed or coverage below threshold${NC}"
    FAILURES=$((FAILURES + 1))
  fi
  echo ""
else
  echo -e "${YELLOW}[3/5] Skipping unit tests (--skip-tests)${NC}"
  echo ""
fi

# Run integration tests
if [ "$RUN_INTEGRATION" = true ]; then
  echo -e "${BLUE}[4/5] Running integration tests...${NC}"

  # Check AWS credentials
  if aws sts get-caller-identity > /dev/null 2>&1; then
    ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    echo -e "${GREEN}✓ AWS credentials found (Account: $ACCOUNT_ID)${NC}"

    # Run integration tests
    if python -m pytest tests/integration/ -v \
        --integration \
        --aws-region="$AWS_REGION" \
        --dest-region="$AWS_DEST_REGION" \
        --tb=short; then
      echo -e "${GREEN}✓ Integration tests passed${NC}"
    else
      echo -e "${RED}✗ Integration tests failed${NC}"
      FAILURES=$((FAILURES + 1))
    fi
  else
    echo -e "${YELLOW}⚠ AWS credentials not configured${NC}"
    echo "Integration tests will be skipped"
    if [ "$STRICT_MODE" = true ]; then
      echo -e "${RED}✗ Strict mode enabled - AWS credentials required${NC}"
      FAILURES=$((FAILURES + 1))
    fi
  fi
  echo ""
else
  echo -e "${YELLOW}[4/5] Skipping integration tests (use --integration to enable)${NC}"
  echo ""
fi

# Generate test report
echo -e "${BLUE}[5/5] Test Summary${NC}"
echo "─────────────────────────────────────────────"

if [ $FAILURES -eq 0 ]; then
  echo -e "${GREEN}✓ All checks passed!${NC}"
  echo ""
  echo "Next steps:"
  echo "  • Review coverage report: htmlcov/index.html"
  echo "  • Deploy: ./scripts/deploy.sh <environment>"
  exit 0
else
  echo -e "${RED}✗ $FAILURES check(s) failed${NC}"
  echo ""
  echo "Fix issues and run tests again:"
  echo "  • Format code: black src/ tests/"
  echo "  • Fix linting: pylint src/"
  echo "  • Run tests: pytest tests/unit/ -v"
  exit 1
fi
