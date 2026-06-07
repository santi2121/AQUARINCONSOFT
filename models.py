from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class UsuarioSistema(Base):
    __tablename__ = "usuarios_sistema"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombres: Mapped[str] = mapped_column(String(120), nullable=False)
    apellidos: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    telefono: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    rol: Mapped[str] = mapped_column(Enum("admin", "usuario"), nullable=False, default="usuario")
    codigo_recibo_vinculado: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_login_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    session_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    data_consent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    data_consent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    verification_codes: Mapped[list["CodigoVerificacion"]] = relationship(back_populates="user")


class CodigoVerificacion(Base):
    __tablename__ = "codigos_verificacion"
    __table_args__ = (
        Index("idx_codigos_user", "user_id"),
        Index("idx_codigos_used", "used"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("usuarios_sistema.id"), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    user: Mapped[UsuarioSistema] = relationship(back_populates="verification_codes")


class AuditoriaSeguridad(Base):
    __tablename__ = "auditoria_seguridad"
    __table_args__ = (
        Index("idx_auditoria_evento", "evento"),
        Index("idx_auditoria_usuario", "id_usuario_sistema"),
        Index("idx_auditoria_fecha", "fecha_creacion"),
    )

    id_auditoria: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_usuario_sistema: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evento: Mapped[str] = mapped_column(String(80), nullable=False)
    exito: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detalle: Mapped[str | None] = mapped_column(Text, nullable=True)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
