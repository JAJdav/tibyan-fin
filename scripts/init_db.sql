CREATE TABLE IF NOT EXISTS customers (
  customer_id VARCHAR(64) NOT NULL, attributes JSON NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (customer_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS merchants (
  merchant_id VARCHAR(64) NOT NULL, attributes JSON NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (merchant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS transactions (
  transaction_id VARCHAR(64) NOT NULL, customer_id VARCHAR(64) NULL,
  merchant_id VARCHAR(64) NULL, account_id VARCHAR(64) NULL, device_id VARCHAR(64) NULL,
  counterparty_account_id VARCHAR(64) NULL, amount DECIMAL(18,2) NOT NULL,
  currency CHAR(3) NOT NULL, direction VARCHAR(16) NULL, channel VARCHAR(32) NULL,
  event_time DATETIME(3) NOT NULL, received_at DATETIME(3) NOT NULL,
  request_hash CHAR(64) NOT NULL, raw_payload JSON NOT NULL, metadata JSON NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (transaction_id),
  CONSTRAINT chk_amount_positive CHECK (amount > 0),
  CONSTRAINT fk_tx_customer FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
  CONSTRAINT fk_tx_merchant FOREIGN KEY (merchant_id) REFERENCES merchants(merchant_id),
  INDEX idx_tx_customer_time (customer_id, event_time),
  INDEX idx_tx_merchant_time (merchant_id, event_time),
  INDEX idx_tx_device_time (device_id, event_time),
  INDEX idx_tx_event_time (event_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS detection_results (
  id BIGINT NOT NULL AUTO_INCREMENT, transaction_id VARCHAR(64) NOT NULL,
  engine VARCHAR(16) NOT NULL, status VARCHAR(20) NOT NULL,
  risk_score DECIMAL(6,5) NULL, reason_codes JSON NOT NULL, evidence JSON NOT NULL,
  processing_ms INT NOT NULL DEFAULT 0, engine_version VARCHAR(64) NOT NULL,
  degraded BOOLEAN NOT NULL DEFAULT FALSE,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id), UNIQUE KEY uq_det_tx_engine (transaction_id, engine),
  CONSTRAINT fk_det_tx FOREIGN KEY (transaction_id) REFERENCES transactions(transaction_id),
  INDEX idx_det_engine_status (engine, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS risk_decisions (
  decision_id VARCHAR(36) NOT NULL, transaction_id VARCHAR(64) NOT NULL,
  decision VARCHAR(16) NOT NULL, combined_risk_score DECIMAL(6,5) NULL,
  fraud_risk_score DECIMAL(6,5) NULL, aml_risk_score DECIMAL(6,5) NULL,
  reason_codes JSON NOT NULL, policy_version VARCHAR(64) NOT NULL,
  feature_version VARCHAR(64) NOT NULL, model_versions JSON NOT NULL,
  degraded BOOLEAN NOT NULL DEFAULT FALSE, missing_features JSON NOT NULL,
  processing_ms INT NOT NULL DEFAULT 0, decision_basis VARCHAR(64) NULL,
  correlation_id VARCHAR(64) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (decision_id), UNIQUE KEY uq_dec_tx (transaction_id),
  CONSTRAINT fk_dec_tx FOREIGN KEY (transaction_id) REFERENCES transactions(transaction_id),
  INDEX idx_dec_decision_time (decision, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS investigations (
  transaction_id VARCHAR(64) NOT NULL, status VARCHAR(20) NOT NULL DEFAULT 'pending',
  report_json JSON NULL, prompt_version VARCHAR(64) NULL, llm_model VARCHAR(128) NULL,
  llm_mode VARCHAR(32) NULL, generated_at DATETIME(3) NULL,
  retry_count INT NOT NULL DEFAULT 0, last_error TEXT NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (transaction_id),
  CONSTRAINT fk_inv_tx FOREIGN KEY (transaction_id) REFERENCES transactions(transaction_id),
  INDEX idx_inv_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS idempotency_records (
  idempotency_key VARCHAR(128) NOT NULL, transaction_id VARCHAR(64) NOT NULL,
  request_hash CHAR(64) NOT NULL, response_json JSON NOT NULL, status VARCHAR(20) NOT NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (idempotency_key), UNIQUE KEY uq_idem_tx (transaction_id),
  CONSTRAINT fk_idem_tx FOREIGN KEY (transaction_id) REFERENCES transactions(transaction_id),
  INDEX idx_idem_hash (request_hash)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS outbox_events (
  event_id VARCHAR(36) NOT NULL, event_type VARCHAR(64) NOT NULL,
  aggregate_type VARCHAR(32) NOT NULL, aggregate_id VARCHAR(64) NOT NULL,
  transaction_id VARCHAR(64) NOT NULL, payload JSON NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'pending', attempts INT NOT NULL DEFAULT 0,
  next_attempt_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  locked_at DATETIME(3) NULL, locked_by VARCHAR(64) NULL, last_error TEXT NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (event_id),
  CONSTRAINT fk_out_tx FOREIGN KEY (transaction_id) REFERENCES transactions(transaction_id),
  INDEX idx_out_status_next (status, next_attempt_at),
  INDEX idx_out_tx (transaction_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
