# Todo: Catalog & Product

Kế hoạch: `plan.md`. Ý định: `docs/intent/catalog.md`.

**Quality gate chung** (mỗi task phải qua trước khi tick):

```bash
uv run ruff format --check . && uv run ruff check . && uv run mypy app && uv run pytest -q && uv lock --check
```

Test cần PostgreSQL: `docker compose --env-file compose.env up -d --wait` rồi `uv run pytest -q -m db`.
Mỗi thay đổi bảng: model → import trong `app/models/__init__.py` (+ `__all__`) →
`uv run alembic revision --autogenerate -m "..."` → sửa tay CHECK / partial index →
`alembic upgrade head` và `downgrade -1` đều sạch.
Đường dẫn file bên dưới là dự kiến; theo layout `AGENTS.md` (mỗi layer một file theo model / flow).

---

## Phase 1: Catalog (admin)

### Task 1: Permission `catalog:manage` (cổng ghi catalog tạm thời)

**Description:** Thêm permission `catalog:manage` để các route ghi catalog có cổng quyền. Đây là giải pháp tạm: phase sau chuyển sang platform admin (xem `plan.md`, mục *Next phase*).

**Acceptance criteria:**
- [x] Migration seed thêm permission `catalog:manage` ("Configure the shared catalog: categories, attributes, brands"), idempotent (`ON CONFLICT DO NOTHING`)
- [x] Chỉ system role `owner` được gán; `manager` và `viewer` không có (ghi rõ trong comment migration và cập nhật `MANAGER_EXCLUDED`-tương đương nếu cần, không sửa migration cũ)
- [x] `downgrade` gỡ đúng permission và các dòng `role_permissions` của nó
- [x] Dùng `require_permissions("catalog:manage")` có sẵn, không thêm dependency mới; có route/dependency mẫu để Task 2 dùng
- [x] Comment / docstring ghi rõ đây là quyền tạm thời và trỏ tới *Next phase* trong `plan.md`
- [x] **Cập nhật test seed hiện có** `tests/integration/test_identity_seed_db.py`: `EXPECTED_PERMISSIONS` thêm `catalog:manage`; `OWNER_ONLY` thêm `catalog:manage`; các test "owner giữ mọi permission", "manager thiếu permission owner-only", "viewer chỉ đọc", "không role nào giữ permission chưa seed" vẫn đúng và được sửa cho khớp
- [x] Đồng bộ lệnh type-check trong `AGENTS.md` (`mypy src`) và `README.md` (`mypy src alembic`, hai chỗ: bảng lệnh và mô tả job `quality`) thành `uv run mypy app`, khớp CI

**Verification:**
- [x] `-m db`: `test_identity_seed_db.py` đã sửa vẫn xanh; thêm test riêng cho `catalog:manage` (owner có, manager/viewer không, chạy lại không nhân đôi, downgrade sạch)
- [x] `-m db`: token owner → `200`, manager/viewer → `403` trên route mẫu
- [x] `rg -n "mypy src" .` không còn kết quả
- [x] Gate chung xanh

**Dependencies:** None
**Files likely touched:** migration seed mới, `tests/integration/test_identity_seed_db.py`, `tests/integration/test_catalog_permission_db.py`, `AGENTS.md`, `README.md`
**Estimated scope:** Medium (5 files, đa số sửa nhỏ)

### Task 2: Brands (admin CRUD + read)

**Description:** Slice đầu tiên của catalog, dựng khung layer `catalog` (models/errors/constants/schemas/api) mà các task sau dùng lại.

**Acceptance criteria:**
- [x] `brands` (id, name, slug, timestamps); slug unique, sinh từ name, không đổi khi rename
- [x] Routes (đúng *Route map* trong `plan.md`): `POST /api/v1/admin/catalog/brands`, `PATCH` và `DELETE /api/v1/admin/catalog/brands/{brand_id}` (cần `catalog:manage`); `GET /api/v1/catalog/brands` (đăng nhập)
- [x] Trùng slug/name → `409` với mã lỗi ổn định; xóa brand đang có product → `409`
- [x] Response dạng `BaseResponse[...]`; lỗi theo `core/errors.py`; router đăng ký trong `api/v1/__init__.py`

**Verification:**
- [x] Unit: schema validation, sinh slug
- [x] `-m db`: repository + API (owner ghi được, manager/viewer `403`, đọc được)
- [x] `test_openapi_envelope`, `test_migration_metadata` xanh; gate chung xanh

**Dependencies:** Task 1
**Files likely touched:** `app/models/catalog.py`, `app/repositories/brand_repository.py`, `app/services/catalog_service.py`, `app/schemas/catalog/brand.py`, `app/api/v1/catalog/brands.py` (+ errors, constants, migration, `__init__`)
**Estimated scope:** Medium — dựng khung, chấp nhận vượt 5 file vì phần lớn là file khởi tạo layer

### Task 3: Categories (cây)

**Description:** Category dạng cây `parent_id`, admin CRUD, đọc cây.

**Acceptance criteria:**
- [x] `categories` (id, parent_id nullable, name, slug, position, timestamps); slug unique
- [x] Không cho tạo vòng (đặt cha là chính nó hoặc hậu duệ) → `422/409` rõ ràng; giới hạn độ sâu nếu chọn (ghi vào constants)
- [x] Routes: `GET /api/v1/catalog/categories` (cây, có `is_leaf`), `GET /api/v1/catalog/categories/{category_id}`; `POST /api/v1/admin/catalog/categories`, `PATCH` và `DELETE /api/v1/admin/catalog/categories/{category_id}` (cần `catalog:manage`)
- [x] Bảng `attribute_options` thuộc Task 4 (xem đó cho `UNIQUE (id, attribute_id)`); Task này chỉ lo `categories`
- [x] Bất biến (theo *Catalog invariants*): thêm con / đổi cha vào category đang có product → `409`; xóa category còn con hoặc có product → `409`; đặt cha tạo vòng → `422`
- [x] Thêm con / đổi cha khóa hàng category cha `FOR UPDATE` (để Task 7 khóa `FOR SHARE` khi tạo product)

**Verification:**
- [x] Unit: phát hiện vòng (hàm thuần trong `utils/catalog.py`)
- [x] `-m db`: CRUD, cây 3 tầng (Điện tử → Máy tính → Laptop), xóa bị chặn
- [x] Gate chung xanh

**Dependencies:** Task 2
**Files likely touched:** `app/models/catalog.py`, `app/repositories/category_repository.py`, `app/services/catalog_service.py`, `app/schemas/catalog/category.py`, `app/api/v1/catalog/categories.py`
**Estimated scope:** Medium

### Task 4: Attributes + options

**Description:** Kho attribute dùng chung và option cho attribute dạng chọn.

**Acceptance criteria:**
- [x] `attributes` (id, name, key/slug, `data_type` ∈ TEXT|NUMBER|SELECT); `attribute_options` (id, attribute_id, value, sort_order)
- [x] Routes (cần `catalog:manage`): `POST /api/v1/admin/catalog/attributes`; `PATCH`, `DELETE /api/v1/admin/catalog/attributes/{attribute_id}`; `POST /api/v1/admin/catalog/attributes/{attribute_id}/options`; `PATCH`, `DELETE /api/v1/admin/catalog/attributes/{attribute_id}/options/{option_id}`
- [x] Đọc: `GET /api/v1/catalog/attributes/{attribute_id}` kèm options (sắp theo `sort_order`), đăng nhập
- [x] Option chỉ hợp lệ với attribute `SELECT`; `value` unique trong attribute; đổi `value` (tên hiển thị) luôn được
- [x] `attribute_options` có `UNIQUE (id, attribute_id)` để Task 8/9 dùng cho composite FK `(option_id, attribute_id)` (mục *Cross-row integrity* trong `plan.md`)
- [x] `data_type` và `key` **bất biến**: `PATCH` chứa trường này → `422`
- [x] Xóa attribute còn gắn category hoặc *đang dùng* → `409`; xóa option *đang dùng* → `409` (định nghĩa "đang dùng" ở *Catalog invariants*; kiểm bằng exists-query, không dựa vào `IntegrityError`)

**Verification:**
- [x] Unit: schema, ràng buộc `data_type` ↔ option
- [x] `-m db`: CRUD, ràng buộc unique/CHECK, `409` khi đang dùng
- [x] Gate chung xanh

**Dependencies:** Task 2
**Files likely touched:** `app/models/catalog.py`, `app/repositories/attribute_repository.py`, `app/schemas/catalog/attribute.py`, `app/api/v1/catalog/attributes.py`, migration
**Estimated scope:** Medium

### Task 5: Category attribute config + read API

**Description:** Gắn attribute vào category và phơi metadata để frontend dựng form động.

**Acceptance criteria:**
- [x] `category_attributes` (category_id, attribute_id, `required`, `filterable`, `searchable`, **`is_variation`**, position), PK composite
- [x] Admin (cần `catalog:manage`): `PUT /api/v1/admin/catalog/categories/{category_id}/attributes/{attribute_id}` (gắn hoặc cập nhật cờ, idempotent) và `DELETE` cùng đường dẫn
- [x] `is_variation=true` chỉ hợp lệ với attribute `data_type=SELECT` → ngược lại `422`
- [x] Đổi `is_variation`, hoặc gỡ attribute, khi **trong category đó** đã có product *valued/varied* với attribute này → `409`
- [x] Đổi `required` / `filterable` / `searchable` luôn được; `required` không hồi tố (không đổi status product đã có); thêm attribute vào category đã có product vẫn được
- [x] `GET /api/v1/catalog/categories/{id}/attributes` trả `[{id, name, type, required, is_variation, options?}]` đúng ví dụ trong mô tả, có options với attribute `SELECT`

**Verification:**
- [x] `-m db`: thêm Dog Food + Weight(NUMBER, required) + Flavor(SELECT, required) chỉ bằng API, GET trả đúng JSON
- [x] Unit: schema response
- [x] Gate chung xanh

**Dependencies:** Task 3, Task 4
**Files likely touched:** `app/models/catalog.py`, `app/repositories/category_attribute_repository.py`, `app/schemas/catalog/category_attribute.py`, `app/api/v1/catalog/category_attributes.py`, migration
**Estimated scope:** Medium

### Task 6: Seed catalog mẫu

**Description:** Migration seed idempotent để demo chạy được ngay: Thời trang → Nam → Áo thun; Điện tử → Máy tính → Laptop; Điện thoại; vài brand; attribute Color/Size/Material/RAM/Storage/CPU/Screen (+ options).

**Acceptance criteria:**
- [x] Áo thun: Size (required, variation), Color (required, variation), Material (optional)
- [x] Laptop: RAM, Storage (required, variation), CPU (required), Screen, Color (optional)
- [x] Chạy lại không lỗi, không nhân đôi; `downgrade` chỉ xóa đúng các dòng đã seed
- [x] Không chứa thông tin bí mật / dữ liệu cá nhân

**Verification:**
- [x] `-m db`: test seed như `test_identity_seed_db.py` (đủ dòng, idempotent, downgrade sạch)
- [x] Gate chung xanh

**Dependencies:** Task 5
**Files likely touched:** migration seed mới, `tests/integration/test_catalog_seed_db.py`
**Estimated scope:** Small (1–2 file)

### Checkpoint A: Catalog

- [x] Gate chung xanh; `alembic upgrade head` rồi `downgrade` tới base đều sạch
- [x] Demo: thêm category "Dog Food" + attribute qua API, không migrate, `GET .../attributes` trả đúng
- [x] `manager` / `viewer` nhận `403` trên mọi route `/admin/catalog/*`; Next phase (platform admin) đã có trong `plan.md`
- [ ] Review với người dùng trước khi qua Phase 2

---

## Phase 2: Product (seller)

### Task 7: Product core

**Description:** Product thuộc shop, chưa có attribute/variant. Đây là slice tenancy quan trọng nhất.

**Acceptance criteria:**
- [x] `products` (id, shop_id, category_id, brand_id nullable, name, description, status ∈ draft|active|inactive, created_by_user_id, updated_by_user_id, timestamps, `deleted_at`)
- [x] Routes: `POST /api/v1/products`, `GET /api/v1/products` (phân trang, lọc `status`), `GET`, `PATCH`, `DELETE /api/v1/products/{product_id}`; `shop_id` lấy từ principal, không nhận từ client
- [x] Product luôn được tạo ở `draft`; `POST` và `PATCH` **không nhận `status`** (schema `extra="forbid"` → `422`); `PATCH` cũng không nhận `category_id` (bất biến sau khi tạo)
- [x] Đổi trạng thái chỉ qua hàm `transition()` trong service (được Task 12 nối vào `publish`/`unpublish`); chưa có đường nào khác đổi `status`
- [x] Ghi cần `products:write`, đọc cần `products:read`; viewer ghi → `403`
- [x] Product của shop khác → `404` (đọc, sửa, xóa)
- [x] `products` có `UNIQUE (id, shop_id)` (đích của composite FK từ `product_variants`, Task 9)
- [x] `category_id` phải là category lá; tạo product khóa hàng category `FOR SHARE` (tuần tự với việc thêm con ở Task 3); brand tồn tại
- [x] `DELETE` là soft delete theo *Delete semantics*; service `delete_product` là điểm mở rộng để Task 9 (cascade variant) và Task 11 (xóa ảnh) nối vào

**Verification:**
- [x] Unit: schema, quy tắc category lá
- [x] `-m db`: CRUD; hai shop cô lập nhau; viewer `403`; audit user đúng người thao tác
- [x] Gate chung xanh

**Dependencies:** Task 3 (Task 2 cho brand)
**Files likely touched:** `app/models/product.py`, `app/repositories/product_repository.py`, `app/services/product_service.py`, `app/schemas/product/product.py`, `app/api/v1/products/products.py`
**Estimated scope:** Medium

### Task 8: Product attribute values

**Description:** Lưu giá trị attribute động theo category, validate chặt.

**Acceptance criteria:**
- [x] `product_attribute_values` (product_id, attribute_id, option_id, value_text, value_number); PK (product_id, attribute_id); CHECK đúng một cột giá trị khác NULL
- [x] Body create/update product nhận `attributes: [{attribute_id, option_id | value_text | value_number}]`. Semantics của `PATCH`: **không gửi `attributes` → giữ nguyên** tập giá trị hiện có; **gửi `attributes: []` → xóa toàn bộ**; gửi danh sách → thay thế toàn bộ tập bằng danh sách đó (không merge). Phân biệt "không gửi" với `[]` bằng `model_fields_set` của Pydantic (không dùng `None` làm dấu hiệu). Trên product `active`, `attributes: []` chỉ được nếu vẫn thỏa *published invariants*, nếu không `422`
- [x] Từ chối (`422`): attribute không thuộc category của product; sai kiểu so với `data_type`; `option_id` không thuộc attribute; giá trị trùng attribute; **attribute có `is_variation=true`** (mã `attribute_is_variation`: giá trị đó thuộc variant options, không thuộc product)
- [x] FK composite `(option_id, attribute_id) → attribute_options (id, attribute_id)` để DB bảo đảm option thuộc đúng attribute (NULL `option_id` không kích hoạt)
- [x] Trên product đang `active`, thay attribute values phải giữ đúng *published invariants* (không được xóa giá trị của attribute `required` non-variation), nếu không `422 product_invariant_violated`
- [x] `GET` product trả attribute values kèm tên attribute/option

**Verification:**
- [x] Unit: hàm validate giá trị theo `data_type` (thuần, table-driven test)
- [x] `-m db`: `PATCH` không có `attributes` giữ nguyên giá trị; `attributes: []` xóa hết (product `draft`), bị `422` trên product `active` thiếu `required`; danh sách mới thay thế toàn bộ
- [x] `-m db`: MacBook (RAM option, Storage option, CPU text, Screen number) lưu và đọc lại đúng
- [x] Gate chung xanh

**Dependencies:** Task 5, Task 7
**Files likely touched:** `app/models/product.py`, `app/repositories/product_attribute_repository.py`, `app/utils/catalog.py`, `app/services/product_service.py`, migration
**Estimated scope:** Medium

### Task 9: Variants — tạo & đọc

**Description:** Variant/SKU với option động (không hard-code Color/Size).

**Acceptance criteria:**
- [x] `product_variants` (id, product_id, shop_id, sku_code, price BIGINT ≥ 0, stock INT ≥ 0, `status` ∈ `active|inactive` mặc định `active` (CHECK), `option_key`, timestamps, `deleted_at`); `sku_code` unique trong shop (partial, live)
- [x] **Chống trùng tổ hợp bằng DB:** `option_key` do `utils/catalog.py` tính (cặp `attribute_id:option_id` sắp theo `attribute_id`, nối `|`, rỗng nếu không có option) + partial unique index `(product_id, option_key) WHERE deleted_at IS NULL`; `IntegrityError` → `409`
- [x] **Cross-row integrity ở DB:** FK composite `(product_id, shop_id) → products (id, shop_id)` (nên `variant.shop_id` luôn bằng `product.shop_id`); `UNIQUE (id, product_id)` trên `product_variants` (đích cho Task 11); `product_variant_options` có FK composite `(option_id, attribute_id) → attribute_options (id, attribute_id)`; service gán `shop_id` từ product, không nhận từ client
- [x] Mọi ghi variant khóa hàng product `SELECT … FOR UPDATE` ở đầu transaction (bảo vệ kiểm tra "nhất quán tập attribute" và "variant active cuối cùng")
- [x] Xóa product cascade soft delete mọi variant live (cùng `deleted_at`) theo *Delete semantics*; nối vào `delete_product` của Task 7
- [x] `product_variant_options` (variant_id, attribute_id, option_id), `UNIQUE(variant_id, attribute_id)`
- [x] Routes: `POST /api/v1/products/{product_id}/variants`; `GET /api/v1/products/{product_id}/variants`; `GET /api/v1/products/{product_id}/variants/{variant_id}`. Body tạo: `sku_code`, `price`, `stock`, `status?`, `options: [{attribute_id, option_id}]`
- [x] Mỗi option: attribute phải `is_variation=true` trong category của product; option thuộc attribute; một attribute tối đa một lần
- [x] Tập attribute variation phải nhất quán giữa các variant live của product (`422`); product không có attribute variation chỉ có đúng một variant không option (variant thứ hai → `409` do `option_key` rỗng trùng)
- [x] Tạo variant trên product `active` phải giữ *published invariants* (vd thiếu variation attribute `required` → `422 product_invariant_violated`)
- [x] Quyền `products:write`/`read`, tenancy như Task 7

**Verification:**
- [x] Unit: kiểm tra tổ hợp trùng / nhất quán (hàm thuần)
- [x] `-m db`: Áo Polo tạo đủ 6 SKU Color × Size với giá khác nhau; tạo trùng `Black/S` → `409`; `sku_code` trùng cùng shop → `409`, khác shop → OK
- [x] `-m db` **đồng thời:** hai request `asyncio.gather` cùng tạo tổ hợp `Black/S` → đúng một `201`, một `409`, DB chỉ có một dòng; hai request cùng `sku_code` tương tự
- [x] Unit: `option_key` không phụ thuộc thứ tự option trong body
- [x] `-m db` **bỏ qua service** (chèn bằng repository/SQL): variant có `shop_id` khác `products.shop_id` → `IntegrityError`; `product_variant_options` với option không thuộc attribute → `IntegrityError`
- [x] Gate chung xanh

**Dependencies:** Task 7, Task 5 (cần `is_variation`)
**Files likely touched:** `app/models/product.py`, `app/repositories/variant_repository.py`, `app/services/variant_service.py`, `app/schemas/product/variant.py`, `app/api/v1/products/variants.py`
**Estimated scope:** Medium (5 file + migration; nếu vượt, tách repository/option sang Task riêng)

### Task 10: Variants — sửa, xóa, tồn kho

**Description:** Hoàn thiện vòng đời variant.

**Acceptance criteria:**
- [x] `PATCH /api/v1/products/{product_id}/variants/{variant_id}`: sửa `price`, `stock`, `status`, `sku_code`; **không nhận `options`** (`422`; muốn đổi tổ hợp thì xóa rồi tạo lại) — ghi rõ trong contract
- [x] Variant `status` ∈ `active|inactive`; chuyển qua lại tự do; đặt `inactive` hoặc `DELETE` variant `active` cuối cùng của product `active` → `409 last_active_variant`
- [x] `DELETE /api/v1/products/{product_id}/variants/{variant_id}` là soft delete; giữ `product_variant_options`; giải phóng `sku_code` và `option_key`
- [x] Mọi ghi variant khóa hàng product `FOR UPDATE` như Task 9
- [x] `stock` không âm (CHECK DB + validate); đặt `stock` là ghi đè giá trị tuyệt đối, không phải cộng dồn

**Verification:**
- [x] `-m db`: sửa giá/tồn, `stock=-1` → `422`, `PATCH` có `options` → `422`, xóa hoặc deactivate variant active cuối của product active → `409`, tạo lại tổ hợp sau khi xóa → OK, tenancy `404`
- [x] `-m db`: query variant/option của product đã soft delete không lộ ra qua API
- [x] Gate chung xanh

**Dependencies:** Task 9
**Files likely touched:** `app/services/variant_service.py`, `app/repositories/variant_repository.py`, `app/schemas/product/variant.py`, `app/api/v1/products/variants.py`, `tests/integration/test_variant_api.py`
**Estimated scope:** Small–Medium

### Task 11: Product images

**Description:** Ảnh của product và của variant (một variant có N ảnh).

**Acceptance criteria:**
- [x] `product_images` (id, product_id, variant_id nullable, key, position, timestamps); **DB bảo đảm** `variant_id` thuộc đúng `product_id` bằng FK composite `(variant_id, product_id) → product_variants (id, product_id)` (NULL `variant_id` không kích hoạt, ảnh chung vẫn hợp lệ); service thêm điều kiện variant còn live
- [x] Routes: `POST /api/v1/products/{product_id}/images` (multipart, field `file`, tùy chọn `variant_id`); `PATCH /api/v1/products/{product_id}/images/{image_id}` với body **`{ "position": integer }`** (chỉ trường này; trường khác → `422`) và `DELETE` cùng đường dẫn. Quy tắc reindex: `position` là chỉ số đích `0..n-1` trong cùng phạm vi (ảnh chung của product, hoặc ảnh của cùng variant); giá trị ngoài `[0, n-1]` → `422`; ảnh được chèn vào vị trí đích, các ảnh còn lại dịch để giữ dãy liên tục không trùng; `DELETE` cũng dồn lại dãy. Không đổi được `variant_id` của ảnh đã có (xóa rồi tải lại). Ảnh xuất hiện trong response `GET` product/variant kèm URL
- [x] Chính sách ảnh theo Decision 9: nhận JPEG/PNG/WEBP, dung lượng ≤ `Settings.max_upload_bytes`, cạnh trong `[MIN_SIDE, MAX_SIDE]`; hàm mới `normalize_product_image` trong `utils/media.py` lưu WEBP, không crop, thu nhỏ vừa 1600 × 1600 giữ tỉ lệ, không phóng to
- [x] Giới hạn: tối đa 9 ảnh chung (`variant_id` NULL) mỗi product, 5 ảnh mỗi variant; vượt → `409 image_limit_reached` (hằng số trong `constants/`)
- [x] `position` server cấp (append), `PATCH` di chuyển và giữ dense `0..n-1` trong từng phạm vi
- [x] File lưu qua `StorageBackend` (mở rộng `MediaService`), DB chỉ giữ key; URL dựng bằng `media_urls`; rate limit như upload hiện có
- [x] Xóa: `DELETE` ảnh xóa cứng dòng rồi xóa object sau commit (best-effort, lỗi chỉ log); xóa variant → xóa cứng ảnh của variant đó; xóa product → xóa cứng mọi ảnh của product (nối vào `delete_product`); không đẩy ảnh variant lên thành ảnh chung

**Verification:**
- [x] Unit: `MediaService` cho ảnh product (dùng storage giả)
- [x] `-m db`: `PATCH {"position": 0}` trên ảnh thứ 3 → dãy liên tục `0..n-1`, không trùng; `position` ngoài khoảng → `422`; body có trường khác → `422`; `DELETE` ảnh giữa dãy dồn lại đúng
- [x] `-m db`: upload ảnh chung + 2 ảnh cho variant Black; `variant_id` của product khác → `422`; ảnh thứ 10 chung / thứ 6 của variant → `409`; xóa variant/product không còn dòng ảnh nào; tenancy `404`
- [x] `-m db` **bỏ qua service**: chèn ảnh với `variant_id` của product khác → `IntegrityError`; ảnh chung (`variant_id` NULL) chèn được
- [x] Unit: `normalize_product_image` (không crop, không phóng to, ra WEBP, ảnh nhỏ giữ nguyên kích thước)
- [x] Gate chung xanh

**Dependencies:** Task 9
**Files likely touched:** `app/models/product.py`, `app/repositories/product_image_repository.py`, `app/services/media_service.py`, `app/schemas/product/image.py`, `app/api/v1/products/images.py`
**Estimated scope:** Medium

### Task 12: Publish rules (`draft → active`)

**Description:** Chốt tiêu chí "thiếu attribute required thì bị từ chối" tại thời điểm publish.

**Acceptance criteria:**
- [x] Routes: `POST /api/v1/products/{product_id}/publish` (`draft|inactive → active`), `POST /api/v1/products/{product_id}/unpublish` (`active → inactive`); cần `products:write`; cặp chuyển khác → `409 invalid_status_transition`
- [x] `publish` chạy đủ *published invariants* (plan.md): (1) mọi attribute `required` non-variation có giá trị; (2) mọi attribute `required` variation có option ở **mọi** variant live — thỏa bằng variant options, không bằng attribute values; (3) ≥ 1 variant live `active`; (4) tập attribute variation nhất quán. Thực hiện dưới khóa hàng product `FOR UPDATE`
- [x] Vi phạm → `422 product_invariant_violated` kèm danh sách attribute thiếu (id + tên) theo dạng ổn định, không lộ chi tiết nội bộ
- [x] Kiểm tra invariant dùng **một hàm chung** với các mutation trên product `active` (Task 8, 9, 10): không có đường **mutation của product** nào đưa nó vào trạng thái vi phạm. Invariants chỉ được enforce ở `publish` và mutation của product, không phải bất biến toàn cục
- [x] Product "stale" (catalog đổi sau khi publish, vd thêm attribute `required`): giữ `active`, **không tự unpublish**; lần sửa tiếp theo bị kiểm và trả `422` liệt kê attribute cần bổ sung; có test chứng minh

**Verification:**
- [x] Unit: hàm tính danh sách thiếu (thuần)
- [x] `-m db`: Laptop thiếu CPU → `422` liệt kê CPU; bổ sung → publish OK
- [x] `-m db`: Áo Polo có Color/Size `required` + variation: publish khi một variant thiếu Size → `422` liệt kê Size; đủ → OK; gửi giá trị Color qua attribute values → `422 attribute_is_variation`
- [x] `-m db`: `PATCH` có `status` → `422`; `active → draft` → `409`; sửa/xóa làm vỡ invariant trên product active bị từ chối; đường `PATCH`/variant/attribute values không lách được luật publish
- [x] `-m db`: product `active` → admin thêm attribute `required` mới vào category → product vẫn `active` (không đổi); `PATCH` product đó bị `422` liệt kê attribute mới; `unpublish` rồi `publish` cũng bị `422` tới khi bổ sung
- [x] `-m db` đồng thời: `publish` chạy cùng lúc với xóa variant cuối → kết quả nhất quán (hoặc publish bị `422`, hoặc xóa bị `409`)
- [x] Gate chung xanh

**Dependencies:** Task 8, Task 9
**Files likely touched:** `app/services/product_service.py`, `app/utils/catalog.py`, `app/errors/catalog.py`, `tests/unit/test_product_publish_rules.py`, `tests/integration/test_product_publish_api.py`
**Estimated scope:** Small–Medium

### Checkpoint B: Product

- [x] Gate chung xanh; `-m db` xanh
- [x] Hai shop không thấy/không sửa được product của nhau (test rõ)
- [ ] Review với người dùng trước khi qua Phase 3

---

## Phase 3: Acceptance & Docs

### Task 13: Acceptance end-to-end

**Description:** Một bộ test tích hợp chạy đúng các kịch bản của tiêu chí Success, làm bằng chứng và làm nguồn ví dụ cho tài liệu.

**Acceptance criteria:**
- [x] Kịch bản Dog Food: admin thêm category + attribute qua API → seller đăng product → publish OK; thiếu `required` → bị từ chối
- [x] Kịch bản Áo Polo Nike: Color(Black, White) × Size(S, M, L) = 6 SKU, giá 300000/320000, ảnh theo variant
- [x] Kịch bản MacBook Pro M4: attribute RAM/Storage/CPU/Screen; variant theo RAM × Storage
- [x] Không cần migration nào ngoài seed để thêm category mới trong kịch bản

**Verification:**
- [x] `uv run pytest -q -m db tests/integration/test_catalog_acceptance.py`
- [x] Gate chung xanh
- [ ] CI `readiness` job xanh — chưa chạy trên CI (chưa push); toàn bộ `-m db` đã xanh ở máy local

**Dependencies:** Task 6, Task 11, Task 12
**Files likely touched:** `tests/integration/test_catalog_acceptance.py`, `tests/conftest.py` (fixture)
**Estimated scope:** Small–Medium

### Task 14: Tài liệu `PRODUCT.md` và `DECISIONS.md`

**Description:** Tạo hai file theo mẫu `D:\KLTN\vya-ocr-exp\docs\product\` (tiếng Việt), tại `docs/product/`. `PRODUCT.md` là luật của sản phẩm; `DECISIONS.md` trả lời "vì sao" cho từng luật kèm hướng đã cân rồi loại.

**Acceptance criteria:**
- [x] `PRODUCT.md` có các mục theo mẫu: Actors (người quản trị catalog = owner có `catalog:manage` ở phase này, seller/thành viên shop, buyer — ghi rõ buyer ngoài phạm vi; ghi platform admin là bước kế tiếp), Objects, Source of truth, Business rules, Glossary, Human decisions, The bet, Not this product, Open
- [x] Business rules đánh số, mỗi luật một câu kiểm chứng được: ownership Product→Shop→Membership→User, `created_by` chỉ để audit, attribute theo category lá, `required` chỉ áp khi publish, variant option động, `stock` trên variant, xóa mềm product/variant, cách ly tenancy
- [x] `DECISIONS.md` mỗi mục dạng "### Vì sao …?", nói rõ dựa trên điều gì để mở lại được; bao phủ ít nhất: Shop là domain riêng (không `user_id` trên product) · EAV có kiểm soát · `is_variation` · không kế thừa attribute · draft/active · `stock` trên variant và cách chuyển sang `inventories` sau · `catalog:manage` là quyền tạm thời và vì sao chuyển sang platform admin (cờ trên user) ở phase sau, kèm điều kiện mở lại · BIGINT VND · xóa cứng catalog / mềm product · vòng đời product (chỉ `publish`/`unpublish` đổi status) và published invariants · required của variation attribute thỏa bằng variant options · định nghĩa "đang dùng" và các bất biến catalog · `option_key` + khóa hàng chống race · giữ dòng con khi soft delete, xóa cứng ảnh · chính sách ảnh
- [x] Mọi luật trong `PRODUCT.md` đều có mục tương ứng trong `DECISIONS.md` và ngược lại; nội dung khớp code đã merge, không mô tả tính năng chưa làm

**Verification:**
- [x] Đối chiếu từng luật với một test/route thật (danh sách đối chiếu ghi trong mô tả PR)
- [ ] Người dùng review văn phong, cấu trúc so với mẫu

**Dependencies:** Task 13 (nội dung phải khớp hành vi đã chạy được)
**Files likely touched:** `docs/product/PRODUCT.md`, `docs/product/DECISIONS.md`
**Estimated scope:** Small (2 file)

### Task 15: API contract catalog/product + README

**Description:** Tạo file API contract theo mẫu `D:\KLTN\vya-ocr-exp\docs\API_CONTRACT_EXTRACT.md` (tiếng Việt), tại `docs/API_CONTRACT_CATALOG.md`; cập nhật bảng endpoint trong `README.md` (yêu cầu của `AGENTS.md` khi contract đổi).

**Acceptance criteria:**
- [x] Mở đầu nêu đối tượng đọc (kỹ sư frontend/hệ khác), phạm vi "chỉ mô tả hợp đồng trên dây", và nguồn sự thật là code + `/api/v1/openapi.json`
- [x] Có mục Base URL & xác thực (Bearer, cách phân quyền: `catalog:manage` / `products:read` / `products:write`; ghi chú `catalog:manage` là tạm thời và sẽ đổi sang platform admin), envelope `BaseResponse` và định dạng lỗi `{error, message}`
- [x] Với mỗi nhóm endpoint (admin catalog, catalog read, products, variants, images): request (bảng trường: kiểu, bắt buộc, ghi chú), response theo từng hình dạng, bảng mã lỗi với `code` ổn định
- [x] Có ví dụ JSON thật cho: `GET /catalog/categories/{id}/attributes`, tạo Áo Polo với 6 variant, lỗi thiếu attribute `required` khi publish
- [x] Mục "Ghi chú cho hệ gọi": tenancy (shop lấy từ token), `404` cho product shop khác, giá là số nguyên VND, cách dựng form động từ metadata, không thể đổi tổ hợp option của variant
- [x] Contract ghi rõ hai body dễ nhầm: `PATCH /products/{product_id}` (`attributes` vắng = giữ nguyên, `[]` = xóa hết, danh sách = thay thế; không nhận `status`, `category_id`) và `PATCH /products/{product_id}/images/{image_id}` (`{ "position": integer }`, quy tắc reindex như Task 11), kèm ví dụ request/response
- [x] Bảng route trong contract khớp từng dòng với *Route map* trong `plan.md` và với `/api/v1/openapi.json` (method, path, quyền); mã lỗi `409/422` mới (`invalid_status_transition`, `product_invariant_violated`, `attribute_is_variation`, `last_active_variant`, `image_limit_reached`) đều có mô tả
- [x] Mọi ví dụ và mã lỗi đối chiếu được với OpenAPI/test; bảng endpoint `README.md` cập nhật

**Verification:**
- [x] So sánh contract với `/api/v1/openapi.json` xuất từ app đang chạy (không lệch đường dẫn/trường)
- [x] Ví dụ JSON khớp response thực từ test Task 13
- [ ] Người dùng review

**Dependencies:** Task 13 (Task 14 không bắt buộc, làm song song được)
**Files likely touched:** `docs/API_CONTRACT_CATALOG.md`, `README.md`
**Estimated scope:** Small (2 file)

### Checkpoint: Complete

- [x] Mọi tiêu chí Success trong `docs/intent/catalog.md` đạt
- [x] Ba tài liệu (`PRODUCT.md`, `DECISIONS.md`, `API_CONTRACT_CATALOG.md`) đã viết và khớp code
- [ ] Người dùng review và duyệt
