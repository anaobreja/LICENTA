import urllib.request, json, sys
sys.stdout.reconfigure(encoding='utf-8')

# First get a token
login_data = json.dumps({"email": "ana.obreja@lsacbucuresti.ro", "password": "parola"}).encode()
req = urllib.request.Request(
    'http://localhost:8000/auth/login',
    data=login_data,
    headers={'Content-Type': 'application/json'},
    method='POST'
)
try:
    with urllib.request.urlopen(req) as r:
        auth = json.loads(r.read())
        token = auth.get('access_token', '')
        print(f'Token ok: {bool(token)}')
except Exception as e:
    print(f'Login eroare: {e}')
    token = ''

if not token:
    print('Nu s-a putut autentifica')
    exit()

req2 = urllib.request.Request(
    'http://localhost:8000/map/stations',
    headers={'Authorization': f'Bearer {token}'}
)
with urllib.request.urlopen(req2) as r:
    data = json.loads(r.read())
    print(f'Statii returnate: {len(data)}')
    names = [s['name'] for s in data]
    print(f'Huedin prezent: {any("Huedin" in n for n in names)}')
    galati = [n for n in names if 'Gala' in n]
    print(f'Galati: {galati}')
    brasov = [n for n in names if 'Bra' in n and 'ov' in n]
    print(f'Brasov: {brasov[:3]}')
    cluj = [n for n in names if 'Cluj' in n]
    print(f'Cluj: {cluj[:3]}')
