"""Speak provider timestamps as estimates, never invented live arrival guarantees."""
import math
from datetime import datetime, timezone

def transit_speech(route, current=None):
    current = current or datetime.now(timezone.utc)
    sentence = f"Google Maps lists line {route['line']} from {route['stop']}."
    value = route.get('departure_time')
    if not value:
        return sentence + ' No departure time was returned.'
    try:
        departure = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if departure.tzinfo is None: raise ValueError()
        seconds = (departure-current).total_seconds()
    except (ValueError, TypeError):
        return sentence + ' I could not read its departure time.'
    if seconds < -30:
        return sentence + ' The returned departure estimate has already passed; do not rely on it as the next bus.'
    if seconds < 60:
        return sentence + ' Its estimated departure is within one minute. This is a Maps estimate, not a confirmed bus arrival.'
    minutes = math.ceil(seconds/60)
    return sentence + f' It is estimated to depart in {minutes} minutes. I can read the bus number when it is in view.'
