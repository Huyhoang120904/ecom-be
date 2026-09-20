# API Contract — Catalog & Product

**Đối tượng đọc:** kỹ sư ở repo khác (frontend seller, frontend quản trị, hệ gọi) cần tích hợp với
`ecom-be`. Tài liệu này chỉ mô tả **hợp đồng trên dây** (đường dẫn, request/response, mã lỗi, ngữ nghĩa
các trường) — không mô tả cách service implement bên trong. Luật của sản phẩm và lý do đằng sau nằm ở
`docs/product/PRODUCT.md` và `docs/product/DECISIONS.md`; các số hiệu `R…` dưới đây trỏ tới `PRODUCT.md`.

Nguồn sự thật của tài liệu này: mã trong `app/api/v1/catalog/`, `app/api/v1/products/`,
`app/schemas/catalog/`, `app/schemas/product/`, `app/errors/catalog.py`, và
`/api/v1/openapi.json` (sinh từ chính các schema đó). Khi code đổi mà tài liệu này chưa cập nhật, tin
theo code. OpenAPI mô tả **request và response thành công**; bảng mã lỗi ở § 7 là phần OpenAPI không
sinh ra.

## Base URL & xác thực

- Mọi đường dẫn nằm dưới `/api/v1`.
- Header bắt buộc trên **mọi** route trong tài liệu này, trừ đường xem ảnh (§ 6):
  `Authorization: Bearer <access_token>`. Token lấy từ `POST /api/v1/auth/login` (không thuộc tài liệu này).
  Thiếu, sai định dạng, hết hạn hay ký sai → `401 invalid_token`.
- Token mang **shop đang chọn** của người gọi. Mọi route sản phẩm, biến thể và ảnh làm việc trên shop đó;
  **không có** trường `shop_id` nào trong request (gửi vào là `422`).

## Phong bì chung

**Thành công có nội dung** — `200` hoặc `201` — luôn bọc trong một phong bì:

```json
{ "status_code": 200, "message": "Success", "data": { } }
```

`status_code` lặp lại mã HTTP; `data` luôn có mặt (danh sách rỗng là `[]`, không bao giờ `null`). **`204`
không có body** — mọi `DELETE` thành công đều `204`.

**Lỗi không bọc phong bì.** Mọi lỗi có đúng hình dạng này:

```json
{ "error": "<mã ổn định>", "message": "<câu cố định, an toàn>" }
```

`error` là mã máy đọc, ổn định, để rẽ nhánh; `message` là câu người đọc, **cố định theo mã** (không chứa dữ liệu
người dùng gửi). Đúng một lỗi có thêm trường `details`: `422 product_invariant_violated` (§ 3).

**`422 validation_error` là lỗi request cấp khung.** Body sai kiểu, thiếu trường, trường lạ, chuỗi quá dài, số
âm khi đòi ≥ 0, UUID sai định dạng trong đường dẫn — tất cả trả cùng một body, **không nói trường nào sai**:

```json
{ "error": "validation_error", "message": "Request validation failed" }
```

**`PATCH` một phần và `null`.** Ở `PATCH` của danh mục, tuỳ chọn và biến thể, một trường gửi `null` được coi
như **không gửi**. Chỉ có ba chỗ `null` mang nghĩa "xoá": `parent_id` của danh mục (về gốc), `brand_id` và
`description` của sản phẩm.

Mọi request body **cấm trường lạ** (`extra="forbid"`): gửi thừa một trường là `422`. Đây cũng là cách hợp đồng
từ chối `status` ở `PATCH` sản phẩm, `shop_id` ở mọi nơi, `options` ở `PATCH` biến thể.

## Quyền

| Nhóm route | Cần gì | Vai hiện có |
|---|---|---|
| `GET /catalog/**` | bất kỳ người đã đăng nhập | `owner`, `manager`, `viewer` |
| `POST/PUT/PATCH/DELETE /admin/catalog/**` | quyền `catalog:manage` | **chỉ `owner`** |
| `GET /products/**` | `products:read` | `owner`, `manager`, `viewer` |
| `POST/PATCH/DELETE /products/**` (gồm biến thể, ảnh, `publish`, `unpublish`) | `products:write` | `owner`, `manager` |

Thiếu quyền → `403 forbidden` (người gọi đã xác thực, thứ được hỏi tồn tại — chỉ là không được làm). Quyền
đọc từ cơ sở dữ liệu ở **mỗi** lần gọi: đổi vai có hiệu lực ngay, không đợi token hết hạn.

> **`catalog:manage` là chỗ tạm.** Nó là quyền *trong một shop*, nên mọi `owner` của mọi shop đều ghi được
> catalog chung. Phase sau sẽ đổi sang quản trị sàn (`users.is_platform_admin`); lúc đó các route
> `/admin/catalog/**` đổi điều kiện nhưng **đường dẫn và body giữ nguyên**. Xem `PRODUCT.md` › R5.

## Vòng đời sản phẩm

```
POST /products ──► draft ──publish──► active ◄──publish── inactive
                                        │                    ▲
                                        └────unpublish───────┘
```

- Sản phẩm luôn sinh ra ở `draft`. `PATCH` **không** đổi trạng thái; chỉ `publish` và `unpublish` đổi.
- `publish` (từ `draft` hoặc `inactive`) chạy đủ các điều kiện của một sản phẩm đang bán (§ 3) và có thể
  trả `422 product_invariant_violated`. Mọi chuyển trạng thái khác (`active → draft`, `publish` khi đã
  `active`, `unpublish` khi không `active`) trả `409 invalid_status_transition`.

---

## 1. Đọc catalog (mọi người đã đăng nhập)

Năm route để dựng form đăng sản phẩm. Frontend **không cần biết** ngành nào có thuộc tính gì: hỏi rồi vẽ.

| Method | Path | Trả về |
|---|---|---|
| `GET` | `/catalog/brands` | `BrandData[]`, xếp theo tên |
| `GET` | `/catalog/categories` | `CategoryTreeNode[]` — **cả cây**, lồng nhau |
| `GET` | `/catalog/categories/{category_id}` | `CategoryData` |
| `GET` | `/catalog/categories/{category_id}/attributes` | `CategoryAttributeData[]` — **thứ dựng form từ đó** |
| `GET` | `/catalog/attributes/{attribute_id}` | `AttributeData` (kèm tuỳ chọn) |

Sai `category_id`/`attribute_id` → `404 category_not_found` / `404 attribute_not_found`.

**`BrandData`**: `{ id, name, slug }`.

**`CategoryTreeNode`**: `{ id, name, slug, position, is_leaf, children: CategoryTreeNode[] }`. Mỗi cấp xếp
theo `position` rồi theo tên. **Chỉ danh mục `is_leaf: true` nhận được sản phẩm.**

**`CategoryData`**: `{ id, parent_id (null nếu là gốc), name, slug, position, is_leaf }`.

### `GET /catalog/categories/{category_id}/attributes`

Trả những thuộc tính mà danh mục này hỏi, theo thứ tự hiển thị. **Không kế thừa từ danh mục cha**: danh mục
nào khai gì thì trả đúng cái đó (R7). Mỗi phần tử là **một trường của form**:

| Trường | Kiểu | Ý nghĩa |
|---|---|---|
| `id` | uuid | Id **của thuộc tính** — thứ mà giá trị sản phẩm và tuỳ chọn biến thể trỏ tới |
| `key` | string | Mã máy ổn định, ví dụ `color`, `ram` |
| `name` | string | Nhãn hiển thị |
| `type` | `"TEXT" \| "NUMBER" \| "SELECT"` | Ô nhập gì: chữ / số / chọn trong danh sách |
| `required` | boolean | Bắt buộc **để sản phẩm được bán** (không phải để lưu nháp) |
| `filterable`, `searchable` | boolean | Metadata cho tìm kiếm phía người mua; hôm nay chưa tác động gì |
| `is_variation` | boolean | `true` → không nhập ở sản phẩm mà chọn **ở từng biến thể** (§ 4) |
| `position` | integer | Thứ tự hiển thị |
| `options` | `OptionData[]` | Đầy đủ khi `type = SELECT`, `[]` với `TEXT`/`NUMBER`. `OptionData = { id, value, sort_order }` |

```json
{
  "status_code": 200,
  "message": "Success",
  "data": [
    {
      "id": "330ba2e2-0f0f-4213-a737-1fd3b2b0e49c",
      "key": "size",
      "name": "Size",
      "type": "SELECT",
      "required": true,
      "filterable": false,
      "searchable": false,
      "is_variation": true,
      "position": 0,
      "options": [
        { "id": "b4e80c4c-d81a-40be-a467-a79f8e4e4a18", "value": "S", "sort_order": 0 },
        { "id": "370612d7-c500-4eef-87ac-66569831d610", "value": "M", "sort_order": 1 }
      ]
    },
    {
      "id": "74fcfda0-9761-4977-bd49-1d2439036194",
      "key": "material",
      "name": "Material",
      "type": "TEXT",
      "required": false,
      "filterable": false,
      "searchable": false,
      "is_variation": false,
      "position": 2,
      "options": []
    }
  ]
}
```

Cách vẽ form từ đây: thuộc tính `is_variation: false` là ô ở **sản phẩm**; thuộc tính `is_variation: true`
là **trục của bảng biến thể** (mỗi tổ hợp Color × Size là một dòng). `required: true` đánh dấu `*`.

---

## 2. Ghi catalog (`catalog:manage`)

Tất cả dưới `/admin/catalog`. Thêm một ngành hàng mới **chỉ cần các lời gọi này**, không migrate (R6).

### Thương hiệu

| Method | Path | Body | Thành công |
|---|---|---|---|
| `POST` | `/admin/catalog/brands` | `{ name }` | `201` `BrandData` |
| `PATCH` | `/admin/catalog/brands/{brand_id}` | `{ name }` | `200` `BrandData` |
| `DELETE` | `/admin/catalog/brands/{brand_id}` | — | `204` |

`name`: 1–120 ký tự, một dòng. Trùng tên (**không phân biệt hoa thường**) → `409 brand_exists`. `slug` sinh
một lần từ tên (`"Hoàng Gia"` → `hoang-gia`, đụng thì thêm `-2`) và **không đổi khi đổi tên** (R10). Xoá
thương hiệu còn sản phẩm (kể cả sản phẩm đã xoá) → `409 brand_in_use`.

### Danh mục

| Method | Path | Body | Thành công |
|---|---|---|---|
| `POST` | `/admin/catalog/categories` | `{ name, parent_id?, position? }` | `201` `CategoryData` |
| `PATCH` | `/admin/catalog/categories/{category_id}` | `{ name?, parent_id?, position? }` | `200` `CategoryData` |
| `DELETE` | `/admin/catalog/categories/{category_id}` | — | `204` |

`name` 1–120 ký tự; `position` 0–100000 (mặc định 0); `parent_id` bỏ qua hoặc `null` = danh mục gốc.

**`PATCH` phân biệt "vắng" với `null`** ở `parent_id`: **không gửi** = giữ cha; **`null`** = chuyển về gốc;
**một uuid** = chuyển dưới danh mục đó. `name` và `position` gửi `null` thì bị bỏ qua như không gửi.

| Lỗi | Khi nào |
|---|---|
| `404 category_not_found` | danh mục (hoặc `parent_id`) không tồn tại |
| `422 category_cycle` | đặt cha là chính nó hoặc hậu duệ của nó |
| `422 category_too_deep` | cây sâu quá 6 tầng (tính cả nhánh con đang chuyển theo) |
| `409 category_has_products` | thêm con / chuyển vào / xoá một danh mục **đang có sản phẩm** (R12) |
| `409 category_has_children` | xoá danh mục còn con |

### Thuộc tính và tuỳ chọn

| Method | Path | Body | Thành công |
|---|---|---|---|
| `POST` | `/admin/catalog/attributes` | `{ key, name, data_type }` | `201` `AttributeData` |
| `PATCH` | `/admin/catalog/attributes/{attribute_id}` | `{ name }` | `200` `AttributeData` |
| `DELETE` | `/admin/catalog/attributes/{attribute_id}` | — | `204` |
| `POST` | `/admin/catalog/attributes/{attribute_id}/options` | `{ value, sort_order? }` | `201` `OptionData` |
| `PATCH` | `/admin/catalog/attributes/{attribute_id}/options/{option_id}` | `{ value?, sort_order? }` | `200` `OptionData` |
| `DELETE` | `/admin/catalog/attributes/{attribute_id}/options/{option_id}` | — | `204` |

`key`: chữ thường, số và `_`, bắt đầu bằng chữ, 2–64 ký tự (`^[a-z][a-z0-9_]*$`). `name`: 1–80 ký tự.
`data_type`: `TEXT` \| `NUMBER` \| `SELECT`. **`key` và `data_type` không đổi được** — `PATCH` thuộc tính chỉ nhận
`name`, gửi `key` hay `data_type` là `422` (R8). `value` của tuỳ chọn 1–120 ký tự; `sort_order` bỏ qua thì
tuỳ chọn xếp cuối.

| Lỗi | Khi nào |
|---|---|
| `409 attribute_exists` | `key` đã có |
| `409 attribute_attached` | xoá thuộc tính còn gắn vào một danh mục — gỡ trước |
| `409 attribute_in_use` | xoá thuộc tính đang được sản phẩm dùng |
| `422 options_require_select` | tạo tuỳ chọn cho thuộc tính không phải `SELECT` |
| `409 option_exists` | trùng `value` **trong cùng thuộc tính** (cùng giá trị ở thuộc tính khác thì được) |
| `404 option_not_found` | tuỳ chọn không tồn tại **hoặc thuộc thuộc tính khác** |
| `409 option_in_use` | xoá tuỳ chọn đang được sản phẩm hoặc biến thể dùng |

"Đang dùng" tính **cả sản phẩm và biến thể đã xoá** (R11).

### Cấu hình thuộc tính của danh mục

| Method | Path | Body | Thành công |
|---|---|---|---|
| `PUT` | `/admin/catalog/categories/{category_id}/attributes/{attribute_id}` | `CategoryAttributeRequest` | `200` `CategoryAttributeData` |
| `DELETE` | `/admin/catalog/categories/{category_id}/attributes/{attribute_id}` | — | `204` |

**`PUT` là gắn *hoặc* thay cờ**, idempotent, và **thay hết**: cờ không gửi về `false`, `position` về `0`.
`CategoryAttributeRequest` = `{ required = false, filterable = false, searchable = false, is_variation = false,
position = 0 }`.

| Lỗi | Khi nào |
|---|---|
| `404 category_not_found` / `404 attribute_not_found` | id không tồn tại |
| `422 variation_requires_select` | `is_variation: true` cho thuộc tính không phải `SELECT` |
| `409 variation_flag_locked` | đổi `is_variation` khi **trong danh mục này** đã có sản phẩm dùng thuộc tính |
| `404 category_attribute_not_found` | `DELETE` một thuộc tính chưa từng gắn |
| `409 attribute_detach_locked` | gỡ thuộc tính mà sản phẩm **của danh mục này** đang dùng |

Đổi `required`, `filterable`, `searchable` **luôn được**, và gắn thêm thuộc tính vào danh mục đã có sản phẩm
cũng được. Đổi `required` **không hồi tố**: sản phẩm đang bán giữ nguyên (xem "Sản phẩm cũ" ở § 3).

---

## 3. Sản phẩm

Mọi route làm việc trên **shop trong token**. Sản phẩm của shop khác trả **`404 product_not_found`** ở mọi
route, kể cả `publish` (R3).

| Method | Path | Quyền | Thành công |
|---|---|---|---|
| `POST` | `/products` | write | `201` `ProductData` |
| `GET` | `/products` | read | `200` `ProductPage` |
| `GET` | `/products/{product_id}` | read | `200` `ProductData` |
| `PATCH` | `/products/{product_id}` | write | `200` `ProductData` |
| `DELETE` | `/products/{product_id}` | write | `204` |
| `POST` | `/products/{product_id}/publish` | write | `200` `ProductData` |
| `POST` | `/products/{product_id}/unpublish` | write | `200` `ProductData` |

### `POST /products`

| Trường | Kiểu | Bắt buộc | Ghi chú |
|---|---|---|---|
| `category_id` | uuid | Có | Phải là danh mục **lá** (`is_leaf: true`). **Không đổi được sau khi tạo.** |
| `name` | string | Có | 2–200 ký tự, một dòng |
| `brand_id` | uuid \| null | Không | Phải tồn tại |
| `description` | string \| null | Không | Tối đa 5000 ký tự, cho xuống dòng |
| `attributes` | `AttributeValueRequest[]` | Không | Tối đa 100. Chỉ thuộc tính **không phải biến thể** |

Không có `status`: sản phẩm **luôn** sinh ra ở `draft`.

**`AttributeValueRequest`** — đúng **một** trong ba trường giá trị, và đúng cái mà `type` của thuộc tính đòi:

| Trường | Kiểu | Dùng cho |
|---|---|---|
| `attribute_id` | uuid | (luôn có) |
| `option_id` | uuid | thuộc tính `SELECT` — phải là tuỳ chọn của **chính** thuộc tính đó |
| `value_text` | string (≤ 500, không rỗng) | thuộc tính `TEXT` |
| `value_number` | number (|x| < 10¹⁴, không NaN/∞) | thuộc tính `NUMBER` |

| Lỗi | Khi nào |
|---|---|
| `404 category_not_found` / `404 brand_not_found` | id không tồn tại |
| `422 category_not_leaf` | danh mục còn con |
| `422 attribute_not_in_category` | thuộc tính không được cấu hình cho danh mục này |
| `422 attribute_is_variation` | gửi giá trị cho một **thuộc tính biến thể** — nó thuộc về biến thể (R15) |
| `422 invalid_attribute_value` | sai loại, hai trường cùng lúc, chuỗi rỗng, tuỳ chọn của thuộc tính khác |
| `422 duplicate_attribute_value` | một thuộc tính xuất hiện hai lần |

### `PATCH /products/{product_id}`

`{ name?, description?, brand_id?, attributes? }` — mọi trường tuỳ chọn. **Không** nhận `status`,
`category_id`, `shop_id` (gửi vào là `422`).

- `description` và `brand_id` nhận `null` để **xoá**; không gửi = giữ nguyên. `name` không nhận `null`.
- **`attributes`** có ba nghĩa: **không gửi** → giữ nguyên tập giá trị; **`[]`** → xoá hết; **một danh sách** →
  **thay cả tập bằng danh sách đó** (không gộp). `attributes: null` là `422`.
- Sản phẩm **đang `active`** phải vẫn thoả các điều kiện bán sau khi sửa; nếu không, `422
  product_invariant_violated` và **không có gì bị đổi**.

### `GET /products`

Query: `status` (`draft` \| `active` \| `inactive`, bỏ qua = tất cả), `page` (≥ 1, mặc định 1), `page_size` (1–100,
mặc định 20). Xếp mới nhất trước. Sản phẩm đã xoá không bao giờ có mặt. Ngoài khoảng → `422`.

```json
{
  "status_code": 200,
  "message": "Success",
  "data": {
    "items": [
      {
        "id": "99697b88-c471-4828-8e54-4bc393c9c3de",
        "category_id": "57066243-85db-48b2-af2f-1c76fdae31c9",
        "brand_id": "43603426-047f-4a6a-b803-a4ffca13d446",
        "name": "Áo Polo Nike",
        "status": "draft",
        "created_at": "2026-09-20T09:20:41.558220Z",
        "updated_at": "2026-09-20T09:20:41.558220Z"
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20
  }
}
```

### `ProductData` — một sản phẩm và mọi thứ treo trên nó

| Trường | Kiểu | Ý nghĩa |
|---|---|---|
| `id`, `category_id`, `brand_id` | uuid (`brand_id` có thể `null`) | |
| `name`, `description` | string (`description` có thể `null`) | |
| `status` | `"draft" \| "active" \| "inactive"` | |
| `created_at`, `updated_at` | date-time (UTC) | |
| `attributes` | `ProductAttributeData[]` | giá trị thuộc tính **không phải biến thể**, xếp theo tên thuộc tính |
| `variants` | `VariantData[]` | biến thể còn sống (§ 4), kèm ảnh của từng biến thể |
| `images` | `ImageData[]` | chỉ ảnh **chung** của sản phẩm (`variant_id: null`) |

**`ProductAttributeData`**: `{ attribute_id, name, type, option_id, option_value, value_text, value_number }` —
đúng một trong `option_id` (kèm `option_value`), `value_text`, `value_number` khác `null`, khớp `type`.

### `POST /products/{product_id}/publish`

Đưa sản phẩm lên `active` khi nó thoả **cả bốn điều**:

1. mọi thuộc tính `required` **không phải biến thể** có giá trị ở sản phẩm;
2. mọi thuộc tính `required` **là biến thể** có mặt ở **mọi** biến thể còn sống (kể cả biến thể `inactive`);
3. có ít nhất một biến thể `active`;
4. mọi biến thể dùng **cùng một tập** thuộc tính biến thể.

Không thoả → **`422 product_invariant_violated`** và sản phẩm không đổi. Đây là lỗi duy nhất có `details`:

```json
{
  "error": "product_invariant_violated",
  "message": "The product does not meet the requirements to be active",
  "details": {
    "missing": [
      { "attribute_id": "c23d675a-aefd-40d2-b92d-43d5db2adbb3", "name": "CPU", "where": "product" }
    ],
    "reasons": []
  }
}
```

- `missing[]`: mỗi phần tử là một thuộc tính còn thiếu. `where`: `"product"` (thiếu giá trị ở sản phẩm) hoặc
  `"variants"` (một số biến thể thiếu tuỳ chọn cho thuộc tính này).
- `reasons[]`: các nguyên nhân không gắn với một thuộc tính — `"no_active_variant"` (điều 3),
  `"inconsistent_variation_attributes"` (điều 4). Có thể vừa có `missing` vừa có `reasons`.

Hai mảng luôn có mặt (có thể rỗng); chúng được dựng từ id và tên trong cơ sở dữ liệu, không từ dữ liệu
request. Frontend dùng `attribute_id` để chỉ đúng ô còn thiếu.

### `POST /products/{product_id}/unpublish`

`active` → `inactive`, luôn được khi đang `active`. Mọi trạng thái khác → `409 invalid_status_transition`.

### `DELETE /products/{product_id}`

`204`. **Xoá mềm**: sản phẩm và mọi biến thể của nó biến khỏi API; ảnh bị xoá hẳn; `sku_code` được giải phóng.
Sản phẩm đã xoá trả `404` ở mọi route.

### Sản phẩm cũ (stale)

Khi quản trị viên thêm một thuộc tính `required` vào danh mục, sản phẩm **đang `active`** của danh mục đó
**vẫn `active`** — hệ thống không tự gỡ (R16). Lần `PATCH` (hoặc thao tác biến thể) kế tiếp trên sản phẩm đó
trả `422 product_invariant_violated` với `details.missing` chỉ thuộc tính mới; sản phẩm được chấp nhận lại khi
đã bổ sung. Hệ gọi nên coi `422` này ở sản phẩm đang bán là lời mời *bổ sung*, không phải lỗi hỏng.

---

## 4. Biến thể (SKU)

Biến thể là **một tổ hợp tuỳ chọn** của các thuộc tính `is_variation` của danh mục — Đen / S, hay RAM 16GB
/ Ổ 512GB — kèm giá và tồn (R18). Mỗi sản phẩm không có thuộc tính biến thể có **đúng một** biến thể không có tuỳ
chọn.

| Method | Path | Quyền | Thành công |
|---|---|---|---|
| `POST` | `/products/{product_id}/variants` | write | `201` `VariantData` |
| `GET` | `/products/{product_id}/variants` | read | `200` `VariantData[]` (xếp theo lúc tạo) |
| `GET` | `/products/{product_id}/variants/{variant_id}` | read | `200` `VariantData` |
| `PATCH` | `/products/{product_id}/variants/{variant_id}` | write | `200` `VariantData` |
| `DELETE` | `/products/{product_id}/variants/{variant_id}` | write | `204` |

### `POST` — tạo biến thể

| Trường | Kiểu | Bắt buộc | Ghi chú |
|---|---|---|---|
| `sku_code` | string | Có | 1–64 ký tự. **Duy nhất trong shop** |
| `price` | integer | Có | `0…10¹²`, đơn vị nhỏ nhất của VND (`300000` = 300.000 ₫) |
| `stock` | integer | Không | `0…10⁹`, mặc định `0` |
| `status` | `"active" \| "inactive"` | Không | mặc định `active` |
| `options` | `{ attribute_id, option_id }[]` | Không | tối đa 5; rỗng cho sản phẩm không có thuộc tính biến thể |

Ví dụ — biến thể **Đen / S** của Áo Polo Nike:

```json
{
  "sku_code": "POLO-BLACK-S",
  "price": 300000,
  "stock": 10,
  "options": [
    { "attribute_id": "6a055647-cef5-410c-9fd1-761b5de1e9f4", "option_id": "ff10e372-d79c-40b3-a9fd-0f2ef43ae1e7" },
    { "attribute_id": "330ba2e2-0f0f-4213-a737-1fd3b2b0e49c", "option_id": "b4e80c4c-d81a-40be-a467-a79f8e4e4a18" }
  ]
}
```

Trả `201`:

```json
{
  "status_code": 201,
  "message": "Success",
  "data": {
    "id": "1ed11d9b-39ac-4e57-b973-172a54cce7d5",
    "product_id": "99697b88-c471-4828-8e54-4bc393c9c3de",
    "sku_code": "POLO-BLACK-S",
    "price": 300000,
    "stock": 10,
    "status": "active",
    "options": [
      { "attribute_id": "6a055647-cef5-410c-9fd1-761b5de1e9f4", "attribute_name": "Color",
        "option_id": "ff10e372-d79c-40b3-a9fd-0f2ef43ae1e7", "option_value": "Black" },
      { "attribute_id": "330ba2e2-0f0f-4213-a737-1fd3b2b0e49c", "attribute_name": "Size",
        "option_id": "b4e80c4c-d81a-40be-a467-a79f8e4e4a18", "option_value": "S" }
    ],
    "images": []
  }
}
```

**Một sản phẩm, sáu biến thể.** Áo Polo với Color {Black, White} × Size {S, M, L} là **sáu lời gọi `POST`**, mỗi
lời một tổ hợp:

| `sku_code` | Color | Size | `price` |
|---|---|---|---|
| `POLO-BLACK-S` | Black | S | 300000 |
| `POLO-BLACK-M` | Black | M | 300000 |
| `POLO-BLACK-L` | Black | L | 320000 |
| `POLO-WHITE-S` | White | S | 300000 |
| `POLO-WHITE-M` | White | M | 300000 |
| `POLO-WHITE-L` | White | L | 320000 |

`GET /products/{product_id}` sau đó trả `variants` gồm đủ sáu, mỗi phần tử có hình như ví dụ trên.

**`VariantData`**: `{ id, product_id, sku_code, price, stock, status, options: VariantOptionData[], images:
ImageData[] }`, với `VariantOptionData = { attribute_id, attribute_name, option_id, option_value }`.

| Lỗi | Khi nào |
|---|---|
| `404 product_not_found` | sản phẩm không tồn tại hoặc thuộc shop khác |
| `422 variant_option_invalid` | thuộc tính không phải biến thể của danh mục, không thuộc danh mục, tuỳ chọn của thuộc tính khác, hoặc một thuộc tính hai lần |
| `422 variation_set_inconsistent` | tập thuộc tính khác với các biến thể đã có của sản phẩm |
| `409 variant_combination_exists` | **tổ hợp đã có** (thứ tự `options` không quan trọng) — hoặc, với sản phẩm không có thuộc tính biến thể, đã có biến thể thứ nhất |
| `409 sku_exists` | `sku_code` đã dùng **trong shop** (shop khác dùng cùng mã thì được) |
| `422 product_invariant_violated` | sản phẩm đang `active` mà biến thể mới làm nó vi phạm điều kiện bán |

Hai yêu cầu đồng thời tạo cùng một tổ hợp hay cùng một `sku_code`: **đúng một** thắng, cái kia nhận `409` tương
ứng (R20).

### `PATCH` — sửa biến thể

`{ sku_code?, price?, stock?, status? }` — mọi trường tuỳ chọn.

- **`options` không sửa được** và gửi vào là `422`. Muốn đổi tổ hợp: `DELETE` rồi `POST` lại.
- **`stock` được đặt, không cộng dồn**: `{ "stock": 4 }` nghĩa là "còn 4", gửi hai lần vẫn là 4.
- Trùng `sku_code` → `409 sku_exists`.
- `status: "inactive"` trên **biến thể `active` cuối cùng của sản phẩm đang `active`** → `409
  last_active_variant`.

### `DELETE`

`204`, **xoá mềm**; tuỳ chọn của biến thể được giữ, ảnh của biến thể xoá hẳn, `sku_code` và tổ hợp được giải
phóng (tạo lại được đúng biến thể đó). Xoá **biến thể `active` cuối cùng của sản phẩm đang `active`** → `409
last_active_variant`; `unpublish` trước, hoặc thêm biến thể khác rồi mới xoá.

---

## 5. Ảnh

Ảnh thuộc **sản phẩm** (ảnh chung, `variant_id: null`) hoặc **một biến thể**. Mỗi phạm vi có thứ tự riêng.

| Method | Path | Quyền | Thành công |
|---|---|---|---|
| `POST` | `/products/{product_id}/images` | write | `201` `ImageData` |
| `PATCH` | `/products/{product_id}/images/{image_id}` | write | `200` `ImageData[]` (cả phạm vi, theo thứ tự mới) |
| `DELETE` | `/products/{product_id}/images/{image_id}` | write | `204` |

**`ImageData`**: `{ id, variant_id (null với ảnh chung), position, url }`. `position` luôn là `0..n-1` liên tục
trong phạm vi của ảnh. `url` là địa chỉ tuyệt đối để đặt thẳng vào `<img>` (§ 6); chuỗi `?v=` đổi khi nội dung
ảnh đổi, nên trình duyệt cache được lâu.

### `POST` — tải ảnh lên

`multipart/form-data`:

| Trường | Kiểu | Bắt buộc | Ghi chú |
|---|---|---|---|
| `file` | file | Có | `image/jpeg`, `image/png` hoặc `image/webp`. **Nhãn khai báo phải khớp nội dung thật** |
| `variant_id` | uuid | Không | Bỏ qua = ảnh chung. Phải là biến thể còn sống của **chính sản phẩm này** |

Ảnh được **chuẩn hoá**: lưu `WEBP`, bỏ siêu dữ liệu, **không cắt**, **thu nhỏ vừa khung 1600 × 1600 giữ tỉ lệ** và
**không bao giờ phóng to** (ảnh nhỏ hơn khung giữ nguyên kích thước). Ảnh mới được thêm **vào cuối** phạm vi.

```bash
curl -X POST http://<host>/api/v1/products/<product_id>/images \
  -H "Authorization: Bearer <token>" \
  -F "file=@black-front.png;type=image/png" \
  -F "variant_id=<variant_id>"
```

```json
{
  "status_code": 201,
  "message": "Success",
  "data": {
    "id": "67dc5ed8-a2ab-4e30-9f45-67c13095404a",
    "variant_id": "de40432d-d476-4e07-b812-594bcc61ba26",
    "position": 0,
    "url": "http://<host>/api/v1/media/product-image/67dc5ed8-a2ab-4e30-9f45-67c13095404a.webp?v=aaadc43867cd3bb6565b4779947c25077f72cf9e5a132013df1aa253e3df9e9d"
  }
}
```

| Lỗi | Khi nào |
|---|---|
| `415 unsupported_image` | không phải JPEG/PNG/WebP, hỏng, hoặc nhãn không khớp nội dung |
| `413 image_too_large` | vượt dung lượng tối đa của cấu hình, hoặc cạnh dài hơn 4096 điểm, hoặc cạnh ngắn dưới 32 điểm |
| `409 image_limit_reached` | phạm vi đã đủ: **9** ảnh chung cho mỗi sản phẩm, **5** ảnh cho mỗi biến thể |
| `422 image_variant_invalid` | `variant_id` không tồn tại, đã xoá, hoặc thuộc sản phẩm khác |
| `429 rate_limited` | quá **30** lượt tải lên trong một giờ từ một địa chỉ khách (cùng hạn mức với ảnh đại diện) |

### `PATCH` — đổi thứ tự

Body **chỉ** `{ "position": integer }`; trường khác → `422`. `position` là chỉ số đích `0…n-1` **trong cùng phạm
vi** (ảnh chung, hoặc ảnh của cùng một biến thể). Ảnh được chèn vào đó; các ảnh còn lại dịch chỗ để dãy vẫn
liên tục và không trùng. Ngoài khoảng → `422 invalid_image_position`. Không đổi được `variant_id` của một
ảnh đã có: xoá rồi tải lại.

Ví dụ: hai ảnh của một biến thể, đưa ảnh thứ hai lên đầu (`{ "position": 0 }`) trả cả phạm vi theo thứ tự mới:

```json
{
  "status_code": 200,
  "message": "Success",
  "data": [
    { "id": "2b2a07ea-a41d-47c1-a3e8-68031f579ce7", "variant_id": "de40432d-d476-4e07-b812-594bcc61ba26", "position": 0, "url": "…" },
    { "id": "67dc5ed8-a2ab-4e30-9f45-67c13095404a", "variant_id": "de40432d-d476-4e07-b812-594bcc61ba26", "position": 1, "url": "…" }
  ]
}
```

### `DELETE`

`204`, xoá cứng dòng ảnh và dồn lại dãy vị trí của phạm vi. Tệp trong kho được xoá sau đó, ở mức cố gắng hết
sức. Ảnh không tồn tại, hoặc thuộc sản phẩm khác, → `404 product_image_not_found`.

---

## 6. Xem ảnh

`GET /api/v1/media/product-image/{image_id}.webp` — **công khai, không cần token**, vì ảnh sản phẩm sinh ra để
được xem (R26).

- `200` `image/webp`, kèm `ETag` và `Cache-Control: public, max-age=31536000, immutable`. Gửi `If-None-Match`
  khớp `ETag` → `304`.
- `404 not_found` khi ảnh không tồn tại hoặc đã bị xoá.

Frontend không cần tự dựng đường dẫn này: dùng nguyên `url` mà `ImageData` trả về.

---

## 7. Bảng mã lỗi

Mọi lỗi có dạng `{ "error", "message" }`. Rẽ nhánh theo **`error`**, không theo `message`.

**Chung (xác thực, quyền, khung request):**

| HTTP | `error` | Khi nào |
|---|---|---|
| `401` | `invalid_token` | thiếu/sai/hết hạn token |
| `401` | `account_inactive` | tài khoản bị vô hiệu |
| `401` | `shop_not_accessible` | shop đang chọn không còn dùng được |
| `403` | `forbidden` | thiếu quyền của route |
| `422` | `validation_error` | request sai khung (xem "Phong bì chung") |
| `429` | `rate_limited` | tải ảnh quá hạn mức |

**Catalog:**

| HTTP | `error` | Khi nào |
|---|---|---|
| `404` | `brand_not_found` · `category_not_found` · `attribute_not_found` · `option_not_found` · `category_attribute_not_found` | không có / không thuộc cha |
| `409` | `brand_exists` · `attribute_exists` · `option_exists` | trùng khoá duy nhất |
| `409` | `brand_in_use` · `attribute_attached` · `attribute_in_use` · `option_in_use` | xoá thứ còn được tham chiếu |
| `409` | `category_has_children` · `category_has_products` | thay đổi cấu trúc cây vi phạm "chỉ lá mới nhận sản phẩm" |
| `409` | `variation_flag_locked` · `attribute_detach_locked` | đổi/gỡ cấu hình thuộc tính khi sản phẩm của danh mục đang dùng |
| `422` | `category_cycle` · `category_too_deep` | cây sai cấu trúc |
| `422` | `options_require_select` · `variation_requires_select` | dùng tuỳ chọn / biến thể với thuộc tính không phải `SELECT` |

**Sản phẩm, biến thể, ảnh:**

| HTTP | `error` | Khi nào |
|---|---|---|
| `404` | `product_not_found` · `variant_not_found` · `product_image_not_found` | không có, đã xoá, hoặc thuộc shop khác |
| `409` | `invalid_status_transition` | `publish`/`unpublish` từ trạng thái không cho phép |
| `409` | `variant_combination_exists` · `sku_exists` | trùng tổ hợp / `sku_code` |
| `409` | `last_active_variant` | tắt hay xoá biến thể `active` cuối của sản phẩm đang bán |
| `409` | `image_limit_reached` | quá 9 ảnh chung / 5 ảnh mỗi biến thể |
| `422` | `category_not_leaf` | tạo sản phẩm ở danh mục còn con |
| `422` | `attribute_not_in_category` · `attribute_is_variation` · `invalid_attribute_value` · `duplicate_attribute_value` | giá trị thuộc tính sai |
| `422` | `variant_option_invalid` · `variation_set_inconsistent` | tuỳ chọn biến thể sai |
| `422` | `product_invariant_violated` | sản phẩm không thoả điều kiện bán — **có `details`** |
| `422` | `invalid_image_position` · `image_variant_invalid` | vị trí ngoài khoảng / biến thể không thuộc sản phẩm |
| `413` · `415` | `image_too_large` · `unsupported_image` | ảnh không đạt |

---

## 8. Ghi chú vận hành hệ gọi cần biết

- **Shop luôn lấy từ token, không từ request.** Không có `shop_id` để gửi. Người có nhiều shop dùng chức năng
  đổi shop ở identity để lấy token của shop khác.
- **`404` cho sản phẩm của shop khác**, không phải `403`: đừng dựa vào `403` để biết một id có tồn tại.
- **Giá là số nguyên**, đơn vị nhỏ nhất của VND, không có tiền tệ nào khác. `price` là `int`, không phải chuỗi
  hay số thực.
- **`stock` là "đặt", không "cộng".** Gửi lại cùng một `PATCH` là an toàn. **Chưa có kho hàng và chưa có giữ hàng**
  ở phase này — chỉ một số tồn trên mỗi biến thể.
- **Đổi tổ hợp của biến thể = xoá rồi tạo lại**; `PATCH` biến thể không nhận `options`.
- **Lưu nháp không bị chặn, bán mới bị chặn.** `POST`/`PATCH` sản phẩm `draft` chấp nhận thiếu thuộc tính
  bắt buộc; chỉ `publish` (và sửa sản phẩm đang bán) đòi đủ. Dùng `details.missing[].attribute_id` để đánh dấu ô
  còn thiếu.
- **Thuộc tính biến thể không nhập ở sản phẩm.** `422 attribute_is_variation` nếu gửi. Chúng là trục của bảng biến
  thể (§ 1).
- **`is_leaf` quyết định danh mục có chọn được không**: chỉ danh mục lá nhận sản phẩm.
- **Danh mục của sản phẩm không đổi** sau khi tạo; muốn đổi thì tạo sản phẩm mới.
- **Xoá là xoá mềm** cho sản phẩm và biến thể (không khôi phục qua API), và xoá cứng cho ảnh. Catalog chỉ xoá
  được khi chưa ai dùng — kể cả sản phẩm đã xoá.
- **Phân trang chỉ có ở `GET /products`.** Danh sách biến thể, thương hiệu, cây danh mục trả **toàn bộ**.
- **Không có tìm kiếm, lọc theo thuộc tính, hay duyệt phía người mua.** Cờ `filterable`/`searchable` chỉ là
  metadata cho đợt sau.
- **Contract này thay đổi khi catalog chuyển sang quản trị sàn** (`catalog:manage` → `users.is_platform_admin`):
  điều kiện quyền đổi, đường dẫn và body của `/admin/catalog/**` không đổi.
