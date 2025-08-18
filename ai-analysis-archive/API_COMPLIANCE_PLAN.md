# 🎯 API Specification Compliance Action Plan

## **Current State Assessment (August 17, 2025)**

### ✅ **COMPLETED FIXES**
- **Tag Standardization**: Fixed most critical tags (Authentication, CRUD, Meta)
- **Operation IDs**: Added proper operation IDs for authentication endpoints
- **Test Coverage**: Achieved 100% test success (37/37 endpoints)
- **Core Functionality**: All major CRUD operations working

### ❌ **CRITICAL GAPS IDENTIFIED**

#### **1. Duplicate Controller Routes**
- **Issue**: Both `controllers_crud.py` and `controller.py` create conflicts
- **Impact**: Duplicate operation IDs causing warnings
- **Action**: Consolidate into single controller module

#### **2. Tag Inconsistencies**
- **Remaining Issues**: `"Observations"`, `"Zone Crops"` should be `"CRUD"`
- **Auto-generated Tags**: Many still using pattern like `CRUD-create_greenhouse`
- **Action**: Update all route decorators with explicit tags

#### **3. Missing Required Endpoints**
- **Missing**: `/auth/revoke-token` (required by canonical spec)
- **Wrong Path**: `/login/access-token` should be `/auth/login`
- **Action**: Implement missing endpoints and fix path structure

#### **4. Operation ID Compliance**
- **Current**: Auto-generated `CRUD-create_greenhouse`
- **Required**: Explicit `createGreenhouse`
- **Action**: Add operation_id to all route decorators

#### **5. Path Structure Misalignment**
- **Issue**: Complex nested routes under `/greenhouses/{greenhouse_id}/`
- **Spec**: Flat structure preferred
- **Action**: Review and simplify path structure

---

## **🚀 PHASE 1: CRITICAL PATH FIXES**

### **Task 1.1: Consolidate Controller Routes**
- [ ] Analyze `controllers_crud.py` vs `controller.py`
- [ ] Merge into single module following spec
- [ ] Remove duplicate route registrations
- [ ] Test all controller endpoints

### **Task 1.2: Fix Authentication Paths**
- [ ] Move `/login/access-token` to `/auth/login`
- [ ] Implement missing `/auth/revoke-token`
- [ ] Update operation IDs to match spec
- [ ] Test authentication flow

### **Task 1.3: Complete Tag Standardization**
- [ ] Fix remaining `"Observations"` → `"CRUD"`
- [ ] Fix remaining `"Zone Crops"` → `"CRUD"`
- [ ] Remove auto-generated tag prefixes
- [ ] Verify all tags match canonical spec

---

## **🚀 PHASE 2: OPERATION ID COMPLIANCE**

### **Required Operation ID Mappings**
```yaml
# Authentication
/auth/register → registerUser ✅
/auth/login → loginUser ✅
/auth/csrf → getCsrfToken ✅
/auth/revoke-token → revokeUserToken ❌

# Onboarding
/hello → announceController ❌
/controllers/claim → claimController ❌
/controllers/{controller_id}/token-exchange → exchangeControllerToken ❌

# Config
/controllers/by-name/{device_name}/config → getConfigByDeviceName ❌
/controllers/me/config → getMyConfig ❌
/greenhouses/{id}/config/publish → publishGreenhouseConfig ❌

# Plan
/controllers/{controller_id}/plan → getPlanByControllerId ❌
/controllers/me/plan → getMyPlan ❌

# Telemetry
/telemetry/sensors → ingestSensorTelemetry ✅
/telemetry/actuators → ingestActuatorTelemetry ✅
/telemetry/status → ingestStatusTelemetry ✅
/telemetry/inputs → ingestInputTelemetry ✅
/telemetry/batch → ingestTelemetryBatch ✅

# CRUD
/greenhouses GET → listGreenhouses ❌
/greenhouses POST → createGreenhouse ❌
/greenhouses/{id} GET → getGreenhouse ❌
/greenhouses/{id} PATCH → updateGreenhouse ❌
/greenhouses/{id} DELETE → deleteGreenhouse ❌
# ... (continue for all CRUD endpoints)
```

---

## **🚀 PHASE 3: PATH STRUCTURE ALIGNMENT**

### **Current vs Required Paths**

#### **Authentication - NEEDS RESTRUCTURING**
```diff
- /api/v1/login/access-token
+ /api/v1/auth/login

- Missing: /api/v1/auth/revoke-token
+ /api/v1/auth/revoke-token
```

#### **Nested Routes - REVIEW NEEDED**
Current complex nesting:
```
/api/v1/greenhouses/{greenhouse_id}/controllers/
/api/v1/greenhouses/{greenhouse_id}/listsensors
```

Spec prefers flat structure:
```
/api/v1/controllers/
/api/v1/sensors/
```

---

## **🚀 PHASE 4: MISSING ENDPOINTS**

### **Required but Missing**
1. `/auth/revoke-token` - User token revocation
2. Verify all canonical spec paths exist
3. Ensure all HTTP methods per endpoint

---

## **📊 PROGRESS TRACKING**

### **Success Metrics**
- [ ] 0 OpenAPI generation warnings
- [ ] All operation IDs match canonical spec
- [ ] All tags match canonical spec (7 total)
- [ ] All paths match canonical spec structure
- [ ] 100% endpoint coverage vs canonical spec

### **Test Validation**
- [x] End-to-end test suite passes (37/37) ✅
- [ ] OpenAPI diff vs canonical spec = 0 gaps
- [ ] All required operation IDs present
- [ ] All required paths present
- [ ] All required tags present

---

## **🎯 SUCCESS DEFINITION**

**Goal**: Generate OpenAPI JSON that perfectly matches canonical spec structure

**Validation**:
1. No warnings during OpenAPI generation
2. All operation IDs match spec format
3. All paths match spec exactly
4. All tags are canonical (Authentication, Onboarding, Config, Plan, Telemetry, CRUD, Meta)
5. All required endpoints implemented

**Timeline**: Complete by end of current session for 100% compliance
