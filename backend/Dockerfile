FROM golang:1.25-alpine AS builder

WORKDIR /src
COPY go.mod go.sum* ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/api ./cmd/api && \
    CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/worker ./cmd/worker && \
    CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/mock-model ./cmd/mock-model && \
    CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/simulator ./cmd/simulator

FROM alpine:3.22
RUN apk add --no-cache ca-certificates tzdata
WORKDIR /app
COPY --from=builder /out/ /app/
USER 65532:65532
ENTRYPOINT ["/app/api"]
