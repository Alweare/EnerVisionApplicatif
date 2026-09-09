-- Gain estimé d'une recommandation, en kW (ex. charge à délester pour repasser
-- sous la capacité). NULL quand la règle ne produit pas de chiffre.
ALTER TABLE ener.recommendation ADD COLUMN estimated_gain_kw FLOAT;
