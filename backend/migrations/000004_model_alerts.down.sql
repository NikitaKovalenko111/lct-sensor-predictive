DELETE FROM incidents
WHERE risk_level NOT IN ('high', 'critical');

ALTER TABLE incidents
    DROP CONSTRAINT incidents_risk_level_check;

ALTER TABLE incidents
    ADD CONSTRAINT incidents_risk_level_check
        CHECK (risk_level IN ('high', 'critical'));

ALTER TABLE predictions
    DROP COLUMN IF EXISTS is_alert;
