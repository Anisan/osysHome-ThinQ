from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired

# Определение класса формы
class SettingsForm(FlaskForm):
    api_key = StringField('API key', validators=[DataRequired()])
    country = StringField("Country (RU)")
    submit = SubmitField('Submit')
