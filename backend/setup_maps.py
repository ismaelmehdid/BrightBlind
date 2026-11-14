"""Configure Routes on the authorized event project, keeping the key out of output and Git."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ACCOUNT = 'devstar7088@gcplab.me'
PROJECT_NAME = 'VexoHacks-7088'
KEY_NAME = 'SecondVision Routes'

def gcloud(*args):
    result = subprocess.run(['gcloud', *args, '--account='+ACCOUNT, '--format=json', '--quiet'],
                            capture_output=True, text=True, timeout=180)
    if result.returncode:
        # Do not print stdout, which can contain a key string.
        raise RuntimeError(result.stderr.strip() or 'Google Cloud command failed.')
    return json.loads(result.stdout) if result.stdout.strip() else {}

def save_key(path, key, project):
    lines = path.read_text().splitlines() if path.exists() else []
    lines = [line for line in lines if not line.startswith(('GOOGLE_MAPS_API_KEY=', 'GOOGLE_MAPS_PROJECT='))]
    temporary = path.with_name('.env.maps-tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write('\n'.join(lines + ['GOOGLE_MAPS_API_KEY='+key, 'GOOGLE_MAPS_PROJECT='+project])+'\n')
    os.replace(temporary, path)
    os.chmod(path, 0o600)

def verify_route(key):
    payload = {'origin': {'address': 'Ferry Building, San Francisco'},
               'destination': {'address': 'Union Square, San Francisco'}, 'travelMode': 'TRANSIT'}
    for attempt in range(6):
        request = Request('https://routes.googleapis.com/directions/v2:computeRoutes',
            headers={'X-Goog-Api-Key': key, 'Content-Type': 'application/json',
                     'X-Goog-FieldMask': 'routes.duration,routes.legs.steps.transitDetails'},
            data=json.dumps(payload).encode())
        try:
            with urlopen(request, timeout=25) as response:
                data = json.load(response)
            if not data.get('routes'): raise RuntimeError('Maps authenticated but returned no transit route.')
            return {'http_status': 200, 'routes': len(data['routes']),
                    'duration': data['routes'][0].get('duration')}
        except HTTPError as error:
            data = json.loads(error.read())
            reasons = [detail.get('reason') for detail in data.get('error', {}).get('details', []) if detail.get('reason')]
            if error.code == 403 and attempt < 5 and any(reason in ('SERVICE_DISABLED', 'API_KEY_SERVICE_BLOCKED') for reason in reasons):
                print('Waiting for API/key configuration to propagate...', flush=True)
                time.sleep(5)
                continue
            raise RuntimeError('Maps HTTP '+str(error.code)+': '+', '.join(reasons or ['request rejected'])) from None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', help='Exact event project ID; inferred from its display name when omitted')
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    accounts = gcloud('auth', 'list')
    if not any(item.get('account') == ACCOUNT for item in accounts):
        raise RuntimeError('Sign in to '+ACCOUNT+' with gcloud first.')
    projects = gcloud('projects', 'list')
    matches = [project for project in projects if project.get('projectId') == args.project] if args.project else [
        project for project in projects if project.get('name', '').casefold() == PROJECT_NAME.casefold()]
    if len(matches) != 1:
        raise RuntimeError('Could not uniquely identify the event project. Supply --project with its exact project ID.')
    project = matches[0]['projectId']
    print('Event project:', project, flush=True)
    billing = gcloud('billing', 'projects', 'describe', project)
    if not billing.get('billingEnabled'):
        raise RuntimeError('The event project has no active billing. Ask the organizer to enable Maps billing/credits; no billing account was changed.')
    print('Project billing is enabled. Credit coverage must be verified in the sponsor console.', flush=True)
    if args.check_only: return
    gcloud('services', 'enable', 'routes.googleapis.com', 'apikeys.googleapis.com', '--project='+project)
    keys = gcloud('services', 'api-keys', 'list', '--project='+project)
    matches = [key for key in keys if key.get('displayName') == KEY_NAME]
    if len(matches) > 1: raise RuntimeError('Multiple keys share the SecondVision name; no key was modified.')
    if matches:
        resource = matches[0]['name']
        key = gcloud('services', 'api-keys', 'describe', resource)
        targets = key.get('restrictions', {}).get('apiTargets', [])
        if not targets or any(target.get('service') != 'routes.googleapis.com' for target in targets):
            raise RuntimeError('Existing named key is not restricted to Routes; refusing to repurpose it.')
    else:
        created = gcloud('services', 'api-keys', 'create', '--project='+project,
                         '--display-name='+KEY_NAME, '--api-target=service=routes.googleapis.com')
        resource = created.get('name', '')
        if '/keys/' not in resource: resource = created.get('response', {}).get('name', '')
        if '/keys/' not in resource: raise RuntimeError('Key creation returned no key resource name.')
    key = gcloud('services', 'api-keys', 'get-key-string', resource)['keyString']
    result = verify_route(key)
    save_key(Path(__file__).with_name('.env'), key, project)
    report = {'project': project, 'api': 'routes.googleapis.com', 'key_restricted_to_routes': True,
              'live_test': result, 'credit_deduction_verified': False}
    Path(__file__).with_name('maps-verification.json').write_text(json.dumps(report, indent=2)+'\n')
    print('Real transit request passed. Maps key saved privately; restart the backend to load it.')

if __name__ == '__main__':
    try: main()
    except (RuntimeError, subprocess.TimeoutExpired) as error:
        raise SystemExit(str(error))
