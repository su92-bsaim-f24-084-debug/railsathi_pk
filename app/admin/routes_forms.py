"""WTForms for Routes & Pricing Master-Data (Phase 5B).

Models:
- Model #20: Route
- Model #21: RouteStop
- Model #22: FareRule
"""
from decimal import Decimal
from flask_wtf import FlaskForm
from wtforms import (
    StringField,
    SubmitField,
    SelectField,
    IntegerField,
    DecimalField,
)
from wtforms.validators import (
    DataRequired,
    InputRequired,
    Length,
    NumberRange,
    ValidationError,
)
from sqlalchemy import select
from app.extensions import db
from app.models.routes import Route, RouteStop, FareRule


class RouteForm(FlaskForm):
    """Form to create or edit mainline and branch railway corridors."""
    code = StringField("Route Code (e.g., ML1, ML2)", validators=[DataRequired(), Length(min=2, max=20)])
    name = StringField("Route Name (e.g., Karachi - Peshawar Main Line 1)", validators=[DataRequired(), Length(min=2, max=100)])
    source_station_id = SelectField("Origin Terminal Station", coerce=int, validators=[DataRequired()])
    destination_station_id = SelectField("Destination Terminal Station", coerce=int, validators=[DataRequired()])
    total_distance_km = DecimalField(
        "Total Corridor Distance (km)",
        places=2,
        validators=[InputRequired(), NumberRange(min=0.0, message="Distance cannot be negative.")],
    )
    submit = SubmitField("Save Route")

    def __init__(self, original_id=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_id = original_id

    def validate_code(self, field):
        code_clean = field.data.strip().upper()
        stmt = select(Route).filter(Route.code == code_clean, Route.is_deleted == False)
        if self.original_id:
            stmt = stmt.filter(Route.id != self.original_id)
        if db.session.scalar(stmt):
            raise ValidationError(f"An active route with code '{code_clean}' already exists.")

    def validate_destination_station_id(self, field):
        if field.data == self.source_station_id.data:
            raise ValidationError("Origin and destination stations cannot be the same.")


class RouteStopForm(FlaskForm):
    """Form to configure sequential station stops on a railway route."""
    route_id = SelectField("Railway Route Corridor", coerce=int, validators=[DataRequired()])
    station_id = SelectField("Intermediate Station", coerce=int, validators=[DataRequired()])
    stop_sequence = IntegerField("Stop Sequence (1, 2, 3...)", validators=[DataRequired(), NumberRange(min=1)])
    distance_from_origin_km = DecimalField(
        "Cumulative Distance from Origin (km)",
        places=2,
        validators=[InputRequired(), NumberRange(min=0.0, message="Distance cannot be negative.")],
    )
    standard_halt_minutes = IntegerField("Scheduled Halt Duration (minutes)", default=5, validators=[InputRequired(), NumberRange(min=0)])
    submit = SubmitField("Save Route Stop")

    def __init__(self, original_id=None, fixed_route_id=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_id = original_id
        self.fixed_route_id = fixed_route_id

    def validate_stop_sequence(self, field):
        r_id = self.fixed_route_id or self.route_id.data
        seq = field.data
        stmt = select(RouteStop).filter(
            RouteStop.route_id == r_id,
            RouteStop.stop_sequence == seq,
            RouteStop.is_deleted == False,
        )
        if self.original_id:
            stmt = stmt.filter(RouteStop.id != self.original_id)
        if db.session.scalar(stmt):
            raise ValidationError(f"Stop sequence #{seq} is already assigned on this route.")

        # Contiguous check: sequence must start at 1 and not leave gaps
        existing_seqs = db.session.scalars(
            select(RouteStop.stop_sequence)
            .filter(RouteStop.route_id == r_id, RouteStop.is_deleted == False)
            .order_by(RouteStop.stop_sequence)
        ).all()
        if not self.original_id:
            max_seq = max(existing_seqs) if existing_seqs else 0
            if seq > max_seq + 1:
                raise ValidationError(
                    f"Stop sequence must be contiguous starting from 1 (next expected sequence is #{max_seq + 1})."
                )


class FareRuleForm(FlaskForm):
    """Form to configure distance-bracketed pricing rules per coach class."""
    coach_class_id = SelectField("Coach Accommodation Class", coerce=int, validators=[DataRequired()])
    min_distance_km = DecimalField(
        "Min Distance (km)",
        default=Decimal("0.00"),
        places=2,
        validators=[InputRequired(), NumberRange(min=0.0)],
    )
    max_distance_km = DecimalField(
        "Max Distance (km)",
        default=Decimal("9999.00"),
        places=2,
        validators=[InputRequired(), NumberRange(min=0.0)],
    )
    base_fare = DecimalField(
        "Base Flag-Fall Fare (PKR)",
        default=Decimal("0.00"),
        places=2,
        validators=[InputRequired(), NumberRange(min=0.0, message="Fare cannot be negative.")],
    )
    rate_per_km = DecimalField(
        "Per-KM Rate (PKR)",
        default=Decimal("0.00"),
        places=2,
        validators=[InputRequired(), NumberRange(min=0.0, message="Rate cannot be negative.")],
    )
    reservation_charge = DecimalField(
        "Reservation Fee (PKR)",
        default=Decimal("0.00"),
        places=2,
        validators=[InputRequired(), NumberRange(min=0.0, message="Charge cannot be negative.")],
    )
    submit = SubmitField("Save Fare Rule")

    def validate_max_distance_km(self, field):
        if field.data < self.min_distance_km.data:
            raise ValidationError("Maximum distance cannot be less than minimum distance.")

