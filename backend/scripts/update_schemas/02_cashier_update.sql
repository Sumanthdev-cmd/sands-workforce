CREATE TABLE IF NOT EXISTS cashbook_entries (
 id UUID PRIMARY KEY,
 organization_id UUID NOT NULL REFERENCES organizations(id),
 created_by_user_id UUID NOT NULL REFERENCES users(id),
 created_by_code VARCHAR(100) NOT NULL,
 client_request_id UUID NOT NULL,
 fingerprint VARCHAR(64) NOT NULL,
 transaction_date DATE NOT NULL,
 direction VARCHAR(10) NOT NULL CHECK(direction IN ('CREDIT','DEBIT')),
 amount NUMERIC(16,2) NOT NULL CHECK(amount>0),
 organization_account VARCHAR(160) NOT NULL,
 payment_mode VARCHAR(30) NOT NULL,
 counterparty VARCHAR(160) NOT NULL,
 counterparty_account VARCHAR(64),
 payment_reference VARCHAR(160),
 notes TEXT,
 document_id UUID REFERENCES document_records(id) ON DELETE RESTRICT,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 voided_at TIMESTAMPTZ,
 voided_by_user_id UUID REFERENCES users(id),
 void_reason TEXT,
 CONSTRAINT uq_cashbook_request UNIQUE(organization_id,created_by_user_id,client_request_id)
);
CREATE INDEX IF NOT EXISTS ix_cashbook_org_date ON cashbook_entries(organization_id,transaction_date);
