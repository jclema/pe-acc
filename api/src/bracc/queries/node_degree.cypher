MATCH (n)
WHERE elementId(n) = $entity_id
  AND (n:Provider OR n:Entity OR n:ProcurementProcess OR n:Award OR n:BudgetExecution
       OR n:Person OR n:Company OR n:Contract OR n:Sanction OR n:Election
       OR n:Amendment OR n:Finance OR n:Embargo OR n:Health OR n:Education
       OR n:Convenio OR n:LaborStats OR n:PublicOffice)
RETURN COUNT { (n)--() } AS degree
