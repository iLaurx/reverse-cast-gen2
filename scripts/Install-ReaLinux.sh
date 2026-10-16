#!/usr/bin/env bash
set -euo pipefail
# Requires the system packages listed in README.md and a configured Rust toolchain.
if [ "$(id -u)" = 0 ]; then
    echo 'Run as the dedicated WSL user rea, not root.' >&2
    exit 1
fi
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source "$SCRIPT_DIR/rea-linux-env.sh"
mkdir -p "$REA_TOOLS_DIR/downloads" "$HOME/.config/rea" "$HOME/.local/bin"
install -m 644 "$SCRIPT_DIR/rea-linux-env.sh" "$HOME/.config/rea/env.sh"

NODE_ARCHIVE="$REA_TOOLS_DIR/downloads/node-v24.21.0-linux-x64.tar.xz"
if [ ! -f "$NODE_ARCHIVE" ]; then
    curl --fail --location --retry 3 --output "$NODE_ARCHIVE" \
        https://nodejs.org/dist/v24.21.0/node-v24.21.0-linux-x64.tar.xz
fi
echo "fd8e59d5a511510f6a298afb548f18c7d2b1be404d8b4a27d94fbe49f56cb2d6  $NODE_ARCHIVE" | sha256sum --check
mkdir -p "$REA_TOOLS_DIR/node"
tar -xJf "$NODE_ARCHIVE" -C "$REA_TOOLS_DIR/node" --strip-components=1

GHIDRA_ARCHIVE="$SCRIPT_DIR/../evidence/tool-downloads/ghidra-12.1.4.zip"
echo "ddac49f903da9d5bac833e5cc79395098b9c33cfd3279be5f31bd00387d2d4db  $GHIDRA_ARCHIVE" | sha256sum --check
if [ ! -f "$GHIDRA_INSTALL_DIR/support/analyzeHeadless" ]; then
    unzip -q "$GHIDRA_ARCHIVE" -d "$REA_TOOLS_DIR"
fi

npm install --global --prefix "$REA_TOOLS_DIR/npm" --ignore-scripts rea-agents@6.5.0
if [ ! -x "$REA_TOOLS_DIR/unblob/bin/python" ]; then
    python3 -m venv "$REA_TOOLS_DIR/unblob"
fi
"$REA_TOOLS_DIR/unblob/bin/python" -m pip install unblob==26.6.4
"$REA_TOOLS_DIR/unblob/bin/python" -m pip check

if ! command -v binwalk >/dev/null || [ "$(binwalk --version)" != 'binwalk 3.1.0' ]; then
    cargo install --git https://github.com/ReFirmLabs/binwalk --tag v3.1.0 --locked --jobs 2 binwalk
fi

cat > "$HOME/.local/bin/rea-linux" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
source "$HOME/.config/rea/env.sh"
exec "$REA_TOOLS_DIR/node/bin/node" "$REA_TOOLS_DIR/npm/lib/node_modules/rea-agents/scripts/rea.mjs" "$@"
EOF
chmod 755 "$HOME/.local/bin/rea-linux"
node --version
rea --version
java -version
unblob --version
