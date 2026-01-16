#!/bin/bash
set -e

PROTO_DIR="proto"
OUT_DIR="app/generated"

mkdir -p "$OUT_DIR"

python -m grpc_tools.protoc \
    -I"$PROTO_DIR" \
    --python_out="$OUT_DIR" \
    --grpc_python_out="$OUT_DIR" \
    "$PROTO_DIR/recognitionv2.proto" \
    "$PROTO_DIR/synthesisv2.proto"

touch "$OUT_DIR/__init__.py"

echo "Proto stubs generated in $OUT_DIR"
