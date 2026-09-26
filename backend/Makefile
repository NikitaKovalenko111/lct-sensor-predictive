.PHONY: tidy test build up up-mock down logs

tidy:
	go mod tidy

test:
	go test ./...

build:
	go build ./...

up:
	docker compose up --build

up-mock:
	docker compose --profile mock --profile demo up --build

down:
	docker compose down

logs:
	docker compose logs -f api worker mock-model
