MATCH (e)
WHERE (e:Provider AND e.ruc = $identifier)
   OR (e:Entity AND e.entity_id = $identifier)
   OR (e:ProcurementProcess AND (e.process_id = $identifier OR e.seace_code = $identifier))
   OR (e:Award AND e.award_id = $identifier)
   OR (e:BudgetExecution AND e.execution_id = $identifier)
   OR (e:Person AND (e.cpf = $identifier OR e.cpf = $identifier_formatted))
   OR (e:Company AND (e.cnpj = $identifier OR e.cnpj = $identifier_formatted))
RETURN e, labels(e) AS entity_labels, elementId(e) AS entity_id
LIMIT 1
