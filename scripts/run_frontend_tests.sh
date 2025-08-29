#!/bin/bash

# Frontend test runner script for the PDF processing application
# This script provides convenient commands for running frontend tests with Jest

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
FRONTEND_DIR="$PROJECT_ROOT/frontend"

echo -e "${PURPLE}${BOLD}=== PDF Processing Frontend Test Runner ===${NC}"
echo -e "${CYAN}Frontend directory: $FRONTEND_DIR${NC}"

# Check if frontend directory exists
if [ ! -d "$FRONTEND_DIR" ]; then
    echo -e "${RED}Error: Frontend directory not found at $FRONTEND_DIR${NC}"
    exit 1
fi

# Change to frontend directory
cd "$FRONTEND_DIR"

# Check if package.json exists
if [ ! -f "package.json" ]; then
    echo -e "${RED}Error: package.json not found in frontend directory${NC}"
    exit 1
fi

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}node_modules not found. Installing dependencies...${NC}"
    npm install
fi

# Check if npm test script exists
if ! npm run test --silent 2>/dev/null | grep -q ""; then
    echo -e "${YELLOW}npm test script not found. Checking for jest...${NC}"
    if ! npx jest --version &> /dev/null; then
        echo -e "${RED}Error: Jest not found and no test script available${NC}"
        exit 1
    fi
fi

# Function to run tests with specific options
run_tests() {
    local test_type="$1"
    local verbose="$2" 
    local coverage="$3"
    local watch="$4"
    
    echo -e "${BLUE}Running $test_type tests...${NC}"
    
    # Base command
    local cmd="npm test --"
    
    # Set environment variables
    export CI=true
    export NODE_ENV=test
    
    # Add test type specific options
    case "$test_type" in
        "unit")
            cmd="$cmd --testPathPattern=unit"
            echo -e "${CYAN}Filter: Unit tests only${NC}"
            ;;
        "integration") 
            cmd="$cmd --testPathPattern=integration"
            echo -e "${CYAN}Filter: Integration tests only${NC}"
            ;;
        "component")
            cmd="$cmd --testPathPattern=components"
            echo -e "${CYAN}Filter: Component tests only${NC}"
            ;;
        "e2e")
            cmd="$cmd --testPathPattern=e2e"
            echo -e "${CYAN}Filter: End-to-end tests only${NC}"
            ;;
        "all")
            echo -e "${CYAN}Running all tests${NC}"
            ;;
    esac
    
    # Add coverage options
    if [ "$coverage" = "true" ]; then
        cmd="$cmd --coverage"
        echo -e "${CYAN}Coverage: Enabled${NC}"
    else
        cmd="$cmd --coverage=false"
    fi
    
    # Add watch mode
    if [ "$watch" = "true" ]; then
        cmd="$cmd --watch"
        echo -e "${CYAN}Watch mode: Enabled${NC}"
    else
        cmd="$cmd --watchAll=false"
    fi
    
    # Add verbosity
    if [ "$verbose" = "true" ]; then
        cmd="$cmd --verbose"
    fi
    
    # Add common options
    cmd="$cmd --passWithNoTests --colors"
    
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

# Function to run tests with custom Jest command
run_jest_direct() {
    local args="$1"
    
    echo -e "${BLUE}Running Jest directly with args: $args${NC}"
    
    # Set environment variables
    export CI=true
    export NODE_ENV=test
    
    local cmd="npx jest $args"
    
    echo -e "${CYAN}Command: $cmd${NC}"
    echo ""
    
    if eval "$cmd"; then
        echo -e "${GREEN}✓ Jest tests passed${NC}"
        return 0
    else
        echo -e "${RED}✗ Jest tests failed${NC}"
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
    echo "  component   - Run component tests only"
    echo "  e2e         - Run end-to-end tests only"
    echo ""
    echo -e "${BOLD}Options:${NC}"
    echo "  -v, --verbose    - Verbose output"
    echo "  -c, --coverage   - Enable coverage reporting"
    echo "  --no-cov        - Disable coverage reporting"
    echo "  -w, --watch     - Run in watch mode"
    echo "  -u, --update    - Update snapshots"
    echo "  --bail          - Stop after first test failure"
    echo "  --silent        - Prevent tests from printing messages"
    echo "  -t PATTERN      - Run tests with names matching pattern"
    echo "  --testNamePattern PATTERN - Run tests matching pattern"
    echo "  --maxWorkers N  - Run tests with N workers"
    echo "  --runInBand     - Run tests serially"
    echo "  --detectOpenHandles - Detect handles that prevent Jest from exiting"
    echo "  -h, --help      - Show this help message"
    echo ""
    echo -e "${BOLD}Examples:${NC}"
    echo "  $0                           # Run all tests"
    echo "  $0 unit --verbose            # Run unit tests with verbose output"
    echo "  $0 component -c              # Run component tests with coverage"
    echo "  $0 -t 'FileUpload'           # Run tests matching 'FileUpload'"
    echo "  $0 --watch                   # Run in watch mode"
    echo "  $0 --update                  # Update snapshots"
}

# Parse command line arguments
TEST_TYPE="all"
VERBOSE="false"
COVERAGE="true"
WATCH="false"
CUSTOM_JEST_ARGS=""

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
        -w|--watch)
            WATCH="true"
            shift
            ;;
        -u|--update)
            CUSTOM_JEST_ARGS="$CUSTOM_JEST_ARGS --updateSnapshot"
            shift
            ;;
        --bail)
            CUSTOM_JEST_ARGS="$CUSTOM_JEST_ARGS --bail"
            shift
            ;;
        --silent)
            CUSTOM_JEST_ARGS="$CUSTOM_JEST_ARGS --silent"
            shift
            ;;
        -t)
            CUSTOM_JEST_ARGS="$CUSTOM_JEST_ARGS -t $2"
            shift 2
            ;;
        --testNamePattern)
            CUSTOM_JEST_ARGS="$CUSTOM_JEST_ARGS --testNamePattern $2"
            shift 2
            ;;
        --maxWorkers)
            CUSTOM_JEST_ARGS="$CUSTOM_JEST_ARGS --maxWorkers $2"
            shift 2
            ;;
        --runInBand)
            CUSTOM_JEST_ARGS="$CUSTOM_JEST_ARGS --runInBand"
            shift
            ;;
        --detectOpenHandles)
            CUSTOM_JEST_ARGS="$CUSTOM_JEST_ARGS --detectOpenHandles"
            shift
            ;;
        unit|integration|component|e2e|all)
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

# Show environment info
echo -e "${CYAN}Node version: $(node --version)${NC}"
echo -e "${CYAN}NPM version: $(npm --version)${NC}"

# Check if Jest is available
if npx jest --version &> /dev/null; then
    echo -e "${CYAN}Jest version: $(npx jest --version)${NC}"
fi

echo ""

# Run tests based on options
if [ -n "$CUSTOM_JEST_ARGS" ]; then
    # Run with custom Jest arguments
    jest_args="$CUSTOM_JEST_ARGS"
    
    # Add coverage if enabled
    if [ "$COVERAGE" = "true" ]; then
        jest_args="--coverage $jest_args"
    fi
    
    # Add test type filter
    if [ "$TEST_TYPE" != "all" ]; then
        jest_args="--testPathPattern=$TEST_TYPE $jest_args"
    fi
    
    # Add watch mode
    if [ "$WATCH" = "true" ]; then
        jest_args="--watch $jest_args"
    else
        jest_args="--watchAll=false $jest_args"
    fi
    
    # Add verbosity
    if [ "$VERBOSE" = "true" ]; then
        jest_args="--verbose $jest_args"
    fi
    
    run_jest_direct "$jest_args"
    test_result=$?
else
    # Run with standard test function
    run_tests "$TEST_TYPE" "$VERBOSE" "$COVERAGE" "$WATCH"
    test_result=$?
fi

# Show coverage report location if generated
if [ "$COVERAGE" = "true" ] && [ -d "coverage" ]; then
    echo ""
    echo -e "${GREEN}Coverage report generated at: $FRONTEND_DIR/coverage/lcov-report/index.html${NC}"
fi

# Show additional information
if [ -f "coverage/coverage-summary.json" ]; then
    echo -e "${CYAN}Coverage summary available at: coverage/coverage-summary.json${NC}"
fi

if [ -d ".jest-cache" ]; then
    echo -e "${CYAN}Jest cache directory: .jest-cache${NC}"
fi

# Show test result summary
echo ""
if [ $test_result -eq 0 ]; then
    echo -e "${GREEN}${BOLD}✓ All tests completed successfully${NC}"
    
    # Show next steps
    echo ""
    echo -e "${CYAN}Next steps:${NC}"
    echo -e "  • View coverage report: open coverage/lcov-report/index.html"
    echo -e "  • Run specific tests: $0 -t 'TestName'"
    echo -e "  • Watch mode: $0 --watch"
else
    echo -e "${RED}${BOLD}✗ Some tests failed${NC}"
    
    # Show debugging tips
    echo ""
    echo -e "${YELLOW}Debugging tips:${NC}"
    echo -e "  • Run with verbose output: $0 --verbose"
    echo -e "  • Run single test: $0 -t 'TestName'"
    echo -e "  • Check for open handles: $0 --detectOpenHandles"
    echo -e "  • Run without coverage: $0 --no-cov"
fi

exit $test_result