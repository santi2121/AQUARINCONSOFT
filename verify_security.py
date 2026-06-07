from app import app

routes = sorted(str(rule) for rule in app.url_map.iter_rules())
print("routes", len(routes))
for route in routes:
    if "perfil" in route or "seguridad" in route or "login" in route:
        print(route)

client = app.test_client()
login_page = client.get("/login")
print("login", login_page.status_code, b"_csrf_token" in login_page.data)
csrf_response = client.post("/register", data={"nombres": "A", "email": "a@b.co", "password": "weak"})
print("csrf_block", csrf_response.status_code)
