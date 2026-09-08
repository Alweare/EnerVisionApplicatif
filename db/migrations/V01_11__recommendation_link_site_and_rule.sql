-- Recommandations générées à partir des prédictions de consommation (EN-258).
--
-- La table existe déjà (schéma initial) mais ne portait que le lien vers une
-- prédiction. On ajoute :
--  - site_id : dénormalisé depuis la prédiction, pour filtrer les recos d'un
--    utilisateur sans passer par une jointure sur ener.prediction ;
--  - rule_key : quelle règle "en dur" (code) a produit la reco, pour la
--    traçabilité et l'idempotence du moteur ;
--  - status : défaut 'pending' (pending -> applied | dismissed).
--
-- L'index unique (prediction_id, rule_key) garantit qu'un nouveau passage du
-- moteur ne recrée pas une reco déjà émise (INSERT ... ON CONFLICT DO NOTHING).

ALTER TABLE ener.recommendation
  ADD COLUMN site_id  VARCHAR(20) REFERENCES ener.site(site_id),
  ADD COLUMN rule_key VARCHAR(50);

ALTER TABLE ener.recommendation
  ALTER COLUMN status SET DEFAULT 'pending';

UPDATE ener.recommendation SET status = 'pending' WHERE status IS NULL;

CREATE UNIQUE INDEX uq_recommendation_prediction_rule
  ON ener.recommendation (prediction_id, rule_key);

CREATE INDEX idx_recommendation_site_id ON ener.recommendation (site_id);
