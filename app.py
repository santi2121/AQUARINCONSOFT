"""
Backend Flask para AquaRincon.
Ejecutar: python app.py
"""

import hashlib
import io
import json
import logging
import os
import re
import secrets
import time
import unicodedata
from datetime import date, datetime, timedelta
from functools import wraps
from logging.handlers import RotatingFileHandler
from urllib.parse import urlparse

from dotenv import load_dotenv
load_dotenv()

from flask import (
    Flask,
    Response,
    flash,
    has_request_context,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    send_file,
    stream_with_context,
    url_for,
)
from flask_bcrypt import Bcrypt
from flask_mail import Mail, Message
from flask_wtf.csrf import CSRFError, CSRFProtect, generate_csrf
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "aquarincon-dev-secret")
app.config.update(
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=int(os.getenv("SESSION_MINUTES", "30"))),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "0") == "1",
    SESSION_REFRESH_EACH_REQUEST=True,
    MAX_CONTENT_LENGTH=8 * 1024 * 1024,
    WTF_CSRF_FIELD_NAME="_csrf_token",
    WTF_CSRF_TIME_LIMIT=int(os.getenv("CSRF_TIME_LIMIT_SECONDS", "3600")),
    WTF_CSRF_SSL_STRICT=os.getenv("WTF_CSRF_SSL_STRICT", "1") == "1",
    WTF_CSRF_CHECK_DEFAULT=False,
)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
os.makedirs("logs", exist_ok=True)
security_log_handler = RotatingFileHandler(
    os.getenv("SECURITY_LOG_FILE", os.path.join("logs", "security.log")),
    maxBytes=1024 * 1024,
    backupCount=5,
    encoding="utf-8",
)
security_log_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
app.logger.addHandler(security_log_handler)

app.config.update(
    MAIL_SERVER=os.getenv("MAIL_SERVER", "smtp.protonmail.ch"),
    MAIL_PORT=int(os.getenv("MAIL_PORT", "587")),
    MAIL_USE_TLS=os.getenv("MAIL_USE_TLS", "1") == "1",
    MAIL_USERNAME=os.getenv("MAIL_USERNAME", ""),
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD", ""),
    MAIL_DEFAULT_SENDER=os.getenv("MAIL_DEFAULT_SENDER", os.getenv("MAIL_USERNAME", "no-reply@aquarincon.local")),
)
mail = Mail(app)
bcrypt = Bcrypt(app)
csrf = CSRFProtect(app)

TARIFA_MENSUAL = 20000
MODEL_NAME = "Meta-Llama-3-8B-Instruct.Q4_0.gguf"
CHAT_MAX_TOKENS = int(os.getenv("CHAT_MAX_TOKENS", "180"))
CHAT_CACHE_TTL = int(os.getenv("CHAT_CACHE_TTL", "3600"))
LOGIN_MAX_ATTEMPTS = int(os.getenv("LOGIN_MAX_ATTEMPTS", "5"))
LOGIN_LOCK_MINUTES = int(os.getenv("LOGIN_LOCK_MINUTES", "15"))
EMAIL_OTP_GRACE_SECONDS = int(os.getenv("EMAIL_OTP_GRACE_SECONDS", "300"))
EMAIL_OTP_EXPIRES_MINUTES = int(os.getenv("EMAIL_OTP_EXPIRES_MINUTES", "5"))
EMAIL_OTP_MAX_ATTEMPTS = int(os.getenv("EMAIL_OTP_MAX_ATTEMPTS", "5"))
EMAIL_OTP_LOCK_MINUTES = int(os.getenv("EMAIL_OTP_LOCK_MINUTES", "15"))
OTP_LENGTH = 6
model = None
chat_cache = {}
rate_limits = {}
last_billing_attempt = None
schema_ready = set()
table_columns_cache = {}
audit_table_ready = False
UPLOAD_FOLDER = os.path.join(app.static_folder, "uploads")
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}
SENSITIVE_ADMIN_ENDPOINTS = {
    "admin_eliminar_usuario_sistema",
    "admin_eliminar_usuario_acueducto",
    "admin_generar_facturacion",
    "admin_verificar_pago",
    "admin_rechazar_pago",
    "admin_conceder_permiso_pago",
    "admin_marcar_factura_pagada",
    "admin_eliminar_punto_pago",
    "admin_eliminar_noticia",
}
CSRF_EXEMPT_ENDPOINTS = {"chat", "chat_stream"}
AUDIT_VIEW_ENDPOINTS = {"static", "chat", "chat_stream"}
EXPLICIT_ACTIVITY_ENDPOINTS = {
    "descargar_factura_pdf",
    "descargar_factura_pdf_publico",
    "descargar_paz_y_salvo",
    "descargar_archivo_recuperacion",
    "usuario_crear_pqrs",
    "pagar",
    "actualizar_perfil",
    "cambiar_contrasena",
}
ACTIVITY_EVENT_LABELS = {
    "user_activity": "Actividad",
    "invoice_pdf_downloaded": "Descarga factura PDF",
    "public_invoice_pdf_downloaded": "Descarga factura publica",
    "paz_y_salvo_downloaded": "Descarga paz y salvo",
    "recovery_file_downloaded": "Descarga recuperacion",
    "payment_report_created": "Reporte de pago",
    "pqrs_created": "PQRS creada",
    "profile_updated": "Perfil actualizado",
    "password_changed": "Contrasena cambiada",
    "login_success": "Inicio de sesion",
    "logout": "Cierre de sesion",
    "sensitive_admin_action": "Accion admin sensible",
}
ENDPOINT_ACTION_LABELS = {
    "dashboard_usuario": "Abrio el dashboard de usuario",
    "dashboard_admin": "Abrio el dashboard de administrador",
    "consultar_facturas_publicas": "Consulto facturas publicas",
    "pagar": "Consulto o reporto pago",
    "descargar_factura_pdf": "Descargo factura PDF",
    "descargar_factura_pdf_publico": "Descargo factura PDF publica",
    "descargar_paz_y_salvo": "Descargo paz y salvo",
    "descargar_archivo_recuperacion": "Descargo archivo de recuperacion",
    "usuario_crear_pqrs": "Radico una PQRS",
    "actualizar_perfil": "Actualizo su perfil",
    "cambiar_contrasena": "Cambio su contrasena",
    "admin_generar_facturacion": "Genero facturacion mensual",
    "admin_marcar_factura_pagada": "Marco factura como pagada",
    "admin_verificar_pago": "Verifico un reporte de pago",
    "admin_rechazar_pago": "Rechazo un reporte de pago",
    "admin_conceder_permiso_pago": "Concedio permiso de pago",
    "admin_crear_usuario_sistema": "Creo usuario del sistema",
    "admin_editar_usuario_sistema": "Edito usuario del sistema",
    "admin_eliminar_usuario_sistema": "Elimino usuario del sistema",
    "admin_crear_usuario_acueducto": "Creo cliente del acueducto",
    "admin_editar_usuario_acueducto": "Edito cliente del acueducto",
    "admin_eliminar_usuario_acueducto": "Elimino cliente del acueducto",
    "admin_responder_pqrs": "Respondio una PQRS",
    "admin_marcar_contacto_leido": "Marco mensaje como leido",
    "admin_crear_punto_pago": "Creo punto de pago",
    "admin_editar_punto_pago": "Edito punto de pago",
    "admin_eliminar_punto_pago": "Elimino punto de pago",
    "admin_crear_noticia": "Creo noticia",
    "admin_editar_noticia": "Edito noticia",
    "admin_eliminar_noticia": "Elimino noticia",
}

DB_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "localhost"),
    "port": int(os.getenv("MYSQL_PORT", "3306")),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", ""),
    "database": os.getenv("MYSQL_DB", "ACUEDUCTO"),
}


def scrypt_digest(value, salt=None, length=32):
    salt = salt or app.secret_key.encode("utf-8")
    return hashlib.scrypt(str(value).encode("utf-8"), salt=salt, n=16384, r=8, p=1, maxmem=64 * 1024 * 1024, dklen=length)


def hash_secret(value):
    return bcrypt.generate_password_hash(value).decode("utf-8")


def _encryption_key():
    raw = os.getenv("DATA_ENCRYPTION_KEY", "").strip()
    if raw:
        try:
            key = bytes.fromhex(raw)
            if len(key) == 32:
                return key
        except Exception:
            pass
        return scrypt_digest(raw, salt=b"AquaRincon AES-GCM key")
    app.logger.warning("DATA_ENCRYPTION_KEY no esta configurada; se deriva una llave de FLASK_SECRET_KEY solo para desarrollo.")
    return scrypt_digest(app.secret_key, salt=b"AquaRincon development key")


def encrypt_value(value):
    if value is None or value == "":
        return value
    value = str(value)
    if value.startswith("enc:v2:"):
        return value
    nonce = secrets.token_bytes(12)
    encrypted = AESGCM(_encryption_key()).encrypt(nonce, value.encode("utf-8"), None)
    return "enc:v2:" + (nonce + encrypted).hex()


def decrypt_value(value):
    if not value or not str(value).startswith("enc:v2:"):
        return value
    try:
        raw = bytes.fromhex(str(value)[7:])
        return AESGCM(_encryption_key()).decrypt(raw[:12], raw[12:], None).decode("utf-8")
    except Exception:
        return ""


def normalize_email(email):
    return (email or "").strip().lower()


def refresh_mail_config_from_env():
    load_dotenv(override=True)
    app.config.update(
        MAIL_SERVER=os.getenv("MAIL_SERVER", "smtp.protonmail.ch"),
        MAIL_PORT=int(os.getenv("MAIL_PORT", "587")),
        MAIL_USE_TLS=os.getenv("MAIL_USE_TLS", "1") == "1",
        MAIL_USERNAME=os.getenv("MAIL_USERNAME", ""),
        MAIL_PASSWORD=os.getenv("MAIL_PASSWORD", ""),
        MAIL_DEFAULT_SENDER=os.getenv(
            "MAIL_DEFAULT_SENDER",
            os.getenv("MAIL_USERNAME", "no-reply@aquarincon.local"),
        ),
    )


def client_ip():
    if not has_request_context():
        return "system"
    forwarded = request.headers.get("X-Forwarded-For", "")
    return (forwarded.split(",", 1)[0].strip() or request.remote_addr or "unknown")[:45]


def user_agent_hash():
    if not has_request_context():
        return scrypt_digest("system", salt=b"AquaRincon user-agent").hex()
    return scrypt_digest(request.headers.get("User-Agent", "") or "", salt=b"AquaRincon user-agent").hex()


def rate_limit(bucket, limit, window_seconds):
    now = time.time()
    key = f"{bucket}:{client_ip()}"
    attempts = [item for item in rate_limits.get(key, []) if now - item < window_seconds]
    if len(attempts) >= limit:
        rate_limits[key] = attempts
        return False
    attempts.append(now)
    rate_limits[key] = attempts
    return True


def valid_email(email):
    return bool(re.fullmatch(r"[^@\s]{3,120}@[^@\s]{2,120}\.[^@\s]{2,20}", email or ""))


def validate_password_policy(password):
    errors = []
    if len(password or "") < 10:
        errors.append("minimo 10 caracteres")
    if not re.search(r"[A-Z]", password or ""):
        errors.append("una mayuscula")
    if not re.search(r"[a-z]", password or ""):
        errors.append("una minuscula")
    if not re.search(r"\d", password or ""):
        errors.append("un numero")
    if not re.search(r"[^A-Za-z0-9]", password or ""):
        errors.append("un simbolo")
    if re.search(r"(.)\1{3,}", password or ""):
        errors.append("sin repeticiones obvias")
    return errors


def csrf_token():
    return generate_csrf()


app.jinja_env.globals["csrf_token"] = csrf_token


def verify_csrf():
    if request.method in ("GET", "HEAD", "OPTIONS") or request.endpoint in CSRF_EXEMPT_ENDPOINTS:
        return True
    try:
        csrf.protect()
        return True
    except CSRFError as exc:
        app.logger.warning("CSRF rechazado endpoint=%s ip=%s motivo=%s", request.endpoint, client_ip(), exc.description)
        return False


def inject_csrf(response):
    if response.content_type and response.content_type.startswith("text/html"):
        html = response.get_data(as_text=True)
        token_input = f'<input type="hidden" name="_csrf_token" value="{csrf_token()}">'
        html = re.sub(
            r"(<form\b(?=[^>]*\bmethod=[\"']?POST[\"']?)[^>]*>)",
            lambda match: match.group(1) + token_input,
            html,
            flags=re.IGNORECASE,
        )
        response.set_data(html)
    return response

SYSTEM_PROMPT = """Eres el asistente virtual del Acueducto Comunitario Rincon Santo.
Respondes siempre en espanol, con claridad y amabilidad.
Da respuestas breves, utiles y directas. Si no sabes un dato exacto, orienta al usuario
para consultar su factura, el panel o el formulario de contacto del sitio.
"""


def get_model():
    global model
    if model is None:
        from gpt4all import GPT4All

        model = GPT4All(MODEL_NAME)
    return model


def normalize_chat_text(text):
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def quick_chat_reply(message):
    text = normalize_chat_text(message)
    if not text:
        return None, "invalid"

    if re.search(r"\b(hola|buenos dias|buenas tardes|buenas noches|saludos)\b", text):
        return "Hola, soy Gotica. Te puedo ayudar con facturas, pagos, acuerdos de pago, PQRS y paz y salvo. Cuentame que necesitas."

    if any(word in text for word in ("factura", "recibo", "deuda", "saldo", "consultar")):
        return (
            "Para consultar tu factura, entra a Consultar facturas o al panel de usuario, "
            "escribe tu codigo de recibo y revisa tus facturas pendientes. Tambien puedes descargar el PDF si la factura aparece disponible."
        )

    if any(word in text for word in ("pagar", "pago", "cancelar", "abonar")):
        return (
            "Para pagar, consulta primero tu factura con el codigo de recibo. Luego usa la opcion Pagar, selecciona los meses pendientes "
            "y registra el metodo o referencia de pago para generar el reporte."
        )

    if "acuerdo" in text or "convenio" in text:
        return (
            "Para un acuerdo de pago, inicia sesion y solicita el acuerdo desde tu panel. Si no puedes ingresar, envia un mensaje de contacto "
            "con tu codigo de recibo para que administracion revise tu caso."
        )

    if any(word in text for word in ("pqrs", "peticion", "queja", "reclamo", "solicitud", "contacto")):
        return (
            "Puedes enviar una PQRS desde el formulario de contacto de la pagina principal. Escribe tu nombre, correo, codigo de recibo si lo tienes, "
            "asunto y descripcion de la solicitud."
        )

    if any(word in text for word in ("horario", "atienden", "atencion", "oficina")):
        return (
            "Los horarios pueden variar. Te recomiendo verificar la informacion publicada en la pagina principal o enviar un mensaje de contacto "
            "para confirmar atencion antes de desplazarte."
        )

    if "paz" in text and "salvo" in text:
        return (
            "El paz y salvo se puede generar cuando no tienes facturas pendientes. Ingresa al panel de usuario y usa la opcion de paz y salvo si tu cuenta esta al dia."
        )

    if any(word in text for word in ("tarifa", "cuanto vale", "valor", "costo")):
        return f"La tarifa mensual registrada en el sistema es de {money(TARIFA_MENSUAL)}. Para ver valores exactos pendientes, consulta tu factura con el codigo de recibo."

    return None


def get_cached_chat_reply(message):
    key = normalize_chat_text(message)
    if not key:
        return None
    cached = chat_cache.get(key)
    if cached and time.time() - cached["created_at"] < CHAT_CACHE_TTL:
        return cached["reply"]
    chat_cache.pop(key, None)
    return None


def set_cached_chat_reply(message, reply):
    key = normalize_chat_text(message)
    if key and reply:
        chat_cache[key] = {"reply": reply, "created_at": time.time()}


def get_db_connection():
    import mysql.connector

    return mysql.connector.connect(**DB_CONFIG)


@app.before_request
def apply_request_security():
    session.permanent = True
    if request.endpoint == "static":
        return None
    if not rate_limit("global", 240, 60):
        return "Demasiadas solicitudes. Intenta nuevamente en un minuto.", 429
    if not verify_csrf():
        audit_event("csrf_rejected", success=False, details={"endpoint": request.endpoint})
        return "Solicitud rechazada por proteccion CSRF.", 400
    if session.get("user_id") and session.get("ua_hash") and session["ua_hash"] != user_agent_hash():
        audit_event("session_device_changed", user_id=session.get("user_id"), success=False)
        session.clear()
        flash("Sesion cerrada por cambio de dispositivo detectado.", "warning")
        return redirect(url_for("login"))
    if request.endpoint in SENSITIVE_ADMIN_ENDPOINTS and session.get("role") == "admin":
        if not is_email_otp_recent():
            flash("Verifica tu identidad con el codigo enviado a tu correo.", "warning")
            return redirect(url_for("verify_email_otp", next=request.endpoint))
        audit_event("sensitive_admin_action", user_id=session.get("user_id"), details=activity_details())
    if should_log_user_activity():
        log_user_activity()
    return None


@app.after_request
def apply_response_security(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(self), camera=(), microphone=()")
    response.headers.setdefault("Cache-Control", "no-store" if session.get("user_id") else "no-cache")
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://maps.googleapis.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: https:; "
        "connect-src 'self' https://maps.googleapis.com; "
        "frame-ancestors 'none'"
    )
    response.headers.setdefault("Content-Security-Policy", csp)
    return inject_csrf(response)


def money(value):
    return f"$ {int(float(value or 0)):,}".replace(",", ".")


app.jinja_env.filters["money"] = money


def table_columns(cursor, table_name):
    cached = table_columns_cache.get(table_name)
    if cached is not None:
        return cached
    cursor.execute(f"SHOW COLUMNS FROM `{table_name}`")
    rows = cursor.fetchall()
    columns = [row["Field"] if isinstance(row, dict) else row[0] for row in rows]
    table_columns_cache[table_name] = columns
    return columns


def invalidate_table_columns(table_name):
    table_columns_cache.pop(table_name, None)


def column_exists(cursor, table_name, column):
    try:
        return column.lower() in {c.lower() for c in table_columns(cursor, table_name)}
    except Exception:
        return False


def password_matches(raw_password, stored_password):
    if not stored_password:
        return False
    stored_password = str(stored_password)
    if stored_password.startswith(("$2a$", "$2b$", "$2y$")):
        return bcrypt.check_password_hash(stored_password, raw_password)
    try:
        if check_password_hash(stored_password, raw_password):
            return True
    except ValueError:
        pass
    return False


def is_password_hash(value):
    value = str(value or "")
    return value.startswith(("scrypt:", "pbkdf2:", "$2a$", "$2b$", "$2y$"))


def sanitize_audit_details(details):
    safe = {}
    for key, value in (details or {}).items():
        if re.search(r"password|token|secret|pin|codigo|code", str(key), re.I):
            safe[key] = "[redacted]"
        else:
            safe[key] = str(value)[:300]
    return safe


def safe_request_args():
    safe = {}
    for key, value in request.values.items():
        if re.search(r"password|token|secret|pin|codigo|code|csrf", key, re.I):
            safe[key] = "[redacted]"
        else:
            safe[key] = str(value)[:120]
    return safe


def current_route_rule():
    return str(request.url_rule) if has_request_context() and request.url_rule else request.path


def activity_details(extra=None):
    details = {
        "action": ENDPOINT_ACTION_LABELS.get(request.endpoint, request.endpoint or "ruta_desconocida"),
        "endpoint": request.endpoint or "",
        "method": request.method,
        "path": request.path,
        "route": current_route_rule(),
        "query_params": json.dumps(safe_request_args(), ensure_ascii=True),
        "user_agent": (request.headers.get("User-Agent") or "")[:180],
    }
    if extra:
        details.update(extra)
    return details


def should_log_user_activity():
    if not has_request_context() or not session.get("user_id"):
        return False
    if request.endpoint in AUDIT_VIEW_ENDPOINTS or request.endpoint is None:
        return False
    if request.endpoint in EXPLICIT_ACTIVITY_ENDPOINTS:
        return False
    if request.endpoint in SENSITIVE_ADMIN_ENDPOINTS:
        return False
    if request.method != "GET" and not request.endpoint:
        return False
    return request.method in ("GET", "POST")


def log_user_activity(event_type="user_activity", extra=None, success=True):
    if has_request_context() and session.get("user_id"):
        audit_event(event_type, user_id=session.get("user_id"), success=success, details=activity_details(extra))


def audit_event(event_type, user_id=None, success=True, details=None):
    global audit_table_ready
    safe_details = sanitize_audit_details(details)
    app.logger.info(
        "security_event event=%s success=%s user_id=%s ip=%s details=%s",
        event_type,
        bool(success),
        user_id or (session.get("user_id") if has_request_context() else None),
        client_ip(),
        json.dumps(safe_details, ensure_ascii=True) if safe_details else "{}",
    )
    try:
        resolved_user_id = user_id or (session.get("user_id") if has_request_context() else None)
        connection = get_db_connection()
        try:
            cursor = connection.cursor()
            if not audit_table_ready:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS auditoria_seguridad (
                      id_auditoria INT AUTO_INCREMENT PRIMARY KEY,
                      id_usuario_sistema INT NULL,
                      evento VARCHAR(80) NOT NULL,
                      exito TINYINT(1) NOT NULL DEFAULT 1,
                      ip VARCHAR(45) NULL,
                      user_agent_hash CHAR(64) NULL,
                      detalle JSON NULL,
                      fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                      INDEX idx_auditoria_evento (evento),
                      INDEX idx_auditoria_usuario (id_usuario_sistema),
                      INDEX idx_auditoria_fecha (fecha_creacion)
                    ) ENGINE=InnoDB
                    """
                )
                audit_table_ready = True
            cursor.execute(
                """
                INSERT INTO auditoria_seguridad
                  (id_usuario_sistema, evento, exito, ip, user_agent_hash, detalle)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    resolved_user_id,
                    event_type[:80],
                    1 if success else 0,
                    client_ip(),
                    user_agent_hash(),
                    json.dumps(safe_details, ensure_ascii=True) if details else None,
                ),
            )
            connection.commit()
        finally:
            connection.close()
    except Exception as exc:
        app.logger.warning("No fue posible registrar auditoria %s: %s", event_type, exc)


def is_email_otp_recent():
    return time.time() - float(session.get("email_otp_verified_at", 0)) <= EMAIL_OTP_GRACE_SECONDS


def current_period():
    return date.today().strftime("%Y-%m")


def next_due_date():
    today = date.today()
    return date(today.year, today.month, 28)


def current_user_name():
    return session.get("user_name") or session.get("user_login") or "Usuario"


def google_maps_api_key():
    return os.getenv("GOOGLE_MAPS_API_KEY", "")


def ensure_system_schema(cursor):
    if "system" in schema_ready:
        return
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS usuarios_sistema (
          id INT AUTO_INCREMENT PRIMARY KEY,
          nombres VARCHAR(120) NOT NULL,
          apellidos VARCHAR(120) NOT NULL DEFAULT '',
          telefono VARCHAR(20) NULL,
          email VARCHAR(120) NOT NULL UNIQUE,
          password VARCHAR(255) NOT NULL,
          rol ENUM('admin', 'usuario') NOT NULL DEFAULT 'usuario',
          codigo_recibo_vinculado VARCHAR(30) NULL,
          fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          INDEX idx_usuarios_sistema_rol (rol),
          INDEX idx_usuarios_sistema_codigo (codigo_recibo_vinculado)
        ) ENGINE=InnoDB
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS usuarios_acueducto (
          id INT AUTO_INCREMENT PRIMARY KEY,
          codigo_recibo VARCHAR(30) NOT NULL UNIQUE,
          nombres VARCHAR(160) NOT NULL,
          apellidos VARCHAR(160) NOT NULL DEFAULT '',
          direccion VARCHAR(180) NOT NULL,
          cedula VARCHAR(30) NULL,
          telefono VARCHAR(30) NULL,
          email_servicio VARCHAR(120) NULL,
          estado ENUM('activo', 'inactivo', 'suspendido') NOT NULL DEFAULT 'activo',
          fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB
        """
    )
    cursor.execute("ALTER TABLE usuarios_acueducto MODIFY cedula TEXT NULL")
    cursor.execute("ALTER TABLE usuarios_acueducto MODIFY telefono TEXT NULL")
    cursor.execute("ALTER TABLE usuarios_acueducto MODIFY email_servicio TEXT NULL")
    if column_exists(cursor, "usuarios_acueducto", "nombre_completo") and not column_exists(cursor, "usuarios_acueducto", "nombres"):
        cursor.execute("ALTER TABLE usuarios_acueducto CHANGE COLUMN nombre_completo nombres VARCHAR(160) NOT NULL")
        cursor.execute("ALTER TABLE usuarios_acueducto ADD COLUMN apellidos VARCHAR(160) NOT NULL DEFAULT ''")
    if not column_exists(cursor, "usuarios_acueducto", "ubicacion_maps"):
        cursor.execute("ALTER TABLE usuarios_acueducto ADD COLUMN ubicacion_maps TEXT NULL")
    cursor.execute("SELECT id, cedula, telefono, email_servicio FROM usuarios_acueducto")
    for client in cursor.fetchall():
        client_id = client["id"] if isinstance(client, dict) else client[0]
        values = {
            "cedula": client["cedula"] if isinstance(client, dict) else client[1],
            "telefono": client["telefono"] if isinstance(client, dict) else client[2],
            "email_servicio": client["email_servicio"] if isinstance(client, dict) else client[3],
        }
        encrypted_values = {
            field: encrypt_value(value)
            for field, value in values.items()
            if not str(value or "").startswith("enc:v2:")
        }
        encrypted_values = {**values, **encrypted_values}
        if encrypted_values != values:
            cursor.execute(
                """
                UPDATE usuarios_acueducto
                SET cedula = %s, telefono = %s, email_servicio = %s
                WHERE id = %s
                """,
                (
                    encrypted_values["cedula"],
                    encrypted_values["telefono"],
                    encrypted_values["email_servicio"],
                    client_id,
                ),
            )
    for column, sql in [
        ("failed_login_attempts", "ALTER TABLE usuarios_sistema ADD COLUMN failed_login_attempts INT NOT NULL DEFAULT 0"),
        ("locked_until", "ALTER TABLE usuarios_sistema ADD COLUMN locked_until DATETIME NULL"),
        ("last_login_at", "ALTER TABLE usuarios_sistema ADD COLUMN last_login_at DATETIME NULL"),
        ("last_login_ip", "ALTER TABLE usuarios_sistema ADD COLUMN last_login_ip VARCHAR(45) NULL"),
        ("password_changed_at", "ALTER TABLE usuarios_sistema ADD COLUMN password_changed_at DATETIME NULL"),
        ("session_version", "ALTER TABLE usuarios_sistema ADD COLUMN session_version INT NOT NULL DEFAULT 0"),
        ("apellidos", "ALTER TABLE usuarios_sistema ADD COLUMN apellidos VARCHAR(120) NOT NULL DEFAULT ''"),
        ("telefono", "ALTER TABLE usuarios_sistema ADD COLUMN telefono VARCHAR(20) NULL"),
        ("cedula", "ALTER TABLE usuarios_sistema ADD COLUMN cedula VARCHAR(20) NULL"),
        ("data_consent", "ALTER TABLE usuarios_sistema ADD COLUMN data_consent TINYINT(1) NOT NULL DEFAULT 0"),
        ("data_consent_at", "ALTER TABLE usuarios_sistema ADD COLUMN data_consent_at DATETIME NULL"),
    ]:
        if not column_exists(cursor, "usuarios_sistema", column):
            cursor.execute(sql)

    if column_exists(cursor, "usuarios_sistema", "nombre") and not column_exists(cursor, "usuarios_sistema", "nombres"):
        cursor.execute("ALTER TABLE usuarios_sistema CHANGE COLUMN nombre nombres VARCHAR(120) NOT NULL")

    cursor.execute(
        """
        INSERT INTO usuarios_sistema (nombres, apellidos, email, password, rol)
        SELECT 'Administrador', 'Demo', 'admin@correo.com', %s, 'admin'
        WHERE NOT EXISTS (SELECT 1 FROM usuarios_sistema WHERE email = 'admin@correo.com')
        """,
        (hash_secret("Admin123!Demo"),),
    )
    cursor.execute(
        """
        INSERT INTO usuarios_sistema (nombres, apellidos, email, password, rol, codigo_recibo_vinculado)
        SELECT 'Usuario', 'Demo', 'usuario@correo.com', %s, 'usuario', 'RS-0001'
        WHERE NOT EXISTS (SELECT 1 FROM usuarios_sistema WHERE email = 'usuario@correo.com')
        """,
        (hash_secret("Usuario123!Demo"),),
    )
    cursor.execute(
        """
        INSERT INTO usuarios_acueducto (codigo_recibo, nombres, apellidos, direccion, cedula, telefono, email_servicio)
        SELECT 'RS-0001', 'Usuario', 'Demo', 'Vereda Rincon Santo', '1000000001', '3000000000', 'usuario@correo.com'
        WHERE NOT EXISTS (SELECT 1 FROM usuarios_acueducto WHERE codigo_recibo = 'RS-0001')
        """
    )
    cursor.execute("SELECT id, password FROM usuarios_sistema")
    for account in cursor.fetchall():
        password_value = account["password"] if isinstance(account, dict) else account[1]
        account_id = account["id"] if isinstance(account, dict) else account[0]
        if not is_password_hash(password_value):
            cursor.execute(
                "UPDATE usuarios_sistema SET password = %s, password_changed_at = COALESCE(password_changed_at, NOW()) WHERE id = %s",
                (hash_secret(str(password_value)), account_id),
            )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS auditoria_seguridad (
          id_auditoria INT AUTO_INCREMENT PRIMARY KEY,
          id_usuario_sistema INT NULL,
          evento VARCHAR(80) NOT NULL,
          exito TINYINT(1) NOT NULL DEFAULT 1,
          ip VARCHAR(45) NULL,
          user_agent_hash CHAR(64) NULL,
          detalle JSON NULL,
          fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          INDEX idx_auditoria_evento (evento),
          INDEX idx_auditoria_usuario (id_usuario_sistema),
          INDEX idx_auditoria_fecha (fecha_creacion)
        ) ENGINE=InnoDB
        """
    )
    schema_ready.add("system")


def ensure_billing_schema(cursor):
    if "billing" in schema_ready:
        return
    ensure_system_schema(cursor)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS facturas (
          id_factura INT AUTO_INCREMENT PRIMARY KEY,
          id_acueducto INT NULL,
          codigo_recibo VARCHAR(30) NULL,
          periodo VARCHAR(20) NOT NULL,
          valor_total DECIMAL(12,2) NOT NULL DEFAULT 0,
          fecha_emision DATE NOT NULL,
          fecha_vencimiento DATE NOT NULL,
          estado ENUM('pendiente', 'pagada', 'vencida', 'anulada') NOT NULL DEFAULT 'pendiente',
          fecha_pago DATETIME NULL,
          id_reporte_pago INT NULL,
          INDEX idx_facturas_acueducto_estado (id_acueducto, estado),
          INDEX idx_facturas_codigo (codigo_recibo),
          INDEX idx_facturas_periodo (periodo)
        ) ENGINE=InnoDB
        """
    )
    for column, sql in [
        ("id_acueducto", "ALTER TABLE facturas ADD COLUMN id_acueducto INT NULL"),
        ("codigo_recibo", "ALTER TABLE facturas ADD COLUMN codigo_recibo VARCHAR(30) NULL"),
        ("fecha_pago", "ALTER TABLE facturas ADD COLUMN fecha_pago DATETIME NULL"),
        ("id_reporte_pago", "ALTER TABLE facturas ADD COLUMN id_reporte_pago INT NULL"),
    ]:
        if not column_exists(cursor, "facturas", column):
            cursor.execute(sql)

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS reportes_pago (
          id_reporte INT AUTO_INCREMENT PRIMARY KEY,
          id_acueducto INT NOT NULL,
          codigo_recibo VARCHAR(30) NOT NULL,
          id_usuario_sistema INT NULL,
          meses_pagados INT NOT NULL,
          valor_reportado DECIMAL(12,2) NOT NULL,
          metodo_pago ENUM('digital', 'fisico') NOT NULL,
          referencia VARCHAR(120) NULL,
          estado ENUM('pendiente', 'verificado', 'rechazado') NOT NULL DEFAULT 'pendiente',
          observacion TEXT NULL,
          fecha_reporte TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          fecha_revision DATETIME NULL,
          revisado_por INT NULL,
          INDEX idx_reportes_pago_estado (estado),
          INDEX idx_reportes_pago_acueducto (id_acueducto)
        ) ENGINE=InnoDB
        """
    )
    if not column_exists(cursor, "reportes_pago", "id_acueducto"):
        cursor.execute("ALTER TABLE reportes_pago ADD COLUMN id_acueducto INT NULL")
    if not column_exists(cursor, "reportes_pago", "id_usuario_sistema"):
        cursor.execute("ALTER TABLE reportes_pago ADD COLUMN id_usuario_sistema INT NULL")
    if not column_exists(cursor, "reportes_pago", "comprobante"):
        cursor.execute("ALTER TABLE reportes_pago ADD COLUMN comprobante LONGBLOB NULL")
    else:
        # Migrate from VARCHAR to LONGBLOB if needed
        cursor.execute("SELECT DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='reportes_pago' AND COLUMN_NAME='comprobante' AND TABLE_SCHEMA=DATABASE()")
        row = cursor.fetchone()
        if row:
            dtype = (row.get("DATA_TYPE") or row[0] or "").upper() if isinstance(row, dict) else (row[0] or "").upper()
            if dtype in ("VARCHAR", "CHAR", "TEXT"):
                cursor.execute("ALTER TABLE reportes_pago MODIFY COLUMN comprobante LONGBLOB NULL")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS permisos_pago (
          id_permiso INT AUTO_INCREMENT PRIMARY KEY,
          id_acueducto INT NOT NULL,
          estado ENUM('activo', 'usado', 'cancelado') NOT NULL DEFAULT 'activo',
          meses_minimos INT NOT NULL DEFAULT 3,
          observacion TEXT NULL,
          concedido_por INT NULL,
          fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          fecha_uso DATETIME NULL,
          INDEX idx_permisos_acueducto_estado (id_acueducto, estado)
        ) ENGINE=InnoDB
        """
    )
    if not column_exists(cursor, "permisos_pago", "id_acueducto"):
        cursor.execute("ALTER TABLE permisos_pago ADD COLUMN id_acueducto INT NULL")
    if not column_exists(cursor, "permisos_pago", "meses_minimos"):
        cursor.execute("ALTER TABLE permisos_pago ADD COLUMN meses_minimos INT NOT NULL DEFAULT 3")
    if not column_exists(cursor, "permisos_pago", "fecha_uso"):
        cursor.execute("ALTER TABLE permisos_pago ADD COLUMN fecha_uso DATETIME NULL")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS envios_facturacion (
          id_envio INT AUTO_INCREMENT PRIMARY KEY,
          id_factura INT NOT NULL,
          id_acueducto INT NOT NULL,
          email VARCHAR(120) NOT NULL,
          estado ENUM('pendiente', 'enviado', 'error') NOT NULL DEFAULT 'pendiente',
          detalle TEXT NULL,
          fecha_envio TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB
        """
    )
    if not column_exists(cursor, "envios_facturacion", "id_acueducto"):
        cursor.execute("ALTER TABLE envios_facturacion ADD COLUMN id_acueducto INT NULL")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS facturacion_control (
          periodo VARCHAR(20) PRIMARY KEY,
          facturas_creadas INT NOT NULL DEFAULT 0,
          correos_enviados INT NOT NULL DEFAULT 0,
          fecha_generacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB
        """
    )
    schema_ready.add("billing")


def ensure_password_reset_schema(cursor):
    if "password_reset" in schema_ready:
        return
    ensure_system_schema(cursor)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS recuperacion_password (
          id_recuperacion INT AUTO_INCREMENT PRIMARY KEY,
          email VARCHAR(120) NOT NULL,
          id_usuario_sistema INT NOT NULL,
          codigo_hash VARCHAR(255) NOT NULL,
          usado TINYINT(1) NOT NULL DEFAULT 0,
          fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          fecha_expiracion DATETIME NOT NULL
        ) ENGINE=InnoDB
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS codigos_verificacion (
          id INT AUTO_INCREMENT PRIMARY KEY,
          user_id INT NOT NULL,
          code_hash VARCHAR(255) NOT NULL,
          expires_at DATETIME NOT NULL,
          used TINYINT(1) NOT NULL DEFAULT 0,
          failed_attempts INT NOT NULL DEFAULT 0,
          locked_until DATETIME NULL,
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          INDEX idx_codigos_user (user_id),
          INDEX idx_codigos_used (used)
        ) ENGINE=InnoDB
        """
    )
    for column, sql in [
        ("failed_attempts", "ALTER TABLE codigos_verificacion ADD COLUMN failed_attempts INT NOT NULL DEFAULT 0"),
        ("locked_until", "ALTER TABLE codigos_verificacion ADD COLUMN locked_until DATETIME NULL"),
    ]:
        if not column_exists(cursor, "codigos_verificacion", column):
            cursor.execute(sql)

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS archivos_recuperacion (
          id_archivo INT AUTO_INCREMENT PRIMARY KEY,
          user_id INT NOT NULL,
          token_hash VARCHAR(255) NOT NULL,
          revoked TINYINT(1) NOT NULL DEFAULT 0,
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          last_used_at DATETIME NULL,
          INDEX idx_archivos_recuperacion_user (user_id),
          INDEX idx_archivos_recuperacion_revoked (revoked)
        ) ENGINE=InnoDB
        """
    )
    schema_ready.add("password_reset")


def ensure_content_schema(cursor):
    if "content" in schema_ready:
        return
    ensure_billing_schema(cursor)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS pqrs (
          id_pqrs INT AUTO_INCREMENT PRIMARY KEY,
          id_usuario_sistema INT NULL,
          id_acueducto INT NULL,
          codigo_recibo VARCHAR(30) NULL,
          nombre VARCHAR(160) NOT NULL,
          email VARCHAR(120) NULL,
          tipo ENUM('peticion', 'queja', 'reclamo', 'sugerencia') NOT NULL DEFAULT 'peticion',
          asunto VARCHAR(180) NOT NULL,
          descripcion TEXT NOT NULL,
          respuesta TEXT NULL,
          estado ENUM('pendiente', 'en_proceso', 'resuelto') NOT NULL DEFAULT 'pendiente',
          fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          fecha_respuesta DATETIME NULL,
          respondido_por INT NULL,
          INDEX idx_pqrs_estado (estado),
          INDEX idx_pqrs_codigo (codigo_recibo),
          INDEX idx_pqrs_usuario (id_usuario_sistema)
        ) ENGINE=InnoDB
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS puntos_pago (
          id_punto INT AUTO_INCREMENT PRIMARY KEY,
          nombre VARCHAR(140) NOT NULL,
          direccion VARCHAR(180) NOT NULL,
          telefono VARCHAR(40) NULL,
          horario VARCHAR(140) NOT NULL,
          latitud DECIMAL(10,7) NULL,
          longitud DECIMAL(10,7) NULL,
          mapa_url TEXT NULL,
          imagen VARCHAR(255) NULL,
          activo TINYINT(1) NOT NULL DEFAULT 1,
          fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB
        """
    )
    if not column_exists(cursor, "puntos_pago", "latitud"):
        cursor.execute("ALTER TABLE puntos_pago ADD COLUMN latitud DECIMAL(10,7) NULL")
    if not column_exists(cursor, "puntos_pago", "longitud"):
        cursor.execute("ALTER TABLE puntos_pago ADD COLUMN longitud DECIMAL(10,7) NULL")
    if not column_exists(cursor, "puntos_pago", "mapa_url"):
        cursor.execute("ALTER TABLE puntos_pago ADD COLUMN mapa_url TEXT NULL AFTER longitud")
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS noticias (
          id_noticia INT AUTO_INCREMENT PRIMARY KEY,
          titulo VARCHAR(180) NOT NULL,
          resumen TEXT NOT NULL,
          contenido TEXT NULL,
          imagen VARCHAR(255) NULL,
          publicada TINYINT(1) NOT NULL DEFAULT 1,
          fecha_publicacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          fecha_actualizacion DATETIME NULL
        ) ENGINE=InnoDB
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS mensajes_contacto (
          id_mensaje INT AUTO_INCREMENT PRIMARY KEY,
          nombre VARCHAR(160) NOT NULL,
          codigo VARCHAR(30) NULL,
          correo VARCHAR(120) NOT NULL,
          asunto VARCHAR(180) NOT NULL,
          mensaje TEXT NOT NULL,
          leido TINYINT(1) NOT NULL DEFAULT 0,
          fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          fecha_lectura DATETIME NULL,
          INDEX idx_contacto_leido (leido),
          INDEX idx_contacto_telefono (telefono)
        ) ENGINE=InnoDB
        """
    )
    # Migration: rename codigo → telefono
    if column_exists(cursor, "mensajes_contacto", "codigo"):
        cursor.execute(
            "ALTER TABLE mensajes_contacto CHANGE COLUMN codigo telefono VARCHAR(30) NULL"
        )
    schema_ready.add("content")


def init_schema():
    connection = get_db_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        ensure_billing_schema(cursor)
        ensure_password_reset_schema(cursor)
        ensure_content_schema(cursor)
        connection.commit()
    finally:
        connection.close()


def authenticate(email, password):
    connection = get_db_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        ensure_system_schema(cursor)
        connection.commit()
        cursor.execute(
            "SELECT * FROM usuarios_sistema WHERE LOWER(email) = LOWER(%s) LIMIT 1",
            (email,),
        )
        account = cursor.fetchone()
        if not account:
            audit_event("login_failed", success=False, details={"email": email, "reason": "unknown_account"})
            return None, "invalid"
        if account.get("locked_until") and account["locked_until"] > datetime.now():
            audit_event("login_blocked", user_id=account["id"], success=False)
            return None, "locked"
        if password_matches(password, account["password"]):
            password_update = ""
            params = [client_ip()]
            if not str(account["password"]).startswith(("$2a$", "$2b$", "$2y$")):
                password_update = ", password = %s, password_changed_at = COALESCE(password_changed_at, NOW())"
                params.append(hash_secret(password))
            params.append(account["id"])
            cursor.execute(
                f"""
                UPDATE usuarios_sistema
                SET failed_login_attempts = 0, locked_until = NULL, last_login_at = NOW(), last_login_ip = %s {password_update}
                WHERE id = %s
                """,
                tuple(params),
            )
            connection.commit()
            audit_event("login_password_ok", user_id=account["id"])
            return account, "ok"
        failed = int(account.get("failed_login_attempts") or 0) + 1
        locked_until = datetime.now() + timedelta(minutes=LOGIN_LOCK_MINUTES) if failed >= LOGIN_MAX_ATTEMPTS else None
        cursor.execute(
            "UPDATE usuarios_sistema SET failed_login_attempts = %s, locked_until = %s WHERE id = %s",
            (failed, locked_until, account["id"]),
        )
        connection.commit()
        audit_event("login_failed", user_id=account["id"], success=False, details={"attempts": failed})
        return None, "locked" if locked_until else "invalid"
    finally:
        connection.close()


def login_required(role=None):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                flash("Debes iniciar sesion para continuar.", "warning")
                return redirect(url_for("login"))
            account = get_system_user(session["user_id"])
            if not account or int(account.get("session_version") or 0) != int(session.get("session_version") or 0):
                audit_event("session_revoked", user_id=session.get("user_id"), success=False)
                session.clear()
                flash("Tu sesion expiro. Inicia sesion nuevamente.", "warning")
                return redirect(url_for("login"))
            if role and session.get("role") != role:
                target = "dashboard_admin" if session.get("role") == "admin" else "dashboard_usuario"
                flash("Tu cuenta no tiene permisos para acceder a esa seccion.", "warning")
                return redirect(url_for(target))
            return view(*args, **kwargs)

        return wrapped

    return decorator


def get_system_user_form_data():
    return {
        "nombres": request.form.get("nombres", "").strip(),
        "apellidos": request.form.get("apellidos", "").strip(),
        "telefono": request.form.get("telefono", "").strip() or None,
        "email": request.form.get("email", "").strip(),
        "password": request.form.get("password", ""),
        "rol": request.form.get("rol", "usuario").strip(),
        "codigo_recibo_vinculado": request.form.get("codigo_recibo_vinculado", "").strip() or None,
    }


def get_acueducto_form_data():
    return {
        "codigo_recibo": request.form.get("codigo_recibo", "").strip(),
        "nombres": request.form.get("nombres", "").strip(),
        "apellidos": request.form.get("apellidos", "").strip(),
        "direccion": request.form.get("direccion", "").strip(),
        "cedula": request.form.get("cedula", "").strip(),
        "telefono": request.form.get("telefono", "").strip(),
        "email_servicio": request.form.get("email_servicio", "").strip(),
        "ubicacion_maps": request.form.get("ubicacion_maps", "").strip(),
    }


def decrypt_client_row(row):
    if not row:
        return row
    row = dict(row)
    for field in ("cedula", "telefono", "email_servicio"):
        row[field] = decrypt_value(row.get(field))
    row["nombre_completo"] = f"{row.get('nombres', '')} {row.get('apellidos', '')}".strip()
    return row


def validate_codigo_recibo(cursor, codigo):
    if not codigo:
        return True
    cursor.execute("SELECT 1 FROM usuarios_acueducto WHERE codigo_recibo = %s LIMIT 1", (codigo,))
    return cursor.fetchone() is not None


def list_system_users():
    connection = get_db_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        ensure_system_schema(cursor)
        connection.commit()
        cursor.execute("SELECT * FROM usuarios_sistema ORDER BY id DESC")
        return cursor.fetchall()
    finally:
        connection.close()


def list_acueducto_users():
    connection = get_db_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        ensure_system_schema(cursor)
        connection.commit()
        cursor.execute("SELECT * FROM usuarios_acueducto ORDER BY id DESC")
        return [decrypt_client_row(row) for row in cursor.fetchall()]
    finally:
        connection.close()


def get_system_user_by_email(email):
    connection = get_db_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        ensure_system_schema(cursor)
        connection.commit()
        cursor.execute("SELECT * FROM usuarios_sistema WHERE LOWER(email) = LOWER(%s) LIMIT 1", (email,))
        return cursor.fetchone()
    finally:
        connection.close()


def get_system_user(user_id):
    connection = get_db_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        ensure_system_schema(cursor)
        connection.commit()
        cursor.execute("SELECT * FROM usuarios_sistema WHERE id = %s", (user_id,))
        return cursor.fetchone()
    finally:
        connection.close()


def get_acueducto_user(user_id):
    connection = get_db_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        ensure_system_schema(cursor)
        connection.commit()
        cursor.execute("SELECT * FROM usuarios_acueducto WHERE id = %s", (user_id,))
        row = cursor.fetchone()
        return decrypt_client_row(row) if row else None
    finally:
        connection.close()


def save_system_user(data, user_id=None):
    if not data.get("nombres") or len(data["nombres"]) < 2 or not valid_email(data["email"]):
        raise ValueError("datos_invalidos")
    if data["rol"] not in ("admin", "usuario"):
        raise ValueError("rol_invalido")
    if data["password"]:
        password_errors = validate_password_policy(data["password"])
        if password_errors:
            raise ValueError("password_insegura")
    connection = get_db_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        ensure_system_schema(cursor)
        if data["codigo_recibo_vinculado"] and not validate_codigo_recibo(cursor, data["codigo_recibo_vinculado"]):
            raise ValueError("codigo_recibo_invalido")
        if user_id:
            params = [data["nombres"], data.get("apellidos", ""), data.get("telefono"), data["email"], data["rol"], data["codigo_recibo_vinculado"]]
            password_sql = ""
            if data["password"]:
                password_sql = ", password = %s, password_changed_at = NOW(), session_version = session_version + 1"
                params.append(hash_secret(data["password"]))
            params.append(user_id)
            cursor.execute(
                f"""
                UPDATE usuarios_sistema
                SET nombres = %s, apellidos = %s, telefono = %s, email = %s, rol = %s, codigo_recibo_vinculado = %s {password_sql}
                WHERE id = %s
                """,
                params,
            )
        else:
            password = data["password"] or "Usuario123!Demo"
            cursor.execute(
                """
                INSERT INTO usuarios_sistema (nombres, apellidos, telefono, email, password, rol, codigo_recibo_vinculado)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    data["nombres"],
                    data.get("apellidos", ""),
                    data.get("telefono"),
                    data["email"],
                    hash_secret(password),
                    data["rol"],
                    data["codigo_recibo_vinculado"],
                ),
            )
        connection.commit()
    finally:
        connection.close()


def delete_system_user(user_id):
    connection = get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("DELETE FROM usuarios_sistema WHERE id = %s", (user_id,))
        connection.commit()
    finally:
        connection.close()


def save_acueducto_user(data, user_id=None):
    if not data["codigo_recibo"] or not data["nombres"] or not data["direccion"]:
        raise ValueError("campos_requeridos")
    protected = {
        **data,
        "cedula": encrypt_value(data.get("cedula")),
        "telefono": encrypt_value(data.get("telefono")),
        "email_servicio": encrypt_value(data.get("email_servicio")),
    }
    connection = get_db_connection()
    try:
        cursor = connection.cursor()
        ensure_system_schema(cursor)
        if user_id:
            cursor.execute(
                """
                UPDATE usuarios_acueducto
                SET codigo_recibo = %s, nombres = %s, apellidos = %s, direccion = %s,
                    cedula = %s, telefono = %s, email_servicio = %s, ubicacion_maps = %s
                WHERE id = %s
                """,
                (
                    protected["codigo_recibo"],
                    protected["nombres"],
                    protected.get("apellidos", ""),
                    protected["direccion"],
                    protected["cedula"],
                    protected["telefono"],
                    protected["email_servicio"],
                    protected.get("ubicacion_maps", ""),
                    user_id,
                ),
            )
        else:
            cursor.execute(
                """
                INSERT INTO usuarios_acueducto
                  (codigo_recibo, nombres, apellidos, direccion, cedula, telefono, email_servicio, ubicacion_maps)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    protected["codigo_recibo"],
                    protected["nombres"],
                    protected.get("apellidos", ""),
                    protected["direccion"],
                    protected["cedula"],
                    protected["telefono"],
                    protected["email_servicio"],
                    protected.get("ubicacion_maps", ""),
                ),
            )
        connection.commit()
        audit_event("client_saved", details={"client_id": user_id or "new"})
    finally:
        connection.close()


def delete_acueducto_user(user_id):
    connection = get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("DELETE FROM usuarios_acueducto WHERE id = %s", (user_id,))
        connection.commit()
    finally:
        connection.close()


def send_invoice_email(email, invoice, user_name=""):
    refresh_mail_config_from_env()
    smtp_host = app.config.get("MAIL_SERVER", "")
    smtp_port = app.config.get("MAIL_PORT", 587)
    smtp_user = app.config.get("MAIL_USERNAME", "")
    smtp_password = app.config.get("MAIL_PASSWORD", "")
    smtp_from = app.config.get("MAIL_DEFAULT_SENDER", smtp_user or "no-reply@aquarincon.local")
    email = email or ""
    if not smtp_host or not smtp_user or not smtp_password or not email:
        return "pendiente", "SMTP no configurado o cliente sin correo."

    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.base import MIMEBase
    from email.encoders import encode_base64 as _encode_b64

    invoice_id = invoice.get("id_factura")
    periodo = invoice.get("periodo", "")
    codigo = invoice.get("codigo_recibo", "")
    valor = money(invoice.get("valor_total", 0))
    deuda = money(invoice.get("deuda_total", 0))
    today_str = date.today().strftime("%d/%m/%Y")
    nombre = (user_name or "Usuario").strip()

    # Build PDF attachment
    pdf_bytes = None
    if invoice_id:
        try:
            pdf_bytes = build_invoice_pdf(invoice_id)
        except Exception:
            pass

    msg = MIMEMultipart()
    msg["Subject"] = f"Factura AquaRincon - {periodo}"
    msg["From"] = smtp_from
    msg["To"] = email

    text = (
        f"Hola, {nombre}\n\n"
        f"Tu factura del periodo {periodo} ya se encuentra disponible.\n\n"
        f"Numero de factura: {codigo}-{invoice_id}\n"
        f"Periodo: {periodo}\n"
        f"Fecha de emision: {today_str}\n"
        f"Valor: ${valor}\n"
        f"Total deuda pendiente: ${deuda}\n\n"
        f"Ingresa al sistema con tu codigo de recibo para consultar y pagar.\n\n"
        f"AquaRincon - Acueducto Vereda Rincon Santo"
    )

    html = (
        '<html><body style="font-family:Arial,sans-serif;background:#f4f7fa;padding:20px;">'
        '<div style="max-width:600px;margin:auto;background:#fff;border-radius:12px;overflow:hidden;'
        'box-shadow:0 4px 20px rgba(0,0,0,0.1);">'
        '<div style="background:linear-gradient(135deg,#0a2540,#00c896);padding:24px 30px;">'
        '<h1 style="color:#fff;margin:0;font-size:22px;">AquaRinc&oacute;n</h1>'
        '<p style="color:rgba(255,255,255,0.8);margin:4px 0 0;">Acueducto Vereda Rinc&oacute;n Santo</p>'
        "</div>"
        '<div style="padding:30px;">'
        f'<h2 style="color:#0a2540;font-size:18px;margin:0 0 6px;">Hola, {nombre}</h2>'
        f'<p style="color:#555;font-size:14px;line-height:1.6;">Tu factura del periodo '
        f"<strong>{periodo}</strong> ya se encuentra disponible.</p>"
        '<table style="width:100%;border-collapse:collapse;margin:16px 0;">'
        f'<tr><td style="padding:8px 12px;background:#f8fafc;border:1px solid #e2e8f0;font-size:13px;'
        f'color:#475569;">N&uacute;mero de factura</td>'
        f'<td style="padding:8px 12px;border:1px solid #e2e8f0;font-size:13px;color:#0a2540;font-weight:600;">'
        f"{codigo}-{invoice_id}</td></tr>"
        f'<tr><td style="padding:8px 12px;background:#f8fafc;border:1px solid #e2e8f0;font-size:13px;'
        f'color:#475569;">Periodo</td>'
        f'<td style="padding:8px 12px;border:1px solid #e2e8f0;font-size:13px;color:#0a2540;">{periodo}</td></tr>'
        f'<tr><td style="padding:8px 12px;background:#f8fafc;border:1px solid #e2e8f0;font-size:13px;'
        f'color:#475569;">Fecha de emisi&oacute;n</td>'
        f'<td style="padding:8px 12px;border:1px solid #e2e8f0;font-size:13px;color:#0a2540;">{today_str}</td></tr>'
        f'<tr><td style="padding:8px 12px;background:#f8fafc;border:1px solid #e2e8f0;font-size:13px;'
        f'color:#475569;">Valor</td>'
        f'<td style="padding:8px 12px;border:1px solid #e2e8f0;font-size:13px;color:#00c896;font-weight:700;">'
        f"${valor}</td></tr>"
        f'<tr><td style="padding:8px 12px;background:#f8fafc;border:1px solid #e2e8f0;font-size:13px;'
        f'color:#475569;">Total deuda pendiente</td>'
        f'<td style="padding:8px 12px;border:1px solid #e2e8f0;font-size:13px;color:#e53e3e;font-weight:700;">'
        f"${deuda}</td></tr>"
        "</table>"
        '<p style="color:#555;font-size:14px;line-height:1.6;">Puedes consultar y pagar tu factura '
        'ingresando al sistema con tu c&oacute;digo de recibo.</p>'
        '<p style="color:#555;font-size:14px;line-height:1.6;">Si tienes dudas, cont&aacute;ctanos a '
        "trav&eacute;s de los canales oficiales de la entidad.</p>"
        "</div>"
        '<div style="background:#f8fafc;padding:20px 30px;border-top:1px solid #e2e8f0;">'
        '<p style="margin:0;font-size:12px;color:#94a3b8;text-align:center;">'
        "AquaRinc&oacute;n &mdash; Acueducto Vereda Rinc&oacute;n Santo<br>"
        "Correo: aquarinconsoft@gmail.com</p></div></div></body></html>"
    )

    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))

    if pdf_bytes:
        part = MIMEBase("application", "pdf")
        part.set_payload(pdf_bytes)
        _encode_b64(part)
        part.add_header("Content-Disposition", f"attachment; filename=\"factura-{invoice_id}.pdf\"")
        msg.attach(part)

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(msg)
    return "enviado", "Correo enviado correctamente."


def generate_monthly_invoices(period=None, send_emails=True):
    period = period or current_period()
    connection = get_db_connection()
    created = 0
    emailed = 0
    errors = []
    try:
        cursor = connection.cursor(dictionary=True)
        ensure_billing_schema(cursor)
        cursor.execute("SELECT * FROM usuarios_acueducto WHERE codigo_recibo IS NOT NULL AND codigo_recibo <> ''")
        clients = cursor.fetchall()
        for client in clients:
            cursor.execute(
                "SELECT id_factura FROM facturas WHERE id_acueducto = %s AND periodo = %s LIMIT 1",
                (client["id"], period),
            )
            if cursor.fetchone():
                continue
            cursor.execute(
                """
                INSERT INTO facturas
                  (id_acueducto, codigo_recibo, periodo, valor_total, fecha_emision, fecha_vencimiento, estado)
                VALUES (%s, %s, %s, %s, %s, %s, 'pendiente')
                """,
                (client["id"], client["codigo_recibo"], period, TARIFA_MENSUAL, date.today(), next_due_date()),
            )
            invoice_id = cursor.lastrowid
            created += 1
            if send_emails:
                email_encrypted = client.get("email_servicio")
                email_to = decrypt_value(email_encrypted) if email_encrypted else None

                # Get total outstanding debt for this client
                cursor.execute(
                    "SELECT COALESCE(SUM(valor_total), 0) AS total FROM facturas "
                    "WHERE id_acueducto = %s AND estado IN ('pendiente', 'vencida')",
                    (client["id"],),
                )
                deuda_total = cursor.fetchone()["total"]

                invoice = {
                    "id_factura": invoice_id,
                    "periodo": period,
                    "codigo_recibo": client["codigo_recibo"],
                    "valor_total": TARIFA_MENSUAL,
                    "deuda_total": deuda_total,
                }
                if email_to:
                    user_name = f"{client.get('nombres', '')} {client.get('apellidos', '')}".strip()
                    try:
                        status, detail = send_invoice_email(email_to, invoice, user_name)
                    except Exception as exc:
                        status, detail = "error", str(exc)
                else:
                    status, detail = "pendiente", "Cliente sin correo registrado."
                if status != "enviado":
                    errors.append(detail)
                    app.logger.warning("Email no enviado a %s (factura %s): %s", email_to or "sin-email", invoice_id, detail)
                cursor.execute(
                    """
                    INSERT INTO envios_facturacion (id_factura, id_acueducto, email, estado, detalle)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (invoice_id, client["id"], email_to or "", status, detail),
                )
                emailed += 1 if status == "enviado" else 0

        cursor.execute(
            """
            INSERT INTO facturacion_control (periodo, facturas_creadas, correos_enviados)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE
              facturas_creadas = facturas_creadas + VALUES(facturas_creadas),
              correos_enviados = correos_enviados + VALUES(correos_enviados),
              fecha_generacion = CURRENT_TIMESTAMP
            """,
            (period, created, emailed),
        )
        connection.commit()
        return created, emailed, errors
    finally:
        connection.close()


def auto_generate_current_billing():
    global last_billing_attempt
    today = date.today()
    if last_billing_attempt == today:
        return
    last_billing_attempt = today
    period = current_period()
    connection = get_db_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        ensure_billing_schema(cursor)
        cursor.execute("SELECT periodo FROM facturacion_control WHERE periodo = %s", (period,))
        exists = cursor.fetchone()
        connection.commit()
    finally:
        connection.close()
    if not exists:
        send_auto_emails = os.getenv("AUTO_FACTURACION_ENVIAR_CORREOS", "0") == "1"
        generate_monthly_invoices(period=period, send_emails=send_auto_emails)


@app.before_request
def monthly_billing_hook():
    if request.endpoint in ("static", None):
        return
    if os.getenv("AUTO_FACTURACION_MENSUAL", "1") != "1":
        return
    try:
        auto_generate_current_billing()
    except Exception as exc:
        app.logger.warning("Facturacion mensual automatica pendiente: %s", exc)


def get_client_by_codigo(codigo):
    connection = get_db_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        ensure_billing_schema(cursor)
        connection.commit()
        cursor.execute("SELECT * FROM usuarios_acueducto WHERE codigo_recibo = %s LIMIT 1", (codigo,))
        row = cursor.fetchone()
        return decrypt_client_row(row) if row else None
    finally:
        connection.close()


def get_client_billing_summary_by_code(codigo):
    connection = get_db_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        ensure_billing_schema(cursor)
        connection.commit()
        cursor.execute("SELECT * FROM usuarios_acueducto WHERE codigo_recibo = %s LIMIT 1", (codigo,))
        client = cursor.fetchone()
        if not client:
            return None, [], None
        client = decrypt_client_row(client)
        cursor.execute(
            """
            SELECT *
            FROM facturas
            WHERE id_acueducto = %s AND estado IN ('pendiente', 'vencida')
            ORDER BY periodo ASC
            """,
            (client["id"],),
        )
        pending = cursor.fetchall()
        cursor.execute(
            """
            SELECT *
            FROM permisos_pago
            WHERE id_acueducto = %s AND estado = 'activo'
            ORDER BY id_permiso DESC LIMIT 1
            """,
            (client["id"],),
        )
        permission = cursor.fetchone()
        return client, pending, permission
    finally:
        connection.close()


def get_invoices_by_codigo(codigo):
    if not codigo:
        return []
    connection = get_db_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        ensure_billing_schema(cursor)
        connection.commit()
        cursor.execute(
            """
            SELECT f.*
            FROM facturas f
            INNER JOIN usuarios_acueducto u ON u.id = f.id_acueducto
            WHERE u.codigo_recibo = %s
            ORDER BY f.periodo DESC
            """,
            (codigo,),
        )
        return cursor.fetchall()
    finally:
        connection.close()


def get_admin_billing_data():
    connection = get_db_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        ensure_billing_schema(cursor)
        cursor.execute("SELECT COUNT(*) AS total FROM facturas")
        total_facturas = cursor.fetchone()["total"]
        cursor.execute("SELECT COUNT(*) AS total FROM facturas WHERE estado IN ('pendiente', 'vencida')")
        facturas_pendientes = cursor.fetchone()["total"]
        cursor.execute("SELECT COUNT(*) AS total FROM usuarios_acueducto")
        total_clientes = cursor.fetchone()["total"]
        cursor.execute(
            """
            SELECT COALESCE(SUM(valor_total), 0) AS total
            FROM facturas
            WHERE estado IN ('pendiente', 'vencida')
            """
        )
        total_pendiente = cursor.fetchone()["total"]
        cursor.execute("SELECT COUNT(*) AS total FROM reportes_pago WHERE estado = 'pendiente'")
        pagos_pendientes = cursor.fetchone()["total"]
        cursor.execute(
            """
            SELECT COUNT(DISTINCT id_acueducto) AS personas,
                   COUNT(*) AS facturas,
                   COALESCE(SUM(valor_total), 0) AS total
            FROM facturas
            WHERE estado = 'pagada'
              AND fecha_pago >= DATE_FORMAT(CURDATE(), '%Y-%m-01')
              AND fecha_pago < DATE_ADD(DATE_FORMAT(CURDATE(), '%Y-%m-01'), INTERVAL 1 MONTH)
            """
        )
        pagos_mes = cursor.fetchone()
        cursor.execute(
            """
            SELECT u.id, u.codigo_recibo, CONCAT(u.nombres, ' ', u.apellidos) AS nombre_completo, u.direccion,
                   COUNT(f.id_factura) AS facturas_pagadas,
                   COALESCE(SUM(f.valor_total), 0) AS total_pagado,
                   MAX(f.fecha_pago) AS ultimo_pago
            FROM facturas f
            INNER JOIN usuarios_acueducto u ON u.id = f.id_acueducto
            WHERE f.estado = 'pagada'
              AND f.fecha_pago >= DATE_FORMAT(CURDATE(), '%Y-%m-01')
              AND f.fecha_pago < DATE_ADD(DATE_FORMAT(CURDATE(), '%Y-%m-01'), INTERVAL 1 MONTH)
            GROUP BY u.id, u.codigo_recibo, u.nombres, u.apellidos, u.direccion
            ORDER BY ultimo_pago DESC, u.nombres ASC
            LIMIT 80
            """
        )
        pagaron_mes = cursor.fetchall()
        cursor.execute(
            """
            SELECT DATE_FORMAT(fecha_pago, '%Y-%m') AS periodo,
                   DATE_FORMAT(fecha_pago, '%b') AS etiqueta,
                   COUNT(DISTINCT id_acueducto) AS personas,
                   COALESCE(SUM(valor_total), 0) AS total_pagado
            FROM facturas
            WHERE estado = 'pagada'
              AND fecha_pago >= DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 5 MONTH), '%Y-%m-01')
            GROUP BY DATE_FORMAT(fecha_pago, '%Y-%m'), DATE_FORMAT(fecha_pago, '%b')
            ORDER BY periodo ASC
            """
        )
        monthly_rows = cursor.fetchall()
        max_paid = max([int(row["personas"] or 0) for row in monthly_rows] or [1])
        pagos_chart = [
            {
                **row,
                "height": max(12, round((int(row["personas"] or 0) / max_paid) * 100)),
            }
            for row in monthly_rows
        ]
        cursor.execute(
            """
            SELECT r.*, CONCAT(u.nombres, ' ', u.apellidos) AS nombre_completo, u.direccion
            FROM reportes_pago r
            INNER JOIN usuarios_acueducto u ON u.id = r.id_acueducto
            ORDER BY r.fecha_reporte DESC
            LIMIT 30
            """
        )
        reportes = cursor.fetchall()
        cursor.execute(
            """
            SELECT u.id, u.codigo_recibo, CONCAT(u.nombres, ' ', u.apellidos) AS nombre_completo, u.direccion,
                   COUNT(f.id_factura) AS meses_debe,
                   COALESCE(SUM(f.valor_total), 0) AS total_debe,
                   MAX(p.estado = 'activo') AS tiene_permiso
            FROM usuarios_acueducto u
            LEFT JOIN facturas f ON f.id_acueducto = u.id AND f.estado IN ('pendiente', 'vencida')
            LEFT JOIN permisos_pago p ON p.id_acueducto = u.id AND p.estado = 'activo'
            GROUP BY u.id, u.codigo_recibo, u.nombres, u.apellidos, u.direccion
            HAVING meses_debe > 0
            ORDER BY meses_debe DESC, u.nombres ASC
            LIMIT 80
            """
        )
        cartera = cursor.fetchall()
        morosos = [item for item in cartera if int(item["meses_debe"] or 0) > 0]
        riesgo_corte = [item for item in morosos if int(item["meses_debe"] or 0) > 5]
        return {
            "total_facturas": total_facturas,
            "total_clientes": total_clientes,
            "facturas_pendientes": facturas_pendientes,
            "total_pendiente": total_pendiente,
            "pagos_pendientes": pagos_pendientes,
            "pagos_mes": pagos_mes,
            "pagaron_mes": pagaron_mes,
            "pagos_chart": pagos_chart,
            "reportes": reportes,
            "cartera": cartera,
            "morosos": morosos,
            "riesgo_corte": riesgo_corte,
        }
    finally:
        connection.close()


def parse_user_agent(ua_string):
    if not ua_string:
        return {"browser": "Desconocido", "os": "Desconocido"}
    ua = ua_string.lower()
    # Browser
    if "edge" in ua or "edg/" in ua:
        browser = "Edge"
    elif "opr" in ua or "opera" in ua:
        browser = "Opera"
    elif "chrome" in ua and "safari" in ua:
        browser = "Chrome"
    elif "firefox" in ua:
        browser = "Firefox"
    elif "safari" in ua:
        browser = "Safari"
    else:
        browser = "Otro"
    # OS
    if "windows" in ua:
        os_name = "Windows"
    elif "mac os" in ua or "macos" in ua:
        os_name = "macOS"
    elif "linux" in ua:
        os_name = "Linux"
    elif "android" in ua:
        os_name = "Android"
    elif "ios" in ua or "iphone" in ua or "ipad" in ua:
        os_name = "iOS"
    else:
        os_name = "Otro"
    return {"browser": browser, "os": os_name}


def decode_audit_detail(raw_detail):
    if not raw_detail:
        return {}
    if isinstance(raw_detail, dict):
        return raw_detail
    try:
        return json.loads(raw_detail)
    except Exception:
        return {}


def get_admin_activity_report(filters=None):
    filters = filters or {}
    connection = get_db_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        ensure_system_schema(cursor)

        where = []
        params = []
        user_id = filters.get("user_id")
        event = (filters.get("event") or "").strip()
        date_from = (filters.get("date_from") or "").strip()
        date_to = (filters.get("date_to") or "").strip()

        if user_id:
            where.append("a.id_usuario_sistema = %s")
            params.append(user_id)
        if event:
            where.append("a.evento = %s")
            params.append(event)
        if date_from:
            where.append("DATE(a.fecha_creacion) >= %s")
            params.append(date_from)
        if date_to:
            where.append("DATE(a.fecha_creacion) <= %s")
            params.append(date_to)

        where_sql = "WHERE " + " AND ".join(where) if where else ""
        cursor.execute(
            f"""
            SELECT a.*, u.nombres, u.apellidos, u.email, u.rol
            FROM auditoria_seguridad a
            LEFT JOIN usuarios_sistema u ON u.id = a.id_usuario_sistema
            {where_sql}
            ORDER BY a.fecha_creacion DESC
            LIMIT 120
            """,
            tuple(params),
        )
        rows = cursor.fetchall()
        events = []
        for row in rows:
            detail = decode_audit_detail(row.get("detalle"))
            full_name = f"{row.get('nombres') or ''} {row.get('apellidos') or ''}".strip()
            ua_info = parse_user_agent(detail.get("user_agent", ""))
            events.append(
                {
                    **row,
                    "detalle": detail,
                    "usuario_nombre": full_name or "Visitante / sistema",
                    "usuario_email": row.get("email") or "Sin correo",
                    "evento_label": ACTIVITY_EVENT_LABELS.get(row.get("evento"), row.get("evento")),
                    "accion": detail.get("action") or ACTIVITY_EVENT_LABELS.get(row.get("evento"), row.get("evento")),
                    "ruta": detail.get("route") or detail.get("path") or "",
                    "path": detail.get("path") or "",
                    "metodo": detail.get("method") or "",
                    "browser": ua_info["browser"],
                    "os": ua_info["os"],
                }
            )

        cursor.execute("SELECT COUNT(*) AS total FROM auditoria_seguridad WHERE DATE(fecha_creacion) = CURDATE()")
        total_today = cursor.fetchone()["total"]
        cursor.execute(
            """
            SELECT COUNT(*) AS total
            FROM auditoria_seguridad
            WHERE evento IN ('invoice_pdf_downloaded', 'public_invoice_pdf_downloaded', 'paz_y_salvo_downloaded', 'recovery_file_downloaded')
              AND DATE(fecha_creacion) = CURDATE()
            """
        )
        downloads_today = cursor.fetchone()["total"]
        cursor.execute(
            """
            SELECT evento, COUNT(*) AS total
            FROM auditoria_seguridad
            GROUP BY evento
            ORDER BY total DESC, evento ASC
            LIMIT 12
            """
        )
        event_counts = cursor.fetchall()

        return {
            "events": events,
            "total_today": total_today,
            "downloads_today": downloads_today,
            "event_counts": event_counts,
            "event_labels": ACTIVITY_EVENT_LABELS,
        }
    finally:
        connection.close()


def allowed_image(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def save_uploaded_image(field_name):
    image = request.files.get(field_name)
    if not image or not image.filename:
        return request.form.get("imagen_actual", "").strip() or None
    if not allowed_image(image.filename):
        raise ValueError("imagen_invalida")
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    base = secure_filename(image.filename)
    filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(4)}-{base}"
    image.save(os.path.join(UPLOAD_FOLDER, filename))
    return f"uploads/{filename}"


def list_payment_points(only_active=True):
    connection = get_db_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        ensure_content_schema(cursor)
        sql = "SELECT * FROM puntos_pago"
        if only_active:
            sql += " WHERE activo = 1"
        sql += " ORDER BY fecha_creacion DESC"
        cursor.execute(sql)
        points = cursor.fetchall()
        for point in points:
            point["ruta_url"] = payment_point_route_url(point)
        return points
    finally:
        connection.close()


def get_payment_point(point_id):
    connection = get_db_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        ensure_content_schema(cursor)
        cursor.execute("SELECT * FROM puntos_pago WHERE id_punto = %s", (point_id,))
        point = cursor.fetchone()
        if point:
            point["ruta_url"] = payment_point_route_url(point)
        return point
    finally:
        connection.close()


def decimal_or_none(value):
    value = str(value or "").strip().replace(",", ".")
    if not value:
        return None
    return float(value)


def google_maps_url_or_none(value):
    value = str(value or "").strip()
    if not value:
        return None
    parsed = urlparse(value)
    host = parsed.netloc.lower()
    allowed_hosts = (
        "google.com",
        "www.google.com",
        "maps.google.com",
        "goo.gl",
        "maps.app.goo.gl",
    )
    if parsed.scheme not in ("http", "https") or not any(host == item or host.endswith(f".{item}") for item in allowed_hosts):
        raise ValueError("mapa_url_invalida")
    return value


def coordinates_from_google_maps_url(value):
    value = str(value or "")
    patterns = (
        r"!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)",
        r"@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)",
        r"[?&](?:q|query|destination)=(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)",
    )
    for pattern in patterns:
        match = re.search(pattern, value)
        if match:
            return float(match.group(1)), float(match.group(2))
    return None, None


def payment_point_route_url(point):
    latitud = point.get("latitud")
    longitud = point.get("longitud")
    if latitud is not None and longitud is not None:
        return f"https://www.google.com/maps/dir/?api=1&destination={latitud},{longitud}"
    return point.get("mapa_url") or ""


def save_payment_point(point_id=None):
    nombre = request.form.get("nombre", "").strip()
    direccion = request.form.get("direccion", "").strip()
    telefono = request.form.get("telefono", "").strip()
    horario = request.form.get("horario", "").strip()
    latitud = decimal_or_none(request.form.get("latitud"))
    longitud = decimal_or_none(request.form.get("longitud"))
    mapa_url = google_maps_url_or_none(request.form.get("mapa_url"))
    if mapa_url and (latitud is None or longitud is None):
        parsed_lat, parsed_lng = coordinates_from_google_maps_url(mapa_url)
        latitud = latitud if latitud is not None else parsed_lat
        longitud = longitud if longitud is not None else parsed_lng
    if not nombre or not direccion or not horario:
        raise ValueError("campos_requeridos")
    if (latitud is not None and not -90 <= latitud <= 90) or (longitud is not None and not -180 <= longitud <= 180):
        raise ValueError("coordenadas_invalidas")
    imagen = save_uploaded_image("imagen")
    connection = get_db_connection()
    try:
        cursor = connection.cursor()
        ensure_content_schema(cursor)
        if point_id:
            cursor.execute(
                """
                UPDATE puntos_pago
                SET nombre = %s, direccion = %s, telefono = %s, horario = %s,
                    latitud = %s, longitud = %s, mapa_url = %s, imagen = %s
                WHERE id_punto = %s
                """,
                (nombre, direccion, telefono, horario, latitud, longitud, mapa_url, imagen, point_id),
            )
        else:
            cursor.execute(
                """
                INSERT INTO puntos_pago (nombre, direccion, telefono, horario, latitud, longitud, mapa_url, imagen)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (nombre, direccion, telefono, horario, latitud, longitud, mapa_url, imagen),
            )
        connection.commit()
    finally:
        connection.close()


def delete_payment_point(point_id):
    connection = get_db_connection()
    try:
        cursor = connection.cursor()
        ensure_content_schema(cursor)
        cursor.execute("DELETE FROM puntos_pago WHERE id_punto = %s", (point_id,))
        connection.commit()
    finally:
        connection.close()


def list_news(only_published=True):
    connection = get_db_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        ensure_content_schema(cursor)
        sql = "SELECT * FROM noticias"
        if only_published:
            sql += " WHERE publicada = 1"
        sql += " ORDER BY fecha_publicacion DESC"
        cursor.execute(sql)
        return cursor.fetchall()
    finally:
        connection.close()


def get_news(news_id):
    connection = get_db_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        ensure_content_schema(cursor)
        cursor.execute("SELECT * FROM noticias WHERE id_noticia = %s", (news_id,))
        return cursor.fetchone()
    finally:
        connection.close()


def save_news(news_id=None):
    titulo = request.form.get("titulo", "").strip()
    resumen = request.form.get("resumen", "").strip()
    contenido = request.form.get("contenido", "").strip()
    publicada = 1 if request.form.get("publicada", "1") == "1" else 0
    if not titulo or not resumen:
        raise ValueError("campos_requeridos")
    imagen = save_uploaded_image("imagen")
    connection = get_db_connection()
    try:
        cursor = connection.cursor()
        ensure_content_schema(cursor)
        if news_id:
            cursor.execute(
                """
                UPDATE noticias
                SET titulo = %s, resumen = %s, contenido = %s, imagen = %s,
                    publicada = %s, fecha_actualizacion = NOW()
                WHERE id_noticia = %s
                """,
                (titulo, resumen, contenido, imagen, publicada, news_id),
            )
        else:
            cursor.execute(
                """
                INSERT INTO noticias (titulo, resumen, contenido, imagen, publicada)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (titulo, resumen, contenido, imagen, publicada),
            )
        connection.commit()
    finally:
        connection.close()


def delete_news(news_id):
    connection = get_db_connection()
    try:
        cursor = connection.cursor()
        ensure_content_schema(cursor)
        cursor.execute("DELETE FROM noticias WHERE id_noticia = %s", (news_id,))
        connection.commit()
    finally:
        connection.close()


def list_contact_messages():
    connection = get_db_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        ensure_content_schema(cursor)
        cursor.execute("SELECT * FROM mensajes_contacto ORDER BY leido ASC, fecha_creacion DESC")
        return cursor.fetchall()
    finally:
        connection.close()


def create_contact_message():
    nombre = request.form.get("nombre", "").strip()
    telefono = request.form.get("telefono", "").strip()
    correo = request.form.get("correo", "").strip()
    asunto = request.form.get("asunto", "").strip()
    mensaje = request.form.get("mensaje", "").strip()
    if not nombre or not correo or not asunto or not mensaje or "@" not in correo:
        raise ValueError("campos_requeridos")
    connection = get_db_connection()
    try:
        cursor = connection.cursor()
        ensure_content_schema(cursor)
        cursor.execute(
            """
            INSERT INTO mensajes_contacto (nombre, telefono, correo, asunto, mensaje)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (nombre, telefono or None, correo, asunto, mensaje),
        )
        connection.commit()
    finally:
        connection.close()


def mark_contact_read(message_id):
    connection = get_db_connection()
    try:
        cursor = connection.cursor()
        ensure_content_schema(cursor)
        cursor.execute("UPDATE mensajes_contacto SET leido = 1, fecha_lectura = NOW() WHERE id_mensaje = %s", (message_id,))
        connection.commit()
    finally:
        connection.close()


def list_pqrs_for_user(user_id, codigo=None):
    connection = get_db_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        ensure_content_schema(cursor)
        if codigo:
            cursor.execute(
                """
                SELECT * FROM pqrs
                WHERE id_usuario_sistema = %s OR codigo_recibo = %s
                ORDER BY fecha_creacion DESC
                """,
                (user_id, codigo),
            )
        else:
            cursor.execute("SELECT * FROM pqrs WHERE id_usuario_sistema = %s ORDER BY fecha_creacion DESC", (user_id,))
        return cursor.fetchall()
    finally:
        connection.close()


def list_all_pqrs(status=None):
    connection = get_db_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        ensure_content_schema(cursor)
        if status:
            cursor.execute("SELECT * FROM pqrs WHERE estado = %s ORDER BY fecha_creacion DESC", (status,))
        else:
            cursor.execute("SELECT * FROM pqrs ORDER BY fecha_creacion DESC")
        return cursor.fetchall()
    finally:
        connection.close()


def create_pqrs():
    tipo = request.form.get("tipo", "peticion").strip()
    asunto = request.form.get("asunto", "").strip()
    descripcion = request.form.get("descripcion", "").strip()
    codigo = (request.form.get("codigo_recibo", "").strip() or session.get("codigo_recibo_vinculado") or "")
    if tipo not in ("peticion", "queja", "reclamo", "sugerencia"):
        tipo = "peticion"
    if not asunto or not descripcion:
        raise ValueError("campos_requeridos")
    client = get_client_by_codigo(codigo) if codigo else None
    nombre = client["nombre_completo"] if client else current_user_name()
    email = client.get("email_servicio") if client else session.get("user_login")
    connection = get_db_connection()
    try:
        cursor = connection.cursor()
        ensure_content_schema(cursor)
        cursor.execute(
            """
            INSERT INTO pqrs
              (id_usuario_sistema, id_acueducto, codigo_recibo, nombre, email, tipo, asunto, descripcion)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (session.get("user_id"), client["id"] if client else None, codigo or None, nombre, email, tipo, asunto, descripcion),
        )
        connection.commit()
    finally:
        connection.close()


def update_pqrs(pqrs_id, admin_id):
    estado = request.form.get("estado", "pendiente").strip()
    respuesta = request.form.get("respuesta", "").strip()
    if estado not in ("pendiente", "en_proceso", "resuelto"):
        raise ValueError("estado_invalido")
    connection = get_db_connection()
    try:
        cursor = connection.cursor()
        ensure_content_schema(cursor)
        cursor.execute(
            """
            UPDATE pqrs
            SET estado = %s, respuesta = %s, fecha_respuesta = IF(%s <> '', NOW(), fecha_respuesta), respondido_por = %s
            WHERE id_pqrs = %s
            """,
            (estado, respuesta or None, respuesta, admin_id if respuesta else None, pqrs_id),
        )
        connection.commit()
    finally:
        connection.close()


def search_invoices(term):
    if not term:
        return []
    like = f"%{term}%"
    connection = get_db_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        ensure_billing_schema(cursor)
        cursor.execute(
            """
            SELECT f.*, CONCAT(u.nombres, ' ', u.apellidos) AS nombre_completo, u.direccion, u.cedula,
                   (
                     SELECT COUNT(*)
                     FROM facturas pf
                     WHERE pf.id_acueducto = u.id AND pf.estado IN ('pendiente', 'vencida')
                   ) AS meses_consumo
            FROM facturas f
            INNER JOIN usuarios_acueducto u ON u.id = f.id_acueducto
            WHERE CAST(f.id_factura AS CHAR) = %s OR u.codigo_recibo LIKE %s
            ORDER BY f.fecha_emision DESC, f.id_factura DESC
            LIMIT 40
            """,
            (term, like),
        )
        return cursor.fetchall()
    finally:
        connection.close()


def mark_invoice_paid(invoice_id, admin_id=None):
    connection = get_db_connection()
    try:
        cursor = connection.cursor()
        ensure_billing_schema(cursor)
        cursor.execute(
            "UPDATE facturas SET estado = 'pagada', fecha_pago = NOW() WHERE id_factura = %s AND estado <> 'pagada'",
            (invoice_id,),
        )
        connection.commit()
        return cursor.rowcount > 0
    finally:
        connection.close()


def update_profile(nombres, apellidos, cedula=None, telefono=None):
    nombres = (nombres or "").strip()
    apellidos = (apellidos or "").strip()
    cedula = (cedula or "").strip() or None
    telefono = (telefono or "").strip() or None
    if len(nombres) < 2:
        raise ValueError("nombre_invalido")
    connection = get_db_connection()
    try:
        cursor = connection.cursor()
        ensure_system_schema(cursor)
        cursor.execute(
            "UPDATE usuarios_sistema SET nombres = %s, apellidos = %s, cedula = %s, telefono = %s WHERE id = %s",
            (nombres, apellidos, cedula, telefono, session["user_id"]),
        )
        connection.commit()
        session["user_name"] = f"{nombres} {apellidos}".strip()
        session["user_nombres"] = nombres
        session["user_apellidos"] = apellidos
    finally:
        connection.close()


def get_paz_y_salvo_data(codigo):
    client = get_client_by_codigo(codigo) if codigo else None
    if not client:
        return None, [], []
    invoices = get_invoices_by_codigo(codigo)
    pending = [invoice for invoice in invoices if invoice["estado"] in ("pendiente", "vencida")]
    paid = [invoice for invoice in invoices if invoice["estado"] == "pagada"]
    return client, pending, paid


def build_paz_y_salvo_pdf(codigo):
    client, pending, paid = get_paz_y_salvo_data(codigo)
    if not client or pending:
        return None
    lines = [
        "Paz y salvo de acueducto",
        f"Nombre completo: {client['nombre_completo']}",
        f"Codigo de usuario: {client['codigo_recibo']}",
        f"Direccion: {client['direccion']}",
        f"Estado: Paz y Salvo",
        f"Fecha de generacion: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Facturas pagadas registradas: {len(paid)}",
        f"Ultimo pago: {paid[0]['fecha_pago'] if paid else 'Sin pagos registrados'}",
        "Sello digital: AquaRincon valida este documento contra su sistema de facturacion.",
    ]
    return make_simple_pdf(lines)


def can_access_invoice(invoice_id):
    if session.get("role") == "admin":
        return True
    codigo = session.get("codigo_recibo_vinculado")
    if not codigo:
        return False
    connection = get_db_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        ensure_billing_schema(cursor)
        cursor.execute("SELECT 1 FROM facturas WHERE id_factura = %s AND codigo_recibo = %s", (invoice_id, codigo))
        return cursor.fetchone() is not None
    finally:
        connection.close()


def create_payment_report(codigo, codigo_confirmacion, meses, metodo, referencia, comprobante=None):
    if codigo != codigo_confirmacion:
        return False, "El codigo de verificacion no coincide con el codigo de recibo.", None

    client, pending, permission = get_client_billing_summary_by_code(codigo)
    if not client:
        return False, "No existe un cliente del acueducto con ese codigo de recibo.", None

    debt_months = len(pending)
    if debt_months == 0:
        return False, "Este cliente no tiene facturas pendientes.", None
    if meses < 1 or meses > debt_months:
        return False, "La cantidad de meses a pagar no es valida.", None
    if debt_months > 5:
        if not permission:
            return False, "Debe mas de 5 meses. Debe solicitar un acuerdo de pago al administrador.", {
                "user": client,
                "pending": pending,
                "permission": permission,
            }
        if meses < int(permission["meses_minimos"]):
            return False, f"Con acuerdo aprobado debe pagar minimo {permission['meses_minimos']} meses.", {
                "user": client,
                "pending": pending,
                "permission": permission,
            }

    # Validate comprobante required for digital methods (transferencia/consignacion)
    if metodo == "digital" and not comprobante:
        return False, "Debes adjuntar la imagen del comprobante de pago.", {
            "user": client, "pending": pending, "permission": permission,
        }

    connection = get_db_connection()
    try:
        cursor = connection.cursor()
        ensure_billing_schema(cursor)
        amount = meses * TARIFA_MENSUAL
        cursor.execute(
            """
            INSERT INTO reportes_pago
              (id_acueducto, codigo_recibo, id_usuario_sistema, meses_pagados, valor_reportado, metodo_pago, referencia, comprobante)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (client["id"], codigo, session.get("user_id"), meses, amount, metodo, referencia, comprobante),
        )
        connection.commit()
        return True, "Reporte de pago enviado al administrador para verificacion.", {
            "user": client,
            "pending": pending,
            "permission": permission,
            "amount": amount,
        }
    finally:
        connection.close()


def verify_payment_report(report_id, admin_id):
    connection = get_db_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        ensure_billing_schema(cursor)
        cursor.execute("SELECT * FROM reportes_pago WHERE id_reporte = %s LIMIT 1", (report_id,))
        report = cursor.fetchone()
        if not report or report["estado"] != "pendiente":
            return False
        cursor.execute(
            """
            SELECT id_factura
            FROM facturas
            WHERE id_acueducto = %s AND estado IN ('pendiente', 'vencida')
            ORDER BY periodo ASC
            LIMIT %s
            """,
            (report["id_acueducto"], int(report["meses_pagados"])),
        )
        for invoice in cursor.fetchall():
            cursor.execute(
                """
                UPDATE facturas
                SET estado = 'pagada', fecha_pago = NOW(), id_reporte_pago = %s
                WHERE id_factura = %s
                """,
                (report_id, invoice["id_factura"]),
            )
        cursor.execute(
            """
            UPDATE reportes_pago
            SET estado = 'verificado', fecha_revision = NOW(), revisado_por = %s
            WHERE id_reporte = %s
            """,
            (admin_id, report_id),
        )
        cursor.execute(
            """
            UPDATE permisos_pago
            SET estado = 'usado', fecha_uso = NOW()
            WHERE id_acueducto = %s AND estado = 'activo'
            """,
            (report["id_acueducto"],),
        )
        connection.commit()
        return True
    finally:
        connection.close()


def reject_payment_report(report_id, admin_id, observation):
    connection = get_db_connection()
    try:
        cursor = connection.cursor()
        ensure_billing_schema(cursor)
        cursor.execute(
            """
            UPDATE reportes_pago
            SET estado = 'rechazado', fecha_revision = NOW(), revisado_por = %s, observacion = %s
            WHERE id_reporte = %s AND estado = 'pendiente'
            """,
            (admin_id, observation, report_id),
        )
        connection.commit()
        return cursor.rowcount > 0
    finally:
        connection.close()


def grant_payment_permission(client_id, admin_id, observation):
    connection = get_db_connection()
    try:
        cursor = connection.cursor()
        ensure_billing_schema(cursor)
        cursor.execute("UPDATE permisos_pago SET estado = 'cancelado' WHERE id_acueducto = %s AND estado = 'activo'", (client_id,))
        cursor.execute(
            """
            INSERT INTO permisos_pago (id_acueducto, meses_minimos, observacion, concedido_por)
            VALUES (%s, 3, %s, %s)
            """,
            (client_id, observation, admin_id),
        )
        connection.commit()
    finally:
        connection.close()


def build_invoice_pdf(invoice_id):
    connection = get_db_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        ensure_billing_schema(cursor)
        cursor.execute(
            """
            SELECT f.*, u.codigo_recibo, CONCAT(u.nombres, ' ', u.apellidos) AS nombre_completo,
                   u.direccion, u.cedula, u.telefono, u.email_servicio
            FROM facturas f
            INNER JOIN usuarios_acueducto u ON u.id = f.id_acueducto
            WHERE f.id_factura = %s
            LIMIT 1
            """,
            (invoice_id,),
        )
        invoice = cursor.fetchone()
        if not invoice:
            return None
    finally:
        connection.close()

    return make_invoice_pdf(invoice)


def pdf_escape(value):
    return str(value or "").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def pdf_text(ops, x, y, text, size=10, font="F1", color=(0.02, 0.10, 0.28), align="left"):
    text = pdf_escape(text)
    width = len(text) * size * 0.48
    if align == "center":
        x -= width / 2
    elif align == "right":
        x -= width
    ops.append(f"{color[0]} {color[1]} {color[2]} rg BT /{font} {size} Tf {x:.2f} {y:.2f} Td ({text}) Tj ET")


def pdf_rect(ops, x, y, w, h, stroke=(0.05, 0.28, 0.62), fill=None, line_width=0.7):
    if fill:
        ops.append(f"{fill[0]} {fill[1]} {fill[2]} rg {x:.2f} {y:.2f} {w:.2f} {h:.2f} re f")
    ops.append(f"{line_width:.2f} w {stroke[0]} {stroke[1]} {stroke[2]} RG {x:.2f} {y:.2f} {w:.2f} {h:.2f} re S")


def pdf_line(ops, x1, y1, x2, y2, color=(0.05, 0.28, 0.62), line_width=0.6):
    ops.append(f"{line_width:.2f} w {color[0]} {color[1]} {color[2]} RG {x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S")


def format_pdf_date(value):
    if not value:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%d/%m/%Y")
    return str(value)


def period_label(period):
    months = {
        "01": "ENERO", "02": "FEBRERO", "03": "MARZO", "04": "ABRIL",
        "05": "MAYO", "06": "JUNIO", "07": "JULIO", "08": "AGOSTO",
        "09": "SEPTIEMBRE", "10": "OCTUBRE", "11": "NOVIEMBRE", "12": "DICIEMBRE",
    }
    parts = str(period or "").split("-")
    if len(parts) >= 2:
        return f"{months.get(parts[1], parts[1])} {parts[0]}"
    return str(period or "")


def make_simple_pdf(lines):
    ops = [
        "1 1 1 rg 0 0 612 792 re f",
        "0.04 0.16 0.36 rg 0 720 612 72 re f",
    ]
    pdf_text(ops, 54, 758, "AquaRincon", 22, "F2", color=(1, 1, 1))
    pdf_text(ops, 54, 740, "Acueducto Comunitario Rincon Santo", 10, "F1", color=(0.86, 0.95, 1))
    pdf_rect(ops, 42, 120, 528, 560, fill=(0.97, 0.99, 1), line_width=0.7)
    y = 640
    for index, line in enumerate(lines):
        font = "F2" if index == 0 else "F1"
        size = 16 if index == 0 else 11
        pdf_text(ops, 68, y, line, size, font)
        y -= 26 if index == 0 else 22
    pdf_text(ops, 68, 92, "Documento generado dinamicamente por el sistema AquaRincon.", 9, "F1", color=(0.33, 0.40, 0.46))
    return make_pdf_document(ops, 612, 792)


def make_invoice_pdf(invoice):
    total = float(invoice.get("valor_total") or 0)
    total_text = money(total)
    periodo = period_label(invoice.get("periodo"))
    fecha_emision = format_pdf_date(invoice.get("fecha_emision"))
    fecha_vencimiento = format_pdf_date(invoice.get("fecha_vencimiento"))
    cliente = invoice.get("nombre_completo") or "Usuario"
    codigo = invoice.get("codigo_recibo") or ""
    direccion = invoice.get("direccion") or "Direccion no registrada"
    cedula = invoice.get("cedula") or "No registrada"
    telefono = invoice.get("telefono") or "313 123 4567"
    email = invoice.get("email_servicio") or "contacto@aquarincon.com"
    ops = [
        "1 1 1 rg 0 0 792 612 re f",
    ]

    pdf_rect(ops, 6, 8, 780, 596, line_width=0.8)

    # Marca
    pdf_text(ops, 120, 440, "AQUARINCON", 24, "F2", align="center")
    pdf_text(ops, 120, 425, "Comprometidos con el agua, comprometidos con nuestra gente", 7, "F1", align="center")
    pdf_text(ops, 120, 512, "ACUEDUCTO", 11, "F2", align="center")
    pdf_text(ops, 120, 494, "COMUNITARIO", 10, "F2", align="center")
    pdf_text(ops, 120, 470, "~", 38, "F2", align="center")

    # Datos del cliente
    pdf_rect(ops, 235, 400, 305, 188, fill=(0.35, 0.78, 0.94), line_width=0)
    pdf_text(ops, 245, 560, "Cliente:", 11, "F2")
    pdf_text(ops, 310, 560, cliente.upper()[:28], 12, "F2")
    pdf_rect(ops, 244, 525, 150, 28, stroke=(0.02, 0.16, 0.42), fill=(0.02, 0.16, 0.42), line_width=0)
    pdf_text(ops, 252, 534, f"Codigo: {codigo}", 14, "F2", color=(1, 1, 1))
    pdf_text(ops, 245, 505, "Estrato:", 11, "F2")
    pdf_text(ops, 300, 505, "Residencial - Estratificacion 1", 11, "F1")
    pdf_text(ops, 245, 480, "Ruta:", 11, "F2")
    pdf_text(ops, 300, 480, codigo or "000000", 11, "F1")
    pdf_text(ops, 245, 455, "Direccion suministro:", 11, "F2")
    pdf_text(ops, 370, 455, direccion.upper()[:30], 10, "F1")
    pdf_text(ops, 245, 430, "Direccion de envio:", 11, "F2")
    pdf_text(ops, 370, 430, direccion.upper()[:30], 10, "F1")
    pdf_text(ops, 245, 407, "Ciudad:", 11, "F2")
    pdf_text(ops, 300, 407, "GUAMO, TOLIMA", 11, "F1")

    # Datos del documento
    pdf_rect(ops, 560, 543, 210, 45)
    pdf_text(ops, 665, 570, "Documento equivalente a", 13, "F2", align="center")
    pdf_text(ops, 665, 552, f"factura No {invoice.get('id_factura')}", 13, "F2", align="center")
    pdf_rect(ops, 560, 480, 210, 55)
    pdf_text(ops, 572, 518, "Fecha de emision:", 10, "F2")
    pdf_text(ops, 665, 518, fecha_emision, 10, "F1")
    pdf_text(ops, 572, 500, "Mes facturado:", 10, "F2")
    pdf_text(ops, 665, 500, periodo, 10, "F1")
    pdf_text(ops, 572, 484, "Periodo consumo:", 10, "F2")
    pdf_text(ops, 665, 484, "Cuota fija", 10, "F1")
    pdf_rect(ops, 560, 415, 210, 55)
    pdf_text(ops, 665, 447, "Sin recargo hasta", 13, "F2", align="center")
    pdf_text(ops, 665, 424, fecha_vencimiento, 17, "F2", align="center")
    pdf_text(ops, 560, 394, "DUPLICADO", 15, "F2")
    pdf_text(ops, 760, 394, "1 DE 1", 9, "F1", align="right")

    # Medicion
    pdf_rect(ops, 22, 335, 748, 50)
    ops.append("0.90 0.96 1 rg 22 362 748 23 re f")
    headers = ["Numero medidor", "Diametro", "Fecha de lectura", "Lectura anterior", "Lectura actual", "Consumo (m3)", "Estimado (S/N)"]
    values = ["0", "0.00", fecha_emision or "00/00/0000", "0", "0", "0", "N"]
    xs = [85, 175, 280, 390, 505, 620, 725]
    for x, h in zip(xs, headers):
        pdf_text(ops, x, 370, h, 9, "F2", align="center")
    for x, value in zip(xs, values):
        pdf_text(ops, x, 344, value, 10, "F1", align="center")

    # Conceptos
    pdf_rect(ops, 22, 72, 510, 252)
    pdf_text(ops, 32, 304, "CONCEPTOS", 15, "F2")
    pdf_line(ops, 22, 292, 532, 292)
    pdf_text(ops, 32, 272, "Concepto", 9, "F2")
    pdf_text(ops, 235, 272, "Cantidad", 9, "F2")
    pdf_text(ops, 330, 272, "Precio", 9, "F2")
    pdf_text(ops, 410, 272, "Valor IVA", 9, "F2")
    pdf_text(ops, 515, 272, "Total", 9, "F2", align="right")
    pdf_text(ops, 32, 248, "Acueducto", 11, "F2", color=(0.02, 0.22, 0.58))
    pdf_text(ops, 34, 228, "Cargo fijo", 10, "F1")
    pdf_text(ops, 250, 228, "1.00 Mes", 10, "F1", align="center")
    pdf_text(ops, 345, 228, total_text, 10, "F1", align="center")
    pdf_text(ops, 430, 228, "0", 10, "F1", align="center")
    pdf_text(ops, 515, 228, total_text, 10, "F1", align="right")
    pdf_text(ops, 34, 208, "Consumo basico", 10, "F1")
    pdf_text(ops, 250, 208, "0.00 m3", 10, "F1", align="center")
    pdf_text(ops, 345, 208, "$ 0", 10, "F1", align="center")
    pdf_text(ops, 430, 208, "0", 10, "F1", align="center")
    pdf_text(ops, 515, 208, "$ 0", 10, "F1", align="right")
    ops.append("0.90 0.96 1 rg 202 185 315 18 re f")
    pdf_text(ops, 210, 190, "Total Acueducto", 10, "F2")
    pdf_text(ops, 515, 190, total_text, 10, "F2", align="right")
    pdf_text(ops, 32, 160, "Otros", 11, "F2", color=(0.02, 0.22, 0.58))
    pdf_text(ops, 34, 140, "Ajuste / recargos", 10, "F1")
    pdf_text(ops, 515, 140, "$ 0", 10, "F1", align="right")
    ops.append("0.90 0.96 1 rg 202 115 315 18 re f")
    pdf_text(ops, 210, 120, "Total Otros", 10, "F2")
    pdf_text(ops, 515, 120, "$ 0", 10, "F2", align="right")
    pdf_rect(ops, 32, 80, 490, 32, stroke=(0.02, 0.16, 0.42), fill=(0.02, 0.16, 0.42), line_width=0)
    pdf_text(ops, 52, 91, "TOTAL A PAGAR", 12, "F2", color=(1, 1, 1))
    pdf_text(ops, 505, 87, total_text, 18, "F2", color=(1, 1, 1), align="right")

    # Laterales
    pdf_rect(ops, 540, 72, 230, 252)
    pdf_text(ops, 555, 302, "Subsidios(-)", 8, "F2")
    pdf_text(ops, 630, 302, "Acueducto", 9, "F2")
    pdf_text(ops, 705, 302, "Alcantarillado", 9, "F2")
    pdf_text(ops, 630, 285, "$ 0", 9, "F1")
    pdf_line(ops, 540, 266, 770, 266)
    pdf_text(ops, 655, 236, "Consumo promedio ultimos", 8, "F2", align="center")
    pdf_text(ops, 655, 222, "6 meses", 8, "F2", align="center")
    pdf_text(ops, 725, 230, "0 m3", 12, "F2", align="center")
    pdf_line(ops, 540, 200, 770, 200)
    pdf_text(ops, 655, 172, "Consumos", 11, "F2", align="center")
    pdf_text(ops, 655, 156, "anteriores en m3", 11, "F2", align="center")
    pdf_text(ops, 655, 128, "0  |  0  |  0  |  0  |  0  |  0", 9, "F1", align="center")

    # Pie
    pdf_line(ops, 6, 50, 786, 50)
    pdf_text(ops, 50, 25, "Vereda Rincon Santo, Guamo - Tolima", 9, "F1")
    pdf_text(ops, 285, 25, telefono, 9, "F1")
    pdf_text(ops, 430, 25, email, 9, "F1")
    pdf_text(ops, 640, 25, "www.aquarincon.com", 9, "F1")
    pdf_text(ops, 32, 25, "PIN", 10, "F2")

    return make_pdf_document(ops, 792, 612)


def make_pdf_document(ops, width, height):
    stream = "\n".join(ops)
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] /Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
        f"<< /Length {len(stream.encode('latin-1', errors='replace'))} >>\nstream\n{stream}\nendstream",
    ]
    pdf = "%PDF-1.4\n"
    offsets = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf.encode("latin-1")))
        pdf += f"{index} 0 obj\n{obj}\nendobj\n"
    xref = len(pdf.encode("latin-1"))
    pdf += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
    for offset in offsets:
        pdf += f"{offset:010d} 00000 n \n"
    pdf += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF"
    return pdf.encode("latin-1", errors="replace")


def create_otp_code(user_id):
    connection = get_db_connection()
    try:
        cursor = connection.cursor()
        ensure_password_reset_schema(cursor)
        code = f"{secrets.randbelow(10 ** OTP_LENGTH):0{OTP_LENGTH}d}"
        cursor.execute(
            "UPDATE codigos_verificacion SET used = 1 WHERE user_id = %s AND used = 0",
            (user_id,),
        )
        cursor.execute(
            """
            INSERT INTO codigos_verificacion (user_id, code_hash, expires_at)
            VALUES (%s, %s, %s)
            """,
            (user_id, hash_secret(code), datetime.now() + timedelta(minutes=EMAIL_OTP_EXPIRES_MINUTES)),
        )
        connection.commit()
        audit_event("email_otp_created", user_id=user_id)
        return code
    finally:
        connection.close()


def verify_otp_code(user_id, code):
    if not user_id or not code:
        return False, "invalid"
    if not re.fullmatch(r"\d{6}", str(code).strip()):
        audit_event("email_otp_failed", user_id=user_id, success=False, details={"reason": "format"})
        return False, "invalid"
    connection = get_db_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        ensure_password_reset_schema(cursor)
        cursor.execute(
            """
            SELECT * FROM codigos_verificacion
            WHERE user_id = %s AND used = 0 AND expires_at >= NOW()
            ORDER BY id DESC LIMIT 1
            """,
            (user_id,),
        )
        record = cursor.fetchone()
        if not record:
            audit_event("email_otp_failed", user_id=user_id, success=False, details={"reason": "expired_or_missing"})
            return False, "expired"
        if record.get("locked_until") and record["locked_until"] > datetime.now():
            audit_event("email_otp_blocked", user_id=user_id, success=False)
            return False, "locked"
        if not password_matches(code, record["code_hash"]):
            failed = int(record.get("failed_attempts") or 0) + 1
            locked_until = datetime.now() + timedelta(minutes=EMAIL_OTP_LOCK_MINUTES) if failed >= EMAIL_OTP_MAX_ATTEMPTS else None
            cursor.execute(
                """
                UPDATE codigos_verificacion
                SET failed_attempts = %s, locked_until = %s
                WHERE id = %s
                """,
                (failed, locked_until, record["id"]),
            )
            if locked_until:
                cursor.execute(
                    "UPDATE usuarios_sistema SET locked_until = %s WHERE id = %s",
                    (locked_until, user_id),
                )
            connection.commit()
            audit_event("email_otp_failed", user_id=user_id, success=False, details={"attempts": failed})
            return False, "locked" if locked_until else "invalid"
        cursor.execute("UPDATE codigos_verificacion SET used = 1 WHERE id = %s", (record["id"],))
        connection.commit()
        audit_event("email_otp_verified", user_id=user_id)
        return True, "ok"
    finally:
        connection.close()


def send_otp_email(to_email, username, code):
    refresh_mail_config_from_env()
    html_body = render_template("email/otp_email.html", username=username, code=code)
    text_body = (
        f"Hola, {username}\n\n"
        f"Recibiste este correo porque solicitaste un codigo de verificacion.\n\n"
        f"Tu codigo de verificacion es: {code}\n\n"
        f"Este codigo expira en {EMAIL_OTP_EXPIRES_MINUTES} minutos.\n\n"
        f"Si no solicitaste este codigo, ignora este mensaje.\n"
        f"Nadie de nuestro equipo te pedira este codigo."
    )
    msg = Message(
        subject="Tu codigo de verificacion - AquaRincon",
        sender=app.config.get("MAIL_DEFAULT_SENDER") or app.config.get("MAIL_USERNAME"),
        recipients=[to_email],
        body=text_body,
        html=html_body,
    )
    mail.send(msg)


def smtp_is_configured():
    refresh_mail_config_from_env()
    username = (app.config.get("MAIL_USERNAME") or "").strip()
    password = (app.config.get("MAIL_PASSWORD") or "").strip()
    if not username or not password:
        return False
    placeholder_patterns = ("tu_", "your_", "example", "demo")
    return not username.lower().startswith(placeholder_patterns) and not password.lower().startswith(placeholder_patterns)


def create_recovery_file_payload(user_id):
    account = get_system_user(user_id)
    if not account:
        raise ValueError("usuario_no_encontrado")
    token = secrets.token_urlsafe(48)
    connection = get_db_connection()
    try:
        cursor = connection.cursor()
        ensure_password_reset_schema(cursor)
        cursor.execute("UPDATE archivos_recuperacion SET revoked = 1 WHERE user_id = %s AND revoked = 0", (user_id,))
        cursor.execute(
            """
            INSERT INTO archivos_recuperacion (user_id, token_hash)
            VALUES (%s, %s)
            """,
            (user_id, hash_secret(token)),
        )
        connection.commit()
    finally:
        connection.close()
    payload = {
        "app": "AquaRincon",
        "type": "password_recovery_file",
        "version": 1,
        "user_id": int(account["id"]),
        "email": account["email"],
        "token": token,
        "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    audit_event("recovery_file_created", user_id=user_id)
    return payload


def verify_recovery_file_payload(payload):
    if not isinstance(payload, dict) or payload.get("app") != "AquaRincon":
        return None
    email = normalize_email(payload.get("email", ""))
    token = str(payload.get("token", "")).strip()
    user_id = payload.get("user_id")
    if not email or not token or not user_id:
        return None
    connection = get_db_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        ensure_password_reset_schema(cursor)
        cursor.execute(
            """
            SELECT ar.*, us.email
            FROM archivos_recuperacion ar
            INNER JOIN usuarios_sistema us ON us.id = ar.user_id
            WHERE ar.user_id = %s AND LOWER(us.email) = LOWER(%s) AND ar.revoked = 0
            ORDER BY ar.id_archivo DESC
            LIMIT 1
            """,
            (user_id, email),
        )
        record = cursor.fetchone()
        if not record or not password_matches(token, record["token_hash"]):
            audit_event("recovery_file_failed", user_id=user_id, success=False)
            return None
        cursor.execute("UPDATE archivos_recuperacion SET last_used_at = NOW() WHERE id_archivo = %s", (record["id_archivo"],))
        connection.commit()
        audit_event("recovery_file_verified", user_id=user_id)
        return record
    finally:
        connection.close()


def create_recovery_code(email):
    connection = get_db_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        ensure_password_reset_schema(cursor)
        cursor.execute("SELECT * FROM usuarios_sistema WHERE LOWER(email) = LOWER(%s) LIMIT 1", (email,))
        account = cursor.fetchone()
        if not account:
            return None
        code = f"{secrets.randbelow(1000000):06d}"
        cursor.execute("UPDATE recuperacion_password SET usado = 1 WHERE LOWER(email) = LOWER(%s) AND usado = 0", (email,))
        cursor.execute(
            """
            INSERT INTO recuperacion_password (email, id_usuario_sistema, codigo_hash, fecha_expiracion)
            VALUES (%s, %s, %s, %s)
            """,
            (account["email"], account["id"], hash_secret(code), datetime.now() + timedelta(minutes=15)),
        )
        connection.commit()
        return code
    finally:
        connection.close()


def verify_recovery_code(email, code):
    connection = get_db_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        ensure_password_reset_schema(cursor)
        cursor.execute(
            """
            SELECT *
            FROM recuperacion_password
            WHERE LOWER(email) = LOWER(%s) AND usado = 0 AND fecha_expiracion >= NOW()
            ORDER BY id_recuperacion DESC LIMIT 1
            """,
            (email,),
        )
        recovery = cursor.fetchone()
        if not recovery or not password_matches(code, recovery["codigo_hash"]):
            return None
        return recovery
    finally:
        connection.close()


def reset_account_password(recovery_id, new_password):
    connection = get_db_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        ensure_password_reset_schema(cursor)
        cursor.execute(
            """
            SELECT * FROM recuperacion_password
            WHERE id_recuperacion = %s AND usado = 0 AND fecha_expiracion >= NOW()
            LIMIT 1
            """,
            (recovery_id,),
        )
        recovery = cursor.fetchone()
        if not recovery:
            return False
        cursor.execute(
            "UPDATE usuarios_sistema SET password = %s, password_changed_at = NOW(), session_version = session_version + 1 WHERE id = %s",
            (hash_secret(new_password), recovery["id_usuario_sistema"]),
        )
        cursor.execute("UPDATE recuperacion_password SET usado = 1 WHERE id_recuperacion = %s", (recovery_id,))
        connection.commit()
        audit_event("password_reset", user_id=recovery["id_usuario_sistema"])
        return True
    finally:
        connection.close()


def reset_account_password_for_user(user_id, new_password):
    connection = get_db_connection()
    try:
        cursor = connection.cursor()
        ensure_password_reset_schema(cursor)
        cursor.execute(
            """
            UPDATE usuarios_sistema
            SET password = %s, password_changed_at = NOW(), session_version = session_version + 1
            WHERE id = %s
            """,
            (hash_secret(new_password), user_id),
        )
        changed = cursor.rowcount > 0
        cursor.execute("UPDATE archivos_recuperacion SET revoked = 1 WHERE user_id = %s AND revoked = 0", (user_id,))
        connection.commit()
        if changed:
            audit_event("password_reset_recovery_file", user_id=user_id)
        return changed
    finally:
        connection.close()


@app.route("/")
def index():
    return render_template("index.html", noticias=list_news(True), puntos_pago=list_payment_points(True))


@app.route("/contacto", methods=["POST"])
def contacto():
    try:
        create_contact_message()
        flash("Mensaje enviado correctamente. El administrador lo revisara pronto.", "success")
    except ValueError:
        flash("Completa nombre, correo valido, asunto y mensaje.", "danger")
    except Exception as exc:
        app.logger.error("Error guardando contacto: %s", exc)
        flash("No fue posible enviar el mensaje.", "danger")
    return redirect(url_for("index") + "#contacto")


@app.route("/facturas/consultar", methods=["GET", "POST"])
def consultar_facturas_publicas():
    codigo = request.values.get("codigo_recibo", "").strip()
    client = None
    invoices = []
    if codigo:
        client = get_client_by_codigo(codigo)
        invoices = get_invoices_by_codigo(codigo) if client else []
        if not client:
            flash("No encontramos usuarios del acueducto con ese codigo.", "danger")
    return render_template("consultar_facturas.html", codigo=codigo, client=client, invoices=invoices)


def resolve_login_destination(role, next_target=""):
    next_target = (next_target or "").strip()
    user_destinations = {
        "pago": (url_for("pagar"), ""),
        "factura": (url_for("dashboard_usuario"), "#consulta-factura"),
        "consultar-factura": (url_for("dashboard_usuario"), "#consulta-factura"),
        "acuerdos": (url_for("dashboard_usuario"), "#pqrs"),
        "cortes": (url_for("dashboard_usuario"), "#facturas"),
        "solicitud-corte": (url_for("dashboard_usuario"), "#pqrs"),
        "puntos-pago": (url_for("dashboard_usuario"), "#puntos-pago-usuario"),
        "pqrs": (url_for("dashboard_usuario"), "#pqrs"),
        "paz-y-salvo": (url_for("dashboard_usuario"), "#paz-salvo"),
    }
    admin_destinations = {
        "pago": (url_for("dashboard_admin"), "#pago-facturas"),
        "factura": (url_for("dashboard_admin"), "#pago-facturas"),
        "consultar-factura": (url_for("dashboard_admin"), "#pago-facturas"),
        "acuerdos": (url_for("dashboard_admin"), "#morosos"),
        "cortes": (url_for("dashboard_admin"), "#morosos"),
        "solicitud-corte": (url_for("dashboard_admin"), "#morosos"),
        "puntos-pago": (url_for("dashboard_admin"), "#puntos-pago"),
        "pqrs": (url_for("dashboard_admin"), "#pqrs-admin"),
        "paz-y-salvo": (url_for("dashboard_admin"), "#pago-facturas"),
        "facturacion": (url_for("dashboard_admin"), "#facturacion"),
        "gestion-usuarios": (url_for("dashboard_admin"), "#sistema"),
        "registro-pagos": (url_for("dashboard_admin"), "#pagos"),
        "morosidad": (url_for("dashboard_admin"), "#morosos"),
        "reportes": (url_for("dashboard_admin"), "#mensajes"),
    }
    destinations = admin_destinations if role == "admin" else user_destinations
    base, anchor = destinations.get(
        next_target,
        (url_for("dashboard_admin" if role == "admin" else "dashboard_usuario"), ""),
    )
    return base + anchor


def start_authenticated_session(account):
    session.clear()
    session["user_id"] = account["id"]
    session["user_login"] = account["email"]
    session["user_name"] = f"{account['nombres']} {account['apellidos']}".strip()
    session["user_nombres"] = account["nombres"]
    session["user_apellidos"] = account["apellidos"]
    session["role"] = account["rol"]
    session["codigo_recibo_vinculado"] = account.get("codigo_recibo_vinculado")
    session["session_version"] = int(account.get("session_version") or 0)
    session["ua_hash"] = user_agent_hash()
    session["login_at"] = int(time.time())
    audit_event("login_success", user_id=account["id"], details=activity_details({"action": "Inicio de sesion exitoso"}))


def start_pending_2fa_session(account, next_target=""):
    session.clear()
    session["pending_2fa_user_id"] = account["id"]
    session["pending_2fa_next"] = next_target or ""
    session["pending_2fa_issued_at"] = int(time.time())
    session["ua_hash"] = user_agent_hash()
    audit_event("login_2fa_pending", user_id=account["id"])


def current_2fa_account():
    user_id = session.get("pending_2fa_user_id") or session.get("user_id")
    return get_system_user(user_id) if user_id else None


def send_login_otp(account):
    if not rate_limit(f"otp_send:{account['id']}", 3, 300):
        audit_event("email_otp_send_rate_limited", user_id=account["id"], success=False)
        return False, "rate_limited"
    if not smtp_is_configured():
        app.logger.warning("SMTP no configurado; no se envio OTP para user_id=%s", account["id"])
        audit_event("email_otp_smtp_missing", user_id=account["id"], success=False, details={"smtp": "not_configured"})
        return False, "smtp_not_configured"
    code = create_otp_code(account["id"])
    send_otp_email(account["email"], f"{account['nombres']} {account['apellidos']}".strip(), code)
    return True, "sent"


@app.route("/login", methods=["GET", "POST"])
def login():
    next_target = request.values.get("next", "").strip()
    if request.method == "GET" and session.get("user_id"):
        return redirect(resolve_login_destination(session.get("role"), next_target))
    if request.method == "POST":
        if not rate_limit("login", 12, 300):
            flash("Demasiados intentos. Espera unos minutos antes de intentar de nuevo.", "danger")
            return render_template("login.html", next_target=next_target)
        email = normalize_email(request.form.get("email", ""))
        password = request.form.get("password", "")
        if not email or not password:
            flash("Ingresa tu correo y contrasena.", "danger")
            return render_template("login.html", next_target=next_target)
        try:
            account, auth_status = authenticate(email, password)
        except Exception as exc:
            app.logger.error("Error de autenticacion: %s", exc)
            flash("No fue posible conectar con la base de datos ACUEDUCTO.", "danger")
            return render_template("login.html", next_target=next_target)
        if not account:
            message = "Cuenta bloqueada temporalmente por multiples intentos fallidos." if auth_status == "locked" else "Correo o contrasena incorrectos."
            flash(message, "danger")
            return render_template("login.html", next_target=next_target)

        start_pending_2fa_session(account, next_target)
        try:
            sent, status = send_login_otp(account)
            if not sent:
                session.clear()
                if status == "smtp_not_configured":
                    flash("No fue posible enviar el codigo porque el correo SMTP no esta configurado.", "danger")
                else:
                    flash("Espera unos minutos antes de solicitar otro codigo.", "warning")
                return redirect(url_for("login", next=next_target) if next_target else url_for("login"))
            else:
                flash("Contrasena validada. Te enviamos un codigo de 6 digitos a tu correo.", "success")
        except Exception as exc:
            app.logger.error("Error enviando OTP de login: %s", exc)
            audit_event("email_otp_send_failed", user_id=account["id"], success=False)
            session.clear()
            flash("No fue posible enviar el codigo de verificacion. Revisa la configuracion SMTP.", "danger")
            return redirect(url_for("login", next=next_target) if next_target else url_for("login"))
        return redirect(url_for("verify_email_otp"))
    return render_template("login.html", next_target=next_target)


@app.route("/register", methods=["POST"])
def register():
    nombres = request.form.get("nombres", "").strip()
    apellidos = request.form.get("apellidos", "").strip()
    telefono = request.form.get("telefono", "").strip() or None
    email = normalize_email(request.form.get("email", ""))
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")
    register_data = {
        "nombres": nombres,
        "apellidos": apellidos,
        "telefono": telefono or "",
        "email": email,
    }
    if not nombres or not email or not password or not confirm_password:
        flash("Completa todos los campos para crear la cuenta.", "danger")
        return render_template("login.html", register_data=register_data, show_register=True)
    if password != confirm_password:
        flash("Las contrasenas no coinciden.", "danger")
        return render_template("login.html", register_data=register_data, show_register=True)
    password_errors = validate_password_policy(password)
    if password_errors:
        flash("La contrasena debe incluir " + ", ".join(password_errors) + ".", "danger")
        return render_template("login.html", register_data=register_data, show_register=True)
    if not request.form.get("data_consent"):
        flash("Debes aceptar la Politica de Tratamiento de Datos Personales para registrarte.", "danger")
        return render_template("login.html", register_data=register_data, show_register=True)
    try:
        save_system_user({"nombres": nombres, "apellidos": apellidos, "telefono": telefono, "email": email, "password": password, "rol": "usuario", "codigo_recibo_vinculado": None})
        account = get_system_user_by_email(email)
        if account:
            connection = get_db_connection()
            try:
                cursor = connection.cursor()
                cursor.execute("UPDATE usuarios_sistema SET data_consent = 1, data_consent_at = NOW() WHERE id = %s", (account["id"],))
                connection.commit()
            finally:
                connection.close()
        audit_event("register_success", details={"email": email, "data_consent": "1"})
        flash("Cuenta creada correctamente. Ahora inicia sesion.", "success")
    except Exception as exc:
        app.logger.error("Error de registro: %s", exc)
        flash("No fue posible registrar la cuenta.", "danger")
        return render_template("login.html", register_data=register_data, show_register=True)
    return redirect(url_for("login"))


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        if not rate_limit("forgot_password", 5, 900):
            flash("Demasiadas solicitudes de recuperacion. Intenta mas tarde.", "danger")
            return render_template("forgot_password.html", step="request")
        email = normalize_email(request.form.get("email", ""))
        if not email:
            flash("Ingresa tu correo.", "danger")
            return render_template("forgot_password.html", step="request", email=email)
        account = get_system_user_by_email(email)
        if not account:
            audit_event("password_recovery_unknown_email", success=False, details={"email": email})
            flash("Si ese correo esta registrado, recibiras un codigo.", "info")
            return render_template("forgot_password.html", step="request", email=email)
        if not smtp_is_configured():
            audit_event("password_recovery_smtp_missing", user_id=account["id"], success=False)
            flash("No fue posible enviar el codigo porque el correo SMTP no esta configurado.", "danger")
            return render_template("forgot_password.html", step="request", email=email)
        try:
            code = create_recovery_code(email)
            send_otp_email(account["email"], f"{account['nombres']} {account['apellidos']}".strip(), code)
            session["recovery_email"] = email
            audit_event("password_recovery_email_sent", user_id=account["id"])
            flash("Te enviamos un codigo de recuperacion al correo registrado.", "success")
            return render_template("forgot_password.html", step="verify", email=email)
        except Exception as exc:
            app.logger.error("Error enviando email de recuperacion: %s", exc)
            audit_event("password_recovery_email_failed", user_id=account["id"], success=False, details={"error": str(exc)})
            flash("No fue posible enviar el codigo. Verifica la configuracion SMTP y vuelve a intentar.", "danger")
            return render_template("forgot_password.html", step="request", email=email)
    return render_template("forgot_password.html", step="request")


@app.route("/verify-reset-code", methods=["POST"])
def verify_reset_code():
    email = normalize_email(request.form.get("email", ""))
    code = request.form.get("code", "").strip()
    recovery = verify_recovery_code(email, code) if email and code else None
    if not recovery:
        flash("El codigo es incorrecto o ya expiro.", "danger")
        return render_template("forgot_password.html", step="verify", email=email)
    session["verified_recovery_id"] = recovery["id_recuperacion"]
    flash("Codigo verificado. Ahora crea tu nueva contrasena.", "success")
    return render_template("forgot_password.html", step="reset", email=email)


@app.route("/verify-recovery-file", methods=["POST"])
def verify_recovery_file():
    uploaded = request.files.get("recovery_file")
    if not uploaded or not uploaded.filename:
        flash("Selecciona tu archivo de recuperacion.", "danger")
        return render_template("forgot_password.html", step="request")
    if not uploaded.filename.lower().endswith(".json"):
        flash("El archivo de recuperacion debe ser un JSON descargado desde tu perfil.", "danger")
        return render_template("forgot_password.html", step="request")
    try:
        payload = json.loads(uploaded.read(16 * 1024).decode("utf-8"))
    except Exception:
        flash("No fue posible leer el archivo de recuperacion.", "danger")
        return render_template("forgot_password.html", step="request")
    record = verify_recovery_file_payload(payload)
    if not record:
        flash("El archivo de recuperacion no es valido o fue reemplazado por uno nuevo.", "danger")
        return render_template("forgot_password.html", step="request")
    session["verified_recovery_file_user_id"] = int(record["user_id"])
    session.pop("verified_recovery_id", None)
    flash("Archivo validado. Ahora crea tu nueva contrasena.", "success")
    return render_template("forgot_password.html", step="reset", email=record["email"])


@app.route("/reset-password", methods=["POST"])
def reset_password():
    recovery_id = session.get("verified_recovery_id")
    recovery_file_user_id = session.get("verified_recovery_file_user_id")
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")
    if not recovery_id and not recovery_file_user_id:
        flash("Primero debes verificar el codigo o tu archivo de recuperacion.", "warning")
        return redirect(url_for("forgot_password"))
    password_errors = validate_password_policy(password)
    if password_errors or password != confirm_password:
        flash("La contrasena debe coincidir e incluir " + ", ".join(password_errors or ["los requisitos de seguridad"]) + ".", "danger")
        return render_template("forgot_password.html", step="reset")
    if recovery_file_user_id:
        if reset_account_password_for_user(recovery_file_user_id, password):
            session.pop("verified_recovery_file_user_id", None)
            flash("Contrasena actualizada. Ya puedes iniciar sesion.", "success")
            return redirect(url_for("login"))
        flash("La solicitud expiro.", "warning")
        return redirect(url_for("forgot_password"))
    if reset_account_password(recovery_id, password):
        session.pop("verified_recovery_id", None)
        flash("Contrasena actualizada. Ya puedes iniciar sesion.", "success")
        return redirect(url_for("login"))
    flash("La solicitud expiro.", "warning")
    return redirect(url_for("forgot_password"))


@app.route("/dashboard/usuario")
@login_required("usuario")
def dashboard_usuario():
    codigo = session.get("codigo_recibo_vinculado")
    factura_codigo = request.args.get("factura_codigo", "").strip()
    client = None
    invoices = []
    factura_consulta = None
    factura_consulta_client = None
    factura_consulta_invoices = []
    pending_months = 0
    pending_total = 0
    puntos_pago = list_payment_points(True)
    if codigo:
        client = get_client_by_codigo(codigo)
        invoices = get_invoices_by_codigo(codigo)
        pending = [i for i in invoices if i["estado"] in ("pendiente", "vencida")]
        pending_months = len(pending)
        pending_total = sum(float(i["valor_total"]) for i in pending)
    if factura_codigo:
        factura_consulta_client = get_client_by_codigo(factura_codigo)
        if factura_consulta_client:
            factura_consulta_invoices = get_invoices_by_codigo(factura_codigo)
            pending_consulta = [i for i in factura_consulta_invoices if i["estado"] in ("pendiente", "vencida")]
            factura_consulta = pending_consulta[0] if pending_consulta else (factura_consulta_invoices[0] if factura_consulta_invoices else None)
        else:
            flash("No encontramos facturas para ese codigo de usuario.", "warning")
    current_user_data = get_system_user(session["user_id"])
    return render_template(
        "dashboard_usuario.html",
        user_name=current_user_name(),
        current_user_data=current_user_data,
        codigo_recibo_vinculado=codigo,
        client=client,
        invoices=invoices,
        factura_codigo=factura_codigo,
        factura_consulta=factura_consulta,
        factura_consulta_client=factura_consulta_client,
        factura_consulta_invoices=factura_consulta_invoices,
        pqrs=list_pqrs_for_user(session["user_id"], codigo),
        puntos_pago=puntos_pago,
        google_maps_api_key=google_maps_api_key(),
        pending_months=pending_months,
        pending_total=pending_total,
    )


@app.route("/dashboard/admin")
@login_required("admin")
def dashboard_admin():
    edit_system_id = request.args.get("editar_sistema", type=int)
    edit_client_id = request.args.get("editar_acueducto", type=int)
    edit_system_user = get_system_user(edit_system_id) if edit_system_id else None
    edit_client = get_acueducto_user(edit_client_id) if edit_client_id else None
    edit_point_id = request.args.get("editar_punto", type=int)
    edit_news_id = request.args.get("editar_noticia", type=int)
    pqrs_status = request.args.get("estado_pqrs", "").strip()
    invoice_search = request.args.get("buscar_factura", "").strip()
    activity_filters = {
        "user_id": request.args.get("audit_user", type=int),
        "event": request.args.get("audit_event", "").strip(),
        "date_from": request.args.get("audit_from", "").strip(),
        "date_to": request.args.get("audit_to", "").strip(),
    }
    current_user_data = get_system_user(session["user_id"])
    return render_template(
        "dashboard_admin.html",
        user_name=current_user_name(),
        current_user_data=current_user_data,
        usuarios_sistema=list_system_users(),
        usuarios_acueducto=list_acueducto_users(),
        edit_system_user=edit_system_user,
        edit_client=edit_client,
        edit_point=get_payment_point(edit_point_id) if edit_point_id else None,
        edit_news=get_news(edit_news_id) if edit_news_id else None,
        billing=get_admin_billing_data(),
        activity_report=get_admin_activity_report(activity_filters),
        activity_filters=activity_filters,
        admin_invoice_search=invoice_search,
        admin_invoices=search_invoices(invoice_search),
        pqrs_status=pqrs_status,
        pqrs_items=list_all_pqrs(pqrs_status or None),
        puntos_pago=list_payment_points(False),
        noticias=list_news(False),
        mensajes_contacto=list_contact_messages(),
        google_maps_api_key=google_maps_api_key(),
        tarifa_mensual=TARIFA_MENSUAL,
    )


@app.route("/admin/sistema/crear", methods=["POST"])
@login_required("admin")
def admin_crear_usuario_sistema():
    try:
        save_system_user(get_system_user_form_data())
        flash("Usuario de sistema creado correctamente.", "success")
    except ValueError as exc:
        message = "La contrasena debe tener minimo 10 caracteres, mayuscula, minuscula, numero y simbolo."
        if str(exc) == "codigo_recibo_invalido":
            message = "El codigo de recibo vinculado no existe en usuarios_acueducto."
        flash(message, "danger")
    except Exception as exc:
        app.logger.error("Error creando usuario sistema: %s", exc)
        flash("No fue posible crear el usuario de sistema.", "danger")
    return redirect(url_for("dashboard_admin"))

@app.route('/tratamiento-de-datos')
def privacy_policy():
    return render_template('tratamiento_de_datos.html')

@app.route("/admin/sistema/<int:user_id>/editar", methods=["POST"])
@login_required("admin")
def admin_editar_usuario_sistema(user_id):
    try:
        save_system_user(get_system_user_form_data(), user_id=user_id)
        flash("Usuario de sistema actualizado.", "success")
    except ValueError as exc:
        message = "La contrasena debe tener minimo 10 caracteres, mayuscula, minuscula, numero y simbolo."
        if str(exc) == "codigo_recibo_invalido":
            message = "El codigo de recibo vinculado no existe."
        flash(message, "danger")
    except Exception as exc:
        app.logger.error("Error actualizando usuario sistema: %s", exc)
        flash("No fue posible actualizar el usuario de sistema.", "danger")
    return redirect(url_for("dashboard_admin"))


@app.route("/admin/sistema/<int:user_id>/eliminar", methods=["POST"])
@login_required("admin")
def admin_eliminar_usuario_sistema(user_id):
    try:
        delete_system_user(user_id)
        flash("Usuario de sistema eliminado.", "success")
    except Exception as exc:
        app.logger.error("Error eliminando usuario sistema: %s", exc)
        flash("No fue posible eliminar el usuario de sistema.", "danger")
    return redirect(url_for("dashboard_admin"))


@app.route("/admin/acueducto/crear", methods=["POST"])
@login_required("admin")
def admin_crear_usuario_acueducto():
    try:
        save_acueducto_user(get_acueducto_form_data())
        flash("Cliente del acueducto creado correctamente.", "success")
    except Exception as exc:
        app.logger.error("Error creando cliente acueducto: %s", exc)
        flash("No fue posible crear el cliente del acueducto.", "danger")
    return redirect(url_for("dashboard_admin"))


@app.route("/admin/acueducto/<int:user_id>/editar", methods=["POST"])
@login_required("admin")
def admin_editar_usuario_acueducto(user_id):
    try:
        save_acueducto_user(get_acueducto_form_data(), user_id=user_id)
        flash("Cliente del acueducto actualizado.", "success")
    except Exception as exc:
        app.logger.error("Error actualizando cliente acueducto: %s", exc)
        flash("No fue posible actualizar el cliente del acueducto.", "danger")
    return redirect(url_for("dashboard_admin"))


@app.route("/admin/acueducto/<int:user_id>/eliminar", methods=["POST"])
@login_required("admin")
def admin_eliminar_usuario_acueducto(user_id):
    try:
        delete_acueducto_user(user_id)
        flash("Cliente del acueducto eliminado.", "success")
    except Exception as exc:
        app.logger.error("Error eliminando cliente acueducto: %s", exc)
        flash("No fue posible eliminar el cliente porque puede tener facturas o pagos.", "danger")
    return redirect(url_for("dashboard_admin"))


@app.route("/admin/facturacion/generar", methods=["POST"])
@login_required("admin")
def admin_generar_facturacion():
    period = request.form.get("periodo", "").strip() or current_period()
    try:
        created, emailed, errors = generate_monthly_invoices(period=period, send_emails=True)
        if created == 0:
            flash(f"Facturacion {period}: no hay facturas nuevas pendientes.", "info")
        elif emailed == created:
            flash(f"Facturacion {period}: {created} factura(s) creadas y {emailed} correo(s) enviados.", "success")
        elif emailed > 0:
            flash(f"Facturacion {period}: {created} factura(s) creadas, {emailed} de {created} correo(s) enviados. Algunos correos no pudieron enviarse.", "warning")
        else:
            first_error = errors[0] if errors else "Error desconocido"
            flash(f"Facturacion {period}: {created} factura(s) creadas pero no se pudo enviar ningun correo. Motivo: {first_error}", "warning")
            app.logger.warning("Errores de envio en facturacion %s: %s", period, " | ".join(errors))
    except Exception as exc:
        app.logger.error("Error generando facturacion: %s", exc)
        flash("No fue posible generar la facturacion.", "danger")
    return redirect(url_for("dashboard_admin"))


@app.route("/admin/pagos/<int:report_id>/verificar", methods=["POST"])
@login_required("admin")
def admin_verificar_pago(report_id):
    verified = verify_payment_report(report_id, session["user_id"])
    flash("Pago verificado y facturas actualizadas." if verified else "El reporte no esta pendiente.", "success" if verified else "warning")
    return redirect(url_for("dashboard_admin"))


@app.route("/admin/pagos/<int:report_id>/rechazar", methods=["POST"])
@login_required("admin")
def admin_rechazar_pago(report_id):
    observation = request.form.get("observacion", "").strip()
    rejected = reject_payment_report(report_id, session["user_id"], observation)
    flash("Pago rechazado." if rejected else "El reporte no esta pendiente.", "success" if rejected else "warning")
    return redirect(url_for("dashboard_admin"))


@app.route("/admin/permisos/<int:user_id>/conceder", methods=["POST"])
@login_required("admin")
def admin_conceder_permiso_pago(user_id):
    grant_payment_permission(user_id, session["user_id"], request.form.get("observacion", "").strip())
    flash("Permiso de acuerdo de pago concedido. El cliente podra pagar minimo 3 meses.", "success")
    return redirect(url_for("dashboard_admin"))


@app.route("/admin/facturas/<int:invoice_id>/pagar", methods=["POST"])
@login_required("admin")
def admin_marcar_factura_pagada(invoice_id):
    paid = mark_invoice_paid(invoice_id, session["user_id"])
    flash("Factura marcada como pagada." if paid else "La factura ya estaba pagada o no existe.", "success" if paid else "warning")
    search = request.form.get("buscar_factura", "").strip()
    return redirect(url_for("dashboard_admin", buscar_factura=search) + "#pago-facturas")


@app.route("/admin/pqrs/<int:pqrs_id>/responder", methods=["POST"])
@login_required("admin")
def admin_responder_pqrs(pqrs_id):
    try:
        update_pqrs(pqrs_id, session["user_id"])
        flash("PQRS actualizada correctamente.", "success")
    except Exception as exc:
        app.logger.error("Error actualizando PQRS: %s", exc)
        flash("No fue posible actualizar la PQRS.", "danger")
    return redirect(url_for("dashboard_admin", estado_pqrs=request.form.get("filtro_estado", "")) + "#pqrs-admin")


@app.route("/admin/contacto/<int:message_id>/leer", methods=["POST"])
@login_required("admin")
def admin_marcar_contacto_leido(message_id):
    mark_contact_read(message_id)
    flash("Mensaje marcado como leido.", "success")
    return redirect(url_for("dashboard_admin") + "#mensajes")


@app.route("/admin/puntos/crear", methods=["POST"])
@login_required("admin")
def admin_crear_punto_pago():
    try:
        save_payment_point()
        flash("Punto de pago creado.", "success")
    except ValueError:
        flash("Completa nombre, direccion y horario. Usa un enlace valido de Google Maps y una imagen PNG, JPG, WEBP o GIF.", "danger")
    return redirect(url_for("dashboard_admin") + "#puntos-pago")


@app.route("/admin/puntos/<int:point_id>/editar", methods=["POST"])
@login_required("admin")
def admin_editar_punto_pago(point_id):
    try:
        save_payment_point(point_id)
        flash("Punto de pago actualizado.", "success")
    except ValueError:
        flash("Completa nombre, direccion y horario. Usa un enlace valido de Google Maps y una imagen PNG, JPG, WEBP o GIF.", "danger")
    return redirect(url_for("dashboard_admin") + "#puntos-pago")


@app.route("/admin/puntos/<int:point_id>/eliminar", methods=["POST"])
@login_required("admin")
def admin_eliminar_punto_pago(point_id):
    delete_payment_point(point_id)
    flash("Punto de pago eliminado.", "success")
    return redirect(url_for("dashboard_admin") + "#puntos-pago")


@app.route("/admin/noticias/crear", methods=["POST"])
@login_required("admin")
def admin_crear_noticia():
    try:
        save_news()
        flash("Noticia creada.", "success")
    except ValueError:
        flash("Completa titulo y resumen. La imagen debe ser PNG, JPG, WEBP o GIF.", "danger")
    return redirect(url_for("dashboard_admin") + "#noticias-admin")


@app.route("/admin/noticias/<int:news_id>/editar", methods=["POST"])
@login_required("admin")
def admin_editar_noticia(news_id):
    try:
        save_news(news_id)
        flash("Noticia actualizada.", "success")
    except ValueError:
        flash("Completa titulo y resumen. La imagen debe ser PNG, JPG, WEBP o GIF.", "danger")
    return redirect(url_for("dashboard_admin") + "#noticias-admin")


@app.route("/admin/noticias/<int:news_id>/eliminar", methods=["POST"])
@login_required("admin")
def admin_eliminar_noticia(news_id):
    delete_news(news_id)
    flash("Noticia eliminada.", "success")
    return redirect(url_for("dashboard_admin") + "#noticias-admin")


@app.route("/perfil/cambiar-contrasena", methods=["POST"])
@login_required()
def cambiar_contrasena():
    current_pw = request.form.get("current_password", "")
    new_pw = request.form.get("new_password", "")
    confirm_pw = request.form.get("confirm_password", "")
    account = get_system_user(session["user_id"])
    if not account or not password_matches(current_pw, account["password"]):
        flash("La contrasena actual no es correcta.", "danger")
        target = "dashboard_admin" if session.get("role") == "admin" else "dashboard_usuario"
        return redirect(url_for(target))
    errors = validate_password_policy(new_pw)
    if errors:
        flash("La contrasena debe incluir: " + ", ".join(errors) + ".", "danger")
        target = "dashboard_admin" if session.get("role") == "admin" else "dashboard_usuario"
        return redirect(url_for(target))
    if new_pw != confirm_pw:
        flash("Las contrasenas nuevas no coinciden.", "danger")
        target = "dashboard_admin" if session.get("role") == "admin" else "dashboard_usuario"
        return redirect(url_for(target))
    connection = get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            "UPDATE usuarios_sistema SET password = %s, password_changed_at = NOW(), session_version = session_version + 1 WHERE id = %s",
            (hash_secret(new_pw), session["user_id"]),
        )
        connection.commit()
        log_user_activity("password_changed")
        flash("Contrasena actualizada correctamente.", "success")
    except Exception as exc:
        app.logger.error("Error cambiando contrasena: %s", exc)
        flash("Error al cambiar la contrasena.", "danger")
    finally:
        connection.close()
    target = "dashboard_admin" if session.get("role") == "admin" else "dashboard_usuario"
    return redirect(url_for(target))


@app.route("/perfil/actualizar", methods=["POST"])
@login_required()
def actualizar_perfil():
    try:
        update_profile(
            nombres=request.form.get("nombres"),
            apellidos=request.form.get("apellidos"),
            cedula=request.form.get("cedula"),
            telefono=request.form.get("telefono"),
        )
        log_user_activity("profile_updated")
        flash("Perfil actualizado con exito.", "success")
    except ValueError:
        flash("El nombre debe tener al menos 2 caracteres.", "danger")
    except Exception as exc:
        app.logger.error("Error actualizando perfil: %s", exc)
        flash("Error al procesar la solicitud.", "danger")
    target = "dashboard_admin" if session.get("role") == "admin" else "dashboard_usuario"
    return redirect(url_for(target))


@app.route("/perfil/archivo-recuperacion")
@login_required()
def descargar_archivo_recuperacion():
    try:
        payload = create_recovery_file_payload(session["user_id"])
    except Exception as exc:
        app.logger.error("Error generando archivo de recuperacion: %s", exc)
        flash("No fue posible generar el archivo de recuperacion.", "danger")
        target = "dashboard_admin" if session.get("role") == "admin" else "dashboard_usuario"
        return redirect(url_for(target))
    data = json.dumps(payload, ensure_ascii=True, indent=2).encode("utf-8")
    filename = f"aquarincon-recuperacion-{session['user_id']}.json"
    log_user_activity("recovery_file_downloaded", {"filename": filename})
    return send_file(
        io.BytesIO(data),
        mimetype="application/json",
        as_attachment=True,
        download_name=filename,
    )


@app.route("/email/verify", methods=["GET", "POST"])
def verify_email_otp():
    account = current_2fa_account()
    if not account:
        flash("Inicia sesion para recibir un codigo de verificacion.", "warning")
        return redirect(url_for("login"))

    pending_login = bool(session.get("pending_2fa_user_id"))
    next_key = session.get("pending_2fa_next", "") if pending_login else request.values.get("next", "")
    next_url = resolve_login_destination(account["rol"], next_key) if pending_login else url_for(
        "dashboard_admin" if session.get("role") == "admin" else "dashboard_usuario"
    )

    if request.method == "GET":
        if request.args.get("resend") == "1":
            try:
                sent, status = send_login_otp(account)
                if sent:
                    flash("Hemos enviado un nuevo codigo de verificacion a tu correo.", "success")
                elif status == "smtp_not_configured":
                    flash("No fue posible enviar el codigo porque el correo SMTP no esta configurado.", "danger")
                else:
                    flash("Espera unos minutos antes de solicitar otro codigo.", "warning")
            except Exception as exc:
                app.logger.error("Error reenviando OTP: %s", exc)
                audit_event("email_otp_send_failed", user_id=account["id"], success=False)
                flash("No fue posible enviar el codigo. Verifica la configuracion del correo.", "danger")
        return render_template("auth/verify_email.html", next_url=next_url)
    otp_code = request.form.get("otp_code", "").strip()
    ok, status = verify_otp_code(account["id"], otp_code)
    if ok:
        if pending_login:
            start_authenticated_session(account)
        session["email_otp_verified_at"] = time.time()
        flash("Identidad verificada correctamente.", "success")
        return redirect(next_url)
    messages = {
        "locked": "Tu cuenta quedo bloqueada temporalmente por multiples codigos incorrectos.",
        "expired": "El codigo expiro. Solicita uno nuevo para continuar.",
        "invalid": "Codigo incorrecto. Revisa los 6 digitos e intenta de nuevo.",
    }
    flash(messages.get(status, "Codigo incorrecto o expirado."), "danger")
    return render_template("auth/verify_email.html", next_url=next_url)


@app.route("/usuario/paz-y-salvo/pdf")
@login_required("usuario")
def descargar_paz_y_salvo():
    codigo = session.get("codigo_recibo_vinculado")
    client, pending, paid = get_paz_y_salvo_data(codigo)
    if not client:
        flash("Tu cuenta no tiene codigo de usuario vinculado.", "warning")
        return redirect(url_for("dashboard_usuario") + "#paz-salvo")
    if pending:
        flash("No puedes descargar el paz y salvo porque tienes pagos pendientes.", "warning")
        return redirect(url_for("dashboard_usuario") + "#paz-salvo")
    pdf = build_paz_y_salvo_pdf(codigo)
    if not pdf:
        flash("Error al generar el documento.", "danger")
        return redirect(url_for("dashboard_usuario") + "#paz-salvo")
    log_user_activity("paz_y_salvo_downloaded", {"receipt": codigo, "filename": "paz-y-salvo.pdf"})
    return Response(pdf, mimetype="application/pdf", headers={"Content-Disposition": "attachment; filename=paz-y-salvo.pdf"})


@app.route("/usuario/pqrs/crear", methods=["POST"])
@login_required("usuario")
def usuario_crear_pqrs():
    try:
        create_pqrs()
        log_user_activity("pqrs_created", {"subject": request.form.get("asunto", "").strip()[:120]})
        flash("PQRS radicada correctamente.", "success")
    except ValueError:
        flash("Completa asunto y descripcion para radicar la PQRS.", "danger")
    return redirect(url_for("dashboard_usuario") + "#pqrs")


@app.route("/comprobante/<int:report_id>")
@login_required()
def comprobante_image(report_id):
    connection = get_db_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        ensure_billing_schema(cursor)
        cursor.execute("SELECT comprobante FROM reportes_pago WHERE id_reporte = %s", (report_id,))
        row = cursor.fetchone()
        if not row or not row["comprobante"]:
            return "No encontrado", 404
        return Response(row["comprobante"], mimetype="image/png")
    finally:
        connection.close()


@app.route("/pagar", methods=["GET", "POST"])
@login_required()
def pagar():
    user = None
    pending = []
    permission = None
    codigo = request.args.get("codigo_recibo", "").strip() or session.get("codigo_recibo_vinculado") or ""
    if request.method == "POST":
        action = request.form.get("action")
        codigo = request.form.get("codigo_recibo", "").strip()
        if not codigo:
            flash("Ingresa el codigo de recibo.", "danger")
            return render_template("pagar.html", codigo=codigo, tarifa_mensual=TARIFA_MENSUAL)
        if action == "consultar":
            user, pending, permission = get_client_billing_summary_by_code(codigo)
            if not user:
                flash("No existe un cliente con ese codigo de recibo.", "danger")
        elif action == "reportar":
            meses = request.form.get("meses", type=int) or 0
            metodo_raw = request.form.get("metodo_pago", "fisico")
            metodo = "fisico" if metodo_raw == "fisico" else "digital"
            referencia = request.form.get("referencia", "").strip()
            codigo_confirmacion = request.form.get("codigo_confirmacion", "").strip()

            # Read comprobante image binary if provided
            comprobante = None
            if metodo_raw in ("transferencia", "consignacion"):
                file = request.files.get("comprobante")
                if file and file.filename:
                    file.seek(0)
                    comprobante = file.read()

            ok, message, data = create_payment_report(codigo, codigo_confirmacion, meses, metodo, referencia, comprobante)
            flash(message, "success" if ok else "warning")
            if ok:
                log_user_activity(
                    "payment_report_created",
                    {"receipt": codigo, "months": meses, "method": metodo, "reference": referencia[:80]},
                )
                return redirect(url_for("dashboard_usuario" if session.get("role") == "usuario" else "dashboard_admin"))
            if data:
                user, pending, permission = data["user"], data["pending"], data["permission"]
    elif codigo:
        user, pending, permission = get_client_billing_summary_by_code(codigo)

    return render_template("pagar.html", codigo=codigo, user=user, pending=pending, permission=permission, tarifa_mensual=TARIFA_MENSUAL)


@app.route("/facturas/<int:invoice_id>/pdf")
@login_required()
def descargar_factura_pdf(invoice_id):
    if not can_access_invoice(invoice_id):
        flash("No tienes permisos para descargar esta factura.", "danger")
        return redirect(url_for("dashboard_usuario" if session.get("role") == "usuario" else "dashboard_admin"))
    pdf = build_invoice_pdf(invoice_id)
    if not pdf:
        flash("No se encontro la factura solicitada.", "danger")
        return redirect(url_for("dashboard_usuario" if session.get("role") == "usuario" else "dashboard_admin"))
    log_user_activity("invoice_pdf_downloaded", {"invoice_id": invoice_id, "filename": f"factura-{invoice_id}.pdf"})
    return Response(pdf, mimetype="application/pdf", headers={"Content-Disposition": f"attachment; filename=factura-{invoice_id}.pdf"})


@app.route("/facturas/<int:invoice_id>/pdf-publico")
def descargar_factura_pdf_publico(invoice_id):
    codigo = request.args.get("codigo_recibo", "").strip()
    invoice = None
    for item in get_invoices_by_codigo(codigo):
        if int(item["id_factura"]) == int(invoice_id):
            invoice = item
            break
    if not codigo or not invoice:
        flash("No fue posible validar el codigo para descargar esta factura.", "danger")
        return redirect(url_for("consultar_facturas_publicas", codigo_recibo=codigo))
    pdf = build_invoice_pdf(invoice_id)
    audit_event(
        "public_invoice_pdf_downloaded",
        details=activity_details({"invoice_id": invoice_id, "filename": f"factura-{invoice_id}.pdf"}),
    )
    return Response(pdf, mimetype="application/pdf", headers={"Content-Disposition": f"attachment; filename=factura-{invoice_id}.pdf"})


@app.route("/logout")
def logout():
    if session.get("user_id"):
        audit_event("logout", user_id=session.get("user_id"), details=activity_details({"action": "Cerro sesion"}))
    session.clear()
    flash("Sesion cerrada correctamente.", "success")
    return redirect(url_for("login"))


@app.route("/api/chat", methods=["POST"])
def chat():
    if not rate_limit("chat", 30, 60):
        return jsonify({"error": "Demasiadas consultas. Intenta de nuevo en un minuto."}), 429
    data = request.get_json(force=True)
    user_message = data.get("message", "").strip()
    if not user_message:
        return jsonify({"error": "Mensaje vacio"}), 400

    quick_reply = quick_chat_reply(user_message)
    if quick_reply:
        return jsonify({"reply": quick_reply, "source": "quick"})

    cached_reply = get_cached_chat_reply(user_message)
    if cached_reply:
        return jsonify({"reply": cached_reply, "source": "cache"})

    try:
        chat_model = get_model()
        prompt = f"{SYSTEM_PROMPT}\nPregunta del usuario: {user_message}\nRespuesta breve:"
        with chat_model.chat_session():
            reply = chat_model.generate(prompt, max_tokens=CHAT_MAX_TOKENS, temp=0.35, top_k=25, top_p=0.85)
        reply = reply.strip()
        set_cached_chat_reply(user_message, reply)
        return jsonify({"reply": reply, "source": "model"})
    except Exception as exc:
        app.logger.error("Error GPT4All: %s", exc)
        return jsonify({"error": "Error interno al procesar tu consulta."}), 500


@app.route("/api/chat/stream", methods=["POST"])
def chat_stream():
    if not rate_limit("chat_stream", 30, 60):
        return jsonify({"error": "Demasiadas consultas. Intenta de nuevo en un minuto."}), 429
    data = request.get_json(force=True)
    user_message = data.get("message", "").strip()
    if not user_message:
        return jsonify({"error": "Mensaje vacio"}), 400

    def generate():
        quick_reply = quick_chat_reply(user_message)
        if quick_reply:
            yield f"data: {json.dumps({'token': quick_reply})}\n\n"
            yield "data: [DONE]\n\n"
            return

        cached_reply = get_cached_chat_reply(user_message)
        if cached_reply:
            yield f"data: {json.dumps({'token': cached_reply})}\n\n"
            yield "data: [DONE]\n\n"
            return

        chat_model = get_model()
        full_reply = []
        prompt = f"{SYSTEM_PROMPT}\nPregunta del usuario: {user_message}\nRespuesta breve:"
        with chat_model.chat_session():
            for token in chat_model.generate(prompt, max_tokens=CHAT_MAX_TOKENS, temp=0.35, top_k=25, top_p=0.85, streaming=True):
                full_reply.append(token)
                yield f"data: {json.dumps({'token': token})}\n\n"
        set_cached_chat_reply(user_message, "".join(full_reply).strip())
        yield "data: [DONE]\n\n"

    return Response(stream_with_context(generate()), content_type="text/event-stream", headers={"Cache-Control": "no-cache"})


if __name__ == "__main__":
    app.run(
        debug=os.getenv("FLASK_DEBUG", "0") == "1",
        host=os.getenv("FLASK_HOST", "0.0.0.0"),
        port=int(os.getenv("FLASK_PORT", "5000")),
        use_reloader=False,
    )
