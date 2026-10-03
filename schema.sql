CREATE TABLE IF NOT EXISTS shows (
  id CHAR(36) PRIMARY KEY,
  name VARCHAR(160) NOT NULL,
  price_paise BIGINT NOT NULL CHECK (price_paise >= 0),
  per_user_limit INTEGER NOT NULL CHECK (per_user_limit > 0),
  total_seats INTEGER NOT NULL CHECK (total_seats > 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reservations (
  id CHAR(36) PRIMARY KEY,
  show_id CHAR(36) NOT NULL REFERENCES shows(id),
  user_id VARCHAR(128) NOT NULL,
  amount_paise BIGINT NOT NULL CHECK (amount_paise >= 0),
  status VARCHAR(16) NOT NULL CHECK (status IN ('confirmed','cancelled')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  cancelled_at TIMESTAMPTZ NULL
);
CREATE INDEX IF NOT EXISTS ix_reservations_show_user_status ON reservations (show_id,user_id,status);

CREATE TABLE IF NOT EXISTS show_user_locks (
  show_id CHAR(36) NOT NULL REFERENCES shows(id),
  user_id VARCHAR(128) NOT NULL,
  PRIMARY KEY (show_id,user_id)
);

CREATE TABLE IF NOT EXISTS seats (
  show_id CHAR(36) NOT NULL REFERENCES shows(id),
  seat_name VARCHAR(32) NOT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'available' CHECK (status IN ('available','held','confirmed')),
  reservation_id CHAR(36) NULL REFERENCES reservations(id),
  PRIMARY KEY (show_id,seat_name)
);
CREATE INDEX IF NOT EXISTS ix_seats_reservation ON seats (reservation_id);

CREATE TABLE IF NOT EXISTS reservation_seats (
  reservation_id CHAR(36) NOT NULL REFERENCES reservations(id),
  show_id CHAR(36) NOT NULL,
  seat_name VARCHAR(32) NOT NULL,
  PRIMARY KEY (reservation_id,seat_name),
  FOREIGN KEY (show_id,seat_name) REFERENCES seats(show_id,seat_name)
);

CREATE TABLE IF NOT EXISTS idempotency_keys (
  user_id VARCHAR(128) NOT NULL,
  show_id CHAR(36) NOT NULL REFERENCES shows(id),
  idem_key VARCHAR(128) NOT NULL,
  fingerprint CHAR(64) NOT NULL,
  reservation_id CHAR(36) NOT NULL REFERENCES reservations(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id,show_id,idem_key)
);

CREATE TABLE IF NOT EXISTS metric_events (
  id BIGSERIAL PRIMARY KEY,
  event_type VARCHAR(16) NOT NULL CHECK (event_type IN ('confirmed','declined','cancelled')),
  reason VARCHAR(40) NOT NULL,
  show_id CHAR(36) NULL REFERENCES shows(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_metric_event_type_reason ON metric_events (event_type,reason);
