CREATE TABLE ener.etl_file_tracking (
  file_path TEXT, 
  processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT pk_etl_file_tracking
    PRIMARY KEY (file_path)
);

GRANT SELECT, INSERT ON ener.etl_file_tracking TO enervision_app;
