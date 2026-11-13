"""WTForms for Timetable Schedules & Journey Instance Operations (Phase 5C).

Models:
- Model #23: Schedule
- Model #24: ScheduleStop
- Model #25: JourneyInstance (Individual and Batch Date Range Generator)
- Model #26: JourneyCoach (Reservation Officer + Super Admin)
"""
from datetime import date, time
from flask_wtf import FlaskForm
from wtforms import (
    StringField,
    BooleanField,
    SubmitField,
    SelectField,
    IntegerField,
    DateField,
    TimeField,
    TextAreaField,
)
from wtforms.validators import (
    DataRequired,
    InputRequired,
    Length,
    Optional,
    NumberRange,
    ValidationError,
)
from sqlalchemy import select
from app.extensions import db
from app.models.schedules import Schedule, ScheduleStop, JourneyInstance
from app.models.bookings import JourneyCoach


class ScheduleForm(FlaskForm):
    """Form to create or edit timetable schedules linking a train and corridor route."""
    train_id = SelectField("Operating Train Rake", coerce=int, validators=[DataRequired()])
    route_id = SelectField("Corridor Route", coerce=int, validators=[DataRequired()])
    schedule_code = StringField("Timetable Code (e.g., SCH-1UP-MAIN)", validators=[DataRequired(), Length(min=2, max=30)])
    departure_time = TimeField("Origin Departure Time", format="%H:%M", validators=[DataRequired()])
    arrival_time = TimeField("Terminal Arrival Time", format="%H:%M", validators=[DataRequired()])
    journey_days_span = IntegerField("Total Journey Calendar Days Span", default=1, validators=[DataRequired(), NumberRange(min=1, max=7)])
    is_active = BooleanField("Timetable Blueprint Active", default=True)
    submit = SubmitField("Save Schedule")

    def __init__(self, original_id=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_id = original_id

    def validate_schedule_code(self, field):
        code_clean = field.data.strip().upper()
        stmt = select(Schedule).filter(Schedule.schedule_code == code_clean, Schedule.is_deleted == False)
        if self.original_id:
            stmt = stmt.filter(Schedule.id != self.original_id)
        if db.session.scalar(stmt):
            raise ValidationError(f"An active schedule with code '{code_clean}' already exists.")


class ScheduleStopForm(FlaskForm):
    """Form to configure timetable arrival and departure timings at a station stop."""
    schedule_id = SelectField("Timetable Schedule", coerce=int, validators=[DataRequired()])
    station_id = SelectField("Timetable Station Stop", coerce=int, validators=[DataRequired()])
    stop_sequence = IntegerField("Sequence Order (1, 2, 3...)", validators=[DataRequired(), NumberRange(min=1)])
    scheduled_arrival = TimeField("Scheduled Arrival (blank for origin)", format="%H:%M", validators=[Optional()])
    scheduled_departure = TimeField("Scheduled Departure (blank for destination)", format="%H:%M", validators=[Optional()])
    day_offset = IntegerField("Day Offset from Origin Departure (0=Same day, 1=+1 day)", default=0, validators=[InputRequired(), NumberRange(min=0, max=6)])
    submit = SubmitField("Save Schedule Stop")

    def __init__(self, original_id=None, fixed_schedule_id=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_id = original_id
        self.fixed_schedule_id = fixed_schedule_id

    def validate_stop_sequence(self, field):
        sch_id = self.fixed_schedule_id or self.schedule_id.data
        seq = field.data
        stmt = select(ScheduleStop).filter(
            ScheduleStop.schedule_id == sch_id,
            ScheduleStop.stop_sequence == seq,
            ScheduleStop.is_deleted == False,
        )
        if self.original_id:
            stmt = stmt.filter(ScheduleStop.id != self.original_id)
        if db.session.scalar(stmt):
            raise ValidationError(f"Stop sequence #{seq} is already assigned on this schedule.")

        # Contiguous check: sequence must start at 1 and not leave gaps
        existing_seqs = db.session.scalars(
            select(ScheduleStop.stop_sequence)
            .filter(ScheduleStop.schedule_id == sch_id, ScheduleStop.is_deleted == False)
            .order_by(ScheduleStop.stop_sequence)
        ).all()
        if not self.original_id:
            max_seq = max(existing_seqs) if existing_seqs else 0
            if seq > max_seq + 1:
                raise ValidationError(
                    f"Stop sequence must be contiguous starting from 1 (next expected sequence is #{max_seq + 1})."
                )

    def validate_scheduled_departure(self, field):
        if self.scheduled_arrival.data and field.data:
            if field.data < self.scheduled_arrival.data:
                raise ValidationError("Departure time cannot be earlier than arrival time on the same day.")


class JourneyInstanceForm(FlaskForm):
    """Form to edit or manually create a single date calendar journey instance."""
    schedule_id = SelectField("Timetable Schedule", coerce=int, validators=[DataRequired()])
    journey_date = DateField("Journey Calendar Date", validators=[DataRequired()])
    status = SelectField(
        "Operational Status",
        choices=[
            ("Scheduled", "Scheduled"),
            ("Running", "Running"),
            ("Delayed", "Delayed"),
            ("Completed", "Completed"),
            ("Cancelled", "Cancelled"),
        ],
        default="Scheduled",
        validators=[DataRequired()],
    )
    current_delay_minutes = IntegerField("Current Delay (Minutes)", default=0, validators=[InputRequired(), NumberRange(min=0)])
    is_booking_open = BooleanField("Passenger Ticketing Open", default=True)
    cancellation_reason = TextAreaField("Cancellation / Disruption Notice", validators=[Optional()])
    submit = SubmitField("Save Journey Instance")

    def __init__(self, original_id=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_id = original_id

    def validate_journey_date(self, field):
        stmt = select(JourneyInstance).filter(
            JourneyInstance.schedule_id == self.schedule_id.data,
            JourneyInstance.journey_date == field.data,
            JourneyInstance.is_deleted == False,
        )
        if self.original_id:
            stmt = stmt.filter(JourneyInstance.id != self.original_id)
        if db.session.scalar(stmt):
            raise ValidationError(f"A journey for schedule #{self.schedule_id.data} on {field.data} already exists.")


class JourneyGenerateForm(FlaskForm):
    """Batch generator form to instantiate journey instances over a calendar range."""
    schedule_id = SelectField("Timetable Schedule", coerce=int, validators=[DataRequired()])
    start_date = DateField("From Date", default=date.today, validators=[DataRequired()])
    end_date = DateField("To Date", validators=[DataRequired()])
    auto_attach_coaches = BooleanField("Automatically Attach Rake Coaches (JourneyCoaches)", default=True)
    submit = SubmitField("Generate Journeys")

    def validate_end_date(self, field):
        if field.data < self.start_date.data:
            raise ValidationError("End date cannot be earlier than start date.")
        if (field.data - self.start_date.data).days > 90:
            raise ValidationError("Generation window cannot exceed 90 calendar days at a time.")


class JourneyCoachForm(FlaskForm):
    """Form to attach or adjust an operational coach on a specific journey instance."""
    journey_instance_id = SelectField("Target Journey Instance", coerce=int, validators=[DataRequired()])
    train_coach_id = SelectField("Train Coach Rake Carriage", coerce=int, validators=[DataRequired()])
    sequence_in_train = IntegerField("Position in Train (1, 2, 3...)", default=1, validators=[DataRequired(), NumberRange(min=1)])
    available_seats_count = IntegerField("Available Berth / Seat Allocation", default=0, validators=[InputRequired(), NumberRange(min=0)])
    is_available = BooleanField("Coach Available for Reservation", default=True)
    submit = SubmitField("Save Journey Coach")

    def __init__(self, original_id=None, fixed_journey_id=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_id = original_id
        self.fixed_journey_id = fixed_journey_id

    def validate_train_coach_id(self, field):
        j_id = self.fixed_journey_id or self.journey_instance_id.data
        stmt = select(JourneyCoach).filter(
            JourneyCoach.journey_instance_id == j_id,
            JourneyCoach.train_coach_id == field.data,
        )
        if self.original_id:
            stmt = stmt.filter(JourneyCoach.id != self.original_id)
        if db.session.scalar(stmt):
            raise ValidationError("This carriage is already attached to this journey instance.")

