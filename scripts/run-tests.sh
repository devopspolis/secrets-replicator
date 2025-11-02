#!/bin/bash
#
# Test runner script for Secrets Replicator
#
# Runs unit tests, integration tests, and performance tests
#
# Usage:
#   ./scripts/run-tests.sh [options]
#
# Options:
#   --unit          Run only unit tests
#   --integration   Run integration tests (requires AWS credentials)
#   --performance   Run performance tests
#   --security      Run security validation tests
#   --coverage      Generate coverage report
#   --html          Generate HTML coverage report
#   --all           Run all tests (unit + integration if credentials available)
#   --help          Show this help message
#
# Examples:
#   ./scripts/run-tests.sh --unit
#   ./scripts/run-tests.sh --integration --coverage
#   ./scripts/run-tests.sh --all --html
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
RUN_UNIT=false
RUN_INTEGRATION=false
RUN_PERFORMANCE=false
RUN_SECURITY=false
RUN_ALL=false
GENERATE_COVERAGE=false
HTML_COVERAGE=false

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --unit)
      RUN_UNIT=true
      shift
      ;;
    --integration)
      RUN_INTEGRATION=true
      shift
      ;;
    --performance)
      RUN_PERFORMANCE=true
      shift
      ;;
    --security)
      RUN_SECURITY=true
      shift
      ;;
    --all)
      RUN_ALL=true
      shift
      ;;
    --coverage)
      GENERATE_COVERAGE=true
      shift
      ;;
    --html)
      HTML_COVERAGE=true
      GENERATE_COVERAGE=true
      shift
      ;;
    --help|-h)
      echo "Usage: $0 [options]"
      echo ""
      echo "Options:"
      echo "  --unit          Run only unit tests"
      echo "  --integration   Run integration tests (requires AWS)"
      echo "  --performance   Run performance tests"
      echo "  --security      Run security validation tests"
      echo "  --coverage      Generate coverage report"
      echo "  --html          Generate HTML coverage report"
      echo "  --all           Run all tests"
      echo "  --help          Show this help message"
      exit 0
      ;;
    *)
      echo -e "${RED}Unknown option: $1${NC}"
      echo "Use --help for usage information"
      exit 1
      ;;
  esac
done

# If no specific test type selected, run unit tests
if [ "$RUN_UNIT" = false ] && \
   [ "$RUN_INTEGRATION" = false ] && \
   [ "$RUN_PERFORMANCE" = false ] && \
   [ "$RUN_SECURITY" = false ] && \
   [ "$RUN_ALL" = false ]; then
  RUN_UNIT=true
fi

echo -e "${BLUE}=== Secrets Replicator Test Suite ===${NC}"
echo ""

# Check for virtual environment
if [ ! -d "venv" ]; then
  echo -e "${YELLOW}Virtual environment not found. Creating...${NC}"
  python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Checking dependencies..."
pip install -q -e ".[dev]" > /dev/null 2>&1

# Build coverage arguments
COV_ARGS=""
if [ "$GENERATE_COVERAGE" = true ]; then
  COV_ARGS="--cov=src --cov-report=term-missing"
  if [ "$HTML_COVERAGE" = true ]; then
    COV_ARGS="$COV_ARGS --cov-report=html"
  fi
fi

# Track overall success
OVERALL_SUCCESS=true

# Run unit tests
if [ "$RUN_UNIT" = true ] || [ "$RUN_ALL" = true ]; then
  echo ""
  echo -e "${BLUE}Running unit tests...${NC}"
  echo "─────────────────────────────────────────────"
  if python -m pytest tests/unit/ -v $COV_ARGS; then
    echo -e "${GREEN}✓ Unit tests passed${NC}"
  else
    echo -e "${RED}✗ Unit tests failed${NC}"
    OVERALL_SUCCESS=false
  fi
fi

# Run integration tests (if requested and AWS credentials available)
if [ "$RUN_INTEGRATION" = true ] || [ "$RUN_ALL" = true ]; then
  echo ""
  echo -e "${BLUE}Running integration tests...${NC}"
  echo "─────────────────────────────────────────────"

  # Check for AWS credentials
  if aws sts get-caller-identity > /dev/null 2>&1; then
    echo -e "${GREEN}AWS credentials found${NC}"

    if python -m pytest tests/integration/ -v --integration $COV_ARGS; then
      echo -e "${GREEN}✓ Integration tests passed${NC}"
    else
      echo -e "${RED}✗ Integration tests failed${NC}"
      OVERALL_SUCCESS=false
    fi
  else
    echo -e "${YELLOW}⚠ AWS credentials not configured${NC}"
    echo "Skipping integration tests"
    echo "To run integration tests:"
    echo "  1. Configure AWS credentials (aws configure)"
    echo "  2. Run: ./scripts/run-tests.sh --integration"
  fi
fi

# Run performance tests
if [ "$RUN_PERFORMANCE" = true ]; then
  echo ""
  echo -e "${BLUE}Running performance tests...${NC}"
  echo "─────────────────────────────────────────────"

  if [ "$(aws sts get-caller-identity 2>/dev/null)" ]; then
    if python -m pytest tests/performance/ -v --integration; then
      echo -e "${GREEN}✓ Performance tests passed${NC}"
    else
      echo -e "${RED}✗ Performance tests failed${NC}"
      OVERALL_SUCCESS=false
    fi
  else
    echo -e "${YELLOW}⚠ AWS credentials not configured${NC}"
    echo "Skipping performance tests"
  fi
fi

# Run security tests
if [ "$RUN_SECURITY" = true ]; then
  echo ""
  echo -e "${BLUE}Running security validation tests...${NC}"
  echo "─────────────────────────────────────────────"

  if [ "$(aws sts get-caller-identity 2>/dev/null)" ]; then
    if python -m pytest tests/integration/test_security.py -v --integration; then
      echo -e "${GREEN}✓ Security tests passed${NC}"
    else
      echo -e "${RED}✗ Security tests failed${NC}"
      OVERALL_SUCCESS=false
    fi
  else
    echo -e "${YELLOW}⚠ AWS credentials not configured${NC}"
    echo "Skipping security tests"
  fi
fi

# Summary
echo ""
echo "─────────────────────────────────────────────"
if [ "$OVERALL_SUCCESS" = true ]; then
  echo -e "${GREEN}✓ All tests passed!${NC}"

  # Show coverage report location if generated
  if [ "$HTML_COVERAGE" = true ]; then
    echo ""
    echo "HTML coverage report: htmlcov/index.html"
    echo "Open with: open htmlcov/index.html"
  fi

  exit 0
else
  echo -e "${RED}✗ Some tests failed${NC}"
  exit 1
fi
