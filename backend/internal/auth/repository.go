package auth

import (
	"context"
	"errors"
	"fmt"
	"strings"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"
)

type Repository struct {
	pool *pgxpool.Pool
}

func NewRepository(pool *pgxpool.Pool) *Repository {
	return &Repository{pool: pool}
}

func (r *Repository) EnsureBootstrapAdmin(ctx context.Context, username, password string) error {
	return r.EnsureBootstrapUser(ctx, username, password, RoleAdmin)
}

func (r *Repository) EnsureBootstrapUser(ctx context.Context, username, password, role string) error {
	username = normalizeUsername(username)
	if password == "" {
		return nil
	}
	if username == "" {
		return fmt.Errorf("bootstrap username is required")
	}
	if !ValidRole(role) {
		return fmt.Errorf("invalid bootstrap role %q", role)
	}
	hash, err := HashPassword(password)
	if err != nil {
		return fmt.Errorf("hash bootstrap password: %w", err)
	}
	_, err = r.pool.Exec(ctx, `
		INSERT INTO users (username, password_hash, role)
		VALUES ($1, $2, $3)
		ON CONFLICT (lower(username)) DO NOTHING
	`, username, hash, role)
	if err != nil {
		return fmt.Errorf("create bootstrap user: %w", err)
	}
	return nil
}

func (r *Repository) CreateUser(ctx context.Context, username, password, role string) (User, error) {
	username = normalizeUsername(username)
	if username == "" {
		return User{}, fmt.Errorf("username is required")
	}
	if !ValidRole(role) {
		return User{}, fmt.Errorf("invalid role %q", role)
	}
	hash, err := HashPassword(password)
	if err != nil {
		return User{}, err
	}
	var user User
	err = r.pool.QueryRow(ctx, `
		INSERT INTO users (username, password_hash, role)
		VALUES ($1, $2, $3)
		RETURNING user_id::text, username, role, active, created_at, last_login_at
	`, username, hash, role).Scan(
		&user.UserID, &user.Username, &user.Role, &user.Active,
		&user.CreatedAt, &user.LastLoginAt,
	)
	var postgresError *pgconn.PgError
	if errors.As(err, &postgresError) && postgresError.Code == "23505" {
		return User{}, ErrUsernameExists
	}
	if err != nil {
		return User{}, fmt.Errorf("create user: %w", err)
	}
	return user, nil
}

func (r *Repository) ListUsers(ctx context.Context, limit, offset int) ([]User, error) {
	if limit <= 0 || limit > 200 {
		limit = 50
	}
	rows, err := r.pool.Query(ctx, `
		SELECT user_id::text, username, role, active, created_at, last_login_at
		FROM users ORDER BY username LIMIT $1 OFFSET $2
	`, limit, offset)
	if err != nil {
		return nil, fmt.Errorf("query users: %w", err)
	}
	defer rows.Close()
	items := make([]User, 0)
	for rows.Next() {
		var user User
		if err := rows.Scan(
			&user.UserID, &user.Username, &user.Role, &user.Active,
			&user.CreatedAt, &user.LastLoginAt,
		); err != nil {
			return nil, fmt.Errorf("scan user: %w", err)
		}
		items = append(items, user)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate users: %w", err)
	}
	return items, nil
}

func (r *Repository) UpdateUserRole(ctx context.Context, userID, role string) (User, error) {
	if !ValidRole(role) {
		return User{}, fmt.Errorf("invalid role %q", role)
	}
	var user User
	err := r.pool.QueryRow(ctx, `
		UPDATE users SET role = $2
		WHERE user_id = $1::uuid
		RETURNING user_id::text, username, role, active, created_at, last_login_at
	`, userID, role).Scan(
		&user.UserID, &user.Username, &user.Role, &user.Active,
		&user.CreatedAt, &user.LastLoginAt,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return User{}, ErrUserNotFound
	}
	if err != nil {
		return User{}, fmt.Errorf("update user role: %w", err)
	}
	return user, nil
}

func (r *Repository) DeleteUser(ctx context.Context, userID string) error {
	result, err := r.pool.Exec(ctx, `DELETE FROM users WHERE user_id = $1::uuid`, userID)
	if err != nil {
		return fmt.Errorf("delete user: %w", err)
	}
	if result.RowsAffected() == 0 {
		return ErrUserNotFound
	}
	return nil
}

func (r *Repository) findForAuthentication(ctx context.Context, username string) (User, string, error) {
	var user User
	var passwordHash string
	err := r.pool.QueryRow(ctx, `
		SELECT user_id::text, username, password_hash, role, active, created_at, last_login_at
		FROM users WHERE lower(username) = $1
	`, normalizeUsername(username)).Scan(
		&user.UserID, &user.Username, &passwordHash, &user.Role,
		&user.Active, &user.CreatedAt, &user.LastLoginAt,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return User{}, "", ErrInvalidCredentials
	}
	if err != nil {
		return User{}, "", fmt.Errorf("find user: %w", err)
	}
	return user, passwordHash, nil
}

func (r *Repository) markLogin(ctx context.Context, userID string) error {
	_, err := r.pool.Exec(ctx, `UPDATE users SET last_login_at = now() WHERE user_id = $1::uuid`, userID)
	if err != nil {
		return fmt.Errorf("update last login: %w", err)
	}
	return nil
}

func (r *Repository) WriteAudit(ctx context.Context, entry AuditEntry) error {
	_, err := r.pool.Exec(ctx, `
		INSERT INTO audit_logs (
			user_id, username, action, resource_type, resource_id,
			method, path, remote_ip, details
		) VALUES (NULLIF($1, '')::uuid, $2, $3, $4, $5, $6, $7, $8, $9)
	`, entry.UserID, entry.Username, entry.Action, entry.Resource, entry.ResourceID,
		entry.Method, entry.Path, entry.RemoteIP, entry.Details)
	if err != nil {
		return fmt.Errorf("write audit log: %w", err)
	}
	return nil
}

func (r *Repository) ListAudit(ctx context.Context, filter AuditFilter) ([]AuditEntry, error) {
	if filter.Limit <= 0 || filter.Limit > 200 {
		filter.Limit = 50
	}
	rows, err := r.pool.Query(ctx, `
		SELECT audit_id, COALESCE(user_id::text, ''), username, action,
		       resource_type, resource_id, method, path, remote_ip, details, created_at
		FROM audit_logs
		WHERE ($1 = '' OR lower(username) = lower($1))
		  AND ($2 = '' OR action = $2)
		ORDER BY created_at DESC
		LIMIT $3 OFFSET $4
	`, filter.Username, filter.Action, filter.Limit, filter.Offset)
	if err != nil {
		return nil, fmt.Errorf("query audit logs: %w", err)
	}
	defer rows.Close()
	items := make([]AuditEntry, 0)
	for rows.Next() {
		var item AuditEntry
		if err := rows.Scan(
			&item.AuditID, &item.UserID, &item.Username, &item.Action,
			&item.Resource, &item.ResourceID, &item.Method, &item.Path,
			&item.RemoteIP, &item.Details, &item.CreatedAt,
		); err != nil {
			return nil, fmt.Errorf("scan audit log: %w", err)
		}
		items = append(items, item)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate audit logs: %w", err)
	}
	return items, nil
}

func normalizeUsername(value string) string {
	return strings.ToLower(strings.TrimSpace(value))
}
