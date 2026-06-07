import re
import secrets

from app import (
    app,
    decrypt_value,
    get_db_connection,
    init_schema,
    save_acueducto_user,
)


def csrf_from(html):
    match = re.search(r'name="_csrf_token" value="([^"]+)"', html)
    return match.group(1) if match else ""


init_schema()

connection = get_db_connection()
try:
    cursor = connection.cursor(dictionary=True)
    cursor.execute("SHOW COLUMNS FROM usuarios_sistema")
    user_columns = {row["Field"] for row in cursor.fetchall()}
    required_user_columns = {
        "failed_login_attempts",
        "locked_until",
        "session_version",
        "twofa_enabled",
        "twofa_secret_enc",
        "security_pin_hash",
    }
    print("user_security_columns", required_user_columns.issubset(user_columns))

    cursor.execute("SHOW TABLES LIKE 'auditoria_seguridad'")
    print("audit_table", cursor.fetchone() is not None)

    cursor.execute("SELECT password FROM usuarios_sistema WHERE email = 'admin@correo.com' LIMIT 1")
    admin = cursor.fetchone()
    print("admin_password_hashed", bool(admin and str(admin["password"]).startswith("scrypt:")))

    cursor.execute(
        """
        SELECT COUNT(*) AS total
        FROM usuarios_acueducto
        WHERE (cedula IS NOT NULL AND cedula <> '' AND cedula NOT LIKE 'enc:v2:%')
           OR (telefono IS NOT NULL AND telefono <> '' AND telefono NOT LIKE 'enc:v2:%')
           OR (email_servicio IS NOT NULL AND email_servicio <> '' AND email_servicio NOT LIKE 'enc:v2:%')
        """
    )
    print("existing_sensitive_plaintext", cursor.fetchone()["total"])
finally:
    connection.close()

client = app.test_client()
login_page = client.get("/login")
csrf = csrf_from(login_page.get_data(as_text=True))
print("csrf_present", bool(csrf))

login_response = client.post(
    "/login",
    data={"_csrf_token": csrf, "email": "admin@correo.com", "password": "admin123"},
    follow_redirects=False,
)
print("admin_login_status", login_response.status_code)

code = "TEST-" + secrets.token_hex(3).upper()
save_acueducto_user(
    {
        "codigo_recibo": code,
        "nombres": "Cliente Prueba",
        "apellidos": "Seguridad",
        "direccion": "Direccion Prueba",
        "cedula": "123456789",
        "telefono": "3001234567",
        "email_servicio": "seguridad@example.com",
    }
)

connection = get_db_connection()
try:
    cursor = connection.cursor(dictionary=True)
    cursor.execute("SELECT id, cedula, telefono, email_servicio FROM usuarios_acueducto WHERE codigo_recibo = %s", (code,))
    row = cursor.fetchone()
    encrypted = all(str(row[field]).startswith("enc:v2:") for field in ("cedula", "telefono", "email_servicio"))
    roundtrip = decrypt_value(row["cedula"]) == "123456789"
    print("client_fields_encrypted", encrypted)
    print("client_decrypt_roundtrip", roundtrip)
    cursor.execute("DELETE FROM usuarios_acueducto WHERE id = %s", (row["id"],))
    connection.commit()
finally:
    connection.close()
