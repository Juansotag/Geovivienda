import os, sys, requests, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv; load_dotenv()
import db, traceback

# Test 1: obtener_perfil
print("=== Test obtener_perfil ===")
try:
    p = db.obtener_perfil()
    print("OK:", p)
except Exception:
    print("ERROR:")
    traceback.print_exc()

# Test 2: Hit the actual live server as a browser would
print("\n=== Test HTTP clientes?correo=... ===")
session = requests.Session()
# Hit login URL
r1 = session.get(
    "http://127.0.0.1:5000/clientes",
    params={"correo": "funcionario@casaencasa.com", "password": "12345"},
    timeout=10
)
print(f"GET /clientes?correo=...: {r1.status_code}")
print(f"Cookies: {dict(session.cookies)}")

# Test 3: Hit the resultados page WITH the session
print("\n=== Test HTTP /clientes/2/resultados?busqueda_id=3 WITH session ===")
r2 = session.get(
    "http://127.0.0.1:5000/clientes/2/resultados",
    params={"busqueda_id": 3},
    timeout=15
)
print(f"Status: {r2.status_code}")
if r2.status_code == 500:
    text = r2.text
    # Flask debug mode should show traceback
    for marker in ['Traceback', 'Error', 'jinja2', 'TemplateSyntaxError', 'UndefinedError']:
        idx = text.find(marker)
        if idx >= 0:
            print(f"\nFound '{marker}' at {idx}:")
            print(text[max(0,idx-100):idx+2000])
            break
    else:
        # Show middle of response
        mid = len(text) // 2
        print("Middle of response:")
        print(text[mid:mid+3000])
else:
    print("Page loaded OK!")
