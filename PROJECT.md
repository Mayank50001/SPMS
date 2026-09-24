# Smart Parking Management System (SPMS)

> Academic Mini Project  
> Stack: Django + Django REST Framework + PostgreSQL + React + TypeScript  
> Development Model: Human-led, AI-assisted  
> Status: In Development

---

# 1. Project Purpose

The Smart Parking Management System (SPMS) is a software-based parking management platform that allows users to:

- discover parking lots
- view available parking slots
- reserve parking slots
- make digital payments through a simulated/integrated payment workflow
- manage bookings
- manage parking lots and slots
- manage users and system-wide rules
- view parking and transaction reports

The project is being developed as an academic mini-project.

The goal is not to reproduce a production-grade parking platform.

The goal is to build a reasonably complete software system while learning:

- backend architecture
- REST API design
- relational database modelling
- authentication and authorization
- transactional consistency
- booking concurrency
- business-rule implementation
- frontend-backend integration
- testing
- debugging
- software engineering practices

---

# 2. Source of Requirements

The primary functional reference for this project is:

`SE_SRS_EXP1.pdf`

The SRS describes the Smart Parking Management System and its major functional areas:

1. User registration, authentication and role management
2. Parking slot search and booking
3. Digital payment processing
4. Vehicle tracking and slot occupancy
5. Parking lot and slot management
6. Platform administration and reporting
7. Notifications and alerts

For this academic implementation, hardware-dependent requirements are intentionally excluded.

The implementation must therefore NOT attempt to build:

- physical parking sensors
- ultrasonic/infrared sensors
- ANPR cameras
- physical entry/exit gates
- boom barriers
- physical QR scanners
- IoT hardware
- MQTT-based hardware communication
- physical vehicle tracking

The software should instead provide reasonable software-level simulations where required.

---

# 3. Project Scope

## 3.1 Included

The project will include:

### Authentication

- Consumer registration
- Login
- Logout
- Password handling
- Role-based authorization
- Administrator-created Manager accounts
- Administrator-created Administrator accounts
- Consumer vehicle registration

### Consumer Features

- View/search parking lots
- View available slots
- View slot information
- Select vehicle
- Create booking
- Temporary slot hold
- Booking confirmation
- Booking history
- Booking cancellation
- Booking extension
- Payment simulation
- Digital receipt
- Booking QR code representation

### Parking Manager Features

- View assigned parking lots
- Create/manage slots within assigned lots
- Configure slot type
- Configure pricing
- Mark slots available/unavailable
- Create walk-in bookings
- Record cash payment for walk-ins
- View bookings
- View occupancy
- View revenue/occupancy reports

### Administrator Features

- Manage users
- Manage Parking Managers
- Manage Administrators
- Manage parking lots
- Assign managers to lots
- Configure global business rules
- View all bookings
- View transactions
- View platform-level statistics
- Suspend users

### Software Simulation

Since hardware is excluded:

- Slot occupancy may be changed through software/admin actions.
- Vehicle entry/exit may be simulated through software actions.
- Payment processing may use a mock payment gateway.
- Notifications may initially be represented as database records/logs instead of real SMS/push infrastructure.

---

# 4. Explicitly Out of Scope

The following MUST NOT be implemented.

## Hardware

- IoT parking sensors
- Ultrasonic sensors
- Infrared sensors
- ANPR cameras
- RFID hardware
- physical gate controllers
- boom barriers
- physical QR scanners

## Hardware Communication

- MQTT
- sensor heartbeat processing
- real sensor event ingestion
- camera event ingestion

## Physical Vehicle Tracking

The project does not track a vehicle's physical GPS position.

The system only manages:

- registered vehicles
- bookings
- parking slots
- simulated occupancy
- simulated entry/exit events

## Production Payment Infrastructure

Do not implement real financial payment processing.

A mock payment service may be created to simulate:

- payment success
- payment failure
- refund
- transaction ID

Never store:

- card number
- CVV
- UPI PIN
- banking credentials

---

# 5. Technology Stack

## Backend

- Python
- Django
- Django REST Framework
- PostgreSQL

## Frontend

- React
- TypeScript
- Vite

## API

- REST
- JSON
- OpenAPI documentation where practical

## Development

Recommended:

- Git
- Docker / Docker Compose where useful
- pytest or Django TestCase
- Postman / Bruno / curl for API testing

---

# 6. High-Level Architecture

The system follows an API-first architecture.

```text
                    ┌──────────────────────┐
                    │      React App       │
                    │     TypeScript       │
                    └──────────┬───────────┘
                               │
                               │ HTTP/JSON
                               ▼
                    ┌──────────────────────┐
                    │     Django REST      │
                    │        API           │
                    ├──────────────────────┤
                    │ Authentication       │
                    │ Authorization        │
                    │ Booking              │
                    │ Parking              │
                    │ Payment              │
                    │ Users                │
                    │ Reports              │
                    │ Notifications        │
                    └──────────┬───────────┘
                               │
                               │ SQL
                               ▼
                    ┌──────────────────────┐
                    │     PostgreSQL       │
                    └──────────────────────┘
```

The frontend must not directly access PostgreSQL.

The frontend communicates only with the Django REST API.

---

# 7. Development Philosophy

This is a HUMAN-LED project.

The AI coding agent is an assistant, not the developer.

The human developer owns:

- architecture
- data model decisions
- business logic
- algorithms
- security decisions
- transaction/concurrency decisions
- API contracts
- debugging decisions
- final code approval

The AI agent assists with:

- frontend implementation
- boilerplate
- project setup
- repetitive code
- code review
- test scaffolding
- debugging assistance
- documentation
- identifying bugs
- suggesting alternatives

---

# 8. CRITICAL AI AGENT OPERATING RULES

These rules apply to Cursor, Antigravity, Claude Code, Copilot, or any other coding agent.

## Rule 1 — NEVER generate the whole project

Never create the entire application in one operation.

Development MUST happen incrementally.

At any point, implement only the current milestone.

---

## Rule 2 — Backend logic belongs to the human developer

The agent must NOT automatically implement important backend logic.

Instead, when the human asks for help with a backend feature:

1. Explain what needs to be done.
2. Identify relevant files.
3. Explain the required data flow.
4. Identify edge cases.
5. Provide function/class/API signatures if useful.
6. Insert a TODO or placeholder.
7. Give implementation hints.
8. Let the human write the actual logic.

Example:

```python
def create_booking(...):
    # TODO: Implement booking creation.
    #
    # Think about:
    # 1. Does the slot exist?
    # 2. Is the slot compatible with the vehicle?
    # 3. Is the slot available for the requested time window?
    # 4. Should a transaction be used?
    # 5. What prevents two users from booking the same slot?
    # 6. When should the temporary hold expire?
    #
    # Implement this logic manually.
    pass
```

Do NOT replace the TODO with a complete implementation unless the human explicitly asks for the implementation.

---

# 9. What Counts as "Core Backend Logic"

The agent should NOT implement these automatically:

- booking allocation
- booking conflict detection
- overlapping time-window logic
- temporary slot holds
- booking state transitions
- payment state transitions
- refund rules
- cancellation rules
- overstay calculations
- pricing calculations
- authorization decisions
- manager-to-lot permission checks
- occupancy calculations
- report aggregation logic
- transaction/concurrency handling
- critical validation logic

The human developer must implement these.

---

# 10. Backend Assistance Levels

When working on backend code, use this order:

### Level 1 — Explain

Explain the problem and relevant concepts.

### Level 2 — Map

Show:

```text
Request
   ↓
URL
   ↓
View/ViewSet
   ↓
Serializer
   ↓
Service/Business Logic
   ↓
Model
   ↓
Database
```

### Level 3 — Placeholder

Create the function/class with TODO comments.

### Level 4 — Hints

Explain the algorithm without writing the implementation.

### Level 5 — Review

The human writes the implementation.

The agent reviews it for:

- correctness
- edge cases
- security
- database behavior
- maintainability
- race conditions

### Level 6 — Debug

If the human's implementation fails, explain why and guide the fix.

Only provide complete replacement code when explicitly requested.

---

### Why all this?

Because the human is a student who is learning backend engineering and wants to become an expert in designing and implementing backend systems.

# 11. Frontend Exception

The human developer does NOT want to spend significant time implementing frontend code.

Therefore:

> The AI agent MAY implement frontend code substantially or completely.

The agent may:

- create React components
- create TypeScript types
- create pages
- implement routing
- implement forms
- implement API integration
- implement dashboards
- implement tables
- implement loading/error states
- implement authentication UI
- implement responsive layouts

However, frontend implementation must still respect the backend API contract.

The agent must not invent backend APIs merely to make the frontend work.

If an API does not exist yet:

```text
TODO: Backend endpoint required.

Expected:
GET /api/parking-lots/

Do not create a fake backend implementation.
```

---

# 12. Agent Must Not Change Architecture Silently

The agent must never:

- replace Django with another backend framework
- replace PostgreSQL
- introduce Node.js backend
- introduce MongoDB
- introduce GraphQL
- introduce microservices
- introduce Kafka
- introduce Redis unless explicitly approved
- introduce Celery unless explicitly approved
- introduce unnecessary infrastructure
- restructure the application without approval

If a change appears beneficial:

1. Explain why.
2. State the trade-offs.
3. Ask the human for approval.

---

# 13. Keep the Project Monolithic

This is an academic mini-project.

Use a modular monolith.

Recommended backend structure:

```text
backend/
├── manage.py
├── config/
│   ├── settings/
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
│
├── apps/
│   ├── accounts/
│   ├── parking/
│   ├── bookings/
│   ├── payments/
│   ├── notifications/
│   └── reports/
│
├── requirements/
└── tests/
```

Do not convert the system into microservices.

---

# 14. Suggested Domain Separation

## accounts

Responsible for:

- users
- roles
- authentication
- vehicles
- account status

## parking

Responsible for:

- parking lots
- parking slots
- slot types
- pricing configuration
- manager assignments

## bookings

Responsible for:

- bookings
- booking lifecycle
- slot reservation
- cancellation
- extension
- temporary holds

## payments

Responsible for:

- payment records
- mock payment gateway
- refunds
- receipts
- transaction status

## notifications

Responsible for:

- notification records
- booking notifications
- payment notifications
- system alerts

## reports

Responsible for:

- occupancy reports
- revenue reports
- booking statistics
- administrator dashboard metrics

---

# 15. Core Domain Entities

The initial data model should contain approximately the following entities.

```text
User
  │
  ├── Vehicle
  │
  └── Booking
          │
          ├── ParkingSlot
          │       └── ParkingLot
          │
          └── Payment
```

Additional entities:

```text
User
Vehicle
ParkingLot
ParkingSlot
ManagerLotAssignment
Booking
Payment
Notification
BusinessRule
AuditLog
```

The exact model structure is a design decision to be made during implementation.

Do not blindly generate all models at once.

---

# 16. Roles

The system has three primary roles.

## Consumer

Can:

- register
- login
- manage own vehicles
- search parking
- view slots
- create bookings
- pay
- cancel bookings
- extend bookings
- view booking history

Cannot:

- manage lots
- manage other users
- modify global rules
- access other consumers' data

---

## Parking Manager

Can:

- manage assigned lots
- manage slots
- configure pricing within allowed limits
- view bookings for assigned lots
- create walk-in bookings
- record cash payments
- manage simulated occupancy
- generate reports for assigned lots

Cannot:

- access unrelated lots
- modify global platform rules
- manage administrator accounts

---

## Administrator

Can:

- manage users
- manage managers
- manage parking lots
- assign managers
- define global business rules
- view platform-wide bookings
- view transactions
- suspend users
- view reports

---

# 17. Booking State Machine

Booking states should be explicitly modeled.

Suggested states:

```text
PENDING_PAYMENT
      │
      ├── payment success
      ▼
  CONFIRMED
      │
      ├── vehicle enters
      ▼
 IN_PROGRESS
      │
      ├── normal completion
      ▼
  COMPLETED

CONFIRMED
   │
   ├── consumer cancels
   ▼
CANCELLED

PENDING_PAYMENT
   │
   ├── payment timeout
   ▼
EXPIRED

CONFIRMED / IN_PROGRESS
   │
   ├── dispute / manager action
   ▼
TERMINATED
```

The exact states and transitions must be validated during implementation.

Do not add states simply because they appear convenient.

---

# 18. Slot State

Suggested software-level slot states:

```text
AVAILABLE
RESERVED
OCCUPIED
OUT_OF_SERVICE
```

The system must maintain a clear distinction between:

- physical occupancy
- booking reservation
- temporary booking hold

Do not collapse these concepts without first reasoning about the consequences.

---

# 19. Booking Rules

The following business rules come from the SRS.

### Temporary Hold

A selected slot is temporarily held for payment for 5 minutes.

If payment is not completed:

```text
temporary hold
      ↓
expired
      ↓
slot becomes available
```

---

### Cancellation

A confirmed booking may receive a full refund if cancelled at least 30 minutes before its start time.

Cancellation within the cutoff is non-refundable.

---

### Overstay

Overstay penalty:

```text
1.5 × applicable hourly rate
```

for every additional hour or part thereof beyond the booked duration.

---

### Walk-in Booking

Parking Managers may create walk-in bookings.

Walk-in bookings may use cash payment.

---

### Out-of-Service

An out-of-service slot must not appear in Consumer availability results.

---

# 20. Critical Database Invariants

The following invariants are more important than the API itself.

## Invariant 1

Two users must never have confirmed overlapping bookings for the same physical slot.

---

## Invariant 2

A Consumer must never access another Consumer's:

- vehicles
- bookings
- payment records

---

## Invariant 3

A Parking Manager must only manage assigned parking lots.

---

## Invariant 4

A Parking Manager cannot set pricing above the administrator-defined maximum.

---

## Invariant 5

An out-of-service slot cannot be booked.

---

## Invariant 6

An expired payment hold must not permanently block the slot.

---

# 21. Concurrency

Booking is a concurrency-sensitive operation.

The implementation must consider:

```text
User A ──────┐
             ├──> Same Slot
User B ──────┘
```

Both requests may arrive nearly simultaneously.

The system must prevent:

```text
User A → confirms Slot A
User B → confirms Slot A
```

for overlapping booking windows.

The human developer must design and implement the concurrency protection.

The AI agent should explain:

- database transactions
- row locking
- isolation
- unique constraints
- race conditions

but should not silently implement the final solution.

---

# 22. API Design

Use RESTful APIs.

Example API structure:

```text
/api/auth/
/api/users/
/api/vehicles/

/api/parking-lots/
/api/parking-lots/{id}/slots/

/api/bookings/
/api/bookings/{id}/
/api/bookings/{id}/cancel/
/api/bookings/{id}/extend/

/api/payments/
/api/payments/{id}/refund/

/api/notifications/

/api/reports/
```

These are starting points, not immutable contracts.

API names must be finalized before frontend integration.

---

# 23. API Contract Rule

Before implementing a frontend feature:

1. Define the API.
2. Define request structure.
3. Define response structure.
4. Define authentication requirements.
5. Define possible errors.
6. Implement backend.
7. Test backend.
8. Integrate frontend.

Do not build frontend around guessed APIs.

---

# 24. Authentication

Use Django's authentication infrastructure where practical.

Authentication must support:

- registration
- login
- logout
- password management
- role identification

The frontend must not determine whether a user is authorized.

Authorization must be enforced by the backend.

For example:

```text
Frontend says:
"I am an ADMIN."

Backend must still verify:
"Is this authenticated user actually an ADMIN?"
```

Never trust role information supplied only by the client.

---

# 25. Authorization

Authorization must be checked server-side.

Examples:

```text
Consumer
   ↓
GET /api/bookings/123/
   ↓
Does booking 123 belong to this Consumer?
```

```text
Manager
   ↓
PATCH /api/parking-lots/10/slots/25/
   ↓
Is Manager assigned to Lot 10?
```

```text
Administrator
   ↓
PATCH /api/business-rules/
   ↓
Is user actually an Administrator?
```

---

# 26. Payment Architecture

Use a payment abstraction.

Example:

```text
Booking
   ↓
Payment Service
   ↓
Payment Gateway Interface
   ↓
Mock Payment Gateway
```

The application should not directly depend on a specific payment provider.

Example conceptual interface:

```python
class PaymentGateway:
    def create_payment(...):
        pass

    def verify_payment(...):
        pass

    def refund_payment(...):
        pass
```

The human developer should implement the actual behavior.

---

# 27. Notifications

For the academic project, notifications may initially be stored in the database.

Example:

```text
Notification
-------------------------
id
user
type
title
message
is_read
created_at
```

A real SMS/email/push provider is optional and not required for the core project.

---

# 28. Simulated Occupancy

Because hardware is excluded, occupancy must be software-controlled.

Possible Manager functionality:

```text
Slot A01
Status: AVAILABLE

        ↓

Manager selects:
"Mark Occupied"

        ↓

Slot A01
Status: OCCUPIED
```

This allows the system to demonstrate occupancy management without physical hardware.

---

# 29. Reports

The system should provide:

## Manager Reports

- total bookings
- active bookings
- completed bookings
- occupancy
- revenue
- cancellations

Filtered by:

- date
- parking lot

## Administrator Reports

- total users
- total lots
- total slots
- total bookings
- total revenue
- occupancy rate
- payment failures
- cancelled bookings

---

# 30. Frontend Requirements

The React frontend should provide separate experiences based on role.

## Consumer

Pages:

```text
Login
Register
Dashboard
Parking Search
Parking Lot Details
Slot Selection
Booking
Payment
Booking Confirmation
My Bookings
Booking Details
Vehicles
Profile
```

## Parking Manager

Pages:

```text
Dashboard
My Parking Lots
Lot Details
Slot Management
Bookings
Walk-in Booking
Occupancy
Reports
Profile
```

## Administrator

Pages:

```text
Dashboard
Users
Managers
Parking Lots
Business Rules
Bookings
Transactions
Reports
Audit Logs
```

---

# 31. Frontend Design Principle

The frontend should be practical rather than visually extravagant.

Prioritize:

1. usability
2. clear navigation
3. correct API integration
4. loading states
5. error handling
6. form validation
7. responsive layout

Do not waste development time on unnecessary animations.

---

# 32. Validation

Validation should exist at multiple levels.

## Frontend

Provide immediate user feedback.

## API Serializer

Validate request data.

## Business Logic

Validate business rules.

## Database

Use database constraints where appropriate.

Never assume frontend validation is sufficient.

---

# 33. Error Handling

API errors should be predictable.

Example:

```json
{
  "error": "BOOKING_CONFLICT",
  "message": "The selected slot is no longer available."
}
```

The frontend should display useful user-facing messages.

Do not expose:

- stack traces
- SQL errors
- secrets
- internal implementation details

to users.

---

# 34. Testing Strategy

Testing should happen incrementally.

## Unit Tests

Test:

- pricing calculation
- cancellation eligibility
- overstay calculation
- booking state transitions
- authorization rules

## Integration Tests

Test:

- registration
- login
- booking
- payment
- cancellation
- refund
- manager operations

## API Tests

Test:

- valid requests
- invalid requests
- unauthorized requests
- forbidden requests
- missing resources
- conflict cases

---

# 35. Important Edge Cases

The project must explicitly consider:

### Booking

- slot does not exist
- slot is out of service
- slot already booked
- overlapping booking
- invalid duration
- booking in the past
- payment timeout
- duplicate payment callback
- cancellation after cutoff
- extension conflict

### Authentication

- duplicate email
- duplicate phone
- wrong password
- repeated failed login
- inactive user
- unauthorized role

### Manager

- manager accesses unrelated lot
- pricing above maximum
- invalid slot type
- deleting a slot with active bookings

### Payment

- payment succeeds
- payment fails
- payment callback repeated
- refund requested
- refund fails

---

# 36. Development Phases

Development must happen in small milestones.

---

## Phase 0 — Repository Setup

Goal:

```text
Repository
   ↓
Django project
   ↓
React project
   ↓
PostgreSQL connection
```

Deliverables:

- Git repository
- backend project
- frontend project
- PostgreSQL database
- environment configuration
- README
- `.gitignore`

No business logic.

---

# Phase 1 — Backend Foundation

Implement:

- Django configuration
- PostgreSQL connection
- application structure
- base API configuration
- environment variables
- basic health endpoint

Example:

```text
GET /api/health/
```

Expected:

```json
{
  "status": "ok"
}
```

Human writes backend logic.

Agent assists with setup and boilerplate.

---

# Phase 2 — Authentication and Users

Implement:

- User model
- roles
- registration
- login
- authentication
- authorization
- Consumer profile
- vehicles

Human writes:

- role logic
- authorization logic
- ownership checks

Agent can create frontend authentication pages.

---

# Phase 3 — Parking Domain

Implement:

- ParkingLot
- ParkingSlot
- manager assignment
- slot types
- pricing

Human writes:

- manager authorization
- pricing validation
- lot ownership/assignment rules

---

# Phase 4 — Booking

This is the most important backend phase.

Implement incrementally:

1. booking model
2. booking states
3. availability query
4. booking creation
5. temporary hold
6. confirmation
7. cancellation
8. extension
9. booking history

Do NOT implement all booking functionality in one agent request.

Each operation must be implemented and tested separately.

---

# Phase 5 — Payment

Implement:

- Payment model
- payment states
- mock payment gateway
- payment creation
- payment confirmation
- receipt
- refund

No real financial processing.

---

# Phase 6 — Occupancy Simulation

Implement:

- software-controlled slot occupancy
- Manager occupancy controls
- booking/occupancy interaction
- entry/exit simulation if required

No hardware integration.

---

# Phase 7 — Notifications

Implement:

- notification model
- notification creation
- notification listing
- read/unread status

Real external notification providers are optional.

---

# Phase 8 — Reports

Implement:

- manager reports
- administrator reports
- booking statistics
- revenue aggregation
- occupancy aggregation

The human developer should implement the important aggregation logic.

---

# Phase 9 — React Frontend

The AI agent may implement most frontend code.

Integrate:

- authentication
- consumer dashboard
- parking search
- booking flow
- payment flow
- manager dashboard
- administrator dashboard
- reports

Frontend must consume real backend APIs.

No fake hardcoded backend data except explicitly identified development mocks.

---

# Phase 10 — Testing and Hardening

Test:

- authentication
- authorization
- booking conflicts
- payment failures
- cancellation
- refunds
- role boundaries
- manager lot restrictions
- data ownership
- API validation

Perform manual API testing.

Perform frontend integration testing.

---

# 37. Incremental Agent Workflow

Every coding session should follow:

```text
1. Inspect repository
        ↓
2. Identify current milestone
        ↓
3. Identify exact task
        ↓
4. Explain plan
        ↓
5. Modify only required files
        ↓
6. Run relevant tests
        ↓
7. Report what changed
        ↓
8. Report remaining TODOs
```

Never jump several milestones ahead.

---

# 38. Maximum Change Principle

Each agent request should have a small scope.

Good:

```text
Implement the ParkingLot model only.
Do not create serializers, views or frontend.
```

Good:

```text
Create the Consumer registration API.
Do not implement login or JWT yet.
```

Good:

```text
Create the React parking-lot list page using the existing API.
```

Bad:

```text
Build the entire parking system.
```

Bad:

```text
Implement authentication, booking, payments and dashboards.
```

---

# 39. Agent Response Format

For backend tasks, the agent should respond in this structure:

```text
## Understanding

What we are implementing.

## Files

Files that need to change.

## Backend Flow

Request → View → Serializer → Business Logic → Database

## What You Need To Implement

The core logic the human should write.

## Placeholder

TODO code or skeleton.

## Hints

Important implementation considerations.

## Edge Cases

Cases that must be handled.

## Testing

Tests that should be written.

## Done When

Definition of completion.
```

---

# 40. Backend TODO Convention

Use explicit TODO markers.

Example:

```python
# TODO(HUMAN):
# Implement booking conflict detection.
#
# Questions to answer:
# - What counts as overlapping?
# - Which booking states should block the slot?
# - Should expired bookings be ignored?
# - How will concurrent requests be handled?
# - Does this require a database transaction?
```

The agent should not remove the TODO until the human implements the logic.

---

# 41. Agent Code Generation Restrictions

For backend tasks, the agent must not:

- generate hundreds of lines unnecessarily
- create unrelated files
- implement future phases
- add speculative abstractions
- introduce unnecessary dependencies
- write business logic without permission
- silently modify database design
- silently modify API contracts
- generate fake data as a substitute for backend implementation

---

# 42. Database Migration Rule

Migrations are important.

Before generating a migration, the agent should explain:

```text
Model change
    ↓
Expected database change
    ↓
Potential data implications
    ↓
Migration
```

Do not repeatedly modify models and generate migrations blindly.

---

# 43. Git Workflow

Use small commits.

Recommended:

```text
feat(accounts): add custom user model
feat(accounts): add consumer registration
feat(parking): add parking lot model
feat(parking): add parking slot model
feat(bookings): add booking model
feat(bookings): add availability endpoint
feat(bookings): implement booking creation
```

Do not create one giant commit containing the whole application.

---

# 44. Environment Variables

Secrets must never be committed.

Example:

```env
DEBUG=True

DB_NAME=
DB_USER=
DB_PASSWORD=
DB_HOST=
DB_PORT=

SECRET_KEY=

PAYMENT_GATEWAY_KEY=
```

Use:

```text
.env
```

and provide:

```text
.env.example
```

---

# 45. Security Requirements

The backend must enforce:

- authentication
- authorization
- ownership checks
- input validation
- password hashing
- CSRF protection where applicable
- secure secret handling
- safe database queries
- rate limiting where practical
- protection against privilege escalation

Never trust:

- user role from frontend
- user ID from request body
- price calculated by frontend
- booking status supplied by frontend
- payment status supplied by frontend

The backend is authoritative.

---

# 46. Backend Authority Principle

The client may REQUEST an action.

The server decides whether that action is valid.

Example:

```text
Frontend:

"Create booking for ₹200"

Backend:

"Let me calculate the price myself."

        ↓

Backend calculates:

₹250

        ↓

Backend stores ₹250
```

Never trust client-side prices.

Similarly:

```text
Frontend:
"User is administrator."

Backend:
"Check database."
```

---

# 47. No Premature Complexity

Do NOT introduce:

- microservices
- Kubernetes
- Kafka
- event sourcing
- CQRS
- distributed locks
- complex caching
- service mesh

unless a concrete project requirement later justifies them.

This is a modular monolith.

The purpose is learning and completing a reliable academic system.

---

# 48. Definition of Done

A feature is NOT complete merely because the code exists.

A feature is complete when:

```text
Requirements understood
        ↓
Database design complete
        ↓
Backend implemented
        ↓
Authorization verified
        ↓
Edge cases handled
        ↓
Tests written
        ↓
API manually tested
        ↓
Frontend integrated
        ↓
Frontend tested
        ↓
Documentation updated
```

---

# 49. Current Development Rule

At the beginning of every new task, the agent must determine:

```text
What phase are we in?

What is the smallest feature we are implementing?

What existing code does it depend on?

What should NOT be touched?

What does the human need to implement?
```

If the request is too broad, break it into smaller tasks before modifying code.

---

# 50. Project Success Criteria

The project is successful if it demonstrates a coherent end-to-end workflow:

```text
Consumer
   │
   ├── Register
   │
   ├── Add Vehicle
   │
   ├── Search Parking
   │
   ├── Select Slot
   │
   ├── Create Booking
   │
   ├── Make Mock Payment
   │
   ├── Receive Confirmation
   │
   └── View Booking
```

and:

```text
Parking Manager
   │
   ├── Manage Lot
   ├── Manage Slots
   ├── Simulate Occupancy
   ├── Manage Walk-ins
   └── View Reports
```

and:

```text
Administrator
   │
   ├── Manage Users
   ├── Manage Managers
   ├── Manage Lots
   ├── Configure Rules
   ├── View Transactions
   └── View Platform Reports
```

---

# 51. Final Agent Instruction

You are an AI coding assistant working under a human developer.

The human developer is the lead engineer.

Your job is to make the human developer better at building the system, not to replace their learning.

For backend work:

> Teach → Explain → Map → Skeleton → TODO → Hints → Review → Debug.

Do not automatically write the core business logic.

For frontend work:

> You may implement the majority of the code because frontend implementation is intentionally delegated to the AI assistant.

Always work incrementally.

Never implement future features without being asked.

Never silently change architecture.

Never invent APIs.

Never hide complexity.

When there is an important engineering decision, explain the decision and its trade-offs before implementing it.

When the human makes a design mistake, point it out directly.

When the human implementation is correct, explain why it works.

When the human implementation is incorrect, identify the exact failure and guide them toward fixing it.

The human owns the final code.

---

# 52. First Task

When beginning development from this document, DO NOT start implementing the entire project.

Start with:

```text
PHASE 0 — Repository Setup
```

First inspect the repository.

Then propose the minimum project structure.

Then create only the initial Django + React + PostgreSQL setup.

Do not create:

- booking logic
- payment logic
- dashboards
- complete models
- complete APIs
- mock business logic

until their respective phases are reached.
