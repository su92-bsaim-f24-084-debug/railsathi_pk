"""
RailSathi PK - Unified Domain Models Package
Exports exactly all 50 verified models matching the approved architecture specification.
"""
from app.models.base import TimestampMixin, SoftDeleteMixin, utc_now

# Identity & Access (#1-#6)
from app.models.identity import (
    User,
    Role,
    UserRole,
    UserProfile,
    StaffProfile,
    UserSessionLog,
)

# Railway Network & Stations (#7-#11)
from app.models.stations import (
    StationDivision,
    Station,
    StationPlatform,
    FacilityCategory,
    StationFacility,
)

# Rolling Stock & Fleet (#12-#19)
from app.models.trains import (
    TrainType,
    Train,
    TrainOperationalDay,
    CoachClass,
    SeatLayoutType,
    BerthType,
    TrainCoach,
    Seat,
)

# Routes & Kilometric Fares (#20-#22)
from app.models.routes import (
    Route,
    RouteStop,
    FareRule,
)

# Schedules & Daily Runs (#23-#25)
from app.models.schedules import (
    Schedule,
    ScheduleStop,
    JourneyInstance,
)

# Bookings & Reservations (#26-#31)
from app.models.bookings import (
    JourneyCoach,
    SeatReservationLock,
    Booking,
    PassengerTicket,
    TicketSeatAllocation,
    BookingStatusHistory,
)

# Payments & Refunds (#32-#35)
from app.models.payments import (
    PaymentMethod,
    PaymentTransaction,
    RefundRequest,
    RefundAuditTrail,
)

# Operations & Delays (#36-#38)
from app.models.operations import (
    TrainDelayLog,
    JourneyStationActual,
    ServiceAlert,
)

# Complaints & Feedback (#39-#42)
from app.models.complaints import (
    ComplaintCategory,
    Complaint,
    ComplaintTimeline,
    FeedbackRating,
)

# Lost & Found (#43-#45)
from app.models.lost_found import (
    LostFoundCategory,
    LostFoundReport,
    LostFoundClaim,
)

# Special Services & Assistance (#46-#47)
from app.models.services import (
    AssistanceType,
    SpecialAssistanceRequest,
)

# Governance & Audit (#48-#50)
from app.models.governance import (
    NotificationTemplate,
    Notification,
    AuditLog,
)

__all__ = [
    # Base
    "TimestampMixin",
    "SoftDeleteMixin",
    "utc_now",
    # Identity (#1-#6)
    "User",
    "Role",
    "UserRole",
    "UserProfile",
    "StaffProfile",
    "UserSessionLog",
    # Stations (#7-#11)
    "StationDivision",
    "Station",
    "StationPlatform",
    "FacilityCategory",
    "StationFacility",
    # Trains (#12-#19)
    "TrainType",
    "Train",
    "TrainOperationalDay",
    "CoachClass",
    "SeatLayoutType",
    "BerthType",
    "TrainCoach",
    "Seat",
    # Routes (#20-#22)
    "Route",
    "RouteStop",
    "FareRule",
    # Schedules (#23-#25)
    "Schedule",
    "ScheduleStop",
    "JourneyInstance",
    # Bookings (#26-#31)
    "JourneyCoach",
    "SeatReservationLock",
    "Booking",
    "PassengerTicket",
    "TicketSeatAllocation",
    "BookingStatusHistory",
    # Payments (#32-#35)
    "PaymentMethod",
    "PaymentTransaction",
    "RefundRequest",
    "RefundAuditTrail",
    # Operations (#36-#38)
    "TrainDelayLog",
    "JourneyStationActual",
    "ServiceAlert",
    # Complaints (#39-#42)
    "ComplaintCategory",
    "Complaint",
    "ComplaintTimeline",
    "FeedbackRating",
    # Lost & Found (#43-#45)
    "LostFoundCategory",
    "LostFoundReport",
    "LostFoundClaim",
    # Services (#46-#47)
    "AssistanceType",
    "SpecialAssistanceRequest",
    # Governance (#48-#50)
    "NotificationTemplate",
    "Notification",
    "AuditLog",
]
