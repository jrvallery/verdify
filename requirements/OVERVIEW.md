# Project Verdify - System Overview

## Executive Summary

Project Verdify is an end-to-end IoT system for greenhouse automation that combines local control (ESPHome controllers), a cloud API, and an AI-assisted Planning Engine. The MVP delivers reliable telemetry, deterministic climate control via a declarative state machine, irrigation/fertilization/lighting scheduling, and a clean configuration model suitable for later scale out.

## Goals

- **Operational control & safety**: Maintain crop appropriate climate while enforcing immutable greenhouse guard rails (min/max temp, min/max VPD).
- **Deterministic behavior**: Use a declarative state machine (MUST_ON/MUST_OFF at each temp_stage × humi_stage intersection) with explicit fan group staging and rotation.
- **LLM assisted planning**: Generate plans (setpoints, deltas, hysteresis, irrigation/fertilization/lighting) informed by crop recipes, observations, telemetry history, and weather; clamp outputs to guard rails.
- **Simple, observable data**: Store all telemetry, actuator events, and controller status in a query friendly schema (TimescaleDB) for reports (e.g., "how long was Fan 1 ON today?").
- **Clear onboarding**: Claim controllers using a user facing device_name (verdify-aabbcc) and a short claim code; keep boot behavior simple and resilient.
- **Extensibility without refactors**: Normalize sensor/actuator kinds and units; keep schemas stable so new hardware is additive, not disruptive.

## Scope (MVP)

### Components

- **App (Web)**: Next.js/React/TypeScript frontend with automatic API client generation, comprehensive CRUD interfaces, real-time dashboards, and responsive design
- **API (FastAPI)**: Auth (JWT), device tokens, full CRUD, config/plan serving with ETags, HTTP telemetry ingest, reporting endpoints
- **Planning Engine (Celery + LLM)**: Periodic plan generation for climate (min/max temp & VPD, stage offsets, hysteresis) and schedules (irrigation/fertilization/lighting)
- **Controller (ESPHome on ESP32/Kincony A16S)**: Pulls config/plan; runs climate loop locally; computes VPD/enthalpy; executes schedules; posts telemetry/events; supports physical override buttons

### Frontend Architecture (Next.js + TypeScript)

**Technology Stack:**
- **Framework**: Next.js with App Router for server-side rendering and client-side interactivity
- **Language**: TypeScript for type safety across frontend-backend boundary
- **UI Library**: Chakra UI component library (aligned with FastAPI template)
- **State Management**: React Query (TanStack Query) for server state and caching
- **API Client**: Auto-generated TypeScript client from OpenAPI specification

**Client Generation:**
```bash
# Generate type-safe API client from backend OpenAPI
npx openapi-typescript-codegen --input http://localhost:8000/openapi.json --output src/api/client
```

**Component Architecture:**
- **Layout Components**: Navigation, sidebar, breadcrumbs, responsive containers
- **CRUD Components**: GreenhouseForm, ZoneForm, SensorForm, ActuatorForm with validation
- **Dashboard Components**: Real-time charts, telemetry widgets, status indicators
- **Configuration Components**: State machine editor, plan preview, config diff viewer
- **Data Components**: Tables with sorting/filtering, infinite scroll, export functions

**Key Features:**
- **Type Safety**: End-to-end type safety from database through API to frontend
- **Real-time Updates**: WebSocket connections for live telemetry and status updates  
- **Offline Support**: Service worker for offline capability and data synchronization
- **Responsive Design**: Mobile-first design with tablet and desktop optimization
- **Error Handling**: Consistent error boundaries and user-friendly error messages
- **Caching**: Intelligent caching with ETag support for config/plan data

### Backend Architecture (FastAPI + Celery + Redis)

**Core Services:**
- **FastAPI Application**: Main API server with SQLModel ORM, automatic OpenAPI generation, and dependency injection
- **Celery Worker**: Background task processing for AI planning, data analysis, and scheduled operations
- **Redis**: Message broker for Celery tasks and caching layer for frequently accessed data
- **PostgreSQL + TimescaleDB**: Primary database with time-series extensions for telemetry storage

**Task Queue Integration:**
```python
# app/core/celery_app.py
from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "verdify",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.planner", "app.tasks.analytics", "app.tasks.notifications"]
)

# app/tasks/planner.py
from celery import shared_task
from app.services.planning import PlanningService

@shared_task(bind=True, max_retries=3)
def generate_plan(self, greenhouse_id: str):
    """Generate AI plan for greenhouse with retry logic"""
    try:
        service = PlanningService()
        result = service.generate_plan(greenhouse_id)
        return {"status": "success", "plan_id": result.id}
    except Exception as exc:
        self.retry(countdown=60, exc=exc)
```

**Background Tasks:**
- **Plan Generation**: Periodic AI planning triggered by schedules or manual requests
- **Data Analytics**: Daily/weekly telemetry analysis and trend detection
- **Notifications**: Alert processing for threshold violations and system events
- **Data Cleanup**: Automated cleanup of expired data and log rotation
- **Health Monitoring**: System health checks and performance metrics collection

**Caching Strategy:**
- **Redis Cache**: ETag values, session data, frequently accessed configurations
- **Application Cache**: In-memory caching for static data (sensor kinds, actuator types)
- **Query Cache**: Database query result caching for dashboard endpoints

### Redis Integration and Configuration

**Redis Deployment:**
```yaml
# docker-compose.yml
services:
  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes --maxmemory 512mb --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    ports:
      - "6379:6379"
    environment:
      - REDIS_PASSWORD=${REDIS_PASSWORD}
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 3
```

**Cache Configuration:**
```python
# app/core/cache.py
import redis
from app.core.config import settings

redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT, 
    password=settings.REDIS_PASSWORD,
    decode_responses=True,
    socket_connect_timeout=5,
    socket_timeout=5,
    retry_on_timeout=True,
    health_check_interval=30
)

# Cache patterns and TTLs
CACHE_PATTERNS = {
    "etag:{config_version}": 3600,       # 1 hour for config ETags
    "etag:{plan_version}": 1800,         # 30 min for plan ETags  
    "session:{session_id}": 86400,       # 24 hours for user sessions
    "greenhouse:{gh_id}:sensors": 300,   # 5 min for sensor lists
    "controller:{id}:status": 60,        # 1 min for controller status
    "user:{id}:permissions": 600,        # 10 min for user permissions
}

async def get_cached(key: str, default=None):
    """Get value from cache with automatic deserialization"""
    try:
        value = redis_client.get(key)
        return json.loads(value) if value else default
    except (redis.RedisError, json.JSONDecodeError):
        return default

async def set_cached(key: str, value, ttl: int = 300):
    """Set cache value with TTL"""
    try:
        redis_client.setex(key, ttl, json.dumps(value))
    except redis.RedisError:
        # Log error but don't fail the request
        logger.warning(f"Cache set failed for key: {key}")
```

**Celery + Redis Message Broker:**
```python
# app/core/celery_app.py (expanded from planning section)
celery_app.conf.update(
    # Redis broker settings
    broker_url=settings.REDIS_URL,
    result_backend=settings.REDIS_URL,
    broker_connection_retry_on_startup=True,
    broker_transport_options={
        'master_name': 'mymaster',  # For Redis Sentinel
        'visibility_timeout': 3600,
        'fanout_prefix': True,
        'fanout_patterns': True
    },
    
    # Task routing
    task_routes={
        'app.tasks.planner.*': {'queue': 'planning'},
        'app.tasks.analytics.*': {'queue': 'analytics'},
        'app.tasks.notifications.*': {'queue': 'notifications'},
        'app.tasks.telemetry.*': {'queue': 'telemetry'},
    },
    
    # Result backend settings
    result_backend_transport_options={
        'master_name': 'mymaster',
        'retry_policy': {
            'timeout': 5.0
        }
    },
    
    # Performance tuning
    worker_prefetch_multiplier=1,      # For long-running tasks
    task_acks_late=True,               # Acknowledge after completion
    worker_disable_rate_limits=True,
    task_compression='gzip',
    result_compression='gzip',
)

# Queue definitions with priorities
CELERY_TASK_QUEUES = [
    Queue('planning', routing_key='planning', priority=3),
    Queue('telemetry', routing_key='telemetry', priority=1), 
    Queue('analytics', routing_key='analytics', priority=2),
    Queue('notifications', routing_key='notifications', priority=4),
]
```

**Cache Usage Patterns:**

| **Use Case** | **Cache Key Pattern** | **TTL** | **Invalidation Strategy** |
|--------------|----------------------|---------|---------------------------|
| Config ETags | `etag:config:{version}` | 1 hour | On config publish |
| Plan ETags | `etag:plan:{version}` | 30 min | On plan generation |
| User Sessions | `session:{session_id}` | 24 hours | On logout/expiry |
| Sensor Lists | `greenhouse:{id}:sensors` | 5 min | On sensor CRUD |
| Controller Status | `controller:{id}:status` | 1 min | On telemetry update |
| User Permissions | `user:{id}:permissions` | 10 min | On role change |
| API Rate Limits | `rate_limit:{user_id}:{endpoint}` | 1 hour | Sliding window |

**Cache Monitoring and Metrics:**
```python
# app/api/routes/monitoring.py
@router.get("/admin/cache/stats")
async def get_cache_statistics():
    """Get Redis cache statistics for monitoring"""
    info = redis_client.info()
    
    return {
        "redis_version": info["redis_version"],
        "connected_clients": info["connected_clients"],
        "used_memory": info["used_memory"],
        "used_memory_human": info["used_memory_human"],
        "used_memory_peak": info["used_memory_peak"],
        "hit_rate": calculate_hit_rate(info),
        "keyspace": info.get("db0", {}),
        "commands_processed": info["total_commands_processed"],
        "instantaneous_ops_per_sec": info["instantaneous_ops_per_sec"],
    }

def calculate_hit_rate(info: dict) -> float:
    """Calculate cache hit rate percentage"""
    hits = info.get("keyspace_hits", 0)
    misses = info.get("keyspace_misses", 0)
    total = hits + misses
    return (hits / total * 100) if total > 0 else 0.0
```

### Control Model

- **Climate loop**: Greenhouse wide and runs on one designated "climate controller." Only temp/humidity sensors flagged include_in_climate_loop=true are averaged (interior). Exterior sensors (temp/humidity/pressure) are separate and never averaged with interior; both are used for enthalpy based dehumidification decisions.
- **Fan lead/lag via fan groups**: Controller rotates the "lead"; on_count per stage drives how many group members run.
- **Manual overrides**: Physical buttons can force cool / humid / heat stages with per button target stage and timeout.

### Irrigation & Locking

- **Per controller valve lockout**: Only one irrigation valve may be ON at a time; overlapping jobs are queued FIFO by the controller.

### Data Model Highlights

- **Zone ↔ Planting 1:1**: One active planting per zone.
- **Sensor ↔ Zone mapping**: A zone can map at most one sensor per kind ("temperature", "humidity", "soil_moisture"), but a sensor may be reused by multiple zones (e.g., shared probe).
- **Context fields**: `context_text` on greenhouse and zone capture operator narrative for the planner.

### Ingest Path

- **HTTP batch ingest**: To API for telemetry (sensors, actuator events, controller status, input events). MQTT/EMQX/Telegraf is out of scope for MVP and may be reconsidered later.

### Database Migration Posture

- **No Alembic migrations**: Required until the first controller is collecting real data; schemas are included and will be stabilized before enabling migrations.

## Deployment Architecture

### Docker Compose Configuration

The system deploys as a multi-container application using Docker Compose with the following services:

```yaml
# docker-compose.yml
version: '3.8'
services:
  # Database with TimescaleDB extension
  db:
    image: timescale/timescaledb:latest-pg15
    environment:
      POSTGRES_DB: verdify
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - db_data:/var/lib/postgresql/data
      - ./scripts/init-db.sql:/docker-entrypoint-initdb.d/init-db.sql
    ports:
      - "5432:5432"
    
  # Redis for Celery broker and caching
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
      
  # FastAPI backend
  backend:
    build: ./backend
    environment:
      DATABASE_URL: postgresql://postgres:${POSTGRES_PASSWORD}@db:5432/verdify
      REDIS_URL: redis://redis:6379/0
      SECRET_KEY: ${SECRET_KEY}
      FIRST_SUPERUSER: ${FIRST_SUPERUSER}
      FIRST_SUPERUSER_PASSWORD: ${FIRST_SUPERUSER_PASSWORD}
    depends_on:
      - db
      - redis
    labels:
      - traefik.enable=true
      - traefik.http.routers.backend.rule=Host(`api.verdify.local`) || PathPrefix(`/api`)
      - traefik.http.services.backend.loadbalancer.server.port=8000
      
  # Celery worker for background tasks
  celery-worker:
    build: ./backend
    command: celery -A app.core.celery_app worker --loglevel=info
    environment:
      DATABASE_URL: postgresql://postgres:${POSTGRES_PASSWORD}@db:5432/verdify
      REDIS_URL: redis://redis:6379/0
    depends_on:
      - db
      - redis
      
  # Next.js frontend
  frontend:
    build: ./frontend
    environment:
      NEXT_PUBLIC_API_URL: http://localhost/api
    labels:
      - traefik.enable=true
      - traefik.http.routers.frontend.rule=Host(`verdify.local`)
      - traefik.http.services.frontend.loadbalancer.server.port=3000
      
  # Traefik reverse proxy
  traefik:
    image: traefik:v3.0
    command:
      - --api.insecure=true
      - --providers.docker=true
      - --providers.docker.exposedbydefault=false
      - --entrypoints.web.address=:80
    ports:
      - "80:80"
      - "8080:8080"  # Traefik dashboard
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro

volumes:
  db_data:
  redis_data:
```

### Environment Configuration

**Development Environment (.env.dev):**
```bash
POSTGRES_PASSWORD=development_password
SECRET_KEY=development_secret_key_change_in_production
FIRST_SUPERUSER=admin@verdify.ai
FIRST_SUPERUSER_PASSWORD=admin_password
ENVIRONMENT=development
```

**Production Environment (.env.prod):**
```bash
POSTGRES_PASSWORD=${SECURE_POSTGRES_PASSWORD}
SECRET_KEY=${SECURE_SECRET_KEY}
FIRST_SUPERUSER=${ADMIN_EMAIL}
FIRST_SUPERUSER_PASSWORD=${SECURE_ADMIN_PASSWORD}
ENVIRONMENT=production
DATABASE_URL=postgresql://user:pass@prod-db:5432/verdify
REDIS_URL=redis://prod-redis:6379/0
DOMAIN=api.verdify.ai
```

### Deployment Commands

**Development:**
```bash
# Start all services
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# View logs
docker-compose logs -f backend

# Run database migrations
docker-compose exec backend alembic upgrade head

# Create initial superuser
docker-compose exec backend python -m app.initial_data
```

**Production:**
```bash
# Deploy with production overrides
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Health check
curl https://api.verdify.ai/health

# Monitor logs
docker-compose logs -f --tail=100
```

### Infrastructure Requirements

**Minimum Resources:**
- **CPU**: 2 cores (backend + celery worker)
- **Memory**: 4GB RAM (2GB backend, 1GB database, 1GB system)
- **Storage**: 50GB SSD (database growth depends on telemetry frequency)
- **Network**: 100Mbps (sufficient for typical IoT telemetry loads)

**Scaling Considerations:**
- **Horizontal**: Add Celery workers for background processing
- **Vertical**: Increase database resources for high-frequency telemetry
- **Storage**: Implement TimescaleDB compression and retention policies
- **Monitoring**: Add Prometheus/Grafana for observability

### Health Monitoring and System Diagnostics

**Health Check Endpoints:**

| **Endpoint** | **Purpose** | **Response Format** | **Critical Dependencies** |
|--------------|-------------|---------------------|---------------------------|
| `GET /health` | Basic liveness check | `{"status": "healthy", "timestamp": "2025-08-13T18:05:00Z"}` | None (always responds) |
| `GET /health/detailed` | Comprehensive system health | JSON with component status | Database, Redis, Celery |
| `GET /health/database` | Database connectivity and performance | Connection pool stats, query latency | PostgreSQL, TimescaleDB |
| `GET /health/cache` | Redis cache status | Cache hit rates, memory usage | Redis |
| `GET /health/workers` | Celery worker health | Active workers, queue lengths | Celery, Redis broker |
| `GET /health/controllers` | Controller connectivity status | Device online/offline, last seen | Database telemetry tables |

**Detailed Health Response Schema:**
```json
{
  "status": "healthy|degraded|critical",
  "timestamp": "2025-08-13T18:05:00Z",
  "version": "2.0.0",
  "uptime_seconds": 86400,
  "components": {
    "database": {
      "status": "healthy",
      "connection_pool": {
        "active": 5,
        "idle": 10,
        "max": 20
      },
      "query_latency_ms": 12.5,
      "last_migration": "2025_08_13_142000_add_device_token_expiry"
    },
    "cache": {
      "status": "healthy", 
      "redis_info": {
        "connected_clients": 3,
        "used_memory_mb": 45.2,
        "hit_rate_pct": 94.8
      },
      "etag_cache_size": 1247
    },
    "workers": {
      "status": "healthy",
      "celery": {
        "active_workers": 2,
        "pending_tasks": 0,
        "failed_tasks_24h": 1
      },
      "queues": {
        "default": 0,
        "planning": 0,
        "telemetry": 0
      }
    },
    "controllers": {
      "status": "degraded",
      "summary": {
        "total_controllers": 3,
        "online_controllers": 2,
        "offline_controllers": 1,
        "last_telemetry_within_5min": 2
      },
      "offline_devices": [
        {
          "device_name": "verdify-a1b2c3",
          "greenhouse_id": "123e4567-e89b-12d3-a456-426614174000",
          "last_seen": "2025-08-13T17:45:00Z",
          "minutes_offline": 20
        }
      ]
    },
    "storage": {
      "status": "healthy",
      "disk_usage": {
        "total_gb": 100,
        "used_gb": 23.5,
        "available_gb": 76.5,
        "usage_pct": 23.5
      },
      "telemetry_retention": {
        "raw_data_days": 90,
        "aggregated_data_days": 365,
        "oldest_record": "2025-05-15T10:00:00Z"
      }
    }
  },
  "alerts": [
    {
      "level": "warning",
      "component": "controllers",
      "message": "Device verdify-a1b2c3 offline for 20 minutes",
      "since": "2025-08-13T17:45:00Z"
    }
  ]
}
```

**Health Status Logic:**
- **Healthy**: All components operational, no alerts
- **Degraded**: Non-critical issues (controller offline, cache miss rate low, high queue depth)
- **Critical**: Core functionality impaired (database down, all workers offline, disk full)

**Monitoring Integration:**

```bash
# Prometheus metrics endpoint
GET /metrics

# Key metrics exposed:
# - verdify_api_requests_total{method, endpoint, status}
# - verdify_database_connections{state}
# - verdify_cache_operations_total{operation, result}
# - verdify_telemetry_ingestion_rate
# - verdify_controller_status{device_name, status}
# - verdify_celery_tasks_total{queue, status}
# - verdify_plan_generation_duration_seconds
```

**Alerting Rules:**

| **Alert** | **Condition** | **Severity** | **Action** |
|-----------|---------------|--------------|------------|
| Database Down | No DB connection for 30s | Critical | Page on-call engineer |
| High Request Latency | P95 > 2s for 5 minutes | Warning | Investigate performance |
| Controller Offline | No telemetry for 10 minutes | Warning | Check device connectivity |
| Disk Space Low | <10% disk space remaining | Warning | Plan capacity expansion |
| Celery Workers Down | No active workers for 2 minutes | Critical | Restart worker processes |
| Failed Task Rate High | >5% task failure rate | Warning | Review task logs |
| Cache Hit Rate Low | <80% hit rate for 30 minutes | Warning | Review cache configuration |

**Automated Health Actions:**
- **Log Rotation**: Automatic cleanup of logs older than 30 days
- **Database Maintenance**: Weekly VACUUM and daily statistics updates
- **Failed Task Retry**: Exponential backoff retry for failed Celery tasks
- **Connection Pool Reset**: Automatic connection recovery on database failover
- **Metric Collection**: 15-second interval metrics collection and aggregation

## Business Invariants and Validation Rules {#business-invariants}

The following validation rules are enforced across the entire system (API, database, controllers, and UI):

| **Category** | **Rule** | **Error Response** | **Enforcement Location** |
|--------------|----------|--------------------|--------------------------|
| **Identity & Formatting** | | | |
| Device Name Format | `device_name` MUST match `^verdify-[0-9a-f]{6}$` | `E400_BAD_REQUEST` | API boundary, controller validation |
| Entity IDs | All entity IDs MUST be valid UUIDv4 strings | `E400_BAD_REQUEST` | API boundary, database constraints |
| Timestamps | All timestamps MUST be UTC ISO-8601 with 'Z' suffix | `E400_BAD_REQUEST` | API boundary, telemetry validation |
| Units | All units MUST be metric; imperial units forbidden | `E400_BAD_REQUEST` | API boundary, controller validation |
| **Uniqueness & Cardinality** | | | |
| Zone Numbers | `(greenhouse_id, zone_number)` MUST be unique | `E409_CONFLICT` | Database constraint, API validation |
| Climate Controller | Exactly one `is_climate_controller=true` per greenhouse | `E409_CONFLICT` | Database constraint, API validation |
| Active Plantings | Exactly one active planting per zone maximum | `E409_CONFLICT` | Database constraint, API validation |
| Sensor-Zone Mapping | `(sensor_id, zone_id, kind)` MUST be unique | `E409_CONFLICT` | Database constraint, API validation |
| Zone Sensor Kinds | One sensor per kind per zone maximum (temp, humidity, soil) | `E409_CONFLICT` | Database constraint, API validation |
| **State Machine Coverage** | | | |
| Grid Completeness | Exactly 49 rows covering all `(temp_stage, humi_stage)` in `[-3..+3] × [-3..+3]` | `E409_CONFLICT` | Configuration validation, publish workflow |
| Fallback Required | Exactly one fallback row with `is_fallback=true` | `E409_CONFLICT` | Configuration validation, publish workflow |
| Actuator References | All state machine actuator IDs MUST exist for the greenhouse | `E422_UNPROCESSABLE_ENTITY` | Configuration validation |
| **Climate & Safety** | | | |
| Guard Rails | Plan setpoints MUST be within greenhouse min/max bounds | Server-side clamping | Planning engine, database functions |
| Climate Loop Sensors | Only temp/humidity sensors may have `include_in_climate_loop=true` | `E422_UNPROCESSABLE_ENTITY` | API validation |
| Zone Scope Mapping | Only `scope='zone'` sensors may have zone mappings | `E422_UNPROCESSABLE_ENTITY` | Database trigger, API validation |
| **Irrigation & Scheduling** | | | |
| Valve Lockout | Only one irrigation valve per controller may be ON concurrently | FIFO queuing | Controller firmware enforcement |
| Schedule Conflicts | Overlapping irrigation jobs accepted but queued sequentially | Warning logged | Controller scheduling, plan validation |
| **Authentication** | | | |
| Token Separation | Device tokens cannot access user endpoints; JWTs cannot access device endpoints | `E401_UNAUTHORIZED` | API middleware |
| **ETags & Caching** | | | |
| Config ETag Format | Configuration ETags MUST follow `config:v<version>:<sha8>` pattern | Strong ETag validation | Configuration pipeline |
| Plan ETag Format | Plan ETags MUST follow `plan:v<version>:<sha8>` pattern | Strong ETag validation | Planning pipeline |

### Cross-References

- **Database Implementation**: See [DATABASE.md - Validation Functions & Triggers](./DATABASE.md#validation-functions-triggers)
- **API Enforcement**: See [API.md - Validation Rules](./API.md#validation-rules)
- **Controller Validation**: See [CONTROLLER.md - Validation & Acceptance](./CONTROLLER.md#validation-acceptance)
- **Configuration Validation**: See [CONFIGURATION.md - Validation Rules](./CONFIGURATION.md#validation-rules)

## Assumptions

- **Single owner per greenhouse**: For MVP (no roles/permissions beyond basic user auth).
- **One climate controller per greenhouse**: Other controllers may host additional sensors/actuators (e.g., irrigation, pumps, lights).
- **Plan expiry handling**: Controllers must continue executing the last valid plan; if no applicable plan segment exists, fallback to greenhouse failsafe values (from initial config).
- **Device token lifecycle**: Token remains valid until the controller is deleted/removed in the API.
- **LLM influence**: Planner may shift stage thresholds (deltas/offsets/hysteresis) but firmware clamps to greenhouse guard rails.
- **External sensing**: At least one exterior temp/humidity/pressure sensor is available to the climate controller for enthalpy comparison.

## Key Risks & Mitigations

### Misconfiguration of State Machine or Mappings
**Mitigation**: Strict API validation (unique zone × kind mapping; on/off conflict checks; on_count ≤ group size; only temp/humidity in climate loop).

### Plan Unavailability/Expiry
**Mitigation**: Controller caches last plan; if a time slot is unspecified, use failsafe rails and baseline config thresholds.

### Multi-Controller Coordination
**Mitigation**: Climate actuators must live on the climate controller; irrigation lockout enforced per controller; schedules are partitioned by actuator/controller in the plan.

### Sensor Quality/Time Sync
**Mitigation**: Controller publishes loop timings and status; enforce UTC; reject ingest with excessive clock skew; allow per sensor calibration (scale/offset).

### Enthalpy Decisions Without Pressure
**Mitigation**: Require pressure inputs for exterior and compute with defaults only if explicitly allowed (flag).

## Standards & Conventions

### Identifiers

- **device_name**: `verdify-aabbcc` (last 3 MAC bytes, lowercase hex, no separators) for claiming and display.
- **All persistent entities**: UUIDv4 (e.g., controller_uuid, greenhouse_id, sensor_id, actuator_id).

### Naming

- **snake_case**: For all JSON fields, DB columns, and API paths.
- **Units**: Metric units throughout (Celsius, kPa, meters, liters).
- **Timestamps**: ISO 8601 UTC (YYYY-MM-DDTHH:MM:SSZ).

### Telemetry

- **Batching**: Preferred for network efficiency.
- **Frequency**: Configurable per sensor/actuator type.
- **Retention**: Long-term storage in TimescaleDB for analytics.

## Business Rules & Validation Constraints

This section consolidates all validation rules and business constraints from across the system components to ensure consistency and provide a single source of truth for implementation.

### Core Business Rules

| Rule Name | Description | Components | Error Code | Implementation |
|-----------|-------------|------------|------------|----------------|
| **Climate Controller Singleton** | Exactly one controller per greenhouse can have `is_climate_controller=true` | API, Database | `E409_CONFLICT` | API validation on PATCH, DB unique constraint trigger |
| **Zone-Sensor Kind Uniqueness** | Each zone can have at most one sensor of each kind | API, Database | `E422_UNPROCESSABLE_ENTITY` | Unique index on `(zone_id, kind)` in sensor_zone_map |
| **Active Planting Singleton** | Each zone can have at most one active planting at any time | API, Database | `E409_CONFLICT` | DB trigger on overlapping date ranges |
| **State Grid Coverage** | Must define exactly 49 state rules (7×7 temp/humi grid) plus 1 fallback | API, Configuration | `E422_UNPROCESSABLE_ENTITY` | API validation, view `vw_missing_state_rows` |
| **Guard Rail Compliance** | All setpoints must be within greenhouse min/max bounds | API, Planner, Database | `E422_UNPROCESSABLE_ENTITY` | Validation functions and triggers |
| **Device Name Format** | Device names must match `^verdify-[0-9a-f]{6}$` pattern | API, Controller | `E422_UNPROCESSABLE_ENTITY` | Regex validation in schemas |
| **Claim Code Format** | Claim codes must be exactly 6 numeric digits | API, Controller | `E422_UNPROCESSABLE_ENTITY` | Regex validation `^\d{6}$` |
| **Metric Units Only** | All sensor values and API payloads use metric units | API, Controller, Database | `E422_UNPROCESSABLE_ENTITY` | Schema validation and conversion |
| **UTC Timestamps** | All timestamps must be UTC ISO-8601 with Z suffix | API, Controller, Database | `E422_UNPROCESSABLE_ENTITY` | Format validation and timezone enforcement |
| **ETag Format** | ETags must follow `{type}:v{version}:{sha8}` pattern | API, Controller | `E400_BAD_REQUEST` | String format validation |
| **Sensor Scope Validation** | Zone-scoped sensors must have zone_id; others must not | API, Database | `E422_UNPROCESSABLE_ENTITY` | Check constraint and trigger validation |
| **Actuator Channel Uniqueness** | Each controller's relay channels must be unique per actuator | API, Database | `E409_CONFLICT` | Unique constraint on `(controller_id, relay_channel)` |
| **Plan Version Monotonic** | Plan versions must increase monotonically per greenhouse | API, Planner | `E409_CONFLICT` | Database check constraint |
| **Fan Group Membership** | Actuators can belong to at most one fan group | API, Configuration | `E422_UNPROCESSABLE_ENTITY` | Validation in config build process |
| **Irrigation Lockout Window** | Irrigation events must respect lockout periods between runs | Controller | N/A (Controller logic) | ESPHome timer validation |

### Data Integrity Constraints

| Constraint Name | Description | Table(s) | Implementation |
|-----------------|-------------|----------|----------------|
| **Greenhouse Bounds** | `min_temp_c < max_temp_c` and `min_vpd_kpa < max_vpd_kpa` | `greenhouse` | Check constraints |
| **Positive Intervals** | All time intervals (poll_interval_s, etc.) must be > 0 | Multiple | Check constraints with `> 0` |
| **Valid Pressure Range** | Atmospheric pressure between 500-1200 hPa | `greenhouse`, `controller_status` | Check constraints |
| **VPD Range** | VPD values between 0-10 kPa (physical limits) | Multiple | Check constraints |
| **Temperature Range** | Temperature values between -50°C and +100°C | Multiple | Check constraints |
| **Percentage Bounds** | Humidity percentages between 0-100% | Multiple | Check constraints |
| **Stage Range** | temp_stage and humi_stage between -3 and +3 | `state_rule`, `plan_setpoint` | Check constraints |
| **Version Positivity** | All version numbers must be positive integers | Multiple | Check constraints `>= 1` |

### API Rate Limiting

| Endpoint Category | Rate Limit | Window | Error Code | Notes |
|------------------|------------|---------|------------|-------|
| **Authentication** | 10 requests | 1 minute | `E429_TOO_MANY_REQUESTS` | Per IP address |
| **Device Onboarding** | 30 requests | 1 minute | `E429_TOO_MANY_REQUESTS` | Per device_name |
| **Telemetry Ingest** | 1000 requests | 1 minute | `E429_TOO_MANY_REQUESTS` | Per controller |
| **Configuration Updates** | 10 requests | 1 minute | `E429_TOO_MANY_REQUESTS` | Per user |
| **General API** | 100 requests | 1 minute | `E429_TOO_MANY_REQUESTS` | Per authenticated user |

### Error Response Standards

All validation failures return consistent error responses following the FastAPI HTTPException format:

```json
{
  "error_code": "E422_UNPROCESSABLE_ENTITY",
  "message": "Validation failed for greenhouse configuration", 
  "details": {
    "field": "min_temp_c",
    "constraint": "must be less than max_temp_c",
    "provided_value": 25.0,
    "max_allowed": 20.0
  }
}
```

## Related Documentation

For detailed implementation specifications, see:

- **[API.md](./API.md)** - Complete REST API specification
- **[CONFIGURATION.md](./CONFIGURATION.md)** - Configuration management and publishing
- **[CONTROLLER.md](./CONTROLLER.md)** - ESPHome firmware specification
- **[PLANNER.md](./PLANNER.md)** - AI planning engine algorithms
- **[DATABASE.md](./DATABASE.md)** - Database schema and migrations
- **[AUTHENTICATION.md](./AUTHENTICATION.md)** - Security and auth flows
- **[GAPS.md](./GAPS.md)** - Known limitations and future work
