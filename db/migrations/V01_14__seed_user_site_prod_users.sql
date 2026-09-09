INSERT INTO ener.user_site (user_id, site_id)
SELECT '2f6840de-1211-44e5-a33a-39972486c3a6', site_id
FROM ener.site
ON CONFLICT (user_id, site_id) DO NOTHING;

-- Gestionnaires régionaux (rôle user) : périmètre partiel (ajuster ici au besoin).
INSERT INTO ener.user_site (user_id, site_id) VALUES
    ('8bb8a5d1-7f75-4815-bcfd-1cc5aa47b048', 'SITE002'),  -- Paul Durand — Usine Lyon
    ('8bb8a5d1-7f75-4815-bcfd-1cc5aa47b048', 'SITE003'),  -- Paul Durand — Data Center Marseille
    ('8bb8a5d1-7f75-4815-bcfd-1cc5aa47b048', 'SITE004'),  -- Paul Durand — Bureau Bordeaux
    ('d6a3be5c-bbe5-4ff1-a3fe-3f3cc17bdb7a', 'SITE001'),  -- Sophie Bernard — Bureau Paris
    ('d6a3be5c-bbe5-4ff1-a3fe-3f3cc17bdb7a', 'SITE005'),  -- Sophie Bernard — Usine Lille
    ('d6a3be5c-bbe5-4ff1-a3fe-3f3cc17bdb7a', 'SITE007')   -- Sophie Bernard — Data Center Strasbourg
ON CONFLICT (user_id, site_id) DO NOTHING;
