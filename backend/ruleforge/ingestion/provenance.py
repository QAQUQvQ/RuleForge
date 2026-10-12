"""Only title relationships explicitly recorded by xParse are used."""
def section_hierarchy(raw, element_id):
    elements = {e['element_id']:e for e in raw['data']['elements']}
    parents = {}
    for e in elements.values():
        for child in e.get('metadata',{}).get('children_ids',[]):
            parents.setdefault(child,[]).append(e['element_id'])
    titles, seen = [], set()
    current = element_id
    while current not in seen:
        seen.add(current)
        candidates = parents.get(current,[])
        if len(candidates) != 1:
            break
        current = candidates[0]
        e = elements.get(current,{})
        if e.get('type')=='Title':
            titles.append(e['text'])
    return list(reversed(titles))
