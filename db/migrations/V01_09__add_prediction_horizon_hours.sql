-- Forecast multi-horizon : une prévision (site_id, predicted_for) ne suffit
-- plus à elle seule à identifier l'horizon de la prédiction, puisqu'un seul
-- appel /forecast peut désormais insérer jusqu'à 168 lignes (une par heure).
-- Sans cette colonne, la comparaison "performance réelle" (repository/
-- prediction_repository.get_matched_predictions) mélangerait des prédictions
-- à tous les horizons, faussant la MAE réelle comparée à la MAE d'entraînement
-- (qui reste, elle, ancrée sur l'horizon T+1h). Colonne nullable, additive :
-- aucune ligne existante n'est modifiée, aucune donnée supprimée.
ALTER TABLE ener.prediction ADD COLUMN horizon_hours INTEGER;
