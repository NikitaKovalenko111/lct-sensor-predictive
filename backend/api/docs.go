package api

import _ "embed"

// OpenAPISpec contains the public HTTP API contract.
//
//go:embed openapi.yaml
var OpenAPISpec []byte
