"""WTForms for Railway Infrastructure & Station Master-Data (Phase 5A)."""
from decimal import Decimal
from flask_wtf import FlaskForm
from wtforms import (
    StringField,
    BooleanField,
    SubmitField,
    SelectField,
    IntegerField,
    DecimalField,
    TextAreaField,
)
from wtforms.validators import (
    DataRequired,
    Length,
    Optional,
    NumberRange,
    ValidationError,
)
from sqlalchemy import select
from app.extensions import db
from app.models.stations import (
    StationDivision,
    Station,
    StationPlatform,
    FacilityCategory,
    StationFacility,
)
from app.auth.forms import PAKISTAN_PROVINCES


class StationDivisionForm(FlaskForm):
    """Form to create or edit regional administrative railway divisions."""
    code = StringField("Division Code (e.g., LHR-DIV)", validators=[DataRequired(), Length(min=2, max=10)])
    name = StringField("Division Name", validators=[DataRequired(), Length(min=2, max=100)])
    headquarters_city = StringField("Headquarters City", validators=[DataRequired(), Length(min=2, max=100)])
    submit = SubmitField("Save Division")

    def __init__(self, original_id=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_id = original_id

    def validate_code(self, field):
        code_clean = field.data.strip().upper()
        stmt = select(StationDivision).filter(
            StationDivision.code == code_clean,
            StationDivision.is_deleted == False,
        )
        if self.original_id:
            stmt = stmt.filter(StationDivision.id != self.original_id)
        if db.session.scalar(stmt):
            raise ValidationError(f"An active division with code '{code_clean}' already exists.")


class StationForm(FlaskForm):
    """Form to create or edit operational railway stations."""
    division_id = SelectField("Railway Division", coerce=int, validators=[DataRequired()])
    code = StringField("Station Code (e.g., LHE, RWP)", validators=[DataRequired(), Length(min=2, max=10)])
    name = StringField("Station Name", validators=[DataRequired(), Length(min=2, max=100)])
    city = StringField("City", validators=[DataRequired(), Length(min=2, max=100)])
    province = SelectField("Province", choices=PAKISTAN_PROVINCES[1:], validators=[DataRequired()])
    latitude = DecimalField(
        "Latitude (-90 to +90)",
        places=6,
        validators=[Optional(), NumberRange(min=-90.0, max=90.0, message="Latitude must be between -90 and +90")],
    )
    longitude = DecimalField(
        "Longitude (-180 to +180)",
        places=6,
        validators=[Optional(), NumberRange(min=-180.0, max=180.0, message="Longitude must be between -180 and +180")],
    )
    contact_number = StringField("Inquiry / Emergency Contact", validators=[Optional(), Length(max=30)])
    is_junction = BooleanField("Junction Station (Intersecting Routes)", default=False)
    submit = SubmitField("Save Station")

    def __init__(self, original_id=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_id = original_id

    def validate_code(self, field):
        code_clean = field.data.strip().upper()
        stmt = select(Station).filter(
            Station.code == code_clean,
            Station.is_deleted == False,
        )
        if self.original_id:
            stmt = stmt.filter(Station.id != self.original_id)
        if db.session.scalar(stmt):
            raise ValidationError(f"An active station with code '{code_clean}' already exists.")


class StationPlatformForm(FlaskForm):
    """Form to create or edit physical railway station platforms."""
    station_id = SelectField("Railway Station", coerce=int, validators=[DataRequired()])
    platform_number = StringField("Platform Number (e.g., 1, 2, 3)", validators=[DataRequired(), Length(max=10)])
    length_meters = IntegerField(
        "Length (Meters)",
        validators=[Optional(), NumberRange(min=10, max=2000, message="Length must be at least 10 meters")],
    )
    has_disabled_access = BooleanField("Disabled & Wheelchair Accessible", default=True)
    is_operational = BooleanField("Platform Operational", default=True)
    submit = SubmitField("Save Platform")

    def __init__(self, original_id=None, fixed_station_id=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_id = original_id
        self.fixed_station_id = fixed_station_id

    def validate_platform_number(self, field):
        val = field.data.strip()
        # Verify platform number is positive integer
        if not val.isdigit() or int(val) <= 0:
            raise ValidationError("Platform number must be a positive integer greater than 0.")

        stn_id = self.fixed_station_id or self.station_id.data
        stmt = select(StationPlatform).filter(
            StationPlatform.station_id == stn_id,
            StationPlatform.platform_number == val,
            StationPlatform.is_deleted == False,
        )
        if self.original_id:
            stmt = stmt.filter(StationPlatform.id != self.original_id)
        if db.session.scalar(stmt):
            raise ValidationError(f"Platform #{val} already exists at this station.")


class FacilityCategoryForm(FlaskForm):
    """Form to create or edit passenger amenity categories."""
    name = StringField("Category Name (e.g., Waiting Room)", validators=[DataRequired(), Length(min=2, max=50)])
    icon_class = StringField("Bootstrap Icon (e.g., bi-cup-hot, bi-shield)", validators=[Optional(), Length(max=50)])
    description = TextAreaField("Description", validators=[Optional()])
    submit = SubmitField("Save Category")

    def __init__(self, original_id=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_id = original_id

    def validate_name(self, field):
        name_clean = field.data.strip()
        stmt = select(FacilityCategory).filter(
            FacilityCategory.name == name_clean,
            FacilityCategory.is_deleted == False,
        )
        if self.original_id:
            stmt = stmt.filter(FacilityCategory.id != self.original_id)
        if db.session.scalar(stmt):
            raise ValidationError(f"An active facility category named '{name_clean}' already exists.")


class StationFacilityForm(FlaskForm):
    """Form to create or edit passenger amenities situated at stations."""
    station_id = SelectField("Railway Station", coerce=int, validators=[DataRequired()])
    category_id = SelectField("Amenity Category", coerce=int, validators=[DataRequired()])
    name = StringField("Facility / Amenity Name", validators=[DataRequired(), Length(min=2, max=100)])
    location_details = StringField("Location Description", validators=[Optional(), Length(max=150)])
    is_free = BooleanField("Complimentary / Free Access", default=True)
    fee_amount = DecimalField(
        "Usage Fee (PKR)",
        default=Decimal("0.00"),
        places=2,
        validators=[NumberRange(min=0.0, message="Fee cannot be negative.")],
    )
    opening_hours = StringField("Operating Hours (e.g., 24/7, 08:00 - 22:00)", validators=[Optional(), Length(max=50)])
    submit = SubmitField("Save Facility")

    def __init__(self, original_id=None, fixed_station_id=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_id = original_id
        self.fixed_station_id = fixed_station_id

