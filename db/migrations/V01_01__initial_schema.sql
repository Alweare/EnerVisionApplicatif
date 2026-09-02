CREATE SCHEMA ener;

CREATE TABLE ener.site (
  site_id VARCHAR(20), -- example SITE001
  site_type VARCHAR(10), -- example office
  site_name VARCHAR(50), -- example Bureau Paris La Défense
  location VARCHAR(30), -- example Paris, France
  capacity_kw FLOAT, -- example 200
  status VARCHAR(10), -- example active
  CONSTRAINT pk_site
    PRIMARY KEY (site_id)
);

CREATE TABLE ener.prediction (
  prediction_id UUID DEFAULT gen_random_uuid(), -- example PRED000001
  site_id VARCHAR(20), -- example SITE001
  predicted_for TIMESTAMP, -- example 2024-06-15T15:00:00
  predicted_consumption_kw FLOAT, -- example 95.4
  model_version VARCHAR(20), -- example v1.2.0
  created_at TIMESTAMP, -- example 2024-06-15T14:32:00
  CONSTRAINT pk_prediction
    PRIMARY KEY (prediction_id),
  CONSTRAINT fk_prediction_site
    FOREIGN KEY (site_id)
    REFERENCES ener.site(site_id)
);

CREATE TABLE ener.recommendation (
  recommendation_id UUID DEFAULT gen_random_uuid(), -- example REC0000001
  prediction_id UUID, -- example PRED000001
  action_type VARCHAR(30), -- example reduce_load
  message TEXT, -- example "Réduire la charge de 10% entre 14h et 16h"
  status VARCHAR(15), -- example pending
  created_at TIMESTAMP, -- example 2024-06-15T14:32:00
  CONSTRAINT pk_recommendation
    PRIMARY KEY (recommendation_id),
  CONSTRAINT fk_recommendation_prediction
    FOREIGN KEY (prediction_id)
    REFERENCES ener.prediction(prediction_id)
);

CREATE TABLE ener.measurement (
  measurement_id UUID DEFAULT gen_random_uuid(), -- example MEAS0000001
  site_id VARCHAR(20), -- example SITE001
  measurement_date TIMESTAMP, -- example 2024-06-15T14:32:00
  consumption_kw FLOAT, -- example 87.34
  consumption_kwh FLOAT, -- example 87.34
  voltage_v FLOAT, -- example 401.2
  current_a FLOAT, -- example 132.5
  power_factor FLOAT, -- example 0.923
  temperature_celsius FLOAT, -- example 22.1
  humidity_percent FLOAT, -- example 58.4
  null_reason TEXT[], -- example {temperature_sensor_failure}
  data_quality VARCHAR(10), -- example good
  created_at TIMESTAMP, -- example 2024-06-15T14:32:00
  CONSTRAINT pk_measurement
    PRIMARY KEY (measurement_id),
  CONSTRAINT fk_measurement_site
    FOREIGN KEY (site_id)
    REFERENCES ener.site(site_id)
);

CREATE TABLE ener.alert (
  alert_id UUID DEFAULT gen_random_uuid(), -- example ALR-SITE002-1718458320
  site_id VARCHAR(20), -- example SITE002
  severity VARCHAR(10), -- example critical
  type VARCHAR(15), -- example outage
  message TEXT, -- example "Risque de surcharge sur Usine Lyon Vénissieux"
  value FLOAT, -- example 812.5
  threshold FLOAT, -- example 720.0
  created_at TIMESTAMP, -- example 2024-06-15T14:32:00
  CONSTRAINT pk_alert
    PRIMARY KEY (alert_id),
  CONSTRAINT fk_alert_site
    FOREIGN KEY (site_id)
    REFERENCES ener.site(site_id)
);