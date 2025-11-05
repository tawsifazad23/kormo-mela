package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"log"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/golang-jwt/jwt/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/redis/go-redis/v9"
)

type Booking struct {
	ID          int64      `json:"id"`
	CustomerID  int64      `json:"customer_id"`
	ProviderID  int64      `json:"provider_id"`
	ServiceType string     `json:"service_type"`
	StartDate   time.Time  `json:"start_date"`
	EndDate     time.Time  `json:"end_date"`
	LocationLat *float64   `json:"location_lat,omitempty"`
	LocationLon *float64   `json:"location_lon,omitempty"`
	PriceBand   *string    `json:"price_band,omitempty"`
	Status      string     `json:"status"`
	CreatedAt   time.Time  `json:"created_at"`
	UpdatedAt   time.Time  `json:"updated_at"`
}

type CreateBookingReq struct {
	CustomerID  int64    `json:"customer_id"`
	ProviderID  int64    `json:"provider_id"`
	ServiceType string   `json:"service_type"`
	StartDate   string   `json:"start_date"`
	EndDate     string   `json:"end_date"`
	LocationLat *float64 `json:"location_lat"`
	LocationLon *float64 `json:"location_lon"`
	PriceBand   *string  `json:"price_band"`
}

type IdempotencyRecord struct {
	Key          string          `json:"key"`
	Method       string          `json:"method"`
	Path         string          `json:"path"`
	RequestHash  string          `json:"request_hash"`
	ResponseCode int             `json:"response_code"`
	ResponseBody json.RawMessage `json:"response_body"`
	CreatedAt    time.Time       `json:"created_at"`
}

var db *pgxpool.Pool
var rdb *redis.Client

// ---------- env helpers ----------
func getenv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

// ---------- auth ----------
type authCtxKey struct{}

type AuthInfo struct {
	UserID int64
	Scope  string
}

func authMiddleware(next http.Handler) http.Handler {
	secret := getenv("AUTH_SECRET", "")
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		h := r.Header.Get("Authorization")
		if !strings.HasPrefix(h, "Bearer ") {
			http.Error(w, `{"detail":"missing bearer token"}`, http.StatusUnauthorized)
			return
		}
		tokenStr := strings.TrimPrefix(h, "Bearer ")

		tok, err := jwt.Parse(tokenStr, func(t *jwt.Token) (interface{}, error) {
			if _, ok := t.Method.(*jwt.SigningMethodHMAC); !ok {
				return nil, errors.New("unexpected signing method")
			}
			return []byte(secret), nil
		})
		if err != nil || !tok.Valid {
			http.Error(w, `{"detail":"invalid token"}`, http.StatusUnauthorized)
			return
		}

		claims, ok := tok.Claims.(jwt.MapClaims)
		if !ok {
			http.Error(w, `{"detail":"invalid claims"}`, http.StatusUnauthorized)
			return
		}

		subStr, _ := claims["sub"].(string)
		var uid int64
		if subStr != "" {
			if n, err := strconv.ParseInt(subStr, 10, 64); err == nil {
				uid = n
			}
		}
		scope, _ := claims["scope"].(string)
		if uid == 0 {
			http.Error(w, `{"detail":"invalid sub"}`, http.StatusUnauthorized)
			return
		}

		ctx := context.WithValue(r.Context(), authCtxKey{}, &AuthInfo{UserID: uid, Scope: scope})
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

func mustAuth(r *http.Request) *AuthInfo {
	v := r.Context().Value(authCtxKey{})
	if v == nil {
		return &AuthInfo{}
	}
	return v.(*AuthInfo)
}

// ---------- audit ----------
func logAudit(ctx context.Context, bookingID, actorID int64, action, from, to string, meta map[string]any) {
	if meta == nil {
		meta = map[string]any{}
	}
	_, err := db.Exec(ctx, `
		INSERT INTO audit_log(booking_id, actor_id, action, from_status, to_status, meta)
		VALUES ($1,$2,$3,$4,$5,$6)
	`, bookingID, actorID, action, from, to, meta)
	if err != nil {
		log.Printf("audit insert failed: %v", err)
	}
}

// ---------- events ----------
const bookingEventsChannel = "booking.events"

type bookingEvent struct {
	Type   string  `json:"type"` // booking.created|accepted|confirmed|completed|canceled
	ID     int64   `json:"id"`
	Actor  int64   `json:"actor_id"`
	UserA  int64   `json:"customer_id"`
	UserB  int64   `json:"provider_id"`
	Status string  `json:"status"`
	Title  string  `json:"title"`
	Body   string  `json:"body"`
	Meta   any     `json:"meta,omitempty"`
}

func pubEvent(ctx context.Context, ev bookingEvent) {
	if rdb == nil {
		return
	}
	b, _ := json.Marshal(ev)
	if err := rdb.Publish(ctx, bookingEventsChannel, b).Err(); err != nil {
		log.Printf("[events] publish error: %v", err)
	}
}

// ---------- startup ----------
func main() {
	ctx := context.Background()
	dsn := "postgres://" + getenv("DB_USER", "kormo") + ":" + getenv("DB_PASS", "kormo") + "@" +
		getenv("DB_HOST", "postgres") + ":" + getenv("DB_PORT", "5432") + "/" + getenv("DB_NAME", "kormo")

	var err error
	db, err = pgxpool.New(ctx, dsn)
	if err != nil {
		log.Fatalf("db connect: %v", err)
	}
	if err = db.Ping(ctx); err != nil {
		log.Fatalf("db ping: %v", err)
	}

	// Redis (for domain events)
	redisHost := getenv("REDIS_HOST", "redis")
	redisPort := getenv("REDIS_PORT", "6379")
	rdb = redis.NewClient(&redis.Options{
		Addr: redisHost + ":" + redisPort,
	})
	if err := rdb.Ping(ctx).Err(); err != nil {
		log.Printf("[warn] redis ping failed: %v (events will be disabled)", err)
		// keep running without events
		rdb = nil
	}

	r := chi.NewRouter()

	// public
	r.Get("/health", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
	})
	r.Get("/ready", func(w http.ResponseWriter, r *http.Request) {
		if err := db.Ping(r.Context()); err != nil {
			writeJSON(w, http.StatusServiceUnavailable, map[string]any{"ready": false})
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"ready": true})
	})

	// protected
	r.Group(func(pr chi.Router) {
		pr.Use(authMiddleware)
		pr.Post("/bookings", withIdempotency(createBooking))
		pr.Post("/bookings/{id}/accept", transition("PENDING", "ACCEPTED", "accept"))
		pr.Post("/bookings/{id}/confirm", transition("ACCEPTED", "CONFIRMED", "confirm"))
		pr.Post("/bookings/{id}/complete", transition("CONFIRMED", "COMPLETED", "complete"))
		pr.Post("/bookings/{id}/cancel", cancelBooking)
		pr.Get("/bookings/{id}", getBooking)
	})

	addr := ":8001"
	log.Printf("booking-go listening on %s", addr)
	log.Fatal(http.ListenAndServe(addr, r))
}

// ---------- idempotency ----------
func withIdempotency(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		key := r.Header.Get("Idempotency-Key")
		if key == "" {
			next.ServeHTTP(w, r)
			return
		}
		bodyBytes := []byte{}
		if r.Body != nil {
			defer r.Body.Close()
			bodyBytes, _ = ioReadAllLimit(r.Body, 1<<20)
			r.Body = newNopCloser(bodyBytes)
		}
		hash := sha256.Sum256(bodyBytes)
		reqHash := hex.EncodeToString(hash[:])

		var rec IdempotencyRecord
		err := db.QueryRow(r.Context(), `
			SELECT key, method, path, request_hash, response_code, response_body, created_at
			FROM idempotency_keys WHERE key=$1
		`, key).Scan(&rec.Key, &rec.Method, &rec.Path, &rec.RequestHash, &rec.ResponseCode, &rec.ResponseBody, &rec.CreatedAt)

		if err == nil {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(rec.ResponseCode)
			w.Write(rec.ResponseBody)
			return
		}

		recorder := &respRecorder{ResponseWriter: w, code: 200}
		next.ServeHTTP(recorder, r)

		_, _ = db.Exec(r.Context(), `
			INSERT INTO idempotency_keys(key, method, path, request_hash, response_code, response_body)
			VALUES ($1,$2,$3,$4,$5,$6)
			ON CONFLICT (key) DO NOTHING
		`, key, r.Method, r.URL.Path, reqHash, recorder.code, recorder.buf)
	}
}

type respRecorder struct {
	http.ResponseWriter
	buf  []byte
	code int
}

func (rr *respRecorder) WriteHeader(statusCode int) {
	rr.code = statusCode
	rr.ResponseWriter.WriteHeader(statusCode)
}

func (rr *respRecorder) Write(p []byte) (int, error) {
	rr.buf = append(rr.buf, p...)
	return rr.ResponseWriter.Write(p)
}

// --- request body reuse helpers ---
type nopCloser struct{ b []byte }

func newNopCloser(b []byte) *nopCloser { return &nopCloser{b} }
func (n *nopCloser) Read(p []byte) (int, error) {
	copy(p, n.b)
	if len(n.b) == 0 {
		return 0, io.EOF
	}
	n.b = n.b[:copy(n.b, n.b[:0])]
	return len(p), io.EOF
}
func (n *nopCloser) Close() error { return nil }

func ioReadAllLimit(r io.Reader, limit int64) ([]byte, error) {
	buf := make([]byte, 0, 4096)
	tmp := make([]byte, 4096)
	var read int64
	for {
		n, err := r.Read(tmp)
		if n > 0 {
			read += int64(n)
			if read > limit {
				return nil, errors.New("request too large")
			}
			buf = append(buf, tmp[:n]...)
		}
		if err != nil {
			if errors.Is(err, io.EOF) {
				break
			}
			return nil, err
		}
	}
	return buf, nil
}

// ---------- handlers ----------
func createBooking(w http.ResponseWriter, r *http.Request) {
	ai := mustAuth(r)

	var req CreateBookingReq
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, `{"detail":"invalid json"}`, http.StatusBadRequest)
		return
	}

	req.CustomerID = ai.UserID

	start, err1 := time.Parse(time.RFC3339, req.StartDate)
	end, err2 := time.Parse(time.RFC3339, req.EndDate)
	if err1 != nil || err2 != nil || !end.After(start) {
		http.Error(w, `{"detail":"invalid dates"}`, http.StatusBadRequest)
		return
	}

	row := db.QueryRow(r.Context(), `
		INSERT INTO bookings (customer_id, provider_id, service_type, start_date, end_date,
			location_lat, location_lon, price_band, status)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'PENDING')
		RETURNING id, customer_id, provider_id, service_type, start_date, end_date,
		         location_lat, location_lon, price_band, status, created_at, updated_at
	`, req.CustomerID, req.ProviderID, req.ServiceType, start, end, req.LocationLat, req.LocationLon, req.PriceBand)

	var b Booking
	if err := row.Scan(&b.ID, &b.CustomerID, &b.ProviderID, &b.ServiceType,
		&b.StartDate, &b.EndDate, &b.LocationLat, &b.LocationLon, &b.PriceBand,
		&b.Status, &b.CreatedAt, &b.UpdatedAt); err != nil {
		http.Error(w, `{"detail":"db error"}`, http.StatusInternalServerError)
		return
	}

	// audit
	logAudit(r.Context(), b.ID, ai.UserID, "create", "", b.Status, map[string]any{
		"provider_id": b.ProviderID,
		"service":     b.ServiceType,
	})

	// publish event
	pubEvent(r.Context(), bookingEvent{
		Type:   "booking.created",
		ID:     b.ID,
		Actor:  ai.UserID,
		UserA:  b.CustomerID,
		UserB:  b.ProviderID,
		Status: b.Status,
		Title:  "Booking created",
		Body:   "Booking #" + strconv.FormatInt(b.ID, 10) + " created",
	})

	writeJSON(w, http.StatusCreated, b)
}

func transition(from, to, action string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		ai := mustAuth(r)
		idStr := chi.URLParam(r, "id")
		id, _ := strconv.ParseInt(idStr, 10, 64)

		row := db.QueryRow(r.Context(), `
			UPDATE bookings
			SET status=$1, updated_at=NOW()
			WHERE id=$2 AND status=$3
			RETURNING id, customer_id, provider_id, service_type, start_date, end_date,
				location_lat, location_lon, price_band, status, created_at, updated_at
		`, to, id, from)

		var b Booking
		if err := row.Scan(&b.ID, &b.CustomerID, &b.ProviderID, &b.ServiceType,
			&b.StartDate, &b.EndDate, &b.LocationLat, &b.LocationLon, &b.PriceBand,
			&b.Status, &b.CreatedAt, &b.UpdatedAt); err != nil {
			http.Error(w, `{"detail":"invalid transition"}`, http.StatusConflict)
			return
		}

		// audit
		logAudit(r.Context(), b.ID, ai.UserID, action, from, to, map[string]any{})

		// publish event
		pubEvent(r.Context(), bookingEvent{
			Type:   "booking." + strings.ToLower(to),
			ID:     b.ID,
			Actor:  ai.UserID,
			UserA:  b.CustomerID,
			UserB:  b.ProviderID,
			Status: b.Status,
			Title:  "Booking " + strings.ToLower(b.Status),
			Body:   "Booking #" + strconv.FormatInt(b.ID, 10) + " is now " + b.Status,
		})

		writeJSON(w, http.StatusOK, b)
	}
}

func cancelBooking(w http.ResponseWriter, r *http.Request) {
	ai := mustAuth(r)
	idStr := chi.URLParam(r, "id")
	id, _ := strconv.ParseInt(idStr, 10, 64)

	row := db.QueryRow(r.Context(), `
		UPDATE bookings
		SET status='CANCELED', updated_at=NOW()
		WHERE id=$1 AND status IN ('PENDING','ACCEPTED','CONFIRMED')
		RETURNING id, customer_id, provider_id, service_type, start_date, end_date,
			location_lat, location_lon, price_band, status, created_at, updated_at
	`, id)

	var b Booking
	if err := row.Scan(&b.ID, &b.CustomerID, &b.ProviderID, &b.ServiceType,
		&b.StartDate, &b.EndDate, &b.LocationLat, &b.LocationLon, &b.PriceBand,
		&b.Status, &b.CreatedAt, &b.UpdatedAt); err != nil {
		http.Error(w, `{"detail":"cannot cancel"}`, http.StatusConflict)
		return
	}

	// audit
	logAudit(r.Context(), b.ID, ai.UserID, "cancel", "", "CANCELED", map[string]any{})

	// publish event
	pubEvent(r.Context(), bookingEvent{
		Type:   "booking.canceled",
		ID:     b.ID,
		Actor:  ai.UserID,
		UserA:  b.CustomerID,
		UserB:  b.ProviderID,
		Status: b.Status,
		Title:  "Booking canceled",
		Body:   "Booking #" + strconv.FormatInt(b.ID, 10) + " was canceled",
	})

	writeJSON(w, http.StatusOK, b)
}

func getBooking(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	row := db.QueryRow(r.Context(), `
		SELECT id, customer_id, provider_id, service_type, start_date, end_date,
		       location_lat, location_lon, price_band, status, created_at, updated_at
		FROM bookings WHERE id=$1
	`, id)

	var b Booking
	if err := row.Scan(&b.ID, &b.CustomerID, &b.ProviderID, &b.ServiceType,
		&b.StartDate, &b.EndDate, &b.LocationLat, &b.LocationLon, &b.PriceBand,
		&b.Status, &b.CreatedAt, &b.UpdatedAt); err != nil {
		http.Error(w, `{"detail":"not found"}`, http.StatusNotFound)
		return
	}
	writeJSON(w, http.StatusOK, b)
}

// ---------- response helper ----------
func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(v)
}
