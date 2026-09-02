ALTER TABLE ener.measurement ALTER COLUMN site_id SET NOT NULL;
ALTER TABLE ener.measurement ALTER COLUMN measurement_date SET NOT NULL;
ALTER TABLE ener.measurement ALTER COLUMN created_at SET DEFAULT now();
ALTER TABLE ener.measurement ALTER COLUMN created_at SET NOT NULL;

ALTER TABLE ener.prediction ALTER COLUMN site_id SET NOT NULL;
ALTER TABLE ener.prediction ALTER COLUMN created_at SET DEFAULT now();
ALTER TABLE ener.prediction ALTER COLUMN created_at SET NOT NULL;

ALTER TABLE ener.recommendation ALTER COLUMN prediction_id SET NOT NULL;
ALTER TABLE ener.recommendation ALTER COLUMN created_at SET DEFAULT now();
ALTER TABLE ener.recommendation ALTER COLUMN created_at SET NOT NULL;

ALTER TABLE ener.alert ALTER COLUMN site_id SET NOT NULL;
ALTER TABLE ener.alert ALTER COLUMN created_at SET DEFAULT now();
ALTER TABLE ener.alert ALTER COLUMN created_at SET NOT NULL;