#!/bin/bash

# Copperlab Data Processing Pipeline
# This script runs the complete pipeline from raw CSV data to MUS1 ingestion

set -e  # Exit on any error

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(dirname "$SCRIPT_DIR")"
DATA_DIR="$PLUGIN_ROOT/data"
CLEAN_DATA_FILE="$SCRIPT_DIR/clean_copperlab_data.json"
PROJECT_PATH="$PLUGIN_ROOT/../../../copperlab_project"  # Relative to MUS1 root

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if virtual environment is activated
check_venv() {
    if [[ "$VIRTUAL_ENV" != "" ]]; then
        log_info "Virtual environment is activated: $VIRTUAL_ENV"
    else
        log_warning "No virtual environment detected. It's recommended to activate the project's virtual environment."
        read -p "Continue anyway? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "Pipeline cancelled by user."
            exit 1
        fi
    fi
}

# Step 1: Data Cleaning
run_data_cleaning() {
    log_info "Step 1: Cleaning and transforming CSV data..."

    if [[ ! -f "$SCRIPT_DIR/data_cleaning.py" ]]; then
        log_error "Data cleaning script not found: $SCRIPT_DIR/data_cleaning.py"
        exit 1
    fi

    cd "$SCRIPT_DIR"
    python data_cleaning.py --csv-dir "$DATA_DIR"

    if [[ ! -f "$CLEAN_DATA_FILE" ]]; then
        log_error "Clean data file was not generated: $CLEAN_DATA_FILE"
        exit 1
    fi

    log_success "Data cleaning completed successfully"
}

# Step 2: Data Ingestion
run_data_ingestion() {
    log_info "Step 2: Ingesting data into MUS1..."

    if [[ ! -f "$SCRIPT_DIR/direct_ingest.py" ]]; then
        log_error "Data ingestion script not found: $SCRIPT_DIR/direct_ingest.py"
        exit 1
    fi

    if [[ ! -f "$CLEAN_DATA_FILE" ]]; then
        log_error "Clean data file not found: $CLEAN_DATA_FILE"
        exit 1
    fi

    cd "$SCRIPT_DIR"
    python direct_ingest.py "$CLEAN_DATA_FILE" "$PROJECT_PATH"

    log_success "Data ingestion completed successfully"
}

# Step 3: Verification
run_verification() {
    log_info "Step 3: Verifying ingestion results..."

    if [[ ! -d "$PROJECT_PATH" ]]; then
        log_error "Project directory was not created: $PROJECT_PATH"
        exit 1
    fi

    # Check for project files
    if [[ -f "$PROJECT_PATH/project.json" ]]; then
        log_success "Project structure verified"
    else
        log_warning "Project JSON file not found - this might be normal depending on MUS1's project structure"
    fi

    # Show summary
    if [[ -f "$CLEAN_DATA_FILE" ]]; then
        SUBJECTS=$(python -c "import json; data=json.load(open('$CLEAN_DATA_FILE')); print(len(data['subjects']))")
        EXPERIMENTS=$(python -c "import json; data=json.load(open('$CLEAN_DATA_FILE')); print(len(data['experiments']))")

        log_success "Pipeline Summary:"
        echo "  - Subjects processed: $SUBJECTS"
        echo "  - Experiments processed: $EXPERIMENTS"
        echo "  - Project location: $PROJECT_PATH"
    fi
}

# Main pipeline
main() {
    echo "=================================================="
    echo "🏭 Copperlab Data Processing Pipeline"
    echo "=================================================="
    echo

    # Check virtual environment
    check_venv

    # Run pipeline steps
    run_data_cleaning
    echo
    run_data_ingestion
    echo
    run_verification

    echo
    log_success "🎉 Pipeline completed successfully!"
    echo
    echo "Next steps:"
    echo "  - Open MUS1 and load the project: $PROJECT_PATH"
    echo "  - Verify subjects and experiments were created correctly"
    echo "  - You can now analyze the data using MUS1's tools"
}

# Handle command line arguments
case "${1:-}" in
    "clean")
        log_info "Running only data cleaning step..."
        check_venv
        run_data_cleaning
        ;;
    "ingest")
        log_info "Running only data ingestion step..."
        check_venv
        if [[ ! -f "$CLEAN_DATA_FILE" ]]; then
            log_error "Clean data file not found. Run './run_full_pipeline.sh clean' first."
            exit 1
        fi
        run_data_ingestion
        ;;
    "verify")
        log_info "Running only verification step..."
        run_verification
        ;;
    "help"|"-h"|"--help")
        echo "Copperlab Data Processing Pipeline"
        echo
        echo "Usage: $0 [command]"
        echo
        echo "Commands:"
        echo "  (no command)  Run the full pipeline (clean + ingest + verify)"
        echo "  clean         Run only the data cleaning step"
        echo "  ingest        Run only the data ingestion step"
        echo "  verify        Run only the verification step"
        echo "  help          Show this help message"
        echo
        echo "The pipeline will:"
        echo "  1. Clean and transform the raw CSV files"
        echo "  2. Ingest the cleaned data into a new MUS1 project"
        echo "  3. Verify that everything was created correctly"
        ;;
    *)
        main
        ;;
esac
