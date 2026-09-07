INSERT INTO ener.site (site_id, site_type, site_name, location, capacity_kw, status)
VALUES
    ('SITE001', 'office', 'Bureau Paris La Défense', 'Paris, France', 200, 'active'),
    ('SITE002', 'factory', 'Usine Lyon Vénissieux', 'Lyon, France', 1000, 'active'),
    ('SITE003', 'datacenter', 'Data Center Marseille', 'Marseille, France', 800, 'active'),
    ('SITE004', 'office', 'Bureau Bordeaux Centre', 'Bordeaux, France', 150, 'active'),
    ('SITE005', 'factory', 'Usine Lille Métropole', 'Lille, France', 1200, 'active'),
    ('SITE006', 'office', 'Bureau Nantes Atlantis', 'Nantes, France', 180, 'active'),
    ('SITE007', 'datacenter', 'Data Center Strasbourg', 'Strasbourg, France', 600, 'active')
ON CONFLICT (site_id) DO UPDATE SET
    site_type = EXCLUDED.site_type,
    site_name = EXCLUDED.site_name,
    location = EXCLUDED.location,
    capacity_kw = EXCLUDED.capacity_kw,
    status = EXCLUDED.status;