"""Render model-observed obstacles without turning them into movement commands."""
KINDS = {'chair':'chair', 'table':'table', 'bag':'bag', 'box':'box',
         'cable':'cable', 'stairs':'stairs', 'curb':'curb', 'vehicle':'vehicle',
         'person':'person', 'animal':'animal', 'other':'unidentified object'}
POSITIONS = {'left':'on the left', 'center':'near the center', 'right':'on the right',
             'lower':'in the lower part', 'unclear':'at an unclear position'}
SCHEMA = {'type':'ARRAY', 'items': {'type':'OBJECT', 'required':['kind','position'],
          'properties': {'kind': {'type':'STRING','enum':list(KINDS)},
                         'position': {'type':'STRING','enum':list(POSITIONS)}}}}

def describe_obstacles(items):
    if not isinstance(items, list): return None
    valid = [item for item in items if isinstance(item,dict) and item.get('kind') in KINDS and item.get('position') in POSITIONS][:2]
    if not valid: return None
    facts = [KINDS[item['kind']]+' '+POSITIONS[item['position']] for item in valid]
    return 'Possible '+ '; '.join(facts) + ' of the camera view. Clearance is unverified; use your mobility aid to check.'
