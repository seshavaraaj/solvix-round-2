-- Generated from api/app/db.py by `python scripts/seed_db.py --print-schema`.
-- Postgres dialect. The app creates the same tables on SQLite with metadata.create_all().

CREATE TABLE crowding_reports (
	id SERIAL NOT NULL, 
	device_id VARCHAR(64) NOT NULL, 
	bus_id VARCHAR(40) NOT NULL, 
	route_id VARCHAR(32) NOT NULL, 
	level VARCHAR(16) NOT NULL, 
	lat FLOAT, 
	lon FLOAT, 
	received_at VARCHAR(40) NOT NULL, 
	received_ts FLOAT NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE decisions (
	id SERIAL NOT NULL, 
	recommendation_id VARCHAR(32) NOT NULL, 
	decision VARCHAR(16) NOT NULL, 
	reason VARCHAR(32), 
	note TEXT, 
	decided_by VARCHAR(64) NOT NULL, 
	decided_at VARCHAR(40) NOT NULL, 
	decided_wall_at VARCHAR(40), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_decisions_recommendation UNIQUE (recommendation_id)
);

CREATE TABLE fleet_config (
	depot_id VARCHAR(32) NOT NULL, 
	name VARCHAR(80) NOT NULL, 
	lat FLOAT NOT NULL, 
	lon FLOAT NOT NULL, 
	fleet_size INTEGER NOT NULL, 
	reserve INTEGER NOT NULL, 
	out_of_service INTEGER NOT NULL, 
	updated_at VARCHAR(40) NOT NULL, 
	PRIMARY KEY (depot_id)
);

CREATE TABLE recommendations (
	id SERIAL NOT NULL, 
	scenario VARCHAR(40) NOT NULL, 
	t_s FLOAT NOT NULL, 
	created_at VARCHAR(40) NOT NULL, 
	action VARCHAR(16) NOT NULL, 
	from_route_id VARCHAR(32), 
	to_route_id VARCHAR(32), 
	bus_count INTEGER NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	payload TEXT NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE routes_config (
	route_id VARCHAR(32) NOT NULL, 
	payload TEXT NOT NULL, 
	updated_at VARCHAR(40) NOT NULL, 
	PRIMARY KEY (route_id)
);

CREATE TABLE users (
	id SERIAL NOT NULL, 
	username VARCHAR(64) NOT NULL, 
	password_hash VARCHAR(128) NOT NULL, 
	role VARCHAR(16) NOT NULL, 
	created_at VARCHAR(40) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (username)
);
