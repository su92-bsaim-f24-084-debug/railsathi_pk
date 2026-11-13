"""WTForms for Trains & Rolling Stock Master-Data (Phase 5B).

Models:
- Model #12: TrainType
- Model #13: Train (with TrainOperationalDay checkboxes)
- Model #15: CoachClass
- Model #16: SeatLayoutType
- Model #17: BerthType
- Model #18: TrainCoach
- Model #19: Seat (Individual and Batch Generator)
"""
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
from app.models.trains import (
    TrainType,
    Train,
    CoachClass,
    SeatLayoutType,
    BerthType,
    TrainCoach,
    Seat,
)


class TrainTypeForm(FlaskForm):
    """Form to create or edit rolling stock operational categories."""
    code = StringField("Type Code (e.g., EXP, INT, SF)", validators=[DataRequired(), Length(min=2, max=20)])
    name = StringField("Type Name (e.g., Express, Intercity)", validators=[DataRequired(), Length(min=2, max=50)])
    max_speed_kmh = IntegerField(
        "Max Speed (km/h)",
        validators=[Optional(), NumberRange(min=30, max=300, message="Speed must be between 30 and 300 km/h")],
    )
    description = TextAreaField("Description", validators=[Optional()])
    submit = SubmitField("Save Train Type")

    def __init__(self, original_id=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_id = original_id

    def validate_code(self, field):
        code_clean = field.data.strip().upper()
        stmt = select(TrainType).filter(TrainType.code == code_clean, TrainType.is_deleted == False)
        if self.original_id:
            stmt = stmt.filter(TrainType.id != self.original_id)
        if db.session.scalar(stmt):
            raise ValidationError(f"An active train type with code '{code_clean}' already exists.")

    def validate_name(self, field):
        name_clean = field.data.strip()
        stmt = select(TrainType).filter(TrainType.name == name_clean, TrainType.is_deleted == False)
        if self.original_id:
            stmt = stmt.filter(TrainType.id != self.original_id)
        if db.session.scalar(stmt):
            raise ValidationError(f"An active train type named '{name_clean}' already exists.")


class TrainForm(FlaskForm):
    """Form to create or edit trains with operational day checkboxes."""
    train_type_id = SelectField("Train Category", coerce=int, validators=[DataRequired()])
    train_number = StringField("Train Number (e.g., 1UP, 2DN)", validators=[DataRequired(), Length(min=1, max=20)])
    name = StringField("Train Name (e.g., Khyber Mail, Green Line)", validators=[DataRequired(), Length(min=2, max=100)])
    origin_station_id = SelectField("Origin Terminal Station", coerce=int, validators=[DataRequired()])
    destination_station_id = SelectField("Destination Terminal Station", coerce=int, validators=[DataRequired()])
    is_active = BooleanField("Operational Fleet Active", default=True)

    # Operational Days of Week Checkboxes (0=Monday .. 6=Sunday)
    day_0 = BooleanField("Monday", default=True)
    day_1 = BooleanField("Tuesday", default=True)
    day_2 = BooleanField("Wednesday", default=True)
    day_3 = BooleanField("Thursday", default=True)
    day_4 = BooleanField("Friday", default=True)
    day_5 = BooleanField("Saturday", default=True)
    day_6 = BooleanField("Sunday", default=True)

    submit = SubmitField("Save Train")

    def __init__(self, original_id=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_id = original_id

    def validate_train_number(self, field):
        num_clean = field.data.strip().upper()
        stmt = select(Train).filter(Train.train_number == num_clean, Train.is_deleted == False)
        if self.original_id:
            stmt = stmt.filter(Train.id != self.original_id)
        if db.session.scalar(stmt):
            raise ValidationError(f"An active train with number '{num_clean}' already exists.")

    def validate_destination_station_id(self, field):
        if field.data == self.origin_station_id.data:
            raise ValidationError("Origin and destination terminal stations cannot be the same.")


class CoachClassForm(FlaskForm):
    """Form to create or edit accommodation coach classes."""
    code = StringField("Class Code (e.g., AC_SLEEPER, EC)", validators=[DataRequired(), Length(min=2, max=20)])
    name = StringField("Class Name (e.g., AC Sleeper, Economy)", validators=[DataRequired(), Length(min=2, max=50)])
    base_fare_multiplier = DecimalField(
        "Base Fare Multiplier (e.g. 1.00, 1.80)",
        places=2,
        default=Decimal("1.00"),
        validators=[DataRequired(), NumberRange(min=0.01, message="Multiplier must be greater than 0")],
    )
    description = TextAreaField("Description", validators=[Optional()])
    submit = SubmitField("Save Coach Class")

    def __init__(self, original_id=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_id = original_id

    def validate_code(self, field):
        code_clean = field.data.strip().upper()
        stmt = select(CoachClass).filter(CoachClass.code == code_clean, CoachClass.is_deleted == False)
        if self.original_id:
            stmt = stmt.filter(CoachClass.id != self.original_id)
        if db.session.scalar(stmt):
            raise ValidationError(f"An active coach class with code '{code_clean}' already exists.")


class SeatLayoutTypeForm(FlaskForm):
    """Form to create or edit coach seating geometry."""
    name = StringField("Layout Name (e.g., 2x2 Chair Car, 3x2 Economy)", validators=[DataRequired(), Length(min=2, max=50)])
    total_rows = IntegerField("Total Rows", validators=[DataRequired(), NumberRange(min=1, max=100)])
    seats_per_row = IntegerField("Seats Per Row", validators=[DataRequired(), NumberRange(min=1, max=10)])
    aisle_position = IntegerField("Aisle Position (Column after aisle)", validators=[DataRequired(), NumberRange(min=1, max=10)])
    description = TextAreaField("Description", validators=[Optional()])
    submit = SubmitField("Save Layout Type")

    def __init__(self, original_id=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_id = original_id

    def validate_name(self, field):
        name_clean = field.data.strip()
        stmt = select(SeatLayoutType).filter(SeatLayoutType.name == name_clean, SeatLayoutType.is_deleted == False)
        if self.original_id:
            stmt = stmt.filter(SeatLayoutType.id != self.original_id)
        if db.session.scalar(stmt):
            raise ValidationError(f"An active seat layout named '{name_clean}' already exists.")


class BerthTypeForm(FlaskForm):
    """Form to view/edit reference berth types (deletion blocked)."""
    code = StringField("Berth Code (e.g., LB, MB, UB)", validators=[DataRequired(), Length(min=1, max=10)])
    name = StringField("Berth Name (e.g., Lower Berth, Window)", validators=[DataRequired(), Length(min=2, max=30)])
    description = TextAreaField("Description", validators=[Optional()])
    submit = SubmitField("Update Berth Type")

    def __init__(self, original_id=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_id = original_id

    def validate_code(self, field):
        code_clean = field.data.strip().upper()
        stmt = select(BerthType).filter(BerthType.code == code_clean)
        if self.original_id:
            stmt = stmt.filter(BerthType.id != self.original_id)
        if db.session.scalar(stmt):
            raise ValidationError(f"A berth type with code '{code_clean}' already exists.")


class TrainCoachForm(FlaskForm):
    """Form to attach or configure a physical carriage in a train rake."""
    train_id = SelectField("Train Rake", coerce=int, validators=[DataRequired()])
    coach_class_id = SelectField("Coach Accommodation Class", coerce=int, validators=[DataRequired()])
    layout_type_id = SelectField("Seating Layout Blueprint", coerce=int, validators=[DataRequired()])
    coach_code = StringField("Coach Label (e.g., B1, B2, EC1)", validators=[DataRequired(), Length(min=1, max=10)])
    sequence_number = IntegerField("Sequence Position in Train (>= 1)", validators=[DataRequired(), NumberRange(min=1)])
    total_capacity = IntegerField("Total Rated Capacity (Seats/Berths)", validators=[DataRequired(), NumberRange(min=1, max=200)])
    submit = SubmitField("Save Coach")

    def __init__(self, original_id=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_id = original_id

    def validate_coach_code(self, field):
        code_clean = field.data.strip().upper()
        stmt = select(TrainCoach).filter(
            TrainCoach.train_id == self.train_id.data,
            TrainCoach.coach_code == code_clean,
            TrainCoach.is_deleted == False,
        )
        if self.original_id:
            stmt = stmt.filter(TrainCoach.id != self.original_id)
        if db.session.scalar(stmt):
            raise ValidationError(f"Coach label '{code_clean}' already exists on this train.")

    def validate_sequence_number(self, field):
        seq = field.data
        stmt = select(TrainCoach).filter(
            TrainCoach.train_id == self.train_id.data,
            TrainCoach.sequence_number == seq,
            TrainCoach.is_deleted == False,
        )
        if self.original_id:
            stmt = stmt.filter(TrainCoach.id != self.original_id)
        if db.session.scalar(stmt):
            raise ValidationError(f"Coach sequence position #{seq} is already assigned on this train.")


class SeatBatchGenerateForm(FlaskForm):
    """Batch generator form to instantiate seats for a coach by rows and columns grid."""
    coach_id = SelectField("Target Train Coach", coerce=int, validators=[DataRequired()])
    rows = IntegerField("Number of Rows (e.g. 18)", validators=[DataRequired(), NumberRange(min=1, max=50)])
    columns = IntegerField("Seats Per Row / Columns (e.g. 4)", validators=[DataRequired(), NumberRange(min=1, max=10)])
    default_berth_type_id = SelectField("Default Berth / Seat Type", coerce=int, validators=[DataRequired()])
    window_columns = StringField("Window Columns (comma-separated, e.g. 1,4)", default="1,4", validators=[Optional()])
    ladies_quota_rows = StringField("Ladies Quota Rows (comma-separated, e.g. 1,2)", validators=[Optional()])
    clear_existing = BooleanField("Clear / Replace Existing Active Seats in this Coach", default=False)
    submit = SubmitField("Generate Coach Seats")


class SeatForm(FlaskForm):
    """Individual seat editor form."""
    coach_id = SelectField("Train Coach", coerce=int, validators=[DataRequired()])
    berth_type_id = SelectField("Berth / Seat Type", coerce=int, validators=[DataRequired()])
    seat_number = StringField("Seat Number (e.g., 1, 2, 1A)", validators=[DataRequired(), Length(min=1, max=10)])
    row_number = IntegerField("Row Number", validators=[DataRequired(), NumberRange(min=1)])
    column_number = IntegerField("Column Number", validators=[DataRequired(), NumberRange(min=1)])
    is_window = BooleanField("Window Seat", default=False)
    is_ladies_quota = BooleanField("Ladies Quota Reserved", default=False)
    submit = SubmitField("Save Seat")

    def __init__(self, original_id=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_id = original_id

    def validate_seat_number(self, field):
        val = field.data.strip()
        stmt = select(Seat).filter(
            Seat.coach_id == self.coach_id.data,
            Seat.seat_number == val,
            Seat.is_deleted == False,
        )
        if self.original_id:
            stmt = stmt.filter(Seat.id != self.original_id)
        if db.session.scalar(stmt):
            raise ValidationError(f"Seat '{val}' already exists in this coach.")

