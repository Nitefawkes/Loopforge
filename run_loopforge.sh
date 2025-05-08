#!/bin/bash

echo "LoopForge Execution Script"
echo "======================="

if [ -z "$1" ]; then
    echo "No command specified. Available commands:"
    echo ""
    echo "  setup         - Install Python dependencies"
    echo "  generate      - Generate prompts only"
    echo "  render        - Run the renderer only"
    echo "  process       - Run the video processor only"
    echo "  upload        - Run the uploader only"
    echo "  pipeline      - Run the entire pipeline"
    echo "  api           - Start the API prototype"
    echo ""
    echo "Example usage: ./run_loopforge.sh generate --topic \"minimalist lifestyle\" --count 10"
    exit 1
fi

COMMAND=$1
shift

case $COMMAND in
    setup)
        echo "Installing Python dependencies..."
        pip install -r requirements.txt
        ;;
    generate)
        echo "Running prompt generation..."
        python src/run_pipeline.py --stage generate "$@"
        ;;
    render)
        echo "Running renderer..."
        python src/run_pipeline.py --stage render "$@"
        ;;
    process)
        echo "Running video processor..."
        python src/run_pipeline.py --stage process "$@"
        ;;
    upload)
        echo "Running uploader..."
        python src/run_pipeline.py --stage upload "$@"
        ;;
    pipeline)
        echo "Running full pipeline..."
        python src/run_pipeline.py --all "$@"
        ;;
    api)
        echo "Starting API prototype..."
        python src/run_pipeline.py --stage api "$@"
        ;;
    *)
        echo "Unknown command: $COMMAND"
        echo "Run without parameters to see available commands"
        exit 1
        ;;
esac

exit 0
