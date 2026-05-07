BEGIN;

CREATE TABLE IF NOT EXISTS public_contact_submissions (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    name TEXT NOT NULL CHECK (char_length(name) BETWEEN 2 AND 120),
    email TEXT NOT NULL CHECK (char_length(email) BETWEEN 5 AND 254),
    topic TEXT NOT NULL DEFAULT 'other' CHECK (
        topic IN ('build', 'control', 'data', 'press', 'collaboration', 'correction', 'other')
    ),
    affiliation TEXT CHECK (affiliation IS NULL OR char_length(affiliation) <= 160),
    message TEXT NOT NULL CHECK (char_length(message) BETWEEN 20 AND 4000),
    ip_hash TEXT,
    user_agent TEXT,
    referrer TEXT,
    turnstile_verified BOOLEAN NOT NULL DEFAULT false,
    status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'read', 'replied', 'closed', 'spam')),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_public_contact_submissions_created
    ON public_contact_submissions (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_public_contact_submissions_status_created
    ON public_contact_submissions (status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_public_contact_submissions_ip_recent
    ON public_contact_submissions (ip_hash, created_at DESC);

COMMENT ON TABLE public_contact_submissions IS
    'Public verdify.ai contact form submissions. Raw client IPs are not stored; only salted hashes are retained for rate limiting.';

COMMIT;
