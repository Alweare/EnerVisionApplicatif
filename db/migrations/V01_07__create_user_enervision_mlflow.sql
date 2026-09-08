CREATE SCHEMA IF NOT EXISTS mlflow;

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'enervision_mlflow') THEN
    CREATE USER enervision_mlflow;
  END IF;
END
$$;

GRANT ALL ON SCHEMA mlflow TO enervision_mlflow;
ALTER ROLE enervision_mlflow SET search_path TO mlflow;
