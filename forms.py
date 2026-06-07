import re

from flask_wtf import FlaskForm
from wtforms import HiddenField, PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Regexp, ValidationError


def strong_password(form, field):
    password = field.data or ""
    checks = [
        (len(password) >= 10, "minimo 10 caracteres"),
        (re.search(r"[A-Z]", password), "una mayuscula"),
        (re.search(r"[a-z]", password), "una minuscula"),
        (re.search(r"\d", password), "un numero"),
        (re.search(r"[^A-Za-z0-9]", password), "un simbolo"),
    ]
    missing = [message for ok, message in checks if not ok]
    if missing:
        raise ValidationError("La contrasena debe incluir " + ", ".join(missing) + ".")


class LoginForm(FlaskForm):
    next = HiddenField()
    email = StringField("Correo electronico", validators=[DataRequired(), Email(), Length(max=120)])
    password = PasswordField("Contrasena", validators=[DataRequired(), Length(max=128)])
    submit = SubmitField("Ingresar al sistema")


class RegisterForm(FlaskForm):
    nombre = StringField("Nombre completo", validators=[DataRequired(), Length(min=3, max=120)])
    email = StringField("Correo electronico", validators=[DataRequired(), Email(), Length(max=120)])
    password = PasswordField("Contrasena", validators=[DataRequired(), Length(max=128), strong_password])
    submit = SubmitField("Crear cuenta")


class EmailOTPForm(FlaskForm):
    next = HiddenField()
    otp_code = StringField(
        "Codigo de verificacion",
        validators=[DataRequired(), Regexp(r"^\d{6}$", message="Ingresa el codigo de 6 digitos.")],
    )
    submit = SubmitField("Verificar codigo")


class ForgotPasswordForm(FlaskForm):
    email = StringField("Correo electronico", validators=[DataRequired(), Email(), Length(max=120)])
    submit = SubmitField("Enviar codigo")


class ResetPasswordForm(FlaskForm):
    email = HiddenField(validators=[DataRequired(), Email()])
    password = PasswordField("Nueva contrasena", validators=[DataRequired(), Length(max=128), strong_password])
    confirm_password = PasswordField(
        "Confirmar contrasena",
        validators=[DataRequired(), EqualTo("password", message="Las contrasenas deben coincidir.")],
    )
    submit = SubmitField("Actualizar contrasena")
