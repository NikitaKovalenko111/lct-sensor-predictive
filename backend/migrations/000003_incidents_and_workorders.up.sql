CREATE TABLE incidents (
    incident_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    prediction_id UUID NOT NULL UNIQUE REFERENCES predictions(prediction_id),
    object_id BIGINT NOT NULL,
    incident_type TEXT NOT NULL CHECK (
        incident_type IN ('fire_risk', 'nsd_event', 'nsd_risk', 'equipment_failure')
    ),
    risk_score DOUBLE PRECISION NOT NULL CHECK (risk_score >= 0 AND risk_score <= 1),
    risk_level TEXT NOT NULL CHECK (risk_level IN ('high', 'critical')),
    status TEXT NOT NULL DEFAULT 'new' CHECK (
        status IN ('new', 'in_review', 'resolved', 'dismissed')
    ),
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    assigned_to TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ
);

CREATE INDEX incidents_status_created_idx ON incidents (status, created_at DESC);
CREATE INDEX incidents_object_created_idx ON incidents (object_id, created_at DESC);

CREATE TABLE incident_decisions (
    decision_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
    decision TEXT NOT NULL CHECK (
        decision IN ('confirmed', 'false_alarm', 'monitor', 'dispatch_crew')
    ),
    actor TEXT NOT NULL,
    comment TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX incident_decisions_incident_created_idx
    ON incident_decisions (incident_id, created_at DESC);

CREATE TABLE work_order_drafts (
    work_order_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID NOT NULL UNIQUE REFERENCES incidents(incident_id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    priority TEXT NOT NULL CHECK (priority IN ('normal', 'high', 'emergency')),
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status = 'draft'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
