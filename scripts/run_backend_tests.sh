#!/bin/bash

# Backend test runner script for the PDF processing application
# This script provides convenient commands for running backend tests with pytest

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Project directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$PROJECT_ROOT/backend"

echo -e "${BLUE}${BOLD}=== PDF Processing Backend Test Runner ===${NC}"
echo -e "${CYAN}Backend directory: $BACKEND_DIR${NC}"

# Check if backend directory exists
if [ ! -d "$BACKEND_DIR" ]; then
    echo -e "${RED}Error: Backend directory not found at $BACKEND_DIR${NC}"
    exit 1
fi

# Change to backend directory
cd "$BACKEND_DIR"

# Check for virtual environment
if [ -d ".venv" ]; then
    echo -e "${GREEN}Activating virtual environment...${NC}"
    source .venv/bin/activate
elif [ -d "venv" ]; then
    echo -e "${GREEN}Activating virtual environment...${NC}"
    source venv/bin/activate
else
    echo -e "${YELLOW}No virtual environment found. Using system Python.${NC}"
fi

# Check if pytest is available
if ! command -v pytest &> /dev/null; then
    echo -e "${YELLOW}pytest not found. Installing test dependencies...${NC}"
    if [ -f "requirements-dev.txt" ]; then
        pip install -r requirements-dev.txt
    else
        pip install pytest pytest-django pytest-cov
    fi
fi

# Function to run tests with specific options
run_tests() {
    local test_type="$1"
    local verbose="$2"
    local coverage="$3"
    
    echo -e "${BLUE}Running $test_type tests...${NC}"
    
    # Base pytest command
    local cmd="pytest"
    
    # Add test type specific options
    case "$test_type" in
        "unit")
            cmd="$cmd -m unit"
            echo -e "${CYAN}Filter: Unit tests only${NC}"
            ;;
        "integration")
            cmd="$cmd -m integration"
            echo -e "${CYAN}Filter: Integration tests only${NC}"
            ;;
        "api")
            cmd="$cmd -m api"
            echo -e "${CYAN}Filter: API tests only${NC}"
            ;;
        "performance")
            cmd="$cmd -m performance"
            echo -e "${CYAN}Filter: Performance tests only${NC}"
            ;;
        "slow")
            cmd="$cmd -m slow"
            echo -e "${CYAN}Filter: Slow tests only${NC}"
            ;;
        "all")
            echo -e "${CYAN}Running all tests${NC}"
            ;;
    esac
    
    # Add coverage options if requested
    if [ "$coverage" = "true" ]; then
        cmd="$cmd --cov=app --cov-report=term-missing --cov-report=html:htmlcov --cov-report=xml:coverage.xml --cov-fail-under=80"
    fi
    
    # Add verbosity options
    if [ "$verbose" = "true" ]; then
        cmd="$cmd -v"
    fi
    
    # Add common options
    cmd="$cmd --tb=short --durations=10 --color=yes"
    
    echo -e "${CYAN}Command: $cmd${NC}"
    echo ""
    
    # Run the tests
    if eval "$cmd"; then
        echo -e "${GREEN}✓ $test_type tests passed${NC}"
        return 0
    else
        echo -e "${RED}✗ $test_type tests failed${NC}"
        return 1
    fi
}

# Function to show help
show_help() {
    echo -e "${BOLD}Usage:${NC}"
    echo "  $0 [OPTIONS] [TEST_TYPE]"
    echo ""
    echo -e "${BOLD}Test Types:${NC}"
    echo "  all         - Run all tests (default)"
    echo "  unit        - Run unit tests only"
    echo "  integration - Run integration tests only" 
    echo "  api         - Run API tests only"
    echo "  performance - Run performance tests only"
    echo "  slow        - Run slow tests only"
    echo ""
    echo -e "${BOLD}Options:${NC}"
    echo "  -v, --verbose    - Verbose output"
    echo "  -c, --coverage   - Enable coverage reporting"
    echo "  --no-cov        - Disable coverage reporting"
    echo "  -f, --failed     - Re-run failed tests only"
    echo "  -x, --exitfirst  - Stop after first failure"
    echo "  -k PATTERN      - Run tests matching pattern"
    echo "  --parallel      - Run tests in parallel"
    echo "  --profile       - Profile test execution"
    echo "  --html          - Generate HTML report"
    echo "  -h, --help      - Show this help message"
    echo ""
    echo -e "${BOLD}Examples:${NC}"
    echo "  $0                     # Run all tests with default settings"
    echo "  $0 unit --verbose      # Run unit tests with verbose output"
    echo "  $0 integration -c      # Run integration tests with coverage"
    echo "  $0 -k 'test_upload'    # Run tests matching pattern"
    echo "  $0 --failed            # Re-run only failed tests"
}

# Parse command line arguments
TEST_TYPE="all"
VERBOSE="false"
COVERAGE="true"
EXTRA_ARGS=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -v|--verbose)
            VERBOSE="true"
            shift
            ;;
        -c|--coverage)
            COVERAGE="true"
            shift
            ;;
        --no-cov)
            COVERAGE="false"
            shift
            ;;
        -f|--failed)
            EXTRA_ARGS="$EXTRA_ARGS --lf"
            shift
            ;;
        -x|--exitfirst)
            EXTRA_ARGS="$EXTRA_ARGS -x"
            shift
            ;;
        -k)
            EXTRA_ARGS="$EXTRA_ARGS -k $2"
            shift 2
            ;;
        --parallel)
            EXTRA_ARGS="$EXTRA_ARGS -n auto"
            shift
            ;;
        --profile)
            EXTRA_ARGS="$EXTRA_ARGS --profile"
            shift
            ;;
        --html)
            EXTRA_ARGS="$EXTRA_ARGS --html=report.html --self-contained-html"
            shift
            ;;
        unit|integration|api|performance|slow|all)
            TEST_TYPE="$1"
            shift
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use -h or --help for usage information"
            exit 1
            ;;
    esac
done

# Set up environment variables
export TESTING=true
export DEBUG=false
export DJANGO_SETTINGS_MODULE=app.settings

# Generate test documents if they don't exist
TEST_DOCS_DIR="$PROJECT_ROOT/test_documents"
if [ ! -f "$TEST_DOCS_DIR/simple_text.pdf" ] && [ -f "$TEST_DOCS_DIR/generate_test_pdfs.py" ]; then
    echo -e "${YELLOW}Generating test documents...${NC}"
    python "$TEST_DOCS_DIR/generate_test_pdfs.py" --output-dir "$TEST_DOCS_DIR"
fi

# Run the tests
echo ""
run_tests "$TEST_TYPE" "$VERBOSE" "$COVERAGE"
test_result=$?

# Add extra arguments if specified
if [ -n "$EXTRA_ARGS" ]; then
    echo -e "${CYAN}Running with extra arguments: $EXTRA_ARGS${NC}"
    if [ "$COVERAGE" = "true" ]; then
        pytest $EXTRA_ARGS --cov=app --cov-report=term-missing --tb=short --color=yes
    else
        pytest $EXTRA_ARGS --tb=short --color=yes
    fi
    test_result=$?
fi

# Show coverage report location if generated
if [ "$COVERAGE" = "true" ] && [ -d "htmlcov" ]; then
    echo ""
    echo -e "${GREEN}Coverage report generated at: $BACKEND_DIR/htmlcov/index.html${NC}"
fi

# Show test result summary
echo ""
if [ $test_result -eq 0 ]; then
    echo -e "${GREEN}${BOLD}✓ All tests completed successfully${NC}"
else
    echo -e "${RED}${BOLD}✗ Some tests failed${NC}"
fi

exit $test_result