"""Administrative WTForms for user and staff management."""
from flask_wtf import FlaskForm
from wtforms import (
    StringField,
    PasswordField,
    BooleanField,
    SubmitField,
    SelectField,
    SelectMultipleField,
    EmailField,
    widgets,
)
from wtforms.validators import (
    DataRequired,
    Email,
    Length,
    Regexp,
    Optional,
    ValidationError,
)
from sqlalchemy import select
from app.extensions import db
from app.models.identity import User
from app.auth.forms import CNIC_REGEX, MOBILE_REGEX, validate_password_strength


class MultiCheckboxField(SelectMultipleField):
    """Checkbox list for selecting multiple roles."""
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()


class AdminUserCreateForm(FlaskForm):
    """Admin form to create new system user accounts."""
    first_name = StringField("First Name", validators=[DataRequired(), Length(min=2, max=50)])
    last_name = StringField("Last Name", validators=[DataRequired(), Length(min=2, max=50)])
    email = EmailField("Email Address", validators=[DataRequired(), Email(), Length(max=120)])
    cnic = StringField(
        "CNIC Number (12345-1234567-1)",
        validators=[DataRequired(), Regexp(CNIC_REGEX, message="Format must be 12345-1234567-1")],
    )
    phone_number = StringField(
        "Mobile Number",
        validators=[DataRequired(), Regexp(MOBILE_REGEX, message="Pakistani mobile format required")],
    )
    password = PasswordField("Initial Password", validators=[DataRequired(), validate_password_strength])
    roles = MultiCheckboxField("Assigned Roles", coerce=int)
    is_active_user = BooleanField("Active Account", default=True)
    submit = SubmitField("Create Account")

    def validate_email(self, field):
        stmt = select(User).filter_by(email=field.data.strip().lower(), is_deleted=False)
        if db.session.scalar(stmt):
            raise ValidationError("An active account already exists with this email address.")

    def validate_cnic(self, field):
        stmt = select(User).filter_by(cnic=field.data.strip(), is_deleted=False)
        if db.session.scalar(stmt):
            raise ValidationError("An active account already exists with this CNIC number.")


class AdminUserEditForm(FlaskForm):
    """Admin form to edit existing user accounts."""
    first_name = StringField("First Name", validators=[DataRequired(), Length(min=2, max=50)])
    last_name = StringField("Last Name", validators=[DataRequired(), Length(min=2, max=50)])
    email = EmailField("Email Address", validators=[DataRequired(), Email(), Length(max=120)])
    cnic = StringField(
        "CNIC Number (12345-1234567-1)",
        validators=[DataRequired(), Regexp(CNIC_REGEX, message="Format must be 12345-1234567-1")],
    )
    phone_number = StringField(
        "Mobile Number",
        validators=[DataRequired(), Regexp(MOBILE_REGEX, message="Pakistani mobile format required")],
    )
    password = PasswordField("Reset Password (optional)", validators=[Optional(), validate_password_strength])
    roles = MultiCheckboxField("Assigned Roles", coerce=int)
    is_active_user = BooleanField("Active Account")
    submit = SubmitField("Save Changes")

    def __init__(self, original_user_id=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_user_id = original_user_id

    def validate_email(self, field):
        stmt = select(User).filter(
            User.email == field.data.strip().lower(),
            User.is_deleted == False,
            User.id != self.original_user_id,
        )
        if db.session.scalar(stmt):
            raise ValidationError("Another active account already uses this email address.")

    def validate_cnic(self, field):
        stmt = select(User).filter(
            User.cnic == field.data.strip(),
            User.is_deleted == False,
            User.id != self.original_user_id,
        )
        if db.session.scalar(stmt):
            raise ValidationError("Another active account already uses this CNIC number.")


class StaffProfileForm(FlaskForm):
    """Form to create or edit staff profiles."""
    user_id = SelectField("User Account", coerce=int, validators=[DataRequired()])
    station_id = SelectField("Assigned Railway Station", coerce=int, validators=[Optional()])
    employee_code = StringField("Employee Code", validators=[DataRequired(), Length(min=3, max=30)])
    department = StringField("Department", validators=[DataRequired(), Length(min=2, max=50)])
    designation = StringField("Designation", validators=[DataRequired(), Length(min=2, max=50)])
    shift_timing = SelectField(
        "Shift Timing",
        choices=[
            ("", "Select Shift"),
            ("Morning (06:00 - 14:00)", "Morning (06:00 - 14:00)"),
            ("Evening (14:00 - 22:00)", "Evening (14:00 - 22:00)"),
            ("Night (22:00 - 06:00)", "Night (22:00 - 06:00)"),
            ("General (09:00 - 17:00)", "General (09:00 - 17:00)"),
        ],
        validators=[Optional()],
    )
    submit = SubmitField("Save Staff Profile")


class EmptyActionForm(FlaskForm):
    """CSRF-only form for secure state-changing actions (soft-delete, restore)."""
    submit = SubmitField("Confirm")

