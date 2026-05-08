#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/sample-data/to_test/events"
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"

mapfile -t CONFIGS < <(find "$CONFIG_DIR" -name "*.json" | sort)

TOTAL=${#CONFIGS[@]}
PASS=0
FAIL=0
FAILED_FILES=()

echo "Found $TOTAL config files. Starting pipeline runs..."
echo "=========================================="

for CONFIG in "${CONFIGS[@]}"; do
    NAME=$(basename "$CONFIG" _config_wikidata.json)
    LOG_FILE="$LOG_DIR/${NAME}.log"

    echo -n "[$((PASS + FAIL + 1))/$TOTAL] $NAME ... "

    if python -m src.run_pipeline \
        -j "$CONFIG" \
        -i hdt \
        --compute_score \
        > "$LOG_FILE" 2>&1; then
        echo "OK"
        ((++PASS))
    else
        echo "FAILED (see $LOG_FILE)"
        ((++FAIL))
        FAILED_FILES+=("$NAME")
    fi
done

echo "=========================================="
echo "Done: $PASS passed, $FAIL failed out of $TOTAL"

if [ ${#FAILED_FILES[@]} -gt 0 ]; then
    echo "Failed:"
    for F in "${FAILED_FILES[@]}"; do
        echo "  - $F"
    done
    exit 1
fi
