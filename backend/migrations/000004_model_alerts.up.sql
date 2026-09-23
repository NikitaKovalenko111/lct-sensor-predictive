ALTER TABLE predictions
    ADD COLUMN is_alert BOOLEAN;

ALTER TABLE incidents
    DROP CONSTRAINT incidents_risk_level_check;

ALTER TABLE incidents
    ADD CONSTRAINT incidents_risk_level_check
        CHECK (risk_level IN ('low', 'medium', 'high', 'critical'));

COMMENT ON COLUMN predictions.is_alert IS
    'Model-specific threshold decision. NULL means that the producer uses risk_level only.';
