MATCH (p:Provider)
WHERE elementId(p) = $provider_id
   OR p.ruc = $provider_identifier
RETURN p, labels(p) AS entity_labels, elementId(p) AS entity_id
LIMIT 1
