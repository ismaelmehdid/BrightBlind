"""Generate private team deployment configuration. Does not deploy or contact teammates."""
import argparse
import getpass
import os
from pathlib import Path
import re
import secrets

parser = argparse.ArgumentParser()
parser.add_argument('--domain', required=True)
parser.add_argument('--email', required=True)
args = parser.parse_args()
if not re.fullmatch(r'[A-Za-z0-9.-]+', args.domain) or '.' not in args.domain:
    parser.error('Use a DNS hostname, without a scheme or path')
root = Path(__file__).parent
if (root/'.env').exists() or (root/'access.txt').exists():
    raise SystemExit('Private configuration already exists; it was not overwritten.')
settings = {'DOMAIN': args.domain, 'ADMIN_EMAIL': args.email, 'HOST': '0.0.0.0', 'PORT': '8765',
            'GEMINI_MODEL': 'gemini-4-hydrogen', 'GEMINI_THINKING_LEVEL': 'LOW', 'VOICE_TTS_PROVIDER': 'deepgram', 'DEEPGRAM_TTS_VOICE': 'flux-heather-en', 'LIVE_ONLY': '1'}
for key in ['DEEPGRAM_API_KEY', 'GEMINI_API_KEY', 'GOOGLE_MAPS_API_KEY']:
    value = getpass.getpass(key + ': ').strip()
    if not value: raise SystemExit('Deepgram, Gemini and Maps keys are required for the full team workflow. Nothing was written.')
    settings[key] = value
settings['BAND_RELAY_TOKEN'] = secrets.token_urlsafe(32)
settings['GLASSES_RELAY_TOKEN'] = secrets.token_urlsafe(32)
people = {name: secrets.token_urlsafe(32) for name in ['Andrii', 'Ismaël', 'Tarang']}
settings['DASHBOARD_TOKENS'] = ','.join(people.values())
if any(any(char in value for char in "\r\n'") for value in settings.values()):
    raise SystemExit('Unsupported characters in configuration.')
def private_write(path, content):
    fd = os.open(path, os.O_CREAT|os.O_EXCL|os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w') as stream: stream.write(content)
private_write(root/'.env', '\n'.join(key+"='"+value+"'" for key,value in settings.items())+'\n')
access = ['Dashboard: https://'+args.domain]
access += [name+' dashboard token: '+token for name,token in people.items()]
access += ['Band: wss://'+args.domain+'/ws?token='+settings['BAND_RELAY_TOKEN'],
           'Glasses: wss://'+args.domain+'/ws?token='+settings['GLASSES_RELAY_TOKEN']]
private_write(root/'access.txt', '\n'.join(access)+'\n')
print('Private configuration saved. Team access details are in backend/access.txt; do not commit or broadcast that file.')
