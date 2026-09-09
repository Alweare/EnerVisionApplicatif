-- ---------------------------------------------------------------------------
-- Seed de prédictions de consommation -- DEV LOCAL UNIQUEMENT.
--
-- Alimente ener.prediction avec des données plausibles pour tester
-- l'endpoint GET /api/v1/backend/prediction/{site_id} et le front, en
-- attendant que le worker de prédiction publie de vraies prédictions.
--
-- Ce script N'EST PAS une migration : il ne doit pas tourner en prod.
-- Rejouable : purge d'abord les lignes du modèle de seed.
--
-- Exécution :
--   docker exec -i postgres psql -U enervision_admin -d enervision < db/seed/seed_predictions.sql
-- ---------------------------------------------------------------------------

BEGIN;

DELETE FROM ener.prediction WHERE model_version = 'v0.1.0-seed';

INSERT INTO ener.prediction
    (site_id, predicted_for, predicted_consumption_kw, model_version, created_at)
SELECT
    s.site_id,
    horizon.predicted_for,
    GREATEST(
        0,
        base.avg_kw
            -- profil journalier : creux la nuit, pic vers 14h
            * (1 + 0.22 * sin(2 * pi() * (EXTRACT(HOUR FROM horizon.predicted_for) - 8) / 24.0))
            -- bruit +/- 4 %
            + (random() - 0.5) * base.avg_kw * 0.08
    )::float,
    'v0.1.0-seed',
    now()
FROM ener.site s
JOIN LATERAL (
    SELECT COALESCE(avg(m.consumption_kw), s.capacity_kw * 0.5) AS avg_kw
    FROM ener.measurement m
    WHERE m.site_id = s.site_id
      AND m.consumption_kw IS NOT NULL
      AND m.measurement_date >= now() - interval '24 hours'
) base ON true
CROSS JOIN LATERAL (
    SELECT generate_series(
        date_trunc('hour', now()) - interval '6 hours',
        date_trunc('hour', now()) + interval '24 hours',
        interval '1 hour'
    )::timestamp AS predicted_for
) horizon;

COMMIT;

-- Contrôle
SELECT site_id,
       count(*)                              AS rows,
       round(min(predicted_consumption_kw)::numeric, 1) AS min_kw,
       round(max(predicted_consumption_kw)::numeric, 1) AS max_kw,
       min(predicted_for)                    AS from_ts,
       max(predicted_for)                    AS to_ts
FROM ener.prediction
WHERE model_version = 'v0.1.0-seed'
GROUP BY site_id
ORDER BY site_id;
