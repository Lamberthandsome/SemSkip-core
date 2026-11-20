FROM golang:1.24-bookworm AS build
RUN mkdir -p /out

WORKDIR /src/minio
RUN git clone --depth 1 --branch RELEASE.2025-04-22T22-12-26Z https://github.com/minio/minio.git . \
    && test "$(git rev-parse HEAD)" = 0d7408fc9969caf07de6a8c3a84f9fbb10a6739e \
    && CGO_ENABLED=0 go build -trimpath -o /out/minio .

WORKDIR /src/mc
RUN git clone --depth 1 --branch RELEASE.2025-04-16T18-13-26Z https://github.com/minio/mc.git . \
    && test "$(git rev-parse HEAD)" = b00526b153a31b36767991a4f5ce2cced435ee8e \
    && CGO_ENABLED=0 go build -trimpath -o /out/mc .

FROM debian:bookworm-slim
COPY --from=build /out/minio /out/mc /usr/local/bin/
