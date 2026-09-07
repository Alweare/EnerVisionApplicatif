-- L'identifiant d'alerte vient de la Mock API (ex: ALR-SITE002-1718458320) :
-- c'est une chaîne, pas un UUID. On l'utilise directement comme clé primaire
-- pour garder le même identifiant de bout en bout (API -> blob -> BDD) et
-- pouvoir écarter les doublons avec ON CONFLICT DO NOTHING.
-- La table est vide : le changement de type ne migre aucune donnée.
ALTER TABLE ener.alert ALTER COLUMN alert_id DROP DEFAULT;
ALTER TABLE ener.alert ALTER COLUMN alert_id TYPE VARCHAR(50);
