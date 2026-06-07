CREATE DATABASE IF NOT EXISTS ACUEDUCTO
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE ACUEDUCTO;

CREATE TABLE IF NOT EXISTS usuarios_sistema (
  id INT AUTO_INCREMENT PRIMARY KEY,
  nombres VARCHAR(120) NOT NULL,
  apellidos VARCHAR(120) NOT NULL DEFAULT '',
  telefono VARCHAR(20) NULL,
  email VARCHAR(120) NOT NULL UNIQUE,
  password VARCHAR(255) NOT NULL,
  rol ENUM('admin', 'usuario') NOT NULL DEFAULT 'usuario',
  codigo_recibo_vinculado VARCHAR(30) NULL,
  failed_login_attempts INT NOT NULL DEFAULT 0,
  locked_until DATETIME NULL,
  last_login_at DATETIME NULL,
  last_login_ip VARCHAR(45) NULL,
  password_changed_at DATETIME NULL,
  session_version INT NOT NULL DEFAULT 0,
  fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_usuarios_sistema_rol (rol),
  INDEX idx_usuarios_sistema_codigo (codigo_recibo_vinculado)
) ENGINE=InnoDB;

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
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS usuarios_acueducto (
  id INT AUTO_INCREMENT PRIMARY KEY,
  codigo_recibo VARCHAR(30) NOT NULL UNIQUE,
  nombres VARCHAR(160) NOT NULL,
  apellidos VARCHAR(160) NOT NULL DEFAULT '',
  direccion VARCHAR(180) NOT NULL,
  cedula TEXT NULL,
  telefono TEXT NULL,
  email_servicio TEXT NULL,
  ubicacion_maps TEXT NULL,
  estado ENUM('activo', 'inactivo', 'suspendido') NOT NULL DEFAULT 'activo',
  fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

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
  INDEX idx_facturas_periodo (periodo),
  CONSTRAINT fk_facturas_usuarios_acueducto
    FOREIGN KEY (id_acueducto) REFERENCES usuarios_acueducto(id)
    ON UPDATE CASCADE
    ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS reportes_pago (
  id_reporte INT AUTO_INCREMENT PRIMARY KEY,
  id_acueducto INT NOT NULL,
  codigo_recibo VARCHAR(30) NOT NULL,
  id_usuario_sistema INT NULL,
  meses_pagados INT NOT NULL,
  valor_reportado DECIMAL(12,2) NOT NULL,
  metodo_pago ENUM('digital', 'fisico') NOT NULL,
  comprobante LONGBLOB NULL,
  referencia VARCHAR(120) NULL,
  estado ENUM('pendiente', 'verificado', 'rechazado') NOT NULL DEFAULT 'pendiente',
  observacion TEXT NULL,
  fecha_reporte TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  fecha_revision DATETIME NULL,
  revisado_por INT NULL,
  INDEX idx_reportes_pago_estado (estado),
  INDEX idx_reportes_pago_acueducto (id_acueducto),
  CONSTRAINT fk_reportes_pago_acueducto
    FOREIGN KEY (id_acueducto) REFERENCES usuarios_acueducto(id)
    ON UPDATE CASCADE
    ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS permisos_pago (
  id_permiso INT AUTO_INCREMENT PRIMARY KEY,
  id_acueducto INT NOT NULL,
  estado ENUM('activo', 'usado', 'cancelado') NOT NULL DEFAULT 'activo',
  meses_minimos INT NOT NULL DEFAULT 3,
  observacion TEXT NULL,
  concedido_por INT NULL,
  fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  fecha_uso DATETIME NULL,
  INDEX idx_permisos_acueducto_estado (id_acueducto, estado),
  CONSTRAINT fk_permisos_pago_acueducto
    FOREIGN KEY (id_acueducto) REFERENCES usuarios_acueducto(id)
    ON UPDATE CASCADE
    ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS envios_facturacion (
  id_envio INT AUTO_INCREMENT PRIMARY KEY,
  id_factura INT NOT NULL,
  id_acueducto INT NOT NULL,
  email VARCHAR(120) NOT NULL,
  estado ENUM('pendiente', 'enviado', 'error') NOT NULL DEFAULT 'pendiente',
  detalle TEXT NULL,
  fecha_envio TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS facturacion_control (
  periodo VARCHAR(20) PRIMARY KEY,
  facturas_creadas INT NOT NULL DEFAULT 0,
  correos_enviados INT NOT NULL DEFAULT 0,
  fecha_generacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS recuperacion_password (
  id_recuperacion INT AUTO_INCREMENT PRIMARY KEY,
  email VARCHAR(120) NOT NULL,
  id_usuario_sistema INT NOT NULL,
  codigo_hash VARCHAR(255) NOT NULL,
  usado TINYINT(1) NOT NULL DEFAULT 0,
  fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  fecha_expiracion DATETIME NOT NULL
) ENGINE=InnoDB;

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
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS archivos_recuperacion (
  id_archivo INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  token_hash VARCHAR(255) NOT NULL,
  revoked TINYINT(1) NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_used_at DATETIME NULL,
  INDEX idx_archivos_recuperacion_user (user_id),
  INDEX idx_archivos_recuperacion_revoked (revoked)
) ENGINE=InnoDB;

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
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS puntos_pago (
  id_punto INT AUTO_INCREMENT PRIMARY KEY,
  nombre VARCHAR(140) NOT NULL,
  direccion VARCHAR(180) NOT NULL,
  telefono VARCHAR(40) NULL,
  horario VARCHAR(140) NOT NULL,
  latitud DECIMAL(10,7) NULL,
  longitud DECIMAL(10,7) NULL,
  imagen VARCHAR(255) NULL,
  activo TINYINT(1) NOT NULL DEFAULT 1,
  fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS noticias (
  id_noticia INT AUTO_INCREMENT PRIMARY KEY,
  titulo VARCHAR(180) NOT NULL,
  resumen TEXT NOT NULL,
  contenido TEXT NULL,
  imagen VARCHAR(255) NULL,
  publicada TINYINT(1) NOT NULL DEFAULT 1,
  fecha_publicacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  fecha_actualizacion DATETIME NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS mensajes_contacto (
  id_mensaje INT AUTO_INCREMENT PRIMARY KEY,
  nombre VARCHAR(160) NOT NULL,
  telefono VARCHAR(30) NULL,
  correo VARCHAR(120) NOT NULL,
  asunto VARCHAR(180) NOT NULL,
  mensaje TEXT NOT NULL,
  leido TINYINT(1) NOT NULL DEFAULT 0,
  fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  fecha_lectura DATETIME NULL,
  INDEX idx_contacto_leido (leido),
  INDEX idx_contacto_telefono (telefono)
) ENGINE=InnoDB;

INSERT INTO usuarios_acueducto (codigo_recibo, nombres, apellidos, direccion, cedula, telefono, email_servicio)
VALUES ('RS-0001', 'Usuario', 'Demo', 'Vereda Rincon Santo', '1000000001', '3000000000', 'usuario@correo.com')
ON DUPLICATE KEY UPDATE codigo_recibo = VALUES(codigo_recibo);
