# Dockerfile for duranta-bench-harness
# Base: Ubuntu 24.04 LTS (matching host CPU architecture, e.g., aarch64 on Apple Silicon)

FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC

# Install system dependencies, compilers, build tools, and utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    ninja-build \
    pkg-config \
    git \
    libreadline-dev \
    libconfig-dev \
    libsctp-dev \
    libssl-dev \
    libtool \
    patch \
    openssl \
    zlib1g-dev \
    xxd \
    libyaml-cpp-dev \
    bison \
    flex \
    libpcre2-dev \
    libcap-dev \
    util-linux \
    systemd \
    ca-certificates \
    wget \
    ccache \
    automake \
    autoconf \
    python3 \
    python3-pip \
    python3-venv \
    python3-pytest \
    python3-jsonschema \
    python3-yaml \
    tshark \
    && rm -rf /var/lib/apt/lists/*

# Build and install asn1c (compatible commit 940dd5fa9f3917913fd487b13dfddfacd0ded06e used by OAI)
RUN git clone https://github.com/mouse07410/asn1c /tmp/asn1c && \
    cd /tmp/asn1c && \
    git checkout 940dd5fa9f3917913fd487b13dfddfacd0ded06e && \
    autoreconf -iv && \
    CFLAGS="-O2 -fno-strict-aliasing" ./configure --prefix=/opt/asn1c && \
    make -j$(nproc) && \
    make install && \
    rm -rf /tmp/asn1c

# Install SIMDe (SIMD Everywhere) header library for cross-vector instructions (e.g. AVX/NEON)
RUN git clone https://github.com/simd-everywhere/simde-no-tests.git /tmp/simde && \
    cd /tmp/simde && \
    git checkout 1c68d9ad60bf63f3fb527c4ee3b2319d828ffcc6 && \
    cp -r ../simde /usr/include/ && \
    rm -rf /tmp/simde

# Put asn1c on PATH
ENV PATH="/opt/asn1c/bin:${PATH}"

WORKDIR /workspace
CMD ["/bin/bash"]

