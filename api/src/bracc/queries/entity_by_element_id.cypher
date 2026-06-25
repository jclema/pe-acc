MATCH (e) WHERE elementId(e) = $element_id
  AND (e:Provider OR e:Entity OR e:ProcurementProcess OR e:Award OR e:BudgetExecution
       OR e:Person OR e:Partner OR e:Company OR e:Contract OR e:Sanction OR e:Election OR e:Amendment
       OR e:Finance OR e:Embargo OR e:Health OR e:Education OR e:Convenio OR e:LaborStats
       OR e:PublicOffice)
RETURN e, labels(e) AS entity_labels
LIMIT 1
