---
name: api-review-checklist
description: Use this skill whenever writing, reviewing, or modifying a REST controller or its ServiceImpl in the unisage-backend Spring Boot project (backend-java) — triggers on "review API này", "check lại controller", "viết endpoint mới", "review code trước khi merge", or any diff touching a `controller/*Controller.java` or `service/**/*ServiceImpl.java` file. This is a fast, mechanical checklist (return-type shape + exception-throwing discipline) meant to run on every single endpoint, not just new ones — apply it even to a one-line change to an existing controller method, since the two rules here are exactly the kind of thing that's easy to miss in a small diff.
---

# API review checklist — unisage-backend

Two rules, both non-negotiable because the rest of the codebase (the global exception handler, the frontend's response parsing, pagination UI) is written assuming every endpoint follows them without exception.

## 1. Controller return type shape

Every controller method returns `ResponseEntity<ApiResponse<T>>`, where `T` is:

- A single resource: `ResponseEntity<ApiResponse<XxxxResponse>>`
- A non-paginated list (small, fixed-size collections like `getAllAccessLevels`): `ResponseEntity<ApiResponse<List<XxxxResponse>>>`
- **Any `getAll`/list endpoint that takes a `Pageable`** — which should be essentially every list endpoint over a table that can grow: `ResponseEntity<ApiResponse<PageResponse<List<XxxxResponse>>>>`, built via `ApiResponse.success(service.getAll(pageable))` where the service returns `PageResponse.fromPage(page, this::mapToResponse)`.

Why this matters beyond consistency: `ApiResponse` is what `GlobalExceptionHandler` also wraps every error in, and the frontend unwraps `{code, message, data, errors}` uniformly — a controller that returns a bare `List<XxxxResponse>` or a raw entity breaks that contract silently (it'll still return 200, but the frontend's generic response handler won't find `.data`).

When reviewing, check specifically:

- Is this a `getAll` that will realistically return more than a page worth of rows? If yes and it's returning bare `List<...>` instead of `PageResponse<List<...>>`, flag it — `AccessLevelController.getAllAccessLevels()` is the one accepted exception because it's a small fixed lookup table, not a precedent to copy for anything else.
- Does the method accept `Pageable pageable` as a parameter when it should? (See `DocumentController.getAllDocuments` / `UserController.getAll` for the reference shape.)
- Create returns `HttpStatus.CREATED` (`ResponseEntity.status(HttpStatus.CREATED)...`), not the default 200.
- Delete returns `ResponseEntity<ApiResponse<Void>>` with `ApiResponse.success(null)` after the service call, matching the soft-delete convention.

## 2. ServiceImpl never throws with a raw message

Grep for this while reviewing: `throw new` inside any `*ServiceImpl.java`. The **only** acceptable form is

```java
.orElseThrow(() -> new AppException(ErrorCode.XXX_NOT_FOUND))
```

or, for a business-rule rejection that isn't an `orElseThrow`:

```java
if (someInvalidCondition) {
    throw new AppException(ErrorCode.XXX_...);
}
```

Reject in review:

- `throw new RuntimeException("some message")`, `throw new IllegalArgumentException(...)`, or any exception built from a string literal — these bypass `ErrorCode`'s HTTP status mapping and localized message, so they fall through to `GlobalExceptionHandler`'s generic `SYS_UNCATEGORIZED` handler (500, with a stack trace printed to stdout) instead of the correct 4xx with a proper Vietnamese message.
- `new AppException(ErrorCode.XXX)` constructed eagerly _before_ the `orElseThrow` lambda (e.g. `Xxx x = repo.findById(id).orElseThrow(new AppException(...))` — note: missing `()->`). This still compiles as long as `AppException` matches the functional interface incorrectly, but the more common real mistake is constructing the exception outside the supplier so it evaluates (and potentially fails oddly) even on the found path — always use the `() -> new AppException(...)` lambda form.
- A new failure mode with no matching `ErrorCode` at all — that's a signal the PR is missing the `ErrorCode` addition described in `new-feature-spring-boot` step 7, not a reason to fall back to a raw exception.

Why this is checked separately from "does it compile": raw exceptions are the single most common thing that slips through in a rushed diff, because the code _works_ in the happy path and the failure only surfaces as a wrong status code / wrong message under a condition the reviewer may not manually trigger. Grepping for `throw new` that isn't `AppException` catches it in seconds without needing to exercise the failure path.

## Fast review procedure

1. `grep -n "ResponseEntity<" controller/TouchedController.java` — eyeball every method's generic signature against the shapes above.
2. `grep -n "throw new" service/**/TouchedServiceImpl.java` — every hit should read `new AppException(ErrorCode....)`.
3. If either check fails, point to the exact line and the exact fix — don't just say "follow convention," since the fix is mechanical and cheap once named.
