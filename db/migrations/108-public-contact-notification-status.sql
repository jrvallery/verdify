BEGIN;

ALTER TABLE public_contact_submissions
    ADD COLUMN IF NOT EXISTS notification_status TEXT NOT NULL DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS notification_attempted_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS notification_error TEXT;

ALTER TABLE public_contact_submissions
    DROP CONSTRAINT IF EXISTS public_contact_submissions_notification_status_check;

ALTER TABLE public_contact_submissions
    ADD CONSTRAINT public_contact_submissions_notification_status_check
    CHECK (notification_status IN ('pending', 'sent', 'failed'));

CREATE INDEX IF NOT EXISTS idx_public_contact_submissions_notification_status
    ON public_contact_submissions (notification_status, created_at DESC);

COMMENT ON COLUMN public_contact_submissions.notification_status IS
    'Email notification state for the private contact intake queue. pending means not sent yet or SMTP was not configured.';

COMMIT;
