# Implementation Plan: Catalog & Product

Ý định đã chốt: `docs/intent/catalog.md`. Task chi tiết (tiêu chí nghiệm thu, verify,
file dự kiến): `todo.md` cùng thư mục.

## Overview

Thêm module **catalog** vào `ecom-be`: admin cấu hình category → attribute → option →
brand bằng API; seller (thành viên shop) đăng product có attribute động, variant/SKU,
tồn kho đơn giản và ảnh. Toàn bộ theo layered architecture của `AGENTS.md`
(`identity` là mẫu tham chiếu), mỗi thay đổi schema đi qua Alembic. Hai task cuối là tài
liệu: `PRODUCT.md`, `DECISIONS.md`, và API contract.

## Phát hiện từ codebase (ảnh hưởng thiết kế)

- **Chưa có khái niệm platform admin.** Mọi quyền hiện nay là quyền trong một shop:
  `get_current_principal` yêu cầu token có `sid` và nạp permission của role trong shop
  đó; role `owner/manager/viewer` là system role. Catalog là dữ liệu dùng chung toàn sàn
  nhưng chưa có ai "sở hữu" nó. **Đã chốt:** phase này tạm dùng permission
  `catalog:manage` (quyền trong shop), chuyển sang platform admin ở phase sau (xem
  *Next phase*). → Task 1.
- **Permission `products:read` / `products:write` đã được seed** (owner, manager có
  write; viewer chỉ read). Seller-side tái dùng, không thêm permission mới.
- Mô hình Shop/Membership/Role đã thay thế `shop_members.role` trong tài liệu gốc; giữ
  nguyên, không tạo bảng `shop_members`.
- Pattern cần bám: `UUIDPrimaryKeyMixin` + `TimestampMixin` (+ `SoftDeleteMixin`), CHECK
  constraint viết tay, partial unique index cho bản ghi live, lỗi domain là class có
  `code`/`status_code` trong `errors/`, response `BaseResponse[T]`, route không chạm
  persistence, service commit một lần mỗi use case, test `db` chạy riêng với
  `-m db`.
- Lệnh type-check đang lệch giữa các nơi: CI chạy `mypy app`, `pyproject.toml` khai
  `files = ["app", "alembic"]`, còn `AGENTS.md` ghi `mypy src` và `README.md` ghi
  `mypy src alembic` (`src/` đã bị bỏ). Plan dùng `uv run mypy app` (khớp CI) và Task 1
  đồng bộ lại hai file tài liệu.
- Test seed hiện có (`tests/integration/test_identity_seed_db.py`) khẳng định **đúng tập
  permission** và "owner giữ mọi permission" → thêm `catalog:manage` sẽ làm test đỏ nếu
  không cập nhật trong cùng Task 1.
- `StorageBackend` đã có `delete(key)`; `Settings.max_upload_bytes` và
  `app/utils/media.py` (`ACCEPTED_FORMATS`, `MIN_SIDE`, `MAX_SIDE`, WEBP re-encode) đã có,
  dùng lại cho ảnh product.

## Implementation notes (đã triển khai 20-09-2026)

Trạng thái: **Task 1–15 đã làm xong**; gate (`ruff`, `mypy app`, `pytest`, `pytest -m db`, `uv lock
--check`) xanh ở máy local. Còn lại cho người: review, và chạy CI `readiness`. Các điểm lệch so với kế
hoạch, để người đọc sau không tìm chỗ khác:

- **Migration gộp theo nhóm bảng, không theo từng task:** `598dee5535e8_catalog_taxonomy` (Task 2–5),
  `b8a284382dfb_product_schema` (Task 7–11), `0d597eefb17b_catalog_manage_permission` (Task 1),
  `3c1f9a7d2b40_catalog_seed` (Task 6). Lý do: mô hình catalog và product được viết cùng lúc, và các kiểm tra
  "đang dùng" của catalog cần bảng product ngay từ đầu. `downgrade base` rồi `upgrade head` đã chạy sạch.
- **Hai file service ngoài danh sách dự kiến:** `services/product_view.py` (dựng chi tiết sản phẩm) và
  `services/product_rules.py` (một hàm duy nhất quyết "sản phẩm có được bán không").
- **`core/errors.py` được mở rộng** thêm trường `details` tuỳ chọn cho `AppError`, chỉ để lỗi
  `product_invariant_violated` trả danh sách thuộc tính còn thiếu. Các lỗi khác giữ đúng `{error, message}`.
- **Sửa một lỗi có sẵn ngoài phạm vi:** token Bearer sai định dạng (`Bearer nope`) từng trả **500** ở mọi route có
  xác thực vì `InvalidAccessToken` không được chuyển thành `401`. Sửa ở `api/deps.py` (3 dòng) kèm
  `tests/unit/test_bad_bearer_token.py`, vì contract API ghi `401 invalid_token`.
- **Cổng Postgres/Redis local:** compose mặc định đã là `55432`/`56379` (không đụng `5432`/`5433`/`6379` đang bị
  chiếm); `compose.env` được tạo từ mẫu và `.env` trỏ vào đó. Không sửa `compose.yaml`.
- **Hai test có sẵn lỗi trên Windows** (`tests/unit/test_alembic_url_escaping.py`, `WinError 10106` khi chạy
  subprocess), không liên quan thay đổi này; chúng lỗi cả trước khi bắt đầu.
- **Giới hạn phụ thêm:** mỗi biến thể tối đa 5 tuỳ chọn, để `option_key` nằm gọn trong cột.

## Architecture Decisions

Các điểm lệch/bổ sung so với tài liệu gốc đều có lý do. Các mục 1, 2, 3, 4 đã được người dùng chốt (mục 1 là giải pháp tạm, xem *Next phase*).

1. **Quyền ghi catalog (tạm thời) = permission `catalog:manage`**, seed bằng migration và
   chỉ gán cho system role `owner` (không gán `manager`, `viewer`). Route
   `/api/v1/admin/catalog/*` dùng `require_permissions("catalog:manage")` có sẵn, nên
   không cần đổi `api/deps.py`. **Hệ quả đã được chấp nhận:** đây là quyền *trong shop*,
   nên mọi owner của bất kỳ shop nào đều sửa được catalog toàn sàn. Chấp nhận ở phase
   này vì hệ thống chưa có nhu cầu tách admin sàn. *Phương án để phase sau:* cột
   `users.is_platform_admin` + dependency `require_platform_admin` đọc cờ từ DB mỗi
   request, cấp quyền bằng script vận hành, không qua API công khai. Chi tiết ở mục
   *Next phase*.
2. **`category_attributes` có thêm cột `is_variation`** (không có trong tài liệu gốc).
   Nếu thiếu, Color/Size chỉ là attribute của product mà hệ thống không biết attribute
   nào được dùng để tạo variant. Cột này là thứ cho phép validate `product_variant_options`.
3. **Attribute không kế thừa qua cây category.** `GET /categories/{id}/attributes` trả
   đúng attribute cấu hình trên category đó; product chỉ được gán vào **category lá**.
   Đơn giản, dễ đoán, khớp cách Shopee gắn attribute theo category lá.
4. **Trạng thái product `draft | active | inactive`, đổi trạng thái chỉ qua endpoint riêng**
   (`POST .../publish`, `POST .../unpublish`); `PATCH` không nhận `status`. Product luôn
   được tạo là `draft`. Toàn bộ luật ở mục *Product lifecycle & required rules*. *Phương
   án đã cân:* cho `PATCH` đổi status rồi validate trong service — bị loại vì hai đường
   đi tới cùng một chuyển trạng thái là chỗ dễ để một đường lọt luật.
5. **`product_attribute_values`:** một dòng = một (product, attribute); ba cột giá trị
   `option_id` / `value_text` / `value_number`, `CHECK` đúng một cột khác NULL và khớp
   `attributes.data_type`. Attribute `SELECT` bắt buộc option thuộc đúng attribute.
   `data_type` gồm `TEXT | NUMBER | SELECT` và **bất biến** sau khi tạo. **Attribute
   `is_variation=true` không được có dòng ở bảng này** (nó sống ở `product_variant_options`),
   để mỗi sự thật chỉ có một nguồn; và chỉ attribute `SELECT` mới được đặt `is_variation`.
6. **Variant:** `price` là `BIGINT` ≥ 0 theo đơn vị nhỏ nhất của VND (không dùng float,
   không có cột currency ở phase này); `stock` là `INTEGER` ≥ 0 trên `product_variants`;
   `status` là enum `active | inactive`, mặc định `active`. `sku_code` unique **trong
   shop** (partial unique trên bản ghi live, kèm `shop_id` denormalize từ product để
   index được). Mỗi variant có tối đa một option cho mỗi attribute
   (`UNIQUE(variant_id, attribute_id)`). **Chống trùng tổ hợp bằng khóa chuẩn tắc, không
   chỉ bằng service:** cột `option_key` (chuỗi các cặp `attribute_id:option_id` sắp theo
   `attribute_id`, nối bằng `|`; rỗng cho variant không có option) do `utils/catalog.py`
   tính, với partial unique index `(product_id, option_key) WHERE deleted_at IS NULL`.
   Option của variant bất biến nên khóa không bao giờ lỗi thời. Mọi thao tác ghi variant
   khóa hàng product `SELECT … FOR UPDATE` đầu transaction để các kiểm tra "nhất quán tập
   attribute" và "variant active cuối cùng" không bị race; `IntegrityError` từ unique
   index được ánh xạ thành `409`.
7. **Xóa:** product/variant dùng soft delete (`SoftDeleteMixin`) vì sau này order sẽ tham
   chiếu; category/brand/attribute/option xóa cứng khi không còn được tham chiếu. Số phận
   dòng con, định nghĩa "đang dùng" và mã `409` ở mục *Catalog invariants* và
   *Delete semantics*.
8. **Cách ly tenancy:** mọi route product lấy `shop_id` từ `principal.active_shop_id`,
   không nhận `shop_id` từ client; product của shop khác trả `404` (không lộ sự tồn tại).
9. **Ảnh:** file qua `StorageBackend` sẵn có (mở rộng `MediaService` giống
   `store_background`), DB chỉ lưu key; `product_images.variant_id` nullable, một variant
   có N ảnh. URL dựng qua `api/media_urls.py`. Chính sách (số lượng là **đề xuất**, đặt
   thành hằng số trong `constants/` để đổi dễ):
   - định dạng nhận `JPEG | PNG | WEBP` (`ACCEPTED_FORMATS`), dung lượng tối đa
     `Settings.max_upload_bytes`, cạnh dài ≤ `MAX_SIDE` và ≥ `MIN_SIDE` như ảnh hiện có;
   - lưu **luôn ở WEBP** (cùng `WEBP_QUALITY`/`WEBP_METHOD`, nên bỏ EXIF), **không crop**
     (khác avatar/background vì ảnh sản phẩm có tỉ lệ tùy ý), thu nhỏ vừa khung
     **1600 × 1600 giữ tỉ lệ, không phóng to**; hàm mới `normalize_product_image` trong
     `utils/media.py`;
   - tối đa **9 ảnh chung** (`variant_id` NULL) cho mỗi product và **5 ảnh cho mỗi variant**;
     vượt → `409 image_limit_reached`;
   - `position` do server cấp (thêm vào cuối), `PATCH` để di chuyển; luôn liên tục
     `0..n-1` trong từng phạm vi (ảnh chung của product / ảnh của từng variant).
10. **Đọc catalog** (`GET /api/v1/catalog/...`) cho mọi user đã đăng nhập vì seller cần
    metadata dựng form. Không có route public/buyer ở phase này.
11. **Hai router tách hẳn** theo actor: `/api/v1/admin/catalog/*` (ghi, cần `catalog:manage`) và
    `/api/v1/catalog/*` (đọc), `/api/v1/products/*` (seller). Layout file: `models/catalog.py`,
    `models/product.py`, `repositories/<model>_repository.py`, `services/{catalog,product}_service.py`,
    `errors/catalog.py`, `constants/catalog/*`, `schemas/catalog/*`, `api/v1/catalog/*`.

## Cross-row integrity (chốt chặn ở DB, không chỉ ở service)

Các cột denormalize và quan hệ chéo phải được **DB** bảo đảm bằng composite FK; service
validate chỉ để trả lỗi đẹp, không phải chốt chặn cuối.

| Ràng buộc | Cách thực hiện |
| --------- | -------------- |
| `product_variants.shop_id` luôn bằng `products.shop_id` của product cha | `products` có `UNIQUE (id, shop_id)`; `product_variants` có FK `(product_id, shop_id) → products (id, shop_id)` |
| `product_images.variant_id` thuộc đúng `product_images.product_id` | `product_variants` có `UNIQUE (id, product_id)`; `product_images` có FK `(variant_id, product_id) → product_variants (id, product_id)`. Khi `variant_id` là NULL, FK kiểu `MATCH SIMPLE` không kích hoạt, ảnh chung của product vẫn hợp lệ (FK `product_id → products` riêng vẫn áp dụng) |
| `option_id` thuộc đúng `attribute_id` (ở `product_variant_options` và `product_attribute_values`) | `attribute_options` có `UNIQUE (id, attribute_id)`; hai bảng kia có FK `(option_id, attribute_id) → attribute_options (id, attribute_id)` (NULL `option_id` ở `product_attribute_values` không kích hoạt FK) |
| `product_variant_options` chỉ chứa attribute/option hợp lệ với category của product; attribute là variation; attribute value thuộc category | Không diễn đạt được bằng FK đơn giản → validate ở service **và** có test DB riêng chứng minh phần composite FK ở trên chặn được insert sai khi đi vòng service |

Mỗi ràng buộc trên có một test `-m db` chèn dòng sai bằng SQL/repository trực tiếp (bỏ qua
service) và khẳng định `IntegrityError`.

## Route map

Nguồn sự thật cho OpenAPI và `API_CONTRACT_CATALOG.md` (Task 15 đối chiếu bảng này với
`/api/v1/openapi.json`). Mọi đường dẫn nằm dưới `/api/v1`. "Đăng nhập" = bất kỳ principal hợp lệ.

| Method | Path | Quyền | Task |
| ------ | ---- | ----- | ---- |
| GET | `/catalog/brands` | đăng nhập | 2 |
| POST | `/admin/catalog/brands` | `catalog:manage` | 2 |
| PATCH, DELETE | `/admin/catalog/brands/{brand_id}` | `catalog:manage` | 2 |
| GET | `/catalog/categories` (cây) | đăng nhập | 3 |
| GET | `/catalog/categories/{category_id}` | đăng nhập | 3 |
| POST | `/admin/catalog/categories` | `catalog:manage` | 3 |
| PATCH, DELETE | `/admin/catalog/categories/{category_id}` | `catalog:manage` | 3 |
| GET | `/catalog/attributes/{attribute_id}` (kèm options) | đăng nhập | 4 |
| POST | `/admin/catalog/attributes` | `catalog:manage` | 4 |
| PATCH, DELETE | `/admin/catalog/attributes/{attribute_id}` | `catalog:manage` | 4 |
| POST | `/admin/catalog/attributes/{attribute_id}/options` | `catalog:manage` | 4 |
| PATCH, DELETE | `/admin/catalog/attributes/{attribute_id}/options/{option_id}` | `catalog:manage` | 4 |
| GET | `/catalog/categories/{category_id}/attributes` | đăng nhập | 5 |
| PUT, DELETE | `/admin/catalog/categories/{category_id}/attributes/{attribute_id}` (PUT = gắn hoặc cập nhật cờ, idempotent) | `catalog:manage` | 5 |
| POST | `/products` | `products:write` | 7 |
| GET | `/products` (phân trang, lọc `status`) | `products:read` | 7 |
| GET, PATCH, DELETE | `/products/{product_id}` | `products:read` / `write` | 7 |
| POST | `/products/{product_id}/variants` | `products:write` | 9 |
| GET | `/products/{product_id}/variants`, `/products/{product_id}/variants/{variant_id}` | `products:read` | 9 |
| PATCH, DELETE | `/products/{product_id}/variants/{variant_id}` | `products:write` | 10 |
| POST | `/products/{product_id}/images` (multipart) | `products:write` | 11 |
| PATCH, DELETE | `/products/{product_id}/images/{image_id}` | `products:write` | 11 |
| POST | `/products/{product_id}/publish`, `/products/{product_id}/unpublish` | `products:write` | 12 |

Attribute values đi kèm body `POST/PATCH /products` (Task 8), không có route riêng.

## Catalog invariants

Định nghĩa dùng chung (tính cả product/variant đã soft delete, vì dòng con được giữ, xem
*Delete semantics*, và vì FK `RESTRICT` cũng nhìn thấy chúng):

- **Gắn** (attached): có dòng `category_attributes`.
- **Có giá trị** (valued): có dòng `product_attribute_values` tham chiếu attribute/option.
- **Có variant** (varied): có dòng `product_variant_options` tham chiếu attribute/option.
- **Đang dùng** (in use) = *valued* hoặc *varied*. "Gắn" thì **không** phải "đang dùng".

Ở dạng "trong category C" nghĩa là chỉ tính product thuộc C.

| Thao tác | Quy tắc |
| -------- | ------- |
| Đổi `data_type`, `key` của attribute | Không cho phép (bất biến); muốn khác thì tạo attribute mới |
| Xóa attribute | `409` nếu còn gắn vào category, hoặc đang dùng |
| Đổi `value` (tên hiển thị) của option | Luôn được; vẫn unique trong attribute |
| Xóa option | `409` nếu đang dùng |
| Gắn attribute vào category (`PUT`) | Luôn được, kể cả category đã có product; không hồi tố (xem dòng `required`). `is_variation=true` chỉ hợp lệ khi `data_type=SELECT`, ngược lại `422` |
| Đổi `is_variation` | `409` nếu **trong category đó** đã có product *valued* hoặc *varied* với attribute này |
| Đổi `required` | Luôn được. Không hồi tố: product đang `active` giữ nguyên trạng thái; luật mới áp ở lần publish kế tiếp và ở mọi lần sửa product `active` (lần sửa đó phải qua kiểm tra) |
| Đổi `filterable`, `searchable` | Luôn được; chỉ là metadata cho buyer search (ngoài phạm vi phase này), chưa tác động gì |
| Gỡ attribute khỏi category (`DELETE`) | `409` nếu **trong category đó** đã có product *valued* hoặc *varied* với attribute này |
| Thêm category con / đổi cha (`PATCH parent_id`) | `409` nếu category cha đích đang có product (bất kỳ dòng nào, kể cả đã xóa mềm): giữ bất biến "product chỉ ở category lá" |
| Đặt cha tạo vòng (chính nó hoặc hậu duệ) | `422` |
| Xóa category | `409` nếu còn category con hoặc có product |
| Xóa brand | `409` nếu có product |

Race giữa "thêm category con" và "tạo product vào category": thêm con/đổi cha khóa hàng
category cha `FOR UPDATE`, tạo product khóa hàng category `FOR SHARE`, nên hai thao tác
tuần tự. Category của product **bất biến** sau khi tạo (`PATCH` không nhận `category_id`).

## Product lifecycle & required rules

**Product** (`status`):

| Từ | Đến | Cách | Ghi chú |
| -- | --- | ---- | ------- |
| (mới) | `draft` | `POST /products` | Client không gửi `status` |
| `draft` | `active` | `POST .../publish` | Chạy đủ *published invariants* |
| `inactive` | `active` | `POST .../publish` | Như trên |
| `active` | `inactive` | `POST .../unpublish` | Luôn được |

Mọi cặp khác (vd `active → draft`, `inactive → draft`) không tồn tại → `409
invalid_status_transition`. `PATCH` với `status` là `422` (schema `extra="forbid"`). Chỉ
có **một** hàm `transition()` trong service đổi trạng thái.

**Published invariants** (bốn điều kiện mà product phải thỏa để được `active`; **được
enforce tại `publish` và tại mọi mutation của chính product đó, không phải là bất biến
toàn cục của dữ liệu**):

1. Mọi attribute `required` **không phải variation** có dòng ở `product_attribute_values`.
2. Mọi attribute `required` **là variation** xuất hiện là option của **mọi variant live**
   (bị `inactive` cũng tính, vì có thể bật lại). Required của variation attribute được
   thỏa bởi *variant options*, **không** bởi `product_attribute_values`.
3. Có ≥ 1 variant live `active`.
4. Tập attribute variation nhất quán: mọi variant live dùng cùng một tập attribute (kể cả
   attribute variation không `required`: nếu variant này dùng thì variant nào cũng phải dùng).

Được kiểm ở **publish** và ở **mọi mutation trên product đang `active`** (sửa attribute
values, tạo/sửa/xóa/deactivate variant). Mutation của product làm vỡ invariant bị từ chối
(`422 product_invariant_violated` kèm danh sách attribute thiếu), nên **product không thể
tự đưa mình** vào trạng thái vi phạm.

**Product "stale" (chấp nhận, không tự sửa):** thay đổi *catalog* (thêm attribute
`required` vào category, đổi `required`, thêm attribute variation…) có thể làm một product
đang `active` tạm thời không còn thỏa invariants. Hệ thống **không tự unpublish** và không
quét lại hàng loạt: product giữ `active` cho tới khi seller sửa nó (lần sửa đó phải qua
kiểm tra, seller được yêu cầu bổ sung) hoặc `unpublish`, hoặc `publish` lại. Đây là chủ ý:
đổi catalog không được làm sập gian hàng đang bán. Việc báo cho seller / lọc product stale
ngoài phạm vi phase này. `draft`/`inactive` không bị các kiểm tra này chặn;
chỉ dữ liệu từng dòng vẫn được validate (kiểu, option thuộc attribute, category đúng…).

Product không có attribute variation (vd Dog Food): đúng **một** variant không có option
(`option_key` rỗng) để giữ giá/tồn.

**Variant** (`status ∈ {active, inactive}`, mặc định `active`): chuyển qua lại tự do bằng
`PATCH`. Đặt `inactive` hoặc xóa variant `active` cuối cùng của product `active` → `409
last_active_variant`. Tổ hợp option và `sku_code` bất biến về nghĩa "danh tính" của
variant: muốn đổi tổ hợp thì xóa rồi tạo lại (`sku_code` vẫn `PATCH` được).

## Delete semantics

| Sự kiện | Product / variant | Dòng con |
| ------- | ----------------- | -------- |
| Xóa product | Soft delete product và **cascade soft delete mọi variant live** (cùng `deleted_at`, một transaction) | `product_attribute_values`, `product_variant_options`: **giữ lại** (là một phần lịch sử của product; order sau này cần). `product_images`: **xóa cứng dòng**, xóa object trên storage sau khi commit theo kiểu best-effort (lỗi chỉ log; object mồ côi được chấp nhận, việc quét dọn ngoài phạm vi) |
| Xóa variant | Soft delete variant | Giữ `product_variant_options`; **xóa cứng ảnh của variant đó** (không đẩy lên thành ảnh chung, vì ảnh đó chỉ đúng với variant) |
| Tái sử dụng khóa | `sku_code` và `option_key` của bản ghi đã xóa được giải phóng (partial unique theo `deleted_at IS NULL`) | — |

Hệ quả cần chấp nhận: vì dòng con được giữ và "đang dùng" tính cả bản ghi đã xóa mềm, một
attribute/option từng được product dùng thì **không xóa cứng được nữa** (`409`). Chỗ trống
này sẽ được xử lý bằng cờ `is_active` cho catalog ở phase sau, không phải bằng xóa cứng.
Bắt buộc: mọi query của bảng con phải lọc theo parent live, và có test cho việc này.

## Dependency graph

```
T1 permission catalog:manage
 └─ T2 brands ─ T3 categories ─ T4 attributes+options ─ T5 category_attributes + read API ─ T6 seed
                                                            │
T7 product core ◄───────────────────────────────────────────┘ (cần category lá + brand)
 ├─ T8 attribute values (cần T5)
 ├─ T9 variants create/read ─ T10 variants update/delete/stock
 ├─ T11 images (cần T9 cho variant_id)
 └─ T12 publish rules (cần T8, T9)
T13 e2e acceptance ◄─ T6, T12, T11
T14 PRODUCT.md + DECISIONS.md ◄─ mọi quyết định đã chốt
T15 API contract + README ◄─ T13 (contract phải khớp code)
```

## Task List

### Phase 1: Catalog (admin)

- [x] Task 1: Permission `catalog:manage` (cổng ghi catalog tạm thời)
- [x] Task 2: Brands (admin CRUD + read)
- [x] Task 3: Categories (cây, admin CRUD + read tree)
- [x] Task 4: Attributes + options (admin CRUD)
- [x] Task 5: Category attribute config + `GET /catalog/categories/{id}/attributes`
- [x] Task 6: Seed catalog mẫu

### Checkpoint A: Catalog

- [x] Gate xanh, migration `upgrade head` / `downgrade` sạch
- [x] Thêm "Dog Food" + attribute chỉ bằng API, `GET .../attributes` trả đúng metadata
- [x] `manager` / `viewer` nhận `403` trên `/admin/catalog/*`

### Phase 2: Product (seller)

- [x] Task 7: Product core
- [x] Task 8: Product attribute values
- [x] Task 9: Variants — tạo & đọc
- [x] Task 10: Variants — sửa, xóa, tồn kho
- [x] Task 11: Product images
- [x] Task 12: Publish rules (`draft → active`)

### Checkpoint B: Product

- [x] Gate xanh, cách ly tenancy có test

### Phase 3: Acceptance & Docs

- [x] Task 13: Acceptance end-to-end (Áo Polo 6 SKU, MacBook RAM × Storage, Dog Food)
- [x] Task 14: Viết `docs/product/PRODUCT.md` và `docs/product/DECISIONS.md`
- [x] Task 15: Viết API contract catalog/product + cập nhật `README.md`

### Checkpoint: Complete

- [x] Toàn bộ tiêu chí Success trong `docs/intent/catalog.md` đạt
- [ ] Người dùng review

## Risks and Mitigations

| Risk | Impact | Mitigation |
| ---- | ------ | ---------- |
| `catalog:manage` là quyền trong shop → mọi owner của mọi shop sửa được catalog toàn sàn | High | **Đã chấp nhận có điều kiện** cho phase này; chỉ gán cho `owner`, test `manager`/`viewer` bị `403`; ghi rõ ở DECISIONS và API contract; chuyển sang platform admin ở phase sau (*Next phase*) |
| EAV làm validate phức tạp (type/option/required) và dễ rò dữ liệu sai loại | High | CHECK ở DB + validate tập trung một chỗ trong service, test theo từng `data_type` |
| Hai request đồng thời cùng tạo một tổ hợp option / cùng làm vỡ invariant của product | High | Cột `option_key` + partial unique index (DB là chốt chặn), khóa hàng product `FOR UPDATE` cho mọi ghi variant, ánh xạ `IntegrityError` → `409`; có test đồng thời (`asyncio.gather`) |
| Product `active` bị sửa lách qua nhiều đường (PATCH, variant, attribute values) | High | Chỉ một hàm `transition()`; kiểm *published invariants* ở mọi mutation trên product `active`; `PATCH` cấm `status` |
| Product `active` thành "stale" sau khi catalog đổi (thêm `required`…) | Low | Chấp nhận có chủ ý, không tự unpublish; ghi ở *Product lifecycle* và DECISIONS; phát hiện/báo seller để phase sau |
| Cột denormalize `shop_id` và quan hệ variant/image/option lệch do bug ở service | High | Composite FK ở DB (mục *Cross-row integrity*) + test DB chèn sai bỏ qua service |
| `stock` trên variant phải migrate sang `inventories` khi có warehouse | Med | Đã chấp nhận (người dùng xác nhận); ghi vào DECISIONS như quyết định có thể mở lại |
| Alembic autogenerate không sinh CHECK / partial index | Med | Viết tay như `models/identity.py`; test `test_migration_metadata` |
| Đổi contract OpenAPI làm hỏng client sinh tự động | Low | Ghi rõ trong commit, cập nhật `README.md` (theo AGENTS.md) |
| Task 6 seed ghi vào DB thật ở môi trường khác | Low | Seed idempotent (`ON CONFLICT DO NOTHING`), downgrade chỉ xóa đúng dòng đã seed |

## Next phase (đã ghi nhận, chưa làm)

**Chuyển quyền ghi catalog từ `catalog:manage` sang platform admin.**

- Thêm `users.is_platform_admin` (boolean, default false) + dependency
  `require_platform_admin` trong `api/deps.py`, đọc cờ từ DB mỗi request.
- Cấp cờ bằng script vận hành / repository helper, không qua API công khai.
- Đổi các route `/api/v1/admin/catalog/*` sang dependency mới; gỡ `catalog:manage` khỏi
  role `owner` bằng migration (hoặc xóa permission nếu không còn dùng).
- Cập nhật `PRODUCT.md`, `DECISIONS.md` và `API_CONTRACT_CATALOG.md` (Task 14, 15): các
  file này phải ghi rõ đây là quyết định *tạm thời* ở phase này.
- **Lý do phải làm:** với `catalog:manage`, mọi owner của bất kỳ shop nào đều sửa được
  catalog dùng chung. Chỉ chấp nhận được khi chưa có seller thật ngoài nhóm phát triển.
- **Điều kiện mở lại sớm hơn:** trước khi có người dùng bên ngoài đăng ký shop.

## Open Questions

1. ~~Platform admin~~ **Đã chốt:** dùng `catalog:manage` tạm, chuyển platform admin ở phase sau.
2. ~~`is_variation`~~ **Đã chốt (người dùng đồng ý):** bổ sung cột `is_variation` trên `category_attributes` (Decision 2).
3. ~~Không kế thừa attribute~~ **Đã chốt:** không kế thừa từ category cha, product chỉ vào category lá (Decision 3).
4. ~~Đơn vị tiền~~ **Đã chốt:** `BIGINT` VND, không có cột currency.
5. ~~Con số ảnh~~ **Đã chốt:** 9 ảnh chung + 5 ảnh/variant, khung 1600 × 1600, dung lượng theo `max_upload_bytes` (Decision 9).
6. Đã chốt sau review: đổi status chỉ qua `publish`/`unpublish`; required của variation attribute thỏa bởi variant options; bất biến catalog và "đang dùng" như bảng trên; `option_key` + khóa hàng cho race; soft delete giữ dòng con, xóa cứng ảnh. Các điểm này đã ghi ở các mục *Route map*, *Catalog invariants*, *Product lifecycle*, *Delete semantics*.
