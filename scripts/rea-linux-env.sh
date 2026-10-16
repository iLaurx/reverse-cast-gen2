#!/usr/bin/env bash
# Source this file from the dedicated WSL user (rea).
export REA_TOOLS_DIR="$HOME/.local/share/rea"
export GHIDRA_INSTALL_DIR="$REA_TOOLS_DIR/ghidra_12.1.4_PUBLIC"
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
export REA_BINWALK_COMMAND="$HOME/.cargo/bin/binwalk"
export REA_UNBLOB_COMMAND="$REA_TOOLS_DIR/unblob/bin/unblob"
export REA_FIRMWARE_PRLIMIT_COMMAND=/usr/bin/prlimit
export PATH="$REA_TOOLS_DIR/node/bin:$REA_TOOLS_DIR/npm/bin:$REA_TOOLS_DIR/unblob/bin:$HOME/.cargo/bin:$HOME/.local/bin:/usr/local/bin:/usr/local/sbin:/usr/bin:/usr/sbin:/bin:/sbin"
