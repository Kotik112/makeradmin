
TEST_COMPOSE=docker-compose -p test -f docker-compose.yml -f docker-compose.test.yml
DEV_COMPOSE=docker-compose -f docker-compose.yml -f docker-compose.dev.yml

build: .env
	docker-compose build

run: .env
	docker-compose up

dev: .env
	$(DEV_COMPOSE) up --build

test: .env
	$(TEST_COMPOSE) down || true
	docker volume rm test_dbdata || true
	$(TEST_COMPOSE) build
	python3 db_init.py --project-name test
	$(TEST_COMPOSE) up --abort-on-container-exit --exit-code-from test

dev-test:
	(cd test/src && python3 -m pytest --workers auto -ra)

init-npm:
	cd admin && npm install 
	cd public && npm install 

init-pip:
	python3 -m pip install --upgrade -r requirements.txt

init: init-pip init-npm

# TODO Remove this, db migrations will be done at container startup by each run script.
init-db: .env
	docker-compose run api bash -c "cd /work/src && python3 migrate.py"

insert-devel-data: .env
	docker-compose run backend bash -c "cd /work/src/scrape && python3 tictail2db.py"

.env:
	python3 create_env.py

stop:
	docker-compose down

test-admin-js:
	npm --prefix admin run eslint
	npm --prefix admin run test

firstrun: .env build
	python3 firstrun.py

admin-dev-server:
	mkdir -p admin/node_modules
	docker-compose -f admin/dev-server-compose.yaml rm -sfv
	docker volume rm -f makeradmin_node_modules
	docker-compose -f admin/dev-server-compose.yaml up --build

.PHONY: build firstrun admin-dev-server init init-db init-npm init-pip install run stop dev-test test dev
