# Thông báo quyền riêng tư cho tester — Chisa (bản thử nghiệm có kiểm soát)

Cập nhật: 2026-10-05. Bản hiển thị cho người dùng: `frontend/public/privacy.html`
(phục vụ tại `https://<domain>/privacy.html`). Khi sửa một bản, hãy sửa cả bản kia.

Chisa là dự án cá nhân đang **thử nghiệm với một nhóm tester nhỏ được mời**. Đây không
phải dịch vụ thương mại. Vui lòng **không gửi thông tin nhạy cảm** (mật khẩu, số giấy
tờ, thông tin tài chính, sức khỏe, địa chỉ nhà…) trong tin nhắn hoặc ảnh.

## 1. Chúng tôi lưu những gì

| Dữ liệu | Khi nào | Mục đích |
|---|---|---|
| Tin nhắn và câu trả lời của Chisa | Mỗi lần bạn chat (web hoặc Discord) | Duy trì ngữ cảnh hội thoại, hiển thị lịch sử |
| Ảnh bạn gửi | Khi bạn đính kèm ảnh | Để Chisa "nhìn" ảnh và (nếu bạn bật ký ức dài hạn) nhớ lại sau |
| Ký ức dài hạn (tóm tắt sự kiện, sở thích) | **Chỉ khi bạn bật** (mặc định **tắt**) | Giúp Chisa nhớ bạn giữa các lần trò chuyện |
| Trạng thái cảm xúc của Chisa đối với bạn | Khi chat | Tính năng nhân vật |
| Tài khoản: email, mật khẩu đã băm bằng bcrypt (không lưu mật khẩu gốc), thời điểm đăng nhập gần nhất | Khi bạn tạo tài khoản | Đăng nhập |
| Liên kết Google: mã định danh Google (`sub`) và email Google | Khi bạn đăng nhập/liên kết bằng Google | Đăng nhập bằng Google |
| Phiên đăng nhập: chỉ lưu **mã băm** của refresh token, thời hạn 7 ngày | Khi đăng nhập | Giữ đăng nhập, cho phép đăng xuất |
| Mã xác minh email / đặt lại mật khẩu: chỉ lưu **mã băm**, dùng một lần, hết hạn sau 24 giờ (xác minh) hoặc 30 phút (đặt lại) | Khi đăng ký, gửi lại xác minh, quên mật khẩu | Chứng minh bạn sở hữu email |
| Bộ đếm lượt chat theo ngày (định danh và IP đã được băm) | Mỗi lượt chat, tự xóa sau 2 ngày | Giới hạn chi phí, chống lạm dụng |
| Discord: Discord user ID, guild ID, nội dung tin nhắn gửi cho bot | Khi bạn dùng bot | Ánh xạ bạn với dữ liệu trong Chisa |

**Không dùng chat ẩn danh vẫn để lại dữ liệu:** nếu chưa đăng nhập, bạn là một phiên ẩn
danh gắn với tab trình duyệt. Đóng tab là bạn mất quyền truy cập vào lịch sử đó, nhưng dữ
liệu vẫn nằm trên máy chủ cho tới khi được xóa. Hãy gõ `/clear` trước khi đóng tab nếu
muốn xóa.

## 2. Dữ liệu được gửi cho bên thứ ba

Để tạo câu trả lời, Chisa gửi dữ liệu đến các nhà cung cấp sau:

- **DeepSeek** (nhà cung cấp mô hình ngôn ngữ): tin nhắn của bạn, một phần lịch sử hội
  thoại, ảnh bạn gửi, và ký ức liên quan (nếu bật). Lưu ý: một số bước trung gian (viết
  lại câu hỏi, đánh giá ngữ cảnh, vòng suy luận) gửi **nguyên văn tin nhắn**; chỉ bước tạo
  câu trả lời cuối cùng được lọc bớt thông tin cá nhân.
- **Công cụ tìm kiếm web** (mặc định DuckDuckGo): khi câu hỏi cần thông tin mới, một truy
  vấn tìm kiếm rút ra từ tin nhắn của bạn được gửi đi, và máy chủ tải các trang kết quả.
- **Jina** (sắp xếp kết quả tìm kiếm lore): chỉ nhận đoạn lore công khai của game và câu
  truy vấn đã được xử lý, không nhận lịch sử hội thoại.
- **Nhà cung cấp email giao dịch** (qua SMTP): nhận địa chỉ email và nội dung thư xác minh
  hoặc đặt lại mật khẩu để gửi tới bạn.
- **Google**: chỉ khi bạn chọn đăng nhập bằng Google. Chisa nhận mã định danh và email từ
  Google; Google biết bạn đã đăng nhập vào ứng dụng này.
- **Discord**: nếu bạn dùng bot, tin nhắn đi qua hạ tầng của Discord theo chính sách của
  Discord.

Các nhà cung cấp này xử lý dữ liệu theo chính sách riêng của họ, có thể ở ngoài Việt Nam.

## 3. Cookie và lưu trữ trên trình duyệt

- `chisa_refresh`: cookie HttpOnly, Secure, SameSite=Lax, chỉ gửi tới `/api/v1/auth`.
  Dùng để giữ đăng nhập. Không dùng để theo dõi hay quảng cáo.
- `chisa_oauth`: cookie tạm (10 phút) trong lúc đăng nhập Google.
- `sessionStorage`: mã phiên ẩn danh, tự mất khi đóng tab.

Không có cookie quảng cáo, không có công cụ phân tích của bên thứ ba.

## 4. Bảo vệ dữ liệu

HTTPS bắt buộc; mật khẩu được băm bcrypt; refresh token chỉ lưu dạng băm và được xoay vòng
sau mỗi lần dùng; log hệ thống **không** ghi nội dung tin nhắn, email hay token; cơ sở dữ
liệu không mở ra Internet; bản sao lưu được mã hóa khi gửi ra ngoài máy chủ. Dù vậy, đây là
hệ thống thử nghiệm do một cá nhân vận hành, nên không thể cam kết như một dịch vụ thương mại.

## 5. Lưu giữ và xóa dữ liệu

- **Giới hạn sử dụng:** mỗi phiên, tài khoản, IP và server Discord có số lượt chat tối đa
  mỗi ngày (đặt lại lúc 07:00 giờ Việt Nam).
- **Tài khoản email/password** phải xác minh email trước khi đăng nhập được.

- **Xóa hội thoại và ký ức:** gõ `/clear` (web) hoặc dùng lệnh `/clear` trên Discord. Lệnh
  này xóa lịch sử chat, ký ức dài hạn, ảnh đã lưu và cache liên quan đến bạn.
- **Xóa tài khoản:** đăng nhập, gõ `/clear`, rồi nhắn người vận hành qua kênh đã mời bạn
  tham gia để xóa tài khoản (email, liên kết Google, phiên đăng nhập).
- **Ký ức dài hạn** chỉ được tạo khi bạn bật và có thời hạn lưu giữ theo lựa chọn của bạn.
- Hội thoại được lưu **trong thời gian thử nghiệm**. Khi kết thúc beta, người vận hành sẽ
  xóa dữ liệu tester hoặc thông báo trước nếu muốn giữ lại.
- Bản sao lưu được giữ tối đa 7 ngày trên máy chủ (và theo cùng chu kỳ ở nơi lưu ngoài);
  dữ liệu đã xóa có thể còn trong bản sao lưu cho tới khi bản đó hết hạn.

## 6. Liên hệ

Mọi câu hỏi hoặc yêu cầu (xem, xóa dữ liệu) xin gửi cho người vận hành qua kênh mà bạn được
mời tham gia thử nghiệm. Việc tiếp tục sử dụng Chisa đồng nghĩa với việc bạn đã đọc thông
báo này.
