CREATE TABLE IF NOT EXISTS shows (
  id CHAR(36) PRIMARY KEY,
  name VARCHAR(160) NOT NULL,
  price_paise BIGINT UNSIGNED NOT NULL,
  per_user_limit INT UNSIGNED NOT NULL DEFAULT 4,
  total_seats INT UNSIGNED NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS reservations (
  id CHAR(36) PRIMARY KEY,
  show_id CHAR(36) NOT NULL,
  user_id VARCHAR(128) NOT NULL,
  amount_paise BIGINT UNSIGNED NOT NULL,
  status ENUM('confirmed','cancelled') NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  cancelled_at TIMESTAMP NULL,
  KEY ix_reservations_show_user_status (show_id,user_id,status),
  CONSTRAINT fk_reservations_show FOREIGN KEY (show_id) REFERENCES shows(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS show_user_locks (
  show_id CHAR(36) NOT NULL,
  user_id VARCHAR(128) NOT NULL,
  PRIMARY KEY (show_id,user_id),
  CONSTRAINT fk_show_user_lock_show FOREIGN KEY (show_id) REFERENCES shows(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS seats (
  show_id CHAR(36) NOT NULL,
  seat_name VARCHAR(32) NOT NULL,
  status ENUM('available','held','confirmed') NOT NULL DEFAULT 'available',
  reservation_id CHAR(36) NULL,
  PRIMARY KEY (show_id,seat_name),
  KEY ix_seats_reservation (reservation_id),
  CONSTRAINT fk_seats_show FOREIGN KEY (show_id) REFERENCES shows(id),
  CONSTRAINT fk_seats_reservation FOREIGN KEY (reservation_id) REFERENCES reservations(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS reservation_seats (
  reservation_id CHAR(36) NOT NULL,
  show_id CHAR(36) NOT NULL,
  seat_name VARCHAR(32) NOT NULL,
  PRIMARY KEY (reservation_id,seat_name),
  CONSTRAINT fk_reservation_seats_reservation FOREIGN KEY (reservation_id) REFERENCES reservations(id),
  CONSTRAINT fk_reservation_seats_seat FOREIGN KEY (show_id,seat_name) REFERENCES seats(show_id,seat_name)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS idempotency_keys (
  user_id VARCHAR(128) NOT NULL,
  show_id CHAR(36) NOT NULL,
  idem_key VARCHAR(128) NOT NULL,
  fingerprint CHAR(64) NOT NULL,
  reservation_id CHAR(36) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id,show_id,idem_key),
  CONSTRAINT fk_idempotency_show FOREIGN KEY (show_id) REFERENCES shows(id),
  CONSTRAINT fk_idempotency_reservation FOREIGN KEY (reservation_id) REFERENCES reservations(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS metric_events (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  event_type ENUM('confirmed','declined','cancelled') NOT NULL,
  reason VARCHAR(40) NOT NULL,
  show_id CHAR(36) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY ix_metric_event_type_reason (event_type,reason),
  CONSTRAINT fk_metric_show FOREIGN KEY (show_id) REFERENCES shows(id)
) ENGINE=InnoDB;
