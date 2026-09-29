package httpapi

import (
	"net/http/httptest"
	"strings"
	"testing"
)

func TestParsePaginationRejectsNegativeOffset(t *testing.T) {
	request := httptest.NewRequest("GET", "/?offset=-1", nil)
	response := httptest.NewRecorder()

	_, _, ok := parsePagination(response, request)
	if ok {
		t.Fatal("expected invalid pagination")
	}
	if response.Code != 400 {
		t.Fatalf("unexpected status: got %d, want 400", response.Code)
	}
}

func TestParsePaginationAcceptsValues(t *testing.T) {
	request := httptest.NewRequest("GET", "/?limit=25&offset=50", nil)
	response := httptest.NewRecorder()

	limit, offset, ok := parsePagination(response, request)
	if !ok || limit != 25 || offset != 50 {
		t.Fatalf("unexpected pagination: limit=%d offset=%d ok=%t", limit, offset, ok)
	}
}

func TestDecodeJSONRejectsSecondObject(t *testing.T) {
	request := httptest.NewRequest("POST", "/", strings.NewReader(`{"value":1}{"value":2}`))
	response := httptest.NewRecorder()
	var target struct {
		Value int `json:"value"`
	}

	if decodeJSON(response, request, &target) {
		t.Fatal("expected a second JSON object to be rejected")
	}
	if response.Code != 400 {
		t.Fatalf("unexpected status: got %d, want 400", response.Code)
	}
}
