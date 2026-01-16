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

# Исправляем импорты для работы как пакета (совместимо с Linux и macOS)
sed 's/^import recognitionv2_pb2/from . import recognitionv2_pb2/' "$OUT_DIR/recognitionv2_pb2_grpc.py" > "$OUT_DIR/recognitionv2_pb2_grpc.py.tmp" && mv "$OUT_DIR/recognitionv2_pb2_grpc.py.tmp" "$OUT_DIR/recognitionv2_pb2_grpc.py"
sed 's/^import synthesisv2_pb2/from . import synthesisv2_pb2/' "$OUT_DIR/synthesisv2_pb2_grpc.py" > "$OUT_DIR/synthesisv2_pb2_grpc.py.tmp" && mv "$OUT_DIR/synthesisv2_pb2_grpc.py.tmp" "$OUT_DIR/synthesisv2_pb2_grpc.py"

touch "$OUT_DIR/__init__.py"

echo "Proto stubs generated in $OUT_DIR"
