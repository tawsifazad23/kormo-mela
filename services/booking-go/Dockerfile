# ---- builder ----
    FROM golang:1.22-alpine AS builder

    WORKDIR /src
    COPY go.mod ./
    RUN go mod download
    
    COPY . .
    RUN go mod tidy
    # build static binary
    RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o /out/booking-go
    
    # ---- runner ----
    FROM alpine:3.20
    RUN adduser -D -u 10001 app
    USER app
    
    WORKDIR /home/app
    COPY --from=builder /out/booking-go /usr/local/bin/booking-go
    
    EXPOSE 8001
    ENTRYPOINT ["/usr/local/bin/booking-go"]
    