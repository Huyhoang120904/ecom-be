# ecom — luật của sản phẩm

**Sản phẩm này là gì:** một **sàn thương mại điện tử nhiều shop**. Ai cũng đăng ký được một gian hàng và
tự đăng hàng lên bán; người mua duyệt và mua hàng của nhiều shop ở cùng một nơi. Sàn giữ những luật chung
— ai là ai, ai được sửa gì, hàng nào được bán, catalog dùng chung — còn mỗi shop giữ hàng, giá và tồn của
riêng mình.

**File này là gì:** những điều luôn đúng về cả sàn — ai dùng, dữ liệu gồm những gì, cái gì quyết cái gì, và
cái gì cố ý không làm. Cùng với `DECISIONS.md`, đây là toàn bộ tài liệu sản phẩm. Hợp đồng trên dây của
catalog và sản phẩm nằm ở `docs/API_CONTRACT_CATALOG.md`.

**Hôm nay đã làm tới đâu.** File này mô tả cả sàn, nhưng **mã mới phủ phần người bán**: tài khoản, shop,
catalog và sản phẩm. Phần người mua mua hàng **chưa có mã**. Mỗi luật dưới đây đều đang đúng trong mã, trừ
chỗ ghi rõ là *định hướng*; bảng này nói phần nào đã có:

| Phần của sàn | Hôm nay |
|---|---|
| Tài khoản, phiên đăng nhập, shop, thành viên và quyền | **Đã có** (M1–M10) |
| Catalog dùng chung (danh mục, thuộc tính, tuỳ chọn, thương hiệu) | **Đã có** (R5–R12) |
| Sản phẩm, biến thể (SKU), giá, tồn (một số), ảnh | **Đã có** (R1–R4, R13–R28) |
| Quản trị sàn | **Chưa có**; tạm dùng quyền `catalog:manage` (R5) |
| Tài khoản người mua | **Chưa có**: đăng ký hôm nay luôn tạo kèm một shop (M1) |
| Duyệt, tìm kiếm, xem sản phẩm phía người mua | Chưa có |
| Giỏ hàng, đơn hàng, thanh toán, giao nhận | Chưa có |
| Kho hàng, giữ hàng | Chưa có (R27) |
| Kiểm duyệt shop hay sản phẩm, đánh giá, khuyến mãi, hoàn trả | Chưa có |

**Nguồn nghiệp vụ:** mô tả thiết kế marketplace ban đầu (User → Shop → Product → SKU, thuộc tính theo danh
mục, biến thể động, tồn kho theo SKU) · ý định đã chốt ở `docs/intent/catalog.md` · kế hoạch và các quyết
định kiến trúc ở `changes/20-09-2026-CatalogAndProduct/plan.md`.

**Lý do đằng sau từng luật** nằm ở `DECISIONS.md`, kèm những hướng đã cân rồi loại. Luật của tài khoản, shop
và thành viên đánh số `M1…M10`; luật của catalog và sản phẩm đánh số `R1…R28`. Mỗi mục của `DECISIONS.md`
ghi nó giải thích những luật nào.

## Actors

- **Người mua** — người duyệt và mua hàng của nhiều shop. **Là actor của sản phẩm nhưng chưa có mã**: chưa
  có tài khoản người mua, chưa có đường công khai để xem hàng, chưa có giỏ hay đơn (xem bảng ở đầu file).
- **Chủ shop (`owner`)** — người đăng ký gian hàng và giữ mọi quyền trong đó: sửa hồ sơ shop, mời và quản lý
  thành viên, xoá shop, đăng và sửa sản phẩm. **Hôm nay cũng là người ghi được catalog chung** (R5); đó là chỗ
  tạm.
- **Quản lý shop (`manager`)** — làm việc hằng ngày của shop: đọc và ghi sản phẩm, đơn. Không sửa hồ sơ shop,
  không quản lý thành viên, không ghi catalog.
- **Người xem (`viewer`)** — chỉ đọc trong shop.
- **Quản trị sàn** — người cấu hình catalog dùng chung và giữ luật chung của sàn. **Chưa có như một actor
  riêng**: hôm nay việc ghi catalog do `owner` của bất kỳ shop nào làm (R5) và sẽ chuyển cho quản trị sàn
  trước khi có người ngoài đăng ký shop.
- **Người vận hành** — tạm ngưng hoặc mở lại một shop mà không xoá nó (M4). Hôm nay đó là thao tác nội bộ, chưa
  có API.
- **Frontend / hệ gọi** — dựng giao diện người bán (form đăng sản phẩm dựng từ metadata của ngành hàng) và, về
  sau, giao diện người mua. Nó không thuộc repo này.
- **System** — kiểm các điều kiện để một sản phẩm được bán (R14), và giữ các ràng buộc chéo bảng ở tầng cơ sở
  dữ liệu (R28); không ai can thiệp giữa chừng.

## Objects

| Object | Owned by | States |
|---|---|---|
| Tài khoản (account) | Chính người dùng | đang dùng · **vô hiệu hoá** (giữ email, một chiều) · xoá mềm (nhả email) |
| Shop (gian hàng) | Các thành viên của nó | đang dùng · **tạm ngưng** bởi vận hành · đã xoá (mềm) |
| Thành viên (membership) | Shop | nối một tài khoản với một shop và **một vai**; còn · đã thu hồi |
| Vai (role) | Hệ thống | `owner` · `manager` · `viewer`; mỗi vai là một tập quyền |
| Phiên (session) | Tài khoản | gắn với **một** shop đang chọn; token truy cập ngắn hạn cùng một token làm mới |
| Thương hiệu (brand) | Catalog dùng chung | có · không còn (chỉ xoá được khi chưa product nào tham chiếu) |
| Danh mục (category) | Catalog dùng chung | **lá** (chưa có con, nhận được sản phẩm) · **không phải lá** (có con, không nhận sản phẩm) |
| Thuộc tính (attribute) | Catalog dùng chung | có một `data_type` cố định: `TEXT` · `NUMBER` · `SELECT` |
| Tuỳ chọn (option) | thuộc một thuộc tính `SELECT` | có · không còn (chỉ xoá được khi chưa ai dùng) |
| Cấu hình thuộc tính của danh mục | Catalog dùng chung | một thuộc tính gắn vào một danh mục kèm cờ `required` · `filterable` · `searchable` · `is_variation` |
| Sản phẩm (product) | **Shop** | `draft` → `active` ⇄ `inactive`; xoá mềm |
| Giá trị thuộc tính của sản phẩm | thuộc sản phẩm | một dòng cho mỗi (sản phẩm, thuộc tính không phải biến thể) |
| Biến thể / SKU (variant) | thuộc sản phẩm | `active` ⇄ `inactive`; xoá mềm |
| Tuỳ chọn của biến thể | thuộc biến thể | bất biến từ lúc biến thể được tạo |
| Ảnh (image) | thuộc sản phẩm hoặc một biến thể | có · xoá cứng |

**Chưa có object nào** cho người mua, giỏ hàng, đơn hàng, thanh toán hay kho hàng; xem bảng ở đầu file.

## Source of truth

- **Ai làm được gì trong một shop: vai của thành viên trong shop đó**, đọc từ cơ sở dữ liệu ở **mỗi** lần gọi,
  không mang trong token — nên đổi vai, thu hồi thành viên hay vô hiệu hoá tài khoản có hiệu lực ngay ở lần gọi
  kế tiếp, không đợi token hết hạn.
- **Shop của một lần gọi lấy từ token**, không bao giờ từ body hay đường dẫn.
- **Một shop "dùng được" khi chưa bị xoá và chưa bị vận hành tạm ngưng** (M4). Hai chuyện đó có hai người quyết
  khác nhau nên là hai cờ khác nhau.
- **Một tài khoản "đăng nhập được" khi chưa bị xoá và chưa bị vô hiệu hoá** — không có một cột `is_active` thứ
  ba làm nguồn thứ ba cho cùng một câu hỏi.
- **Ai sở hữu sản phẩm: shop.** Quyền sở hữu là chuỗi *Sản phẩm → Shop → Thành viên → Người dùng*. Người tạo hay
  người sửa cuối chỉ là dấu vết kiểm toán, không phải chủ.
- **Catalog: một bản duy nhất dùng chung cho cả sàn**, không thuộc shop nào. Shop chỉ *trỏ vào* nó.
- **"Sản phẩm này có được bán không" do một hàm duy nhất quyết** — cùng một hàm cho `publish` và cho mọi lần sửa
  một sản phẩm đang bán (R14, R16).
- **Tồn kho hôm nay: một số nguyên trên biến thể.** Chưa có kho hàng; khi có sẽ tách ra (Open).
- **Giá: một số nguyên trên biến thể**, đơn vị nhỏ nhất của VND, không có tiền tệ nào khác.
- **Ảnh: tệp ở kho lưu trữ, dòng ở cơ sở dữ liệu chỉ giữ khoá.** URL dựng ở mỗi response từ khoá đó.
- **Ràng buộc chéo bảng: cơ sở dữ liệu là nguồn**, service chỉ kiểm để trả lỗi rõ hơn (R28).

## Business rules

### Tài khoản, shop và thành viên

- **M1.** **Đăng ký tạo một tài khoản kèm shop đầu tiên của nó**, và người đăng ký là `owner` của shop đó, trong
  **một** giao dịch: không bao giờ có tài khoản nửa vời. Hôm nay chưa có cách đăng ký chỉ để mua hàng.
- **M2.** Một tài khoản có thể là thành viên của **nhiều** shop, mỗi shop một vai. Một phiên làm việc trên đúng
  **một** shop đang chọn; đổi sang shop khác chỉ được khi mình là thành viên của shop đó.
- **M3.** Quyền của một lần gọi là các quyền của vai người gọi **trong shop đang chọn**. Ba vai hệ thống: `owner`
  có mọi quyền; `manager` có mọi quyền **trừ** sửa hồ sơ shop (`shop:update`), quản lý thành viên
  (`membership:manage`) và ghi catalog (`catalog:manage`); `viewer` chỉ có các quyền đọc. Thiếu quyền → `403`.
- **M4.** **Xoá shop** là việc của chủ shop; **tạm ngưng shop** là việc của vận hành. Shop bị tạm ngưng vẫn còn,
  token của thành viên vẫn hợp lệ, nhưng mọi lời gọi cần shop đó bị từ chối (`shop_not_accessible`) cho tới khi
  được mở lại.
- **M5.** `slug` của shop sinh **một lần** từ tên và **không đổi khi đổi tên**: địa chỉ công khai của một gian
  hàng không nên bị một form cài đặt âm thầm viết lại.
- **M6.** Xoá shop cần quyền `shop:update` (chỉ `owner`) **và phải gõ đúng tên shop**, đối chiếu với tên đọc từ
  cơ sở dữ liệu chứ không tin request. Xoá là **xoá mềm**: shop, các thành viên của nó bị gỡ và mọi phiên gắn
  với shop bị thu hồi; dữ liệu không bị xoá vì đơn hàng sau này sẽ cần tham chiếu.
- **M7.** **Vô hiệu hoá tài khoản** cần xác nhận bằng mật khẩu và là một chiều. Tài khoản vô hiệu không đăng nhập
  được và **vẫn giữ email** của nó (người khác không chiếm được); chỉ xoá mềm mới nhả email.
- **M8.** Phiên gồm **token truy cập sống ngắn** (mặc định 15 phút) và **token làm mới sống dài** (mặc định 30
  ngày). Token làm mới **chỉ đi trong cookie `httpOnly`**: không bao giờ nằm trong body, log hay bộ nhớ của
  client, và cơ sở dữ liệu chỉ giữ **bản băm** của nó.
- **M9.** Các đường mà chỉ việc thử đã tiết lộ điều gì (đăng ký lộ email đã có, đăng nhập, tải ảnh) có **hạn
  mức**. Khi Redis hỏng thì hạn mức **cho qua** thay vì chặn: một sự cố bộ nhớ đệm không được thành sự cố đăng
  nhập.
- **M10.** Ảnh đại diện và ảnh nền shop được chuẩn hoá về khung cố định (WebP, cắt giữa) và **bị bỏ siêu dữ
  liệu**: ảnh chụp bằng điện thoại mang toạ độ GPS, và phơi vị trí nhà của người bán qua một đường công khai là
  rò rỉ riêng tư. Hai ảnh này có đường xem công khai.

### Sở hữu và ranh giới shop

- **R1.** Một sản phẩm thuộc **đúng một shop**, và không có cột "chủ là user nào" làm chủ. Quyền sửa đi
  qua thành viên của shop.
- **R2.** `created_by_user_id` và `updated_by_user_id` chỉ ghi *ai đã thao tác*. Chúng không cấp quyền
  gì và không đổi chủ.
- **R3.** Shop của mọi lần gọi lấy từ token. Sản phẩm, biến thể, ảnh của shop khác **trả `404`** như thể
  không tồn tại — không phải `403`, để không lộ sự tồn tại.
- **R4.** Đọc sản phẩm cần `products:read`, ghi cần `products:write`. `viewer` đọc được và không ghi được.

### Catalog dùng chung

- **R5.** Catalog **đọc được bởi mọi người đã đăng nhập** và **ghi cần `catalog:manage`**. Quyền này chỉ
  gán cho `owner`. Đây là **quyết định tạm thời**: nó là quyền *trong một shop*, nên mọi owner của mọi shop
  đều sửa được catalog chung. Chấp nhận được khi chưa có seller ngoài nhóm phát triển; sẽ đổi sang quản trị
  sàn trước khi có người ngoài đăng ký shop.
- **R6.** Thêm một ngành hàng mới (ví dụ thức ăn cho chó) **chỉ bằng lời gọi API** — tạo danh mục, thuộc
  tính, tuỳ chọn, gắn thuộc tính vào danh mục — **không migrate cơ sở dữ liệu, không sửa code**. Frontend
  hỏi `GET /catalog/categories/{id}/attributes` và tự dựng form.
- **R7.** Thuộc tính gắn vào danh mục **không kế thừa qua cây**: danh mục nào khai báo gì thì trả về đúng
  cái đó. Sản phẩm chỉ nằm ở **danh mục lá**, và **danh mục của sản phẩm không đổi sau khi tạo**.
- **R8.** Mỗi thuộc tính có `key` và `data_type` **cố định từ lúc tạo**. Chỉ thuộc tính `SELECT` mới có
  tuỳ chọn. Tên hiển thị thì sửa được.
- **R9.** Chỉ thuộc tính `SELECT` mới được đánh dấu `is_variation`, vì biến thể trỏ tới một tuỳ chọn
  chứ không phải một chuỗi tự do.
- **R10.** `slug` của thương hiệu và danh mục sinh **một lần** từ tên và **không đổi khi đổi tên**.
- **R11.** **"Đang dùng"** nghĩa là có giá trị sản phẩm hoặc tuỳ chọn biến thể tham chiếu tới thuộc tính
  hay tuỳ chọn đó — **kể cả sản phẩm hay biến thể đã xoá mềm**, vì dòng của chúng được giữ. Khi đó:
  không xoá được tuỳ chọn; không xoá được thuộc tính (nếu còn gắn vào danh mục thì phải gỡ trước); và
  **trong danh mục có sản phẩm dùng** thì không đổi được `is_variation` và không gỡ được thuộc tính khỏi
  danh mục đó. Đổi `required`, `filterable`, `searchable` thì **luôn được**.
- **R12.** Danh mục đang có sản phẩm **không được thêm con, không được là cha của danh mục khác, không
  xoá được** — nó phải luôn là lá. Danh mục còn con, hoặc thương hiệu còn sản phẩm, không xoá được. Cây
  danh mục không có vòng và sâu tối đa 6 tầng.

### Vòng đời sản phẩm

- **R13.** Sản phẩm **luôn tạo ra ở `draft`**. Trạng thái **chỉ đổi qua hai đường**: `publish` (`draft` hoặc
  `inactive` → `active`) và `unpublish` (`active` → `inactive`). `PATCH` **không nhận** `status`. Mọi cặp
  khác, như `active` → `draft`, bị từ chối.
- **R14.** Để `active`, sản phẩm phải thoả **bốn điều**: (1) mọi thuộc tính `required` *không phải biến
  thể* có giá trị ở sản phẩm; (2) mọi thuộc tính `required` *là biến thể* có mặt ở **mọi** biến thể còn
  sống; (3) có ít nhất một biến thể `active`; (4) mọi biến thể dùng **cùng một tập** thuộc tính biến thể.
  `draft` và `inactive` được thiếu những điều này. Lỗi trả danh sách cái còn thiếu.
- **R15.** **`required` của thuộc tính biến thể được thoả bằng tuỳ chọn của biến thể**, không phải bằng giá
  trị ở sản phẩm. Thuộc tính biến thể **không được** có giá trị ở cấp sản phẩm — để mỗi sự thật chỉ có
  một chỗ.
- **R16.** Các điều ở R14 được kiểm **tại `publish` và tại mọi lần sửa chính sản phẩm đang `active`** (giá
  trị thuộc tính, tạo/sửa/xoá/tắt biến thể). Một sản phẩm không thể tự đẩy mình ra khỏi R14. Nhưng
  **thay đổi catalog** (thêm một thuộc tính bắt buộc vào danh mục) có thể làm sản phẩm đang `active` tạm
  **cũ (stale)**: nó **giữ `active`, không bị tự gỡ**; lần sửa tiếp theo, hoặc `publish` lại, mới bị đòi
  bổ sung.
- **R17.** Mỗi giá trị thuộc tính có **đúng một** trong `option_id` / `value_text` / `value_number`, đúng
  cái mà `data_type` đòi, và tuỳ chọn phải là của chính thuộc tính đó. Ở `PATCH`: không gửi `attributes`
  → giữ nguyên; `attributes: []` → xoá hết; một danh sách → **thay cả tập**, không gộp.

### Biến thể và tồn kho

- **R18.** Một biến thể **là** một tổ hợp tuỳ chọn (ví dụ Đen / S), không phải một cột cứng "màu, size".
  Tổ hợp **bất biến** từ lúc tạo; muốn đổi thì xoá rồi tạo lại. Mỗi biến thể có tối đa 5 tuỳ chọn.
- **R19.** Mọi biến thể của một sản phẩm dùng **cùng một tập thuộc tính biến thể**. Sản phẩm không có
  thuộc tính biến thể (ví dụ thức ăn cho chó) có **đúng một** biến thể, không tuỳ chọn, để giữ giá và tồn.
- **R20.** `sku_code` **duy nhất trong shop**, và tổ hợp tuỳ chọn **duy nhất trong sản phẩm** (tính trên
  biến thể còn sống). Hai yêu cầu đồng thời tạo cùng một tổ hợp thì đúng một cái thắng, cái kia nhận lỗi
  rõ ràng: cơ sở dữ liệu là trọng tài, không phải một lần kiểm ở service.
- **R21.** `price` là **số nguyên ≥ 0** theo đơn vị nhỏ nhất của VND; `stock` là **số nguyên ≥ 0** nằm
  trên biến thể. `stock` được **đặt**, không cộng dồn.
- **R22.** Biến thể có `active` hoặc `inactive`, chuyển qua lại tự do. **Không tắt hay xoá được biến thể
  `active` cuối cùng của một sản phẩm đang `active`.**
- **R23.** **Xoá sản phẩm/biến thể là xoá mềm.** Xoá sản phẩm xoá mềm luôn mọi biến thể của nó, cùng một
  thời điểm. Giá trị thuộc tính và tuỳ chọn biến thể **được giữ**; mọi truy vấn lọc theo cha còn sống.
  `sku_code` và tổ hợp của bản ghi đã xoá **được giải phóng** để dùng lại.

### Ảnh

- **R24.** **Ảnh xoá cứng** cùng biến thể hoặc sản phẩm của nó (không đẩy ảnh của biến thể lên thành ảnh
  chung); tệp trong kho xoá sau khi ghi nhận thành công, ở mức **cố gắng hết sức** — tệp mồ côi được chấp
  nhận, dòng trỏ vào tệp không tồn tại thì không.
- **R25.** Ảnh nhận `JPEG`, `PNG`, `WEBP`, kiểm bằng nội dung chứ không chỉ theo nhãn khai báo; luôn lưu
  **`WEBP`**, **không cắt xén**, **thu nhỏ vừa khung 1600 × 1600 giữ tỉ lệ, không phóng to**, bỏ siêu dữ liệu.
  Tối đa **9 ảnh chung** cho một sản phẩm và **5 ảnh** cho mỗi biến thể. Vị trí luôn liên tục `0..n-1`
  trong từng phạm vi; `PATCH` ảnh chỉ nhận `position` và không đổi biến thể của ảnh.
- **R26.** **Ảnh sản phẩm có đường xem công khai** (theo id ảnh, không cần token), vì ảnh sản phẩm sinh ra
  để được nhìn. Khác với ảnh giấy tờ nhạy cảm: ở đây không có gì cần giấu.

### Toàn vẹn

- **R27.** Không có kho hàng và không có "giữ hàng" trong phần này: chỉ có một số tồn duy nhất trên biến
  thể, và không có trạng thái "đã đặt".
- **R28.** Những quan hệ chéo bảng mà một bug ở service có thể làm sai **do cơ sở dữ liệu giữ**, bằng khoá
  ngoại ghép: `shop_id` của biến thể luôn bằng `shop_id` của sản phẩm cha; ảnh gắn biến thể phải thuộc
  đúng sản phẩm của ảnh; tuỳ chọn phải thuộc đúng thuộc tính đứng cạnh nó. Cái nào khoá ngoại không diễn
  đạt được (thuộc tính có thuộc danh mục của sản phẩm không, có phải biến thể không) thì service kiểm.

## Glossary

- **catalog** — kho dùng chung của cả sàn gồm danh mục, thuộc tính, tuỳ chọn, thương hiệu và cấu hình
  thuộc tính theo danh mục. **Khác** với *sản phẩm*, thuộc về một shop: catalog trả lời "hàng ở ngành này
  cần khai gì", sản phẩm trả lời "shop này bán gì".
- **danh mục lá** — danh mục chưa có con. Chỉ danh mục lá nhận sản phẩm; một danh mục có sản phẩm thì phải
  giữ là lá.
- **thuộc tính (attribute)** — một đặc điểm hàng hoá, như Color hay RAM, có kiểu cố định. **Khác** với
  *giá trị thuộc tính*, là câu trả lời của một sản phẩm cụ thể cho một thuộc tính.
- **thuộc tính biến thể (`is_variation`)** — thuộc tính mà seller thay đổi để tạo ra biến thể (Color,
  Size). Cùng một thuộc tính có thể là biến thể ở danh mục này và không phải ở danh mục kia (Color của áo
  là biến thể, Color của laptop là một giá trị thường).
- **biến thể / SKU** — đơn vị thực sự được bán và tính giá, tính tồn. Một sản phẩm "Áo Polo Nike" là một
  sản phẩm với sáu biến thể Màu × Size. Nhầm sản phẩm với biến thể là gắn giá và tồn vào chỗ sai.
- **`option_key`** — dạng chữ chuẩn của một tổ hợp tuỳ chọn, dùng để cơ sở dữ liệu chặn hai biến thể trùng
  tổ hợp. Người dùng API không thấy nó.
- **đang dùng** — xem R11. Có giá trị sản phẩm hoặc tuỳ chọn biến thể tham chiếu, kể cả bản ghi đã xoá mềm.
- **sản phẩm cũ (stale)** — sản phẩm đang `active` mà catalog đã đổi sau đó khiến nó không còn thoả R14.
  Nó không bị gỡ; nó chỉ bị đòi bổ sung ở lần sửa kế tiếp.
- **`draft` / `active` / `inactive`** — soạn dở, đang bán, tạm ngưng. Chỉ `draft` được thiếu thuộc tính
  bắt buộc.
- **`catalog:manage`** — quyền tạm thời cho phép ghi catalog. Xem R5.
- **shop / gian hàng** — không gian làm việc của một người bán: sản phẩm, thành viên, hồ sơ. **Khác** với
  *tài khoản*: một tài khoản có thể ở nhiều shop, và quyền luôn tính theo shop đang chọn.
- **thành viên và vai** — thành viên nối một tài khoản với một shop và một vai; vai là một tập quyền. Chữ "thành
  viên" chỉ mối nối đó, không chỉ người.
- **phiên** — một lần đăng nhập, gắn với một shop đang chọn. Đổi shop là đổi phiên, không phải mở thêm phiên.
- **vô hiệu hoá** và **xoá** (tài khoản) — vô hiệu hoá là tạm dừng một chiều, giữ email; xoá mềm nhả email. Hai
  việc khác nhau vì người bán tạm dừng có thể quay lại.
- **tạm ngưng** (shop) — vận hành khoá một shop mà không xoá nó. **Khác** với *xoá shop*, là việc của chủ shop.
- **quản trị sàn** — người giữ luật chung của cả sàn, đối lập với chủ một shop. Hôm nay chưa có; xem R5.

## Human decisions

- Ai được đăng ký shop và bán — chủ sản phẩm. Hôm nay **ai cũng đăng ký được**, không có bước duyệt.
- Tạm ngưng hoặc mở lại một shop — vận hành.
- Khai báo ngành hàng, thuộc tính, tuỳ chọn, thương hiệu, và thuộc tính nào bắt buộc hay là biến thể ở ngành
  nào — người quản trị catalog (hôm nay là `owner`, xem R5).
- Đặt giá, đặt tồn, quyết bật/tắt từng biến thể, và **bấm `publish`** — seller. Không có gì tự đưa sản phẩm
  lên bán.
- Chọn thời điểm chuyển quyền ghi catalog từ `catalog:manage` sang quản trị sàn — chủ sản phẩm; điều kiện đã
  biết là **trước khi có người ngoài đăng ký shop**.
- Chọn con số giới hạn ảnh (9 và 5) và khung 1600 × 1600 — chủ sản phẩm; đặt là hằng số nên đổi được.

## The bet

Một sàn **mở**: mọi shop tự đăng ký và tự đăng hàng mà không cần đội vận hành dựng form hay duyệt từng ngành
hàng. Việc đó đứng được nhờ hai thứ: **ranh giới shop** rõ (mọi thứ của shop đi qua shop, một người có thể ở
nhiều shop) và **catalog có metadata dẫn dắt** (thuộc tính theo danh mục, biến thể là tổ hợp tuỳ chọn), nên
thêm ngành hàng mới là việc cấu hình chứ không phải việc của dev. Nếu sai — ngành hàng nào cũng đòi logic riêng
(gói combo, giá theo cân, hàng đặt theo yêu cầu) — catalog thành một lớp EAV khó truy vấn mà vẫn phải viết code
riêng cho từng ngành; và nếu sàn phải duyệt từng shop trước khi bán thì "mở" chỉ còn là tên gọi.

## Chưa làm (có trong hướng sản phẩm)

- **Người mua và mọi thứ của việc mua:** tài khoản người mua, duyệt và tìm kiếm, giỏ hàng, đơn hàng, thanh
  toán, giao nhận. Sản phẩm chỉ `active` mới bán được (R13) là nền cho việc này; chưa có đường công khai nào
  để người mua thấy nó.
- **Kho hàng và giữ hàng** (R27), và tách `stock` khỏi biến thể.
- **Quản trị sàn thật sự** thay cho `catalog:manage` (R5).
- **Tìm kiếm, lọc theo thuộc tính** phía người mua; cờ `filterable` và `searchable` mới là metadata.
- **Kiểm duyệt** shop hay sản phẩm, đánh giá, khuyến mãi, hoàn trả.
- **Địa chỉ** của người dùng và của shop; **nhiều đơn vị tiền tệ**.
- **Frontend**: repo này chỉ phơi API.

## Not this product

- **Không kế thừa thuộc tính qua cây danh mục.**
- **Không đổi tổ hợp tuỳ chọn của biến thể đã tạo**, không đổi danh mục của sản phẩm đã tạo, không đổi `key`
  hay `data_type` của thuộc tính.
- **Không xoá cứng thứ đã từng được dùng** — catalog chỉ xoá cứng được khi chưa ai tham chiếu.
- **Không tự gỡ sản phẩm khi catalog đổi.** Sản phẩm cũ giữ `active`.
- **Không để token làm mới lộ ra ngoài cookie `httpOnly`.**
- **Không xoá dữ liệu khi xoá shop hay sản phẩm** — chỉ xoá mềm, vì đơn hàng sẽ cần tham chiếu.

## Open

- `OPEN — chủ sản phẩm`: **tài khoản người mua** — người mua đăng ký thế nào, khi đăng ký hôm nay luôn tạo kèm một
  shop (M1)? — default: **tách hai loại đăng ký**, người mua không có shop, và một tài khoản vẫn có thể về sau mở
  thêm shop; làm cùng đợt với luồng mua hàng.
- `OPEN — chủ sản phẩm`: **ai được mở shop** — vẫn mở tự do, hay có bước duyệt? Hôm nay không có bước duyệt.
  — default: **mở tự do** cho tới khi có người bán ngoài nhóm phát triển, rồi cân lại cùng chuyện quản trị sàn.
- `OPEN — chủ sản phẩm`: **chuyển quyền ghi catalog sang quản trị sàn** khi nào? Cần một cờ
  `users.is_platform_admin` và một hàm kiểm tra riêng, rồi gỡ `catalog:manage` khỏi `owner`. — default:
  **trước khi có bất kỳ seller nào ngoài nhóm phát triển đăng ký shop**; chi tiết ở *Next phase* của
  `changes/20-09-2026-CatalogAndProduct/plan.md`.
- `OPEN — chủ sản phẩm`: **tạm ngưng shop** có cần API và giao diện cho vận hành không? Hôm nay đó là thao tác
  trong mã. — default: **có**, cùng đợt với quản trị sàn.
- `OPEN — chủ sản phẩm`: **kho hàng** — khi nào tách `stock` ra bảng theo (kho, biến thể) và thêm số đang giữ? —
  default: **khi làm đơn hàng**, vì "giữ hàng" chỉ có nghĩa khi có đơn.
- `OPEN — chủ sản phẩm`: **đơn hàng và thanh toán** — một đơn thuộc về một shop hay gộp nhiều shop trong một lần
  thanh toán? Chưa có quyết định; mọi thiết kế hiện tại (sản phẩm và biến thể xoá mềm, giữ dòng con) chỉ để chừa
  chỗ cho việc này.
- `OPEN — chủ sản phẩm`: thay xoá cứng catalog bằng cờ **ngừng dùng (`is_active`)**? Hôm nay một thuộc tính hay
  tuỳ chọn từng được sản phẩm dùng thì không xoá được nữa, kể cả sản phẩm đã xoá. — default: **có**, khi bắt đầu
  có người quản trị catalog dọn dẹp thật.
- `OPEN — chủ sản phẩm`: **báo cho seller** biết sản phẩm nào đang cũ (R16) và lọc chúng ra? — default: **có**,
  làm cùng đợt với tìm kiếm phía người bán; hôm nay seller chỉ biết khi sửa sản phẩm và bị đòi bổ sung.
- `OPEN — chủ sản phẩm`: có cần **tiền tệ** trên biến thể không? — default: **không** cho tới khi có sàn bán ra
  ngoài Việt Nam.
