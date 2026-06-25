MATCH (center)
WHERE elementId(center) = $entity_id
  AND (center:Provider OR center:Entity OR center:ProcurementProcess OR center:Award OR center:BudgetExecution
       OR center:Person OR center:Company OR center:Contract OR center:Sanction OR center:Election
       OR center:Amendment OR center:Finance OR center:Embargo OR center:Health OR center:Education
       OR center:Convenio OR center:LaborStats OR center:PublicOffice
       OR center:OffshoreEntity OR center:OffshoreOfficer OR center:GlobalPEP
       OR center:CVMProceeding OR center:Expense)
OPTIONAL MATCH p=(center)-[*1..4]-(n)
WHERE length(p) <= $depth
  AND all(
    x IN nodes(p)
    WHERE NOT (
      x:User OR x:Investigation OR x:Annotation OR x:Tag
    )
  )
WITH center, collect(p) AS paths
WITH center,
     reduce(ns = [center], p IN paths | ns + CASE WHEN p IS NULL THEN [] ELSE nodes(p) END) AS raw_nodes,
     reduce(rs = [], p IN paths | rs + CASE WHEN p IS NULL THEN [] ELSE relationships(p) END) AS raw_rels
UNWIND raw_nodes AS n
WITH center, collect(DISTINCT n) AS nodes, raw_rels
UNWIND CASE WHEN size(raw_rels) = 0 THEN [NULL] ELSE raw_rels END AS r
WITH center, nodes, collect(DISTINCT r) AS rels
RETURN nodes,
       [x IN rels WHERE x IS NOT NULL] AS relationships,
       elementId(center) AS center_id
