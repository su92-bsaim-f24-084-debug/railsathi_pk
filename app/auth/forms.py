"""Authentication and profile forms with server-side validation."""
import re
from flask_wtf import FlaskForm
from wtforms import (
    StringField,
    PasswordField,
    BooleanField,
    SubmitField,
    SelectField,
    TextAreaField,
    EmailField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    Length,
    EqualTo,
    Regexp,
    Optional,
    ValidationError,
)
from sqlalchemy import select
from app.extensions import db
from app.models.identity import User

# Pakistani CNIC format: 12345-1234567-1
CNIC_REGEX = r"^\d{5}-\d{7}-\d{1}$"

# Pakistani Mobile Number formats: 03XX-XXXXXXX or 03XXXXXXXXX or +923XXXXXXXXX
MOBILE_REGEX = r"^(03\d{2}-\d{7}|03\d{9}|\+923\d{9})$"

PAKISTAN_PROVINCES = [
    ("", "Select Province"),
    ("Punjab", "Punjab"),
    ("Sindh", "Sindh"),
    ("Khyber Pakhtunkhwa", "Khyber Pakhtunkhwa"),
    ("Balochistan", "Balochistan"),
    ("Islamabad Capital Territory", "Islamabad Capital Territory"),
    ("Gilgit-Baltistan", "Gilgit-Baltistan"),
    ("Azad Jammu and Kashmir", "Azad Jammu and Kashmir"),
]


def validate_password_strength(form, field):
    """Enforce strong password policy:
    - At least 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character
    """
    password = field.data or ""
    if len(password) < 8:
        raise ValidationError("Password must be at least 8 characters long.")
    if not re.search(r"[A-Z]", password):
        raise ValidationError("Password must include at least one uppercase letter.")
    if not re.search(r"[a-z]", password):
        raise ValidationError("Password must include at least one lowercase letter.")
    if not re.search(r"\d", password):
        raise ValidationError("Password must include at least one number.")
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>_\-+=\[\]\\/]", password):
        raise ValidationError("Password must include at least one special character (!@#$%^&* etc.).")


class RegistrationForm(FlaskForm):
    """Passenger account registration form."""
    first_name = StringField("First Name", validators=[DataRequired(), Length(min=2, max=50)])
    last_name = StringField("Last Name", validators=[DataRequired(), Length(min=2, max=50)])
    email = EmailField("Email Address", validators=[DataRequired(), Email(), Length(max=120)])
    cnic = StringField(
        "CNIC Number (Format: 12345-1234567-1)",
        validators=[
            DataRequired(),
            Regexp(CNIC_REGEX, message="CNIC must follow the 13-digit format: 12345-1234567-1"),
        ],
    )
    phone_number = StringField(
        "Mobile Number (e.g., 0300-1234567)",
        validators=[
            DataRequired(),
            Regexp(MOBILE_REGEX, message="Mobile number must follow Pakistani mobile format (e.g., 0300-1234567)"),
        ],
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired(), validate_password_strength],
    )
    confirm_password = PasswordField(
        "Confirm Password",
        validators=[
            DataRequired(),
            EqualTo("password", message="Password confirmation does not match."),
        ],
    )
    submit = SubmitField("Create Account")

    def validate_email(self, field):
        """Disallow active users with the same email. Soft-deleted users do not block registration."""
        stmt = select(User).filter_by(email=field.data.strip().lower(), is_deleted=False)
        if db.session.scalar(stmt):
            raise ValidationError("An active account is already registered with this email address.")

    def validate_cnic(self, field):
        """Disallow active users with the same CNIC. Soft-deleted users do not block registration."""
        stmt = select(User).filter_by(cnic=field.data.strip(), is_deleted=False)
        if db.session.scalar(stmt):
            raise ValidationError("An active account is already registered with this CNIC number.")


class LoginForm(FlaskForm):
    """User authentication sign-in form."""
    email = EmailField("Email Address", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
    remember_me = BooleanField("Remember Me")
    submit = SubmitField("Sign In")


class ProfileForm(FlaskForm):
    """User profile view/edit form."""
    first_name = StringField("First Name", validators=[DataRequired(), Length(min=2, max=50)])
    last_name = StringField("Last Name", validators=[DataRequired(), Length(min=2, max=50)])
    phone_number = StringField(
        "Mobile Number",
        validators=[
            DataRequired(),
            Regexp(MOBILE_REGEX, message="Mobile number must follow Pakistani mobile format (e.g., 0300-1234567)"),
        ],
    )
    city = StringField("City", validators=[Optional(), Length(max=50)])
    province = SelectField("Province", choices=PAKISTAN_PROVINCES, validators=[Optional()])
    address = TextAreaField("Address", validators=[Optional(), Length(max=255)])
    submit = SubmitField("Save Profile")


class ChangePasswordForm(FlaskForm):
    """User password change form."""
    current_password = PasswordField("Current Password", validators=[DataRequired()])
    new_password = PasswordField(
        "New Password",
        validators=[DataRequired(), validate_password_strength],
    )
    confirm_password = PasswordField(
        "Confirm New Password",
        validators=[
            DataRequired(),
            EqualTo("new_password", message="New password confirmation does not match."),
        ],
    )
    submit = SubmitField("Update Password")

