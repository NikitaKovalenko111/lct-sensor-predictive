package auth

import (
	"context"
	"errors"
	"fmt"
)

type LocalProvider struct {
	repository *Repository
	dummyHash  string
}

func NewLocalProvider(repository *Repository) (*LocalProvider, error) {
	dummyHash, err := HashPassword("invalid-password-placeholder")
	if err != nil {
		return nil, fmt.Errorf("prepare authentication verifier: %w", err)
	}
	return &LocalProvider{repository: repository, dummyHash: dummyHash}, nil
}

func (p *LocalProvider) Authenticate(ctx context.Context, credentials Credentials) (User, error) {
	user, hash, err := p.repository.findForAuthentication(ctx, credentials.Username)
	if errors.Is(err, ErrInvalidCredentials) {
		_ = VerifyPassword(p.dummyHash, credentials.Password)
		return User{}, ErrInvalidCredentials
	}
	if err != nil {
		return User{}, err
	}
	if !VerifyPassword(hash, credentials.Password) {
		return User{}, ErrInvalidCredentials
	}
	if !user.Active {
		return User{}, ErrInactiveUser
	}
	if err := p.repository.markLogin(ctx, user.UserID); err != nil {
		return User{}, err
	}
	return user, nil
}
