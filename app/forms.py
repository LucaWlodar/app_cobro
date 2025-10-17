from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, FloatField, TextAreaField, IntegerField
from wtforms.validators import DataRequired, Length, NumberRange

class RegisterForm(FlaskForm):
    username = StringField('Usuario', validators=[DataRequired(), Length(min=3)])
    password = PasswordField('Contraseña', validators=[DataRequired(), Length(min=3)])
    submit = SubmitField('Registrarse')

class LoginForm(FlaskForm):
    username = StringField('Usuario', validators=[DataRequired()])
    password = PasswordField('Contraseña', validators=[DataRequired()])
    submit = SubmitField('Entrar')

class ProductForm(FlaskForm):
    name = StringField('Nombre', validators=[DataRequired()])
    description = TextAreaField('Descripción')
    price = FloatField('Precio', validators=[DataRequired(), NumberRange(min=0)])
    submit = SubmitField('Guardar')

class AddToCartForm(FlaskForm):
    quantity = IntegerField('Cantidad', default=1, validators=[DataRequired(), NumberRange(min=1)])
    submit = SubmitField('Agregar')
