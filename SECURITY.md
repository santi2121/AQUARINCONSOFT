# Seguridad de AquaRincon

## Cambios implementados

- Autenticacion robusta con hashing `scrypt` de Werkzeug, migracion automatica de claves heredadas en texto plano, politica de contrasena fuerte y bloqueo temporal tras intentos fallidos.
- Sesiones protegidas con expiracion, cookies `HttpOnly`, `SameSite=Lax`, version de sesion revocable y deteccion de cambio de dispositivo por hash de `User-Agent`.
- CSRF automatico para formularios `POST`, rate limiting por IP, headers HTTP seguros y CSP defensiva.
- 2FA TOTP compatible con Google Authenticator. Desde el perfil se genera la clave, se confirma con codigo de 6 digitos y se puede desactivar con un codigo valido.
- PIN de seguridad hasheado para operaciones administrativas sensibles. El PIN se confirma durante una ventana corta antes de eliminar, verificar pagos, generar facturacion o cambiar estados criticos.
- Auditoria en `auditoria_seguridad` para inicios de sesion, fallos, CSRF rechazado, logout, cambios 2FA, PIN y acciones administrativas sensibles. Los detalles sensibles se redactan.
- Cifrado AES-256-GCM de datos personales de clientes (`cedula`, `telefono`, `email_servicio`) al guardar o actualizar registros. Los datos cifrados se serializan en hexadecimal con prefijo `enc:v2:`.

## Variables de entorno recomendadas

- `FLASK_SECRET_KEY`: secreto largo y unico de la aplicacion.
- `DATA_ENCRYPTION_KEY`: llave hexadecimal de 32 bytes para AES-GCM, o una frase secreta que se deriva con `scrypt`. No la guardes en el repositorio.
- `SESSION_COOKIE_SECURE=1`: obligatorio cuando se sirve por HTTPS.
- `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_HOST`, `MYSQL_DB`: usuario de base de datos con privilegios minimos.
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`: para enviar codigos de recuperacion fuera de modo demostracion.

## Pruebas de seguridad sugeridas

- Intentar 5 o mas logins fallidos y verificar que la cuenta queda bloqueada temporalmente.
- Enviar un `POST` sin `_csrf_token` y confirmar respuesta `400`.
- Crear usuario con contrasena debil y confirmar rechazo.
- Activar 2FA, cerrar sesion e intentar login sin codigo OTP.
- Configurar PIN, ejecutar una accion administrativa sensible sin haberlo confirmado y verificar el bloqueo.
- Guardar un cliente y revisar en MySQL que `cedula`, `telefono` y `email_servicio` empiezan por `enc:v2:`.
- Revisar que `auditoria_seguridad` registra eventos sin contrasenas, PIN ni codigos OTP.

## Recomendaciones de produccion

- Servir solo por HTTPS y habilitar `SESSION_COOKIE_SECURE=1`.
- Usar un gestor de secretos para llaves y credenciales.
- Rotar `DATA_ENCRYPTION_KEY` con una estrategia de re-cifrado planificada.
- Usar un usuario MySQL sin permisos globales ni `DROP`.
- Configurar backups cifrados y logs centralizados con alertas.
- Reemplazar el envio de codigos mostrado por pantalla por correo real antes de operar con usuarios finales.
