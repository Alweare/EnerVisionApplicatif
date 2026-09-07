CREATE TABLE ener.user_site (
                                user_id     UUID        NOT NULL,
                                site_id     VARCHAR(50) NOT NULL REFERENCES ener.site(site_id) ON DELETE CASCADE,
                                created_at  TIMESTAMP   NOT NULL DEFAULT now(),
                                PRIMARY KEY (user_id, site_id)
);

CREATE INDEX idx_user_site_site_id ON ener.user_site(site_id);

-- FIXME Données de test temporaires, en attendant un script de seed dédié séparé des migrations Pyway.
INSERT INTO ener.user_site (user_id, site_id) VALUES
                                                  ('a1111111-1111-1111-1111-111111111111', 'SITE001'),
                                                  ('a1111111-1111-1111-1111-111111111111', 'SITE003'),
                                                  ('b2222222-2222-2222-2222-222222222222', 'SITE002');