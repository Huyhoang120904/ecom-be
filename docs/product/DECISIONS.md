# Vì sao sàn lại thế này

Luật của sản phẩm nằm ở `PRODUCT.md`: `M1…M10` cho tài khoản, shop và thành viên, `R1…R28` cho catalog và sản
phẩm. File này trả lời câu **"vì sao lại làm thế"** cho từng luật, kèm những hướng đã cân rồi loại. Mục đích:
người vào sau không mở lại một cuộc bàn đã xong, và **mở lại được** khi lý do cũ hết đúng — mỗi mục đều nói rõ
nó dựa trên điều gì. Cuối mỗi mục có dòng *Luật nằm ở* trỏ ngược về `PRODUCT.md`; mọi luật `M` và `R` đều được
giải thích ở ít nhất một mục.

Sản phẩm là một **sàn thương mại điện tử nhiều shop**: shop đăng ký gian hàng và bán, người mua mua hàng của
nhiều shop. Mã hôm nay mới phủ phần người bán, nên phần lớn quyết định dưới đây thuộc phần đó; những quyết
định về người mua và đơn hàng chưa được đưa ra và nằm ở mục *Open* của `PRODUCT.md`, không bịa ở đây.

Có bốn từ được dùng suốt file này: **shop** là gian hàng của một người bán, **catalog** là kho dùng chung của cả
sàn (danh mục, thuộc tính, tuỳ chọn, thương hiệu), **sản phẩm** là thứ một shop bán, và **biến thể** (SKU) là
đơn vị thực sự có giá và có tồn.

## Cả sàn: tài khoản, shop, phiên

### Vì sao làm phía người bán trước, và vì sao đăng ký tạo luôn shop đầu tiên?

Một sàn cần cả hai phía, nhưng người mua không có gì để mua khi chưa có hàng. Nên thứ tự là: tài khoản và shop
→ catalog → sản phẩm → (đợt sau) người mua, giỏ, đơn, thanh toán. Catalog và sản phẩm là nền của mọi thứ đứng
sau: đơn hàng cần một biến thể có giá và có tồn để trỏ vào.

Vì đi theo hướng đó, **đăng ký hôm nay tạo một tài khoản kèm shop đầu tiên** và người đăng ký là `owner`, trong
một giao dịch — một người bán không bao giờ ở trạng thái "có tài khoản mà không có shop", và bốn lần ghi
(tài khoản, shop, thành viên, phiên đăng nhập) hoặc cùng xong hoặc cùng không.

Cái giá đã biết: **chưa có cách đăng ký chỉ để mua hàng**. Đó là một khoảng trống thật của mô hình, không phải
một luật muốn giữ; nó nằm ở mục *Open* của `PRODUCT.md` và sẽ được gỡ cùng luồng mua hàng.

Mở lại khi bắt đầu làm người mua: lúc đó cần tách hai loại đăng ký, và một tài khoản vẫn có thể về sau mở thêm
shop.

Đã cân và loại: làm người mua trước (không có hàng để mua) · làm cả hai phía cùng lúc (rộng hơn mức kiểm được
trong một đợt) · đăng ký tách bước "tạo tài khoản" rồi "tạo shop" (mở ra trạng thái nửa vời và một lần gọi có
thể lỡ dở).

Luật nằm ở: `PRODUCT.md` › Business rules (M1), Open.

### Vì sao một tài khoản ở nhiều shop, phiên gắn một shop, và quyền đọc từ cơ sở dữ liệu mỗi lần?

Một người có thể quản lý nhiều gian hàng ("Huy Fashion", "Huy Electronics"), và một shop có nhiều người. Nên
quyền không thuộc về tài khoản mà thuộc về **cặp (tài khoản, shop)**: thành viên nối hai bên và mang một vai.
Một phiên làm việc trên **đúng một** shop đang chọn; muốn sang shop khác thì đổi shop (chỉ khi là thành viên
của nó), và mọi lời gọi biết ngay "shop nào" mà không ai phải gửi `shop_id`.

Quyền được **đọc từ cơ sở dữ liệu ở mỗi lần gọi**, không nhét vào token. Token chỉ nói "người này, đang ở shop
này". Nhờ vậy đổi vai, thu hồi một thành viên, vô hiệu hoá một tài khoản hay tạm ngưng một shop có hiệu lực ngay
ở lần gọi kế tiếp, thay vì đợi token hết hạn. Cái giá là mỗi lời gọi tốn một truy vấn nhỏ ở bốn bảng có chỉ mục;
chấp nhận vì sự chậm trễ khi thu hồi quyền mới là chỗ nguy hiểm.

Đã cân và loại: nhét vai và quyền vào token (thu hồi phải chờ hết hạn) · quyền gắn thẳng vào tài khoản (một người
không thể là chủ ở shop này và chỉ được xem ở shop kia) · nhận `shop_id` từ đường dẫn (thêm một chỗ để sai và cho
phép thăm dò shop khác).

Luật nằm ở: `PRODUCT.md` › Business rules (M2, M3), Source of truth.

### Vì sao chỉ có ba vai hệ thống, và mỗi vai được gì?

`owner`, `manager`, `viewer`, mỗi vai là một tập quyền được nạp bằng migration. `owner` có mọi quyền; `manager`
có mọi quyền trừ những gì chỉ chủ mới nên làm — sửa hồ sơ shop, quản lý thành viên, và (tạm thời) ghi catalog;
`viewer` chỉ đọc. Danh sách "quyền của viewer" được **liệt kê tường minh**, không suy ra từ đuôi `:read` của tên:
một quyền tương lai tình cờ có tên như thế sẽ âm thầm được trao cho một vai "chỉ đọc", và "chỉ đọc" là một quyết
định sản phẩm đáng được ghi ra.

Cơ sở dữ liệu đã chừa chỗ cho **vai riêng của từng shop** (vai có thể thuộc về một shop), nhưng hôm nay chưa ai
cần nên chưa có; ba vai đủ cho "chủ, người làm, người xem".

Mở lại khi một shop đủ lớn để cần phân quyền mịn hơn (ví dụ người chỉ quản lý đơn, người chỉ chăm sóc khách).

Đã cân và loại: vai tuỳ biến cho mọi shop ngay từ đầu (chưa có nhu cầu, thêm một bề mặt phải kiểm) · một cờ
`is_admin` trên thành viên (không diễn đạt được "manager làm được gì").

Luật nằm ở: `PRODUCT.md` › Business rules (M3).

### Vì sao tạm ngưng shop và xoá shop là hai chuyện khác nhau, và xoá phải gõ đúng tên?

Hai chuyện có **hai người quyết khác nhau**: xoá là chủ shop tự bỏ gian hàng của mình; tạm ngưng là vận hành
khoá một shop (vi phạm, đang điều tra) mà không xoá nó. Gộp thành một cờ thì không phân biệt được "chủ tự bỏ"
với "sàn khoá", và mở lại một shop bị ngưng sẽ nhầm với khôi phục một shop bị xoá. Nên là hai cờ riêng, và shop
chỉ "dùng được" khi cả hai đều sạch. Shop bị ngưng vẫn còn, token của thành viên vẫn hợp lệ, nhưng mọi lời gọi
cần shop đó bị từ chối với một mã riêng để client biết "chọn shop khác", khác với "tài khoản của bạn đã bị khoá".

Xoá shop là **xoá mềm**: shop và các thành viên của nó bị gỡ, mọi phiên gắn với nó bị thu hồi, còn dữ liệu được
giữ vì đơn hàng sau này sẽ cần tham chiếu. Và việc xoá cần **gõ đúng tên shop**, đối chiếu với tên đọc từ cơ sở
dữ liệu chứ không tin request: một hộp thoại mà một cú nhấp nào cũng đóng được không phải là một chốt chặn.

Cái giá đã biết: hôm nay tạm ngưng chỉ là một thao tác trong mã, chưa có API cho vận hành (mục *Open*).

Đã cân và loại: một cờ duy nhất cho cả hai (mất ai-quyết-gì) · xoá cứng shop (mất chỗ cho đơn hàng) · xác nhận
bằng một nút bấm (không chặn được tay quá nhanh).

Luật nằm ở: `PRODUCT.md` › Business rules (M4, M6), Source of truth.

### Vì sao slug của shop không đổi khi đổi tên?

`slug` sinh **một lần** từ tên và cố định. Đó là địa chỉ công khai của một gian hàng: đường dẫn người mua
lưu lại, chia sẻ, để trong tìm kiếm. Một form cài đặt đổi tên không được âm thầm viết lại nó. Nếu sau này cần
đổi slug thì đó là một thao tác có chủ ý, có chuyển hướng, chứ không phải tác dụng phụ của việc sửa tên.

Cùng lý do áp cho slug của thương hiệu và danh mục ở catalog (M5, R10).

Luật nằm ở: `PRODUCT.md` › Business rules (M5).

### Vì sao vô hiệu hoá tài khoản khác xoá, và cần mật khẩu?

Người bán có thể tạm dừng rồi quay lại, nên **vô hiệu hoá** là một trạng thái riêng: tài khoản không đăng nhập
được nhưng **vẫn giữ email**, để không ai khác chiếm địa chỉ đó trong lúc chủ vắng mặt. Chỉ **xoá mềm** mới nhả
email. Hai thời điểm được ghi riêng (mỗi cái ghi lúc nó xảy ra) thay vì một cờ `is_active` — thêm một cờ là thêm
nguồn thứ ba cho cùng câu hỏi "tài khoản này đăng nhập được không".

Vô hiệu hoá là một chiều và cần **xác nhận bằng mật khẩu**: một phiên bị cướp không nên đủ để khoá chủ nhân ra
khỏi tài khoản của họ.

Đã cân và loại: chỉ có xoá (mất trạng thái tạm dừng) · một cột `is_active` (nguồn thứ ba) · không cần xác nhận
(một token bị lộ đủ để phá tài khoản).

Luật nằm ở: `PRODUCT.md` › Business rules (M7), Source of truth.

### Vì sao token làm mới chỉ ở cookie `httpOnly`, và vì sao đường dễ bị thử có hạn mức?

Token truy cập sống ngắn (mặc định 15 phút) nằm trong body để client gắn vào header; **token làm mới** sống dài
(mặc định 30 ngày) **không bao giờ** xuất hiện trong body, log hay bộ nhớ của client, chỉ đi trong cookie
`httpOnly`, và cơ sở dữ liệu chỉ giữ **bản băm** của nó — nên đọc được cơ sở dữ liệu cũng không dựng lại được một
phiên. Một script chạy trong trang không đọc được cookie `httpOnly`, đó là toàn bộ lý do.

Những đường mà chỉ việc thử đã tiết lộ điều gì — đăng ký (lộ email đã có), đăng nhập, tải ảnh — có **hạn mức**.
Hạn mức được thiết kế **cho qua khi Redis hỏng**: chặn khi bộ nhớ đệm lỗi sẽ biến một sự cố phụ thành sự cố
đăng nhập toàn hệ thống, tệ hơn việc tạm thời không giới hạn; sự kiện được ghi nhật ký để không âm thầm.

Cái giá đã biết: khi Redis hỏng, hạn mức tạm thời vô hiệu.

Đã cân và loại: token làm mới trong body hoặc `localStorage` (lộ cho mọi script) · lưu token làm mới nguyên
văn (một lần đọc cơ sở dữ liệu là đủ để mạo danh) · hạn mức chặn cứng khi Redis lỗi (sự cố phụ thành sự cố
chính).

Luật nằm ở: `PRODUCT.md` › Business rules (M8, M9).

### Vì sao ảnh đại diện và ảnh nền được cắt về khung cố định và bỏ siêu dữ liệu?

Ảnh đại diện (vuông) và ảnh nền shop (chữ nhật) có tỉ lệ đích cố định, nên được cắt giữa về đúng khung rồi lưu
`WebP`. Việc **bỏ siêu dữ liệu** không phải chuyện thẩm mỹ: ảnh chụp bằng điện thoại mang toạ độ GPS, và phơi
vị trí nhà của một người bán qua một đường công khai là rò rỉ riêng tư. Kiểm nội dung thật thay vì tin nhãn
`Content-Type` khai báo, và chặn kích thước trước khi giải mã, để một tệp độc hại không chiếm bộ nhớ.

Ảnh sản phẩm dùng lại đường xử lý này nhưng khác ở chỗ **không cắt** (xem mục ảnh ở dưới).

Luật nằm ở: `PRODUCT.md` › Business rules (M10).

## Sở hữu và quyền

### Vì sao sản phẩm thuộc shop chứ không thuộc user?

Sản phẩm có `shop_id` và **không** có "chủ là user nào". Quyền sửa đi qua chuỗi *Sản phẩm → Shop →
Thành viên → Người dùng*. `created_by_user_id` và `updated_by_user_id` vẫn có, nhưng chỉ để trả lời "ai đã
làm", không cấp quyền gì.

Lý do là mô hình thật của một sàn: một shop có nhiều người (chủ, quản lý sản phẩm, chăm sóc khách), và một
người có thể ở nhiều shop. Đặt `owner_user_id` lên sản phẩm chạy được với một cửa hàng một người, rồi vỡ
đúng ở lúc thêm người thứ hai — và sửa lúc đó nghĩa là đổi khoá của mọi truy vấn. Shop đã là một miền riêng
ở phần identity (có id riêng, có thành viên riêng), nên sản phẩm chỉ việc trỏ vào đó.

Từ token, shop của mỗi lần gọi là shop đang chọn của người gọi; nó **không bao giờ** đến từ body hay đường
dẫn. Vì vậy sản phẩm của shop khác **trả `404`** chứ không phải `403`: người gọi không cần biết id đó có tồn
tại hay không, và một câu trả lời "cấm" đã nói cho họ biết là có.

Cái giá đã biết: mọi truy vấn sản phẩm phải mang `shop_id`, và quên nó là lỗ hổng cô lập. Bù lại bằng cách
gom vào một chỗ — repository chỉ tìm sản phẩm *qua* shop — và có test hai shop chạm vào nhau ở mọi đường.

Đã cân và loại: `owner_user_id` trên sản phẩm (không chịu được nhiều người một shop) · bảng thành viên
riêng cho catalog (đã có sẵn thành viên ở identity) · nhận `shop_id` từ đường dẫn rồi kiểm quyền (thêm một
chỗ để sai, và cho phép thăm dò shop khác).

Luật nằm ở: `PRODUCT.md` › Business rules (R1, R2, R3).

### Vì sao dùng lại thành viên và vai trò có sẵn thay vì dựng bảng `shop_members` mới?

Thiết kế ban đầu vẽ `shop_members(shop_id, user_id, role)` với vai `OWNER`, `ADMIN`, `STAFF`. Repo đã có mô
hình tương đương, giàu hơn: thành viên gắn với **vai**, vai gắn với **tập quyền** (`owner`, `manager`,
`viewer`), và quyền được đọc từ cơ sở dữ liệu ở mỗi lần gọi. Catalog & product chỉ cần hai quyền đã seed sẵn
là `products:read` và `products:write`. Dựng thêm một bảng thành viên thứ hai là hai nguồn cho cùng một câu
hỏi "người này làm được gì ở shop này".

Đọc quyền ở mỗi lần gọi (không nhét vào token) là thứ mà phần này thừa hưởng: hạ một người xuống `viewer`
có hiệu lực ở lần gọi kế tiếp, và test kiểm đúng điều đó ở các route của sản phẩm.

Đã cân và loại: bảng `shop_members` với ba vai cứng (trùng và yếu hơn cái đã có) · quyền riêng cho từng
route sản phẩm (không cần: `read`/`write` đủ).

Luật nằm ở: `PRODUCT.md` › Business rules (R4).

### Vì sao quyền ghi catalog hôm nay là `catalog:manage`, và vì sao sẽ đổi?

Catalog là dữ liệu của **cả sàn**, nhưng repo chưa có ai "sở hữu cả sàn": mọi quyền hiện có đều là quyền
*trong một shop*. Cần một cổng ghi cho catalog thì có hai hướng. Cách đúng là một cờ quản trị sàn trên người
dùng (`users.is_platform_admin`) và một hàm kiểm tra riêng. Cách nhanh là một quyền mới `catalog:manage` gán
cho vai `owner`, dùng nguyên cơ chế quyền có sẵn.

Phase này chọn **cách nhanh, có ghi rõ là tạm**. Cái giá đã biết và chấp nhận: quyền này nằm trong shop, nên
**owner của bất kỳ shop nào đều sửa được catalog chung**. Chấp nhận được vì chưa có seller ngoài nhóm phát
triển, và vì cách đúng cần thêm cột, thêm cách cấp cờ ngoài API, và quyết định "quản trị sàn có cần một shop
không" — những thứ chưa có nhu cầu thật. Chỉ `owner` mới được cấp, để `manager` và `viewer` không sửa được
catalog, và có test cho cả ba vai.

Đọc catalog thì cho **mọi người đã đăng nhập**: seller cần nó để dựng form đăng sản phẩm. Không có đường đọc
công khai ở phase này vì người mua chưa phải actor.

Mở lại khi **sắp có người ngoài đăng ký shop** — lúc đó "owner nào cũng sửa được catalog toàn sàn" thôi là
chấp nhận được. Cách thay đã ghi ở `changes/20-09-2026-CatalogAndProduct/plan.md`, mục *Next phase*: thêm
`users.is_platform_admin`, một dependency `require_platform_admin` đọc cờ từ cơ sở dữ liệu ở mỗi lần gọi, cấp
cờ bằng script vận hành chứ không qua API công khai, đổi các route `/admin/catalog/*` sang đó, và gỡ
`catalog:manage` khỏi `owner`.

Đã cân và loại: gắn tạm vào `products:write` (cho `manager` sửa catalog, tệ hơn) · không có cổng, ai đăng
nhập cũng ghi (không chấp nhận được) · làm ngay quản trị sàn (thêm bề mặt mà chưa ai cần).

Luật nằm ở: `PRODUCT.md` › Business rules (R5), Open.

## Catalog: một schema cho mọi ngành hàng

### Vì sao ngành hàng mới là việc cấu hình chứ không phải migrate?

Áo cần màu, size, chất liệu; laptop cần CPU, RAM, ổ cứng, màn hình; nước hoa cần dung tích, nồng độ. Nếu
những thứ đó là cột của bảng sản phẩm thì mỗi ngành hàng mới là một lần sửa cơ sở dữ liệu, và bảng sản phẩm
thành một hàng cột hầu như luôn `NULL`. Thay vào đó: danh mục có cây cha–con, thuộc tính là dữ liệu, và
một bảng cấu hình nói "danh mục này hỏi những thuộc tính nào, cái nào bắt buộc". Thêm ngành thức ăn cho chó
là vài lời gọi API; frontend hỏi `GET /catalog/categories/{id}/attributes` rồi tự dựng form.

Đây chính là *the bet* của `PRODUCT.md`, và có test chứng minh nó bằng một kịch bản trọn vẹn: tạo danh mục
Dog Food, hai thuộc tính, ba tuỳ chọn, cấu hình chỉ bằng API, rồi một seller đăng sản phẩm và bị từ chối
publish cho tới khi đủ thuộc tính bắt buộc.

`key` và `data_type` của thuộc tính **cố định từ lúc tạo**. Đổi `TEXT` thành `SELECT` dưới chân những sản
phẩm đang có giá trị chữ tự do không có nghĩa an toàn nào; một ý nghĩa khác là một thuộc tính khác. Tên hiển
thị thì sửa được vì nó không làm đổi cái gì.

`slug` của thương hiệu và danh mục sinh một lần từ tên và **không đổi khi đổi tên**, cùng lý do với slug của
shop: một địa chỉ công khai không nên bị một form cài đặt âm thầm viết lại.

Cái giá đã biết: dữ liệu thuộc tính đi qua một lớp EAV nên truy vấn "mọi laptop 16GB RAM" là một phép nối,
không phải một cột. Chấp nhận vì tìm kiếm phía người mua chưa nằm trong phase này; khi tới đó sẽ đo và có thể
thêm bảng phi chuẩn hoá cho chỗ nghẽn.

Đã cân và loại: cột cứng cho từng ngành (mỗi ngành mới là một migrate) · một cột JSON trong bảng sản phẩm
(mất ràng buộc kiểu, mất khoá ngoại tới tuỳ chọn, mất khả năng bảo vệ "đang dùng") · bảng riêng cho từng
ngành (số bảng tăng theo số ngành).

Luật nằm ở: `PRODUCT.md` › Business rules (R6, R8, R10).

### Vì sao chỉ EAV cho phần thuộc tính động, và giữ nó "có kiểm soát"?

Chỉ phần *thuộc tính* đi qua EAV. Sản phẩm, biến thể, giá, tồn, ảnh đều là bảng thường với cột thường. Trong
EAV, mỗi giá trị nằm ở **một trong ba cột** — `option_id`, `value_text`, `value_number` — và một `CHECK` đòi
đúng một cột được điền. Loại của thuộc tính (`TEXT`, `NUMBER`, `SELECT`) quyết định cột nào, và service kiểm
khớp trước khi ghi. Tuỳ chọn thì trỏ bằng khoá ngoại ghép `(option_id, attribute_id)`, nên không thể lưu một
tuỳ chọn của thuộc tính này dưới thuộc tính khác (R28).

"EAV có kiểm soát" là vì cả ba lớp: kiểu (cột), khoá ngoại (tuỳ chọn thuộc đúng thuộc tính), và service (thuộc
tính có thuộc danh mục của sản phẩm không). EAV trần — một cột chữ chứa mọi thứ — là thứ đã bị loại.

Đã cân và loại: EAV trần một cột chữ (không có kiểu, không có ràng buộc) · EAV hoá cả sản phẩm (giá, tồn
cũng thành dòng — vô nghĩa).

Luật nằm ở: `PRODUCT.md` › Business rules (R8, R17, R28).

### Vì sao thuộc tính không kế thừa qua cây, và sản phẩm chỉ nằm ở danh mục lá?

Danh mục là cây (Điện tử › Máy tính › Laptop). Thuộc tính gắn vào danh mục nào thì trả về đúng ở danh mục đó,
**không kế thừa từ cha**, và sản phẩm chỉ nằm ở danh mục **lá**. Hai luật đi cặp: nếu thuộc tính chỉ khai ở
lá thì sản phẩm phải ở lá, nếu không thì một sản phẩm nằm ở giữa cây sẽ không có biểu mẫu nào.

Không kế thừa vì kế thừa kéo theo câu hỏi mà chưa ai có câu trả lời: cha khai `required`, con muốn bỏ thì
sao; con khai `is_variation` trái với cha thì thắng bên nào. Một danh mục khai đủ thứ nó cần thì dễ đoán, dễ
kiểm, và khớp cách các sàn thật gắn thuộc tính vào danh mục lá.

**Lá phải giữ là lá.** Danh mục đang có sản phẩm không được thêm con, không được nhận danh mục khác chuyển
vào, không xoá được (R12). Hai thao tác đồng thời — thêm con và tạo sản phẩm — được xếp hàng bằng khoá dòng
danh mục: thêm con khoá `FOR UPDATE`, tạo sản phẩm khoá `FOR SHARE`, nên cả hai không thể cùng thắng. **Danh
mục của sản phẩm cũng không đổi sau khi tạo**, để giá trị thuộc tính không bao giờ nằm dưới một danh mục mà
chúng chưa được kiểm; muốn khác thì tạo sản phẩm mới.

Cái giá đã biết: một thay đổi cấu trúc cây phải chờ tới khi danh mục không còn sản phẩm; và đổi danh mục của
sản phẩm phải tạo lại. Chấp nhận vì cả hai hiếm, và cái thay thế là tự động di chuyển giá trị thuộc tính giữa
hai bộ cấu hình khác nhau mà không ai kiểm.

Mở lại khi có nhu cầu thật về thuộc tính chung cho cả một nhánh (ví dụ "Thương hiệu" cho mọi ngành).

Đã cân và loại: kế thừa thuộc tính từ cha (chưa có luật giải xung đột) · cho sản phẩm ở danh mục bất kỳ
(sản phẩm ở giữa cây không có biểu mẫu) · cho đổi danh mục của sản phẩm (di chuyển giá trị không kiểm).

Luật nằm ở: `PRODUCT.md` › Business rules (R7, R12).

### Vì sao "đang dùng" tính cả bản ghi đã xoá mềm, và chặn những thay đổi nào?

Một thuộc tính hay tuỳ chọn là **đang dùng** khi có giá trị sản phẩm hoặc tuỳ chọn biến thể trỏ tới nó — kể
cả của sản phẩm và biến thể đã xoá mềm, vì dòng của chúng được giữ (R23) và khoá ngoại `RESTRICT` cũng nhìn
thấy chúng. Định nghĩa trùng với cái cơ sở dữ liệu thực thi khiến hai lớp không bao giờ bất đồng: service
kiểm bằng truy vấn tồn tại để trả `409` với mã cụ thể, và nếu service lỡ thì khoá ngoại vẫn chặn.

Bản đồ các thay đổi:

| Thay đổi | Quy tắc |
|---|---|
| Đổi `key`, `data_type` | không cho (xem mục trên) |
| Xoá tuỳ chọn | chặn khi đang dùng |
| Xoá thuộc tính | chặn khi còn gắn vào danh mục, hoặc đang dùng |
| Đổi `is_variation` | chặn khi **trong danh mục đó** đã có sản phẩm dùng thuộc tính |
| Gỡ thuộc tính khỏi danh mục | chặn khi **trong danh mục đó** đã có sản phẩm dùng |
| Đổi `required`, `filterable`, `searchable` | luôn được |
| Gắn thêm thuộc tính vào danh mục đã có sản phẩm | luôn được |

Khoá theo **từng danh mục** chứ không toàn cục: Color là biến thể ở áo và là một giá trị thường ở laptop, nên
việc áo đang dùng Color không được cản việc chỉnh Color của điện thoại.

Cái giá đã biết: một thuộc tính hay tuỳ chọn từng được dùng thì **không bao giờ xoá cứng được nữa**, kể cả khi
sản phẩm dùng nó đã bị xoá. Chấp nhận vì xoá nhầm một thuộc tính đang bán còn tệ hơn để nó nằm đó. Lối ra
đúng là một cờ ngừng dùng thay cho xoá cứng (Open ở `PRODUCT.md`).

Đã cân và loại: chỉ tính sản phẩm còn sống (khoá ngoại vẫn chặn, service sẽ trả lỗi 500 thay vì `409`) · khoá
toàn cục theo thuộc tính (chặn cả những danh mục không liên quan) · cho xoá rồi để mồ côi giá trị (mất dữ liệu
người bán).

Luật nằm ở: `PRODUCT.md` › Business rules (R11, R23).

## Vòng đời sản phẩm

### Vì sao trạng thái chỉ đổi qua `publish` và `unpublish`, và `PATCH` không nhận `status`?

Luật "sản phẩm phải đủ thuộc tính bắt buộc mới được bán" chỉ đáng tin nếu **chỉ có một đường** vào `active`.
Nếu `PATCH` được đổi `status` thì hai đường dẫn tới cùng một chuyển trạng thái, và một trong hai sẽ quên
kiểm. Nên `PATCH` không có trường `status` (gửi vào là `422`), sản phẩm luôn được tạo ở `draft`, và chỉ có
hai hành động — `publish` (`draft` hoặc `inactive` → `active`) và `unpublish` (`active` → `inactive`) — cùng
đi qua một hàm duy nhất trong service. Mọi cặp khác, như `active` → `draft`, là `409`.

Lỗi publish kèm **danh sách cái còn thiếu** (id thuộc tính, tên, và thiếu ở sản phẩm hay ở biến thể) trong
trường `details`, để frontend chỉ đúng chỗ cho seller. Danh sách được dựng từ id và tên mà service đọc từ cơ
sở dữ liệu, không từ chữ của request, nên không có gì bị phản chiếu.

Đã cân và loại: cho `PATCH` đổi `status` rồi kiểm trong service (hai đường tới một chuyển trạng thái) · tự
động lên `active` khi đủ điều kiện (seller mất quyền quyết khi nào bán) · một trạng thái `archived` (không có
nhu cầu; xoá mềm đã đủ).

Luật nằm ở: `PRODUCT.md` › Business rules (R13).

### Vì sao `draft` được thiếu, còn `active` thì không, và điều kiện gồm những gì?

Seller lưu dở giữa chừng là chuyện thường, nên `draft` và `inactive` không bị chặn vì thiếu thuộc tính bắt
buộc. Chỉ lúc `publish` (và khi sửa một sản phẩm đang `active`) mới đòi đủ. Bốn điều: mọi thuộc tính bắt buộc
không phải biến thể có giá trị; mọi thuộc tính bắt buộc là biến thể có ở **mọi** biến thể còn sống; có ít
nhất một biến thể `active`; mọi biến thể dùng cùng một tập thuộc tính biến thể. Điều 2 tính cả biến thể
`inactive` vì nó có thể được bật lại.

Cả bốn điều nằm trong **một hàm thuần** (`published_gaps`) nhận cấu hình danh mục, tập thuộc tính có giá trị
và hình dạng các biến thể, rồi trả về cái còn thiếu. Hàm thuần thì test được bằng giá trị thường; và vì
`publish` lẫn mọi lần sửa sản phẩm đang bán đều gọi cùng một hàm, luật không thể lệch giữa hai nơi.

Đã cân và loại: bắt đủ ngay từ lúc tạo (seller không lưu dở được) · chỉ kiểm lúc `publish` mà không kiểm khi
sửa sản phẩm đang bán (sửa xong một sản phẩm đang bán có thể phá luật mà không ai biết).

Luật nằm ở: `PRODUCT.md` › Business rules (R14).

### Vì sao `required` của thuộc tính biến thể được thoả bằng tuỳ chọn của biến thể?

Ở áo, Color và Size vừa bắt buộc vừa là biến thể. Nếu cả hai nơi đều được coi là "có giá trị", một seller có
thể khai Color ở sản phẩm *và* Color ở biến thể, hai câu trả lời có thể khác nhau. Nên có một nơi duy nhất
cho mỗi sự thật: thuộc tính biến thể sống ở biến thể, và **API từ chối** một giá trị cấp sản phẩm cho thuộc
tính biến thể (`attribute_is_variation`). Bắt buộc với thuộc tính biến thể nghĩa là mọi biến thể có nó.

Và vì mọi biến thể phải dùng cùng một tập thuộc tính biến thể (R19), "có ở mọi biến thể" tương đương "có ở
biến thể nào cũng được". Sản phẩm không có thuộc tính biến thể (thức ăn cho chó) có đúng một biến thể không
tuỳ chọn để giữ giá và tồn; hai biến thể như thế sẽ trùng tổ hợp rỗng nên bị `409`.

Đã cân và loại: chấp nhận giá trị ở cả hai nơi (hai nguồn cho một sự thật) · bỏ hẳn khái niệm `required` cho
thuộc tính biến thể (Size không bắt buộc thì áo không có size vẫn bán được) · bắt biến thể tự khai bản sao ở
sản phẩm (thừa và có thể lệch).

Luật nằm ở: `PRODUCT.md` › Business rules (R15, R19).

### Vì sao `required` không hồi tố, và sản phẩm đang bán có thể "cũ" mà không bị gỡ?

Khi admin thêm một thuộc tính bắt buộc vào danh mục đã có sản phẩm đang bán, có ba lựa chọn: gỡ ngay tất cả
sản phẩm đó, chặn thay đổi cho tới khi mọi sản phẩm bổ sung, hoặc **để nguyên**. Chọn thứ ba: sản phẩm giữ
`active`, không bị tự gỡ, và chỉ bị đòi bổ sung ở lần sửa kế tiếp hoặc lần `publish` lại. Điều này có nghĩa
các điều kiện ở R14 được **thực thi tại `publish` và khi sửa sản phẩm đó**, không phải là bất biến toàn cục
của dữ liệu — một sản phẩm không thể tự đẩy mình ra khỏi luật, nhưng catalog thì có thể đẩy nó ra.

Lý do: đổi catalog không được làm sập một gian hàng đang bán. Một thay đổi cấu hình của người quản trị, có
thể chỉ là thêm một ô tuỳ chọn được đánh dấu bắt buộc nhầm, không nên âm thầm biến hàng trăm sản phẩm thành
"không còn bán được".

Cái giá đã biết: trong lúc chờ, sản phẩm cũ vẫn bán dù thiếu một thuộc tính mới. Chấp nhận vì cái thay thế
(gỡ hàng loạt) tệ hơn cho người bán. Chưa có cách nào để seller **biết** sản phẩm nào đang cũ ngoài việc bị
từ chối khi sửa; báo và lọc chúng là Open.

Đã cân và loại: gỡ tự động mọi sản phẩm không còn thoả (sập gian hàng vì một thay đổi cấu hình) · chặn admin
đổi khi có sản phẩm đang bán (catalog đóng băng) · kiểm lại toàn bộ theo lịch (chưa có lý do, thêm một tiến
trình nền).

Mở lại khi có tìm kiếm phía người bán, để làm cùng chỗ báo sản phẩm cũ.

Luật nằm ở: `PRODUCT.md` › Business rules (R16).

### Vì sao giá trị thuộc tính có ba cột, và `PATCH` phân biệt "vắng", `[]` và một danh sách?

Mỗi giá trị nằm ở đúng một trong ba cột (chọn / chữ / số), đúng cột mà kiểu thuộc tính đòi. Số lưu dạng
thập phân chính xác chứ không phải số thực dấu phẩy động, dù nhận vào qua JSON là số.

`PATCH` có ba nghĩa cho trường `attributes`: **không gửi** → giữ nguyên; **`[]`** → xoá hết; **một danh sách**
→ thay cả tập, không gộp. Nếu gộp thì không có cách nào xoá một giá trị mà không có thêm một cú pháp xoá;
nếu coi `null` là "không gửi" thì "xoá hết" không có cách nói. Nên "vắng" và `[]` là hai câu khác nhau, phân
biệt bằng `model_fields_set` của Pydantic chứ không bằng `None`, và `attributes: null` bị `422` để không ai
đoán nghĩa. Trên sản phẩm đang `active`, `[]` chỉ được nếu vẫn thoả R14.

Đã cân và loại: gộp thay vì thay (không xoá được) · một route riêng cho giá trị (thêm bề mặt, mất tính nguyên
tử của "sửa sản phẩm cùng giá trị") · coi `null` là xoá hết (dễ xoá nhầm bằng một trường thiếu).

Luật nằm ở: `PRODUCT.md` › Business rules (R17).

## Biến thể, giá và tồn

### Vì sao biến thể là tổ hợp tuỳ chọn, không phải cột "màu" và "size"?

Áo biến thể theo Màu × Size, laptop theo RAM × Ổ cứng, mỹ phẩm theo Màu × Dung tích. Nếu biến thể có cột
`color`, `size` thì laptop không có chỗ đặt RAM. Nên một biến thể là một tập cặp (thuộc tính, tuỳ chọn), và
hệ thống không cần biết "biến thể" nghĩa là gì — nó chỉ biết thuộc tính nào của danh mục được đánh dấu
`is_variation`.

`is_variation` là cột bổ sung ở cấu hình thuộc tính của danh mục, **không có trong mô tả thiết kế ban đầu**.
Thiếu nó thì Color chỉ là một thuộc tính của sản phẩm mà hệ thống không biết nó dùng để tạo biến thể, và
không có gì để kiểm rằng một tuỳ chọn biến thể là hợp lệ. Cờ này theo **từng danh mục**: Color là biến thể ở
áo, là giá trị thường ở laptop. Và chỉ thuộc tính `SELECT` mới được đánh dấu, vì biến thể trỏ tới một tuỳ
chọn chứ không tới một chuỗi tự do.

**Tổ hợp của biến thể bất biến** — đổi tuỳ chọn nghĩa là biến thành một biến thể khác (SKU khác, có thể giá
khác, tồn khác), nên "đổi" là xoá rồi tạo lại. Bất biến cũng để khoá chuẩn tắc `option_key` (mục dưới) không
bao giờ lỗi thời.

Đã cân và loại: cột cứng `color`, `size` (laptop không có chỗ) · cho sửa tuỳ chọn của biến thể (khoá chuẩn
tắc và mọi tham chiếu phải cập nhật, và "biến thể" mất danh tính) · suy `is_variation` từ chỗ thuộc tính được
dùng (đoán, không khai).

Luật nằm ở: `PRODUCT.md` › Business rules (R9, R18).

### Vì sao chặn biến thể trùng bằng khoá chuẩn tắc và khoá dòng, không chỉ bằng service?

Hai yêu cầu đồng thời tạo cùng tổ hợp Đen / S, cả hai đều thấy "chưa có" ở service rồi cùng ghi, là chuyện
xảy ra. Nên cơ sở dữ liệu là trọng tài: mỗi biến thể có cột `option_key` — các cặp `attribute_id:option_id`
sắp theo thuộc tính, nối bằng `|`, rỗng nếu không có tuỳ chọn — và một chỉ mục duy nhất từng phần
`(product_id, option_key)` trên biến thể còn sống. Thứ tự tuỳ chọn trong body không ảnh hưởng vì khoá đã sắp.
Vi phạm chỉ mục được ánh xạ thành `409 variant_combination_exists`; `sku_code` trùng trong shop thành `409
sku_exists`, bằng chỉ mục duy nhất từng phần khác.

Ngoài chỉ mục, mọi thao tác ghi biến thể khoá dòng sản phẩm `FOR UPDATE` ngay đầu giao dịch. Việc này không
dành cho tính duy nhất (chỉ mục đã lo) mà cho những kiểm tra "đọc rồi quyết" như "cùng tập thuộc tính biến
thể" và "biến thể `active` cuối cùng": hai yêu cầu không thể cùng nhìn một bức ảnh cũ. Có test chạy nhiều kết
nối thật, cùng ghi thật, để chứng minh: nhiều yêu cầu đua nhau tạo một tổ hợp chỉ để lại đúng một dòng.

Mỗi biến thể có tối đa 5 tuỳ chọn, để `option_key` (mỗi cặp tối đa 73 ký tự) nằm gọn trong cột.

Cái giá đã biết: thêm một cột phi chuẩn hoá và một ràng buộc mà người dùng API không thấy. Đổi lại, tính duy
nhất không phụ thuộc vào việc service nhớ kiểm.

Đã cân và loại: chỉ kiểm ở service (đua nhau là lọt) · một chỉ mục duy nhất trên `(product_id, tập tuỳ chọn)`
(không diễn đạt được bằng chỉ mục thường; đây là lý do phải có khoá chuẩn tắc) · khoá bảng (chặn cả sản phẩm
khác).

Luật nằm ở: `PRODUCT.md` › Business rules (R20).

### Vì sao giá là số nguyên VND và tồn nằm trên biến thể, chưa có kho?

`price` là `BIGINT` theo đơn vị nhỏ nhất của VND, không phải số thực (làm tròn sai) và không có cột tiền tệ
(chưa có sàn nào bán ra ngoài Việt Nam). `stock` là số nguyên ≥ 0 **nằm ngay trên biến thể**, và được *đặt*
chứ không cộng dồn — một request "tồn là 4" đúng dù bị gửi hai lần, còn "cộng 4" thì không.

Thiết kế ban đầu tách tồn ra `inventories(warehouse_id, variant_id, available, reserved)`. Chưa có kho
(warehouse) và chưa có đơn hàng, nên "giữ hàng" (`reserved`) chưa có nghĩa: nó là trạng thái của một đơn đang
chờ thanh toán. Làm sớm là dựng thứ không có ai dùng. Nên phase này để một số nguyên trên biến thể, và việc
tách ra là một migration ở đợt kho hàng.

Cái giá đã biết: khi có kho, `stock` phải chuyển sang bảng theo (kho, biến thể) — một migration dữ liệu chứ
không phải chỉ đổi schema (mỗi biến thể hiện có một dòng ở "kho mặc định"). Chấp nhận vì cái thay thế là
dựng và bảo trì một mô hình mà chưa có ai đọc.

Mở lại khi làm đơn hàng: "giữ hàng" chỉ có nghĩa từ lúc đó.

Đã cân và loại: dựng ngay `warehouses` và `inventories` với một kho mặc định (nhiều bảng hơn mà không ai đọc)
· số thực cho giá (làm tròn) · cột tiền tệ (chưa có nhu cầu).

Luật nằm ở: `PRODUCT.md` › Business rules (R21, R27).

### Vì sao không tắt hay xoá được biến thể `active` cuối cùng của sản phẩm đang bán?

Một sản phẩm `active` phải có ít nhất một biến thể `active` (R14, điều 3). Nếu cho tắt hay xoá cái cuối thì
sản phẩm đang bán sẽ vi phạm luật ngay sau đó, mà không có lỗi nào đi kèm. Cách đơn giản là chặn thao tác đó
với mã riêng `last_active_variant` (`409`), phân biệt với lỗi "thiếu thuộc tính" (`422`), vì cách sửa khác
nhau: một cái là "thêm biến thể khác trước", một cái là "bổ sung dữ liệu". Muốn bỏ hẳn thì `unpublish` trước,
hoặc thêm biến thể thứ hai rồi mới bỏ cái cũ.

Đã cân và loại: tự động `unpublish` sản phẩm khi biến thể cuối bị tắt (một thao tác ẩn gỡ hàng) · cho phép
rồi để lỗi nổ ở lần `publish` sau (sản phẩm đang bán mà không có gì để bán).

Luật nằm ở: `PRODUCT.md` › Business rules (R22).

## Xoá, ảnh và toàn vẹn

### Vì sao sản phẩm và biến thể xoá mềm, còn dòng con giữ nguyên nhưng ảnh xoá cứng?

Sản phẩm và biến thể sẽ được đơn hàng tham chiếu sau này, nên xoá là **xoá mềm**. Xoá sản phẩm xoá mềm luôn
mọi biến thể của nó, cùng một thời điểm, trong một giao dịch. **Giá trị thuộc tính và tuỳ chọn biến thể được
giữ**: chúng là một phần lịch sử của thứ đã bán, và giữ chúng không tốn gì vì mọi truy vấn lọc theo cha còn
sống (có test cho việc này). `sku_code` và tổ hợp của bản ghi đã xoá được giải phóng — chỉ mục duy nhất tính
trên bản ghi còn sống — nên một seller xoá một biến thể vẫn tạo lại được đúng biến thể đó.

**Ảnh khác:** ảnh xoá cứng cùng biến thể hay sản phẩm của nó. Ảnh của một biến thể đã xoá không còn nghĩa
nào, và không đẩy nó lên thành ảnh chung (nó chỉ đúng với biến thể đó). Tệp trong kho xoá **sau** khi giao
dịch ghi nhận thành công, ở mức cố gắng hết sức: nếu xoá tệp lỗi thì chỉ ghi nhật ký, tệp mồ côi được chấp
nhận, còn dòng trỏ vào tệp không tồn tại thì không. Dọn tệp mồ côi định kỳ nằm ngoài phạm vi.

Cái giá đã biết: vì các dòng con được giữ và "đang dùng" tính cả chúng (R11), một thuộc tính hay tuỳ chọn từng
được dùng thì không bao giờ xoá cứng được nữa. Lối ra là cờ ngừng dùng cho catalog (Open).

Đã cân và loại: xoá cứng sản phẩm (đơn hàng sau này mất chỗ trỏ tới) · xoá cứng luôn giá trị và tuỳ chọn khi
xoá mềm sản phẩm (mất lịch sử, đổi lấy một phần tự do xoá catalog mà chưa ai cần) · xoá mềm cả ảnh (dòng ảnh
không có nghĩa nếu chủ của nó đã mất, và giữ tệp tốn kho).

Luật nằm ở: `PRODUCT.md` › Business rules (R23, R24).

### Vì sao ảnh sản phẩm luôn `WEBP`, không cắt xén, và khoá theo id ảnh?

Ảnh sản phẩm dùng lại đường xử lý ảnh sẵn có (kiểm nội dung thật thay vì tin nhãn, chặn kích thước cực đoan,
bỏ siêu dữ liệu như toạ độ GPS, lưu `WEBP`) nhưng **khác avatar và ảnh nền ở một điểm**: không cắt xén.
Avatar là hình vuông và ảnh nền là hình chữ nhật cố định, nên cắt về tỉ lệ đích là đúng; một tấm ảnh áo hay
laptop có tỉ lệ tuỳ ý và tỉ lệ đó là một phần của bức ảnh. Nên ảnh sản phẩm **thu nhỏ vừa khung 1600 × 1600
giữ tỉ lệ, không bao giờ phóng to** — ảnh nhỏ hơn khung được lưu đúng kích thước của nó.

Giới hạn số ảnh — **9 ảnh chung cho mỗi sản phẩm, 5 ảnh cho mỗi biến thể** — là đề xuất, đặt thành hằng số
để đổi dễ, và tính theo từng phạm vi (ảnh chung của sản phẩm là một phạm vi, ảnh của mỗi biến thể là một
phạm vi riêng). Vị trí do server cấp (thêm vào cuối) và luôn liên tục `0..n-1` trong từng phạm vi. `PATCH`
ảnh chỉ nhận `position` — đổi biến thể của ảnh là xoá rồi tải lại — và trả lại cả phạm vi theo thứ tự mới, để
frontend không phải tự tính lại.

**Khoá lưu trữ dựa theo id của dòng ảnh** chứ không phải theo sản phẩm cộng nội dung: hai dòng ảnh tình cờ
cùng byte sẽ sở hữu hai tệp riêng, nên xoá một dòng không bao giờ xoá tệp của dòng kia. Đổi lại là mất khả
năng khử trùng lặp nội dung giữa các dòng; ảnh sản phẩm ít đến mức không đáng để đánh đổi.

**Đường xem ảnh là công khai** (theo id ảnh, không cần token), khác với ảnh giấy tờ nhạy cảm ở nơi khác: ảnh
sản phẩm sinh ra để được nhìn, và id là UUID chỉ lộ ra cùng sản phẩm. Vì vậy phần này chấp nhận một đường
đọc không cần đăng nhập, trong khi mọi đường khác đều cần.

Mở lại khi có ảnh nào không được công khai (ảnh nháp chưa duyệt), hoặc khi số ảnh trung bình mỗi sản phẩm tăng
đủ để đáng khử trùng lặp.

Đã cân và loại: cắt về khung cố định như avatar (mất phần ảnh) · giữ ảnh gốc không nén (kho phình, lộ siêu dữ
liệu) · khoá theo nội dung dùng chung (xoá nhầm tệp của dòng khác) · số ảnh do client tự đặt (không thể ràng
buộc).

Luật nằm ở: `PRODUCT.md` › Business rules (R25, R26).

### Vì sao quan hệ chéo bảng do cơ sở dữ liệu giữ, bằng khoá ngoại ghép?

Có ba cột hoặc quan hệ mà một bug ở service có thể làm sai âm thầm:

- `shop_id` của biến thể là **bản sao** của `shop_id` của sản phẩm (để `sku_code` duy nhất trong shop bằng
  một chỉ mục). Khoá ngoại ghép `(product_id, shop_id) → products(id, shop_id)` khiến hai cột không thể
  lệch, kể cả khi service gán nhầm.
- Ảnh gắn biến thể phải thuộc **đúng sản phẩm** của ảnh: `(variant_id, product_id) → product_variants(id,
  product_id)`. Khi `variant_id` là `NULL` (ảnh chung của sản phẩm) khoá này không kích hoạt — đúng ý —
  và khoá ngoại `product_id` riêng vẫn áp dụng.
- Tuỳ chọn phải thuộc đúng thuộc tính đứng cạnh nó, ở cả giá trị sản phẩm và tuỳ chọn biến thể:
  `(option_id, attribute_id) → attribute_options(id, attribute_id)`.

Cái giá đã biết: mỗi khoá ngoại ghép đòi một ràng buộc duy nhất phụ ở bảng đích chỉ để làm mục tiêu.
Những điều khoá ngoại không diễn đạt được — thuộc tính có được cấu hình cho danh mục của sản phẩm không, có
phải thuộc tính biến thể không — vẫn ở service; test riêng ghi bỏ qua service và chứng minh phần khoá ngoại
làm việc.

Đã cân và loại: chỉ kiểm ở service (một bug là dữ liệu sai vĩnh viễn) · bỏ cột `shop_id` ở biến thể và nối
qua sản phẩm (chỉ mục "duy nhất trong shop" không còn diễn đạt được bằng một chỉ mục) · trigger (khó thấy,
khó test hơn khoá ngoại).

Luật nằm ở: `PRODUCT.md` › Business rules (R28).
